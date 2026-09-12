"""
O verbo da Umbra: empurrar a crosta ate ela ceder.

Existe porque, sem ele, a Umbra e meia personagem. As duas habilidades do
jogo eram simetricas em estrutura e assimetricas em uso: o facho da Lumen
era obrigatorio em tres das quatro fases, a absorcao da Umbra em uma. Fora
disso ela sabia andar -- e, subindo um degrau so, nem o design vertical
estava aberto pra ela.

Romper a crosta lhe da algo que a Lumen nao faz de jeito nenhum, e nao passa
pelo sistema de luz: e forca bruta, o que o documento de design sempre disse
dela ("pesada, resistente, quebra obstaculos"). Duas consequencias fazem o
verbo valer a pena:

* **E irreversivel.** Toda outra mudanca de terreno do jogo e um interruptor
  -- acender, apagar, acender de novo. A crosta, nao: quebrou, quebrou pra
  fase inteira. "Quebro ou nao?" e a primeira decisao do jogo que nao da
  pra desfazer.
* **Ela abre caminho pra luz.** A crosta e opaca. O buraco que a Umbra faz
  pra passar deixa entrar o que a crosta barrava do outro lado -- e e ela
  quem se dissolve na luz. Ate aqui toda destruicao de terreno ia da Lumen
  pra Umbra; esta vai da Umbra pra ela mesma.
"""
from __future__ import annotations

from ouroboros.core.systems.base_system import ISystem
from ouroboros.core.systems.tile_collision_system import TileCollisionSystem
from ouroboros.core.world import World
from ouroboros.interfaces.input_provider import IInputProvider

from penumbra.state import DualityState, UMBRA

_PLAYER_TWO_PREFIX = "p2_"
"""No modo duo a Umbra e sempre o jogador 2, como em
`DualityControlSystem`. Sem este prefixo o sistema lia as teclas do jogador
1 e exigia `state.active == UMBRA` -- e no duo nao existe 'ativo', entao a
crosta nunca cedia e as fases 2, 7 e 14 eram invenciveis a dois."""
from penumbra.terrain import Terrain


class CrustBreakSystem(ISystem):
    """
    Enquanto a Umbra ATIVA e no chao empurra contra uma celula de crosta,
    acumula tempo; ao completar `break_seconds`, a celula deixa de existir.

    Exige `is_grounded` e uma direcao SEGURADA de proposito: romper e
    irreversivel, entao nao pode acontecer de raspao. O medidor que sobe
    (`DualityState.crust_progress`, desenhado como a celula encolhendo) e o
    que transforma isso numa acao deliberada em vez de um acidente.

    So a Umbra rompe. A Lumen encosta na crosta e para, como faria numa
    rocha -- e essa e a assimetria toda: existe terreno que so ela nao
    resolve.

    Nos dois modos, e pela mesma razao que `DualityControlSystem`: no solo o
    verbo pertence ao ser ATIVO, no duo ao jogador 2. A primeira versao so
    olhava `state.active`, que no duo nunca sai da Lumen -- entao a crosta
    simplesmente nao cedia, e nada na tela dizia por que.
    """

    def __init__(
        self,
        input_provider: IInputProvider,
        terrain: Terrain,
        state: DualityState,
        umbra_tile_collision: TileCollisionSystem,
        break_seconds: float,
        transform_pool_name: str = "transform",
    ) -> None:
        self._input = input_provider
        self._terrain = terrain
        self._state = state
        self._tile_collision = umbra_tile_collision
        self._break_seconds = break_seconds
        self._transform_pool_name = transform_pool_name
        self._transform_pool = None

    def update(self, world: World, delta_time: float) -> None:
        if self._transform_pool is None:
            self._transform_pool = world.get_pool(self._transform_pool_name)

        state = self._state
        target = self._current_target()
        if target is None:
            state.crust_target_col = -1
            state.crust_target_row = -1
            state.crust_progress = 0.0
            return

        col, row = target
        # Trocar de alvo reinicia o esforco: empurrar duas crostas
        # alternadamente nao soma progresso em nenhuma das duas.
        if col != state.crust_target_col or row != state.crust_target_row:
            state.crust_target_col = col
            state.crust_target_row = row
            state.crust_progress = 0.0

        state.crust_progress += delta_time / self._break_seconds
        if state.crust_progress >= 1.0:
            self._terrain.break_crust(col, row)
            state.crust_target_col = -1
            state.crust_target_row = -1
            state.crust_progress = 0.0

    def _current_target(self):
        """Celula de crosta que a Umbra esta empurrando agora, ou `None`.

        A celula testada e a vizinha na direcao SEGURADA, na propria linha
        dela -- e nao a "borda de avanco" geometrica: `TileCollisionSystem`
        ja encostou o corpo dela na crosta e zerou a velocidade, entao a
        posicao ja e a de contato."""
        state = self._state
        if state.duo:
            prefix = _PLAYER_TWO_PREFIX
        elif state.active == UMBRA:
            prefix = ""
        else:
            return None

        moving_left = self._input.is_action_held(f"{prefix}move_left")
        moving_right = self._input.is_action_held(f"{prefix}move_right")
        if moving_left == moving_right:
            return None
        step = 1 if moving_right else -1

        entity_index = int(state.entity_index[UMBRA])
        if not self._tile_collision.is_grounded(entity_index):
            return None

        col = int(state.cell[UMBRA, 0]) + step
        row = int(state.cell[UMBRA, 1])
        terrain = self._terrain
        if not (0 <= col < terrain.cols and 0 <= row < terrain.rows):
            return None
        if not bool(terrain.crust[row, col]):
            return None
        return (col, row)
