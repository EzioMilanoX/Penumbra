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

from typing import Optional, Tuple

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
        self.ambient = 0.0
        """A luz de fundo do MUNDO, vinda do capitulo. Zero nos tres
        primeiros; acima de `solid_threshold` num capitulo que inverte."""
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
        self.echo_seconds = 0.0
        """Quanto tempo os dois ja estao parados lado a lado, sem se tocar.
        Ver `penumbra.systems.echo_system` -- e o segredo do jogo."""
        self.echo_found = False
        self.coyote = np.zeros(2, dtype=np.float32)
        """Segundos de salto ainda validos depois de sair da beira."""
        self.jump_buffer = np.zeros(2, dtype=np.float32)
        """Segundos de salto lembrado, apertado antes de encostar no chao."""
        self.cell = np.zeros((2, 2), dtype=np.int64)
        """Celula `(col, row)` de cada ser no frame corrente."""
        self.reached_goal = np.zeros(2, dtype=bool)
        self.shard_collected = False
        """Fragmento da fonte desta fase, apanhado nesta tentativa. E
        opcional: nao entra na condicao de vitoria, e o desvio pra pegar
        costuma pedir a polaridade oposta a da rota obvia."""
        self.used_ability = False
        """Alguma habilidade foi ligada nesta TENTATIVA. Existe so pra
        conquista de vencer sem usar nenhuma -- nenhuma regra do jogo le
        isto, e por isso ele mora aqui e nao num campo por ser."""
        self.duo = False
        """Dois jogadores, um em cada ser, ao mesmo tempo. No solo o ser
        parado e a tensao (ele nao esta protegido); no duo ele e um parceiro
        -- e o contato entre os dois continua aniquilando os dois, o que
        transforma a cooperacao em algo que da errado de verdade."""

        # --- altares de forma (ver FormAltarSystem) ---
        self.form_spent = np.zeros(2, dtype=bool)
        """Este ser ja deixou a forma num altar nesta tentativa. Uma vez
        verdadeiro, a habilidade dele nao liga mais e a carga nao recompoe:
        a troca e poder por permanencia, e ela e definitiva."""
        self.altar_progress = np.zeros(2, dtype=np.float32)
        """0..1, quanto falta pro altar sob este ser ficar com a forma dele.
        Sobe so enquanto ele esta em cima COM a habilidade ligada, e zera no
        instante em que ele sai ou desliga -- como o medidor da crosta, e
        pela mesma razao: nada irreversivel pode acontecer de raspao."""
        self.altar_light = np.zeros(shape, dtype=np.float32)
        """Luz fixa deixada pela Lumen num altar. Entra no campo como uma
        lampada que nao existia no ASCII da fase -- e por isso ela mora aqui
        e nao no `Terrain`: e estado de uma tentativa, nao terreno."""
        self.altar_shadow = np.zeros(shape, dtype=np.float32)
        """O espelho: escuridao fixa deixada pela Umbra."""

        # --- a fonte que respira ---
        self.source_phase = 0.0
        self.source_intensity = 0.0
        self.source_alt_intensity = 0.0
        """A segunda fonte, meio periodo atras: as duas juntas fazem a
        faixa segura ir e vir entre elas."""
        """Intensidade da fonte neste frame. O raio aceso sai dela --
        `(I - solid_threshold) * falloff_radius_cells` -- entao o chao dilata e
        contrai sem que nada se mova."""

        # --- alavanca de polaridade ---
        self.polarity_swapped = False
        """O mapa esta com eter e contra-eter trocados. Vive aqui e nao no
        `Terrain` porque e estado de uma TENTATIVA -- `reset()` recarrega o
        ASCII e o mundo volta ao que era."""
        self.on_lever = np.zeros(2, dtype=bool)
        """Este ser esta em cima de uma alavanca AGORA. A troca dispara na
        borda de entrada: sem isso, parar em cima dela inverteria o mundo
        sessenta vezes por segundo."""

        # --- lanterna errante ---
        self.wander_col = 0.0
        """Coluna da lanterna, em `float` -- ela anda continuamente e so e
        arredondada na hora de semear o campo de luz."""
        self.wander_dir = 1.0

        # --- crosta que a Umbra esta rompendo agora ---
        self.crust_target_col = -1
        self.crust_target_row = -1
        self.crust_progress = 0.0
        """0..1. Nao vive no `Terrain` porque nao e terreno: e o esforco em
        curso de UM ser sobre uma celula, e reinicia ao trocar de alvo."""

        # --- relogio do mundo (ver WorldClockSystem) ---
        self.beacon_phase = 0.0
        self.beacon_on = True
        self.beacon_seconds_left = 0.0
        """Quanto falta pra o farol virar. O HUD mostra isso -- e a
        informacao com que o jogador planeja a travessia."""
        self.eclipse_touched = False
        self.eclipse_seconds_left = 0.0
        """Prazo da zona de eclipse, iniciado pelo PRIMEIRO toque de
        qualquer um dos dois (nao pelo inicio da fase)."""

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
        self._loaded_rows: Optional[Tuple[str, ...]] = None
        """O ASCII que esta de fato carregado no `Terrain`. `reset()` recarrega
        ISTO, e nao `current.rows`: senao um cenario montado por fora (um teste,
        uma sonda de ferramenta) seria descartado pelo primeiro reset."""

    @property
    def current(self) -> LevelDefinition:
        return self._catalog.at(self._state.level_index)

    @property
    def count(self) -> int:
        return self._catalog.count

    @property
    def terrain(self) -> Terrain:
        """O `Terrain` que esta carregado agora. Exposto porque o HUD precisa
        saber se a fase TEM farol ou eclipse pra decidir se mostra o relogio
        deles -- e nao ha outro caminho do HUD ate o terreno."""
        return self._terrain

    @property
    def is_last(self) -> bool:
        return self._state.level_index >= self._catalog.count - 1

    def load(self, level_index: int) -> None:
        """Carrega a fase `level_index`, na variante do modo corrente.

        Le `state.duo` AQUI, e nao no `PenumbraFlow`, pra que recomecar (`R`)
        e trocar de fase carreguem sempre a mesma versao que esta sendo
        jogada -- um reset que voltasse pra variante do outro modo seria a
        pior hora possivel pra fase mudar debaixo do jogador.
        """
        self._state.level_index = level_index % self._catalog.count
        # O mundo vem do capitulo, e e escrito AQUI e nao em `load_rows`:
        # carregar um ASCII avulso (teste, ferramenta, previa do menu) adota
        # geometria, nao mundo.
        self._state.ambient = float(self.current.ambient)
        self.load_rows(self.current.rows_for(bool(self._state.duo)))

    def load_rows(self, rows: Tuple[str, ...]) -> None:
        """Carrega um ASCII arbitrario e o adota como o que `reset()` deve
        restaurar. E por aqui que testes e ferramentas montam um cenario
        proprio sem que o proximo reset o jogue fora."""
        self._loaded_rows = tuple(rows)
        self._terrain.load_rows(self._loaded_rows)
        self.reset()

    def advance(self) -> None:
        """Vai pra proxima fase (voltando a primeira depois da ultima --
        o slice nao tem tela de fim de jogo)."""
        self.load(self._state.level_index + 1)

    def reset(self) -> None:
        """
        Recomeca a fase corrente do zero.

        Recarrega o ASCII, e nao apenas o estado: romper a crosta MUTA o
        `Terrain` (`break_crust`), entao um reset que so zerasse cargas e
        posicoes devolveria o jogador a uma fase com os buracos que ele
        abriu na tentativa anterior -- e, sendo irreversivel, uma crosta
        quebrada na hora errada deixaria a fase insolvel pra sempre, sem
        nenhum jeito de recuperar.
        """
        self._terrain.load_rows(self._loaded_rows or self.current.rows)
        state = self._state
        state.outcome = OUTCOME_PLAYING
        state.message = ""
        state.restart_requested = False
        state.door_open = not self._terrain.has_door
        state.active = LUMEN
        state.ability_on[:] = False
        state.charge[:] = 1.0
        state.peril[:] = 0.0
        state.coyote[:] = 0.0
        state.jump_buffer[:] = 0.0
        state.echo_seconds = 0.0
        state.echo_found = False
        state.reached_goal[:] = False
        state.shard_collected = False
        state.used_ability = False
        state.crust_target_col = -1
        state.crust_target_row = -1
        state.crust_progress = 0.0
        state.form_spent[:] = False
        state.altar_progress[:] = 0.0
        state.altar_light[:] = 0.0
        state.altar_shadow[:] = 0.0
        state.wander_col = float(self._terrain.wander_min_col)
        state.wander_dir = 1.0
        state.source_phase = 0.0
        state.source_intensity = 0.0
        state.source_alt_intensity = 0.0
        state.polarity_swapped = False
        state.on_lever[:] = False
        state.beacon_phase = 0.0
        state.beacon_on = True
        state.beacon_seconds_left = 0.0
        state.eclipse_touched = False
        state.eclipse_seconds_left = 0.0
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
