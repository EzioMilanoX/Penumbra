"""
Estado de runtime compartilhado pelos sistemas de Penumbra.

`DualityState` e um container de dados puro -- todos os arrays alocados uma
unica vez na composicao. Ele existe porque o conflito central do jogo e
compartilhado por natureza: o campo de luz que o `LightFieldSystem` calcula
e lido pela porta de polaridade, pelas regras de sobrevivencia e pela
apresentacao no MESMO frame. Passar isso por um objeto injetado em cada
sistema mantem cada `ISystem` sem estado por entidade (Regra 1) e sem
precisar recalcular o campo tres vezes.

`LevelRuntime` e o unico lugar que troca de fase: recarrega as mascaras do
`Terrain` no lugar e reposiciona os dois seres. Nenhuma entidade e criada
ou destruida numa transicao -- as 880 celulas visuais e os dois seres vivem
do primeiro ao ultimo frame do processo.
"""
from __future__ import annotations

import numpy as np

from ouroboros.core.world import World

from penumbra.levels import LevelCatalog, LevelDefinition
from penumbra.terrain import Terrain
from penumbra.tuning import DualityTuning

LUMEN = 0
UMBRA = 1
_SIDE_NAMES = ("Lumen", "Umbra")

OUTCOME_PLAYING = 0
OUTCOME_COMPLETE = 1
OUTCOME_FAILED = 2

INITIAL_VELOCITY_Y = 1e-3
"""Spawn com `velocity_y` pequena e NAO-nula, exigido por
`TileCollisionSystem.is_grounded`: cada eixo so e testado quando a
velocidade naquele eixo e diferente de zero, entao um spawn com
`velocity_y == 0.0` faria o primeiro frame reportar "no ar" mesmo em
repouso sobre a rocha -- e o salto seria recusado. Mesmo idioma do
vertical slice do Platformer."""


class DualityState:
    """
    Tudo que muda de um frame pro outro e nao cabe numa `ComponentPool`.

    Os campos por-ser sao arrays de 2 posicoes indexados por `LUMEN`/
    `UMBRA` (nao dois atributos separados) para que os sistemas possam
    tratar os dois lados pelo mesmo caminho de codigo -- a assimetria dos
    dois seres vive nos VALORES de `DualityTuning`, nunca em ramos
    duplicados de logica.
    """

    def __init__(self, terrain: Terrain) -> None:
        shape = (terrain.rows, terrain.cols)

        # --- campo de luz, reescrito a cada frame pelo LightFieldSystem ---
        self.light = np.zeros(shape, dtype=np.float32)
        """Intensidade de luz por celula (0..1), ja occluida por rocha e
        porta trancada e ja suprimida pela absorcao da Umbra."""
        self.display_light = np.zeros(shape, dtype=np.float32)
        """Como `light`, mas com as celulas que BLOQUEIAM luz recebendo o
        maximo dos vizinhos -- so apresentacao (uma parede iluminada de um
        lado precisa parecer iluminada), nunca usado por regra de jogo."""
        self.lit = np.zeros(shape, dtype=bool)
        """`light >= light.solid_threshold`: onde o eter e solido pra Lumen
        (e deixa de ser pra Umbra)."""
        self.absorbed = np.zeros(shape, dtype=bool)
        """Bolsao de escuridao solida criado pela Umbra neste frame."""

        # --- os dois seres ---
        self.entity_index = np.zeros(2, dtype=np.int64)
        self.active = LUMEN
        self.ability_on = np.zeros(2, dtype=bool)
        self.charge = np.ones(2, dtype=np.float32)
        """Carga da habilidade, 0..1. Drena enquanto ligada, recompoe
        enquanto desligada, e forca o desligamento ao chegar em zero -- e
        o que torna a solidificacao do eter TEMPORARIA (e portanto o que
        transforma cada fase num problema de sequencia, nao de um botao
        ligado pra sempre)."""
        self.peril = np.zeros(2, dtype=np.float32)
        """Quanto falta pra polaridade errada matar cada ser, 0..1."""
        self.cell = np.zeros((2, 2), dtype=np.int64)
        """Celula `(col, row)` de cada ser no frame corrente."""
        self.reached_goal = np.zeros(2, dtype=bool)

        # --- porta de polaridade ---
        self.door_open = False
        """Trava por fase: uma vez que os dois seres cumpriram as duas
        zonas AO MESMO TEMPO, a porta fica aberta. Sem essa trava a porta
        seria decorativa -- ninguem consegue estar parado numa zona e
        atravessar a porta no mesmo instante."""

        # --- fluxo ---
        self.level_index = 0
        self.outcome = OUTCOME_PLAYING
        self.message = ""
        self.restart_requested = False

    def side_name(self, side: int) -> str:
        return _SIDE_NAMES[side]

    @property
    def active_name(self) -> str:
        return _SIDE_NAMES[self.active]

    def fail(self, message: str) -> None:
        """Marca a fase como perdida. O PRIMEIRO motivo do frame vence --
        cair no abismo enquanto se dissolvia deve contar uma historia so."""
        if self.outcome == OUTCOME_PLAYING:
            self.outcome = OUTCOME_FAILED
            self.message = message

    def complete(self, message: str) -> None:
        if self.outcome == OUTCOME_PLAYING:
            self.outcome = OUTCOME_COMPLETE
            self.message = message


class LevelRuntime:
    """
    Dono da troca de fase: recarrega `Terrain` no lugar e reposiciona os
    dois seres escrevendo direto nas pools `transform`/`velocity`.

    Nao e um `ISystem` -- e chamado pela cena (`penumbra.scenes`) entre
    dois `world.step()`, nunca de dentro de um, justamente pra nao mexer
    em posicao no meio da cadeia
    `PhysicsSystem -> TileCollisionSystem -> GravitySystem`.
    """

    def __init__(
        self,
        world: World,
        terrain: Terrain,
        catalog: LevelCatalog,
        state: DualityState,
        tuning: DualityTuning,
    ) -> None:
        self._world = world
        self._terrain = terrain
        self._catalog = catalog
        self._state = state
        self._tuning = tuning
        self._transform_pool = world.get_pool("transform")
        self._velocity_pool = world.get_pool("velocity")

    @property
    def current(self) -> LevelDefinition:
        return self._catalog.at(self._state.level_index)

    @property
    def count(self) -> int:
        return self._catalog.count

    @property
    def is_last(self) -> bool:
        return self._state.level_index >= self._catalog.count - 1

    def load(self, level_index: int) -> None:
        """Carrega a fase `level_index` e a coloca no estado inicial."""
        self._state.level_index = level_index % self._catalog.count
        self._terrain.load_rows(self.current.rows)
        self.reset()

    def advance(self) -> None:
        """Vai pra proxima fase (voltando a primeira depois da ultima --
        o slice nao tem tela de fim de jogo)."""
        self.load(self._state.level_index + 1)

    def reset(self) -> None:
        """Recomeca a fase corrente: seres nos pontos de spawn, cargas
        cheias, habilidades desligadas, porta trancada de novo."""
        state = self._state
        state.outcome = OUTCOME_PLAYING
        state.message = ""
        state.restart_requested = False
        state.door_open = not self._terrain.has_door
        state.active = LUMEN
        state.ability_on[:] = False
        state.charge[:] = 1.0
        state.peril[:] = 0.0
        state.reached_goal[:] = False
        state.light[:] = 0.0
        state.display_light[:] = 0.0
        state.lit[:] = False
        state.absorbed[:] = False

        self._place(LUMEN, self._terrain.lumen_spawn_cell)
        self._place(UMBRA, self._terrain.umbra_spawn_cell)

    def _place(self, side: int, cell) -> None:
        entity_index = int(self._state.entity_index[side])
        x, y = self._terrain.cell_center(cell)

        transform_row = self._transform_pool.dense_row_of(entity_index)
        transform_view = self._transform_pool.active_view()
        transform_view["position_x"][transform_row] = x
        transform_view["position_y"][transform_row] = y

        velocity_row = self._velocity_pool.dense_row_of(entity_index)
        velocity_view = self._velocity_pool.active_view()
        velocity_view["linear_x"][velocity_row] = 0.0
        velocity_view["linear_y"][velocity_row] = INITIAL_VELOCITY_Y
        velocity_view["angular"][velocity_row] = 0.0

        self._state.cell[side, 0] = cell[0]
        self._state.cell[side, 1] = cell[1]
