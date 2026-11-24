"""
Como uma fase termina: os quatro jeitos de perder e o unico de ganhar.

Tudo aqui le posicoes JA resolvidas do frame (este sistema roda no fim da
lista) e escreve apenas `DualityState.outcome`/`peril`. Quem reage a isso --
recarregando a fase ou avancando -- e a cena (`penumbra.scenes`), entre dois
`world.step()`, nunca de dentro de um.
"""
from __future__ import annotations

from ouroboros.core.systems.base_system import ISystem
from ouroboros.core.world import World

from penumbra.state import LUMEN, TAPE_RECORD, UMBRA, DualityState
from penumbra.terrain import Terrain
from penumbra.tuning import DualityTuning

_GOAL_TOLERANCE_CELLS = 0.6
"""Meia-largura (em celulas) da janela em torno do centro de um portal que
conta como "chegou". Um pouco maior que meia celula: exigir o centro exato
transformaria o ultimo passo de cada fase numa disputa de pixel, o que nao
e o desafio que este jogo propoe."""


class OutcomeSystem(ISystem):
    """
    Resolve, em ordem, as condicoes de fim de fase:

    1. **Abismo** -- entrar na ultima linha da grade (o vazio validado por
       `Terrain`) mata na hora. E o destino de quem estava de pe num eter
       que o outro ser acabou de despolarizar.
    2. **Contato** -- as duas AABBs se sobrepondo aniquila os dois. Eles
       nasceram da mesma fonte e nao podem se tocar.
    3. **Polaridade errada** -- Lumen se apaga onde a luz cai abaixo de
       `extinguish_below`; Umbra se dissolve onde passa de
       `dissolve_above`. Nao e instantaneo: um medidor por ser sobe
       enquanto o perigo dura e desce quando passa, entao atravessar uma
       nesga da polaridade errada e uma decisao possivel, nao uma morte.
    4. **Portais** -- os dois em cima dos seus portais no MESMO frame
       completa a fase. Simultaneo porque o ser inativo fica parado
       esperando: a tensao e que o chao dele pode desaparecer enquanto o
       jogador leva o outro ate la.

    A ordem importa: `DualityState.fail` guarda so o primeiro motivo do
    frame, e cair no abismo enquanto se dissolvia deve contar uma historia
    so.

    Fora dessas cinco, ha uma coisa que este sistema so REGISTRA: o
    fragmento da fonte. Ele nao entra na vitoria nem na derrota -- e um
    desvio opcional, e o que o torna interessante e que o caminho ate ele
    quase sempre pede a polaridade oposta a da rota obvia.

    **Gravando o eco** (`state.tape_phase == TAPE_RECORD`) a Umbra ainda nao
    chegou: fica no spawn, e nada aqui a mata, a encosta na Lumen ou a conta
    num portal. So a Lumen vive esse tempo -- e e por isso que ela pode ser
    gravada sozinha. Ver `penumbra.tape`.
    """

    def __init__(
        self,
        terrain: Terrain,
        state: DualityState,
        tuning: DualityTuning,
        transform_pool_name: str = "transform",
    ) -> None:
        self._terrain = terrain
        self._state = state
        self._tuning = tuning
        self._sides = (tuning.lumen, tuning.umbra)
        self._transform_pool_name = transform_pool_name
        self._transform_pool = None
        self._position_x = [0.0, 0.0]
        self._position_y = [0.0, 0.0]
        self._sides_alive = (LUMEN, UMBRA)

    def update(self, world: World, delta_time: float) -> None:
        if self._transform_pool is None:
            self._transform_pool = world.get_pool(self._transform_pool_name)

        self._read_positions()
        if self._state.outcome != 0:
            return

        # Gravando o eco, so a Lumen esta no mundo -- o mesmo laco, com um lado.
        self._sides_alive = (LUMEN,) if self._state.tape_phase == TAPE_RECORD else (LUMEN, UMBRA)

        self._check_shard()
        self._check_void()
        self._check_contact()
        self._advance_peril(delta_time)
        self._check_goals()

    # ------------------------------------------------------------------
    # internos
    # ------------------------------------------------------------------

    def _read_positions(self) -> None:
        pool = self._transform_pool
        view = pool.active_view()
        for side in (LUMEN, UMBRA):
            row = pool.dense_row_of(int(self._state.entity_index[side]))
            self._position_x[side] = float(view["position_x"][row])
            self._position_y[side] = float(view["position_y"][row])

    def _check_shard(self) -> None:
        """Qualquer um dos dois apanha o fragmento -- ele nao tem polaridade.
        O que tem polaridade e o CAMINHO ate ele, e e ai que esta o desvio."""
        state, terrain = self._state, self._terrain
        if state.shard_collected or terrain.shard_cell is None:
            return
        shard_x, shard_y = terrain.cell_center(terrain.shard_cell)
        tolerance = _GOAL_TOLERANCE_CELLS * terrain.cell_size
        for side in (LUMEN, UMBRA):
            if (abs(self._position_x[side] - shard_x) <= tolerance
                    and abs(self._position_y[side] - shard_y) <= tolerance):
                state.shard_collected = True
                return

    def _check_void(self) -> None:
        terrain = self._terrain
        void_top = (terrain.rows - 1) * terrain.cell_size
        for side in self._sides_alive:
            if self._position_y[side] >= void_top:
                self._state.fail(f"{self._state.side_name(side)} caiu no abismo.")
                return

    def _check_contact(self) -> None:
        if len(self._sides_alive) < 2:
            return
        lumen, umbra = self._sides[LUMEN], self._sides[UMBRA]
        overlap_x = abs(self._position_x[LUMEN] - self._position_x[UMBRA]) < (lumen.half_width + umbra.half_width)
        overlap_y = abs(self._position_y[LUMEN] - self._position_y[UMBRA]) < (lumen.half_height + umbra.half_height)
        if overlap_x and overlap_y:
            self._state.fail("Luz e sombra se tocaram. Os dois se anularam.")

    def _advance_peril(self, delta_time: float) -> None:
        state, light_tuning = self._state, self._tuning.light
        for side in self._sides_alive:
            col, row = int(state.cell[side, 0]), int(state.cell[side, 1])
            light_here = float(state.light[row, col])
            in_danger = (
                light_here < light_tuning.extinguish_below
                if side == LUMEN
                else light_here > light_tuning.dissolve_above
            )

            tuning = self._sides[side]
            if in_danger:
                peril = float(state.peril[side]) + delta_time / tuning.peril_seconds
                if peril >= 1.0:
                    state.peril[side] = 1.0
                    state.fail(
                        "Lumen se apagou no escuro."
                        if side == LUMEN
                        else "Umbra se dissolveu na luz."
                    )
                    return
                state.peril[side] = peril
            else:
                peril = float(state.peril[side]) - tuning.peril_recovery_per_second * delta_time
                state.peril[side] = 0.0 if peril < 0.0 else peril

    def _check_goals(self) -> None:
        terrain, state = self._terrain, self._state
        tolerance = _GOAL_TOLERANCE_CELLS * terrain.cell_size
        for side, goal_cell in ((LUMEN, terrain.lumen_goal_cell), (UMBRA, terrain.umbra_goal_cell)):
            goal_x, goal_y = terrain.cell_center(goal_cell)
            state.reached_goal[side] = (
                abs(self._position_x[side] - goal_x) <= tolerance
                and abs(self._position_y[side] - goal_y) <= tolerance
            )
        if len(self._sides_alive) < 2:
            return
        if bool(state.reached_goal[LUMEN]) and bool(state.reached_goal[UMBRA]):
            state.complete("Os dois portais responderam ao mesmo tempo.")
