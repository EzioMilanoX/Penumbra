"""
Traduz os mesmos instantes que o audio marca em faisca.

O `AudioSystem` ja resolveu qual e a lista: os eventos que o jogador precisa
SENTIR, e nao apenas ver o resultado. Este sistema olha exatamente as mesmas
bordas e emite no lugar onde a coisa aconteceu -- som e luz tem de concordar,
senao um dos dois vira ruido.

Como a apresentacao e o audio, nao decide nada: removido, o jogo continua
identico e fica sem poeira. E por isso que so e registrado em `build_game`.
"""
from __future__ import annotations

import numpy as np
from ouroboros.core.systems.base_system import ISystem
from ouroboros.core.world import World

from penumbra.sparks import SparkField
from penumbra.state import LUMEN, OUTCOME_FAILED, UMBRA, DualityState
from penumbra.terrain import Terrain


class SparkSystem(ISystem):
    """
    Emite nas bordas e avanca o campo de particulas.

    Roda por ULTIMO, junto com a apresentacao, e le posicoes ja resolvidas.
    As bordas sao guardadas aqui e nao no `DualityState` porque sao memoria
    de APRESENTACAO -- nenhuma regra do jogo pergunta se a crosta cedeu no
    frame passado.
    """

    def __init__(self, sparks: SparkField, state: DualityState, terrain: Terrain,
                 transform_pool_name: str = "transform") -> None:
        self._sparks = sparks
        self._state = state
        self._terrain = terrain
        self._transform_pool_name = transform_pool_name
        self._transform_pool = None
        self._cell = terrain.cell_size

        self._crust_cells = -1
        self._eclipse_cells = -1
        self._was_shard = False
        self._was_spent = [False, False]
        self._was_echo = False
        self._was_outcome = 0
        self._level = -1

    def update(self, world: World, delta_time: float) -> None:
        if self._transform_pool is None:
            self._transform_pool = world.get_pool(self._transform_pool_name)

        state = self._state
        if state.level_index != self._level:
            # Trocar de fase apaga a poeira: o estilhaco de uma crosta rompida
            # na fase anterior chegando no primeiro frame da seguinte seria um
            # evento que nunca aconteceu ali.
            self._sparks.clear()
            self._level = state.level_index
            self._crust_cells = -1
            self._eclipse_cells = -1
            self._was_outcome = 0
            self._was_echo = False
            self._was_shard = False
            self._was_spent = [False, False]

        self._emit()
        self._sparks.update(delta_time)

    # ------------------------------------------------------------------

    def _position(self, side: int):
        pool = self._transform_pool
        row = pool.dense_row_of(int(self._state.entity_index[side]))
        view = pool.active_view()
        return float(view["position_x"][row]), float(view["position_y"][row])

    def _emit(self) -> None:
        state, terrain, sparks = self._state, self._terrain, self._sparks

        # A crosta: a contagem de celulas caiu, entao uma cedeu. Achar QUAL
        # custa um `nonzero` sobre 476 posicoes e so acontece no frame da
        # ruptura -- mais barato que um campo de estado que ninguem mais le.
        crust = int(terrain.crust.sum())
        if 0 <= crust < self._crust_cells:
            col, row = state.crust_target_col, state.crust_target_row
            if col >= 0:
                sparks.crust_broke((col + 0.5) * self._cell, (row + 0.5) * self._cell)
        self._crust_cells = crust

        eclipse = int(terrain.eclipse.sum())
        if self._eclipse_cells > 0 and eclipse == 0:
            # A zona colapsa INTEIRA de uma vez, entao a faisca sai do meio
            # dela -- e onde o jogador estava olhando.
            sparks.eclipse_collapsed(*self._last_eclipse_center)
        elif eclipse:
            rows, cols = np.nonzero(terrain.eclipse)
            self._last_eclipse_center = (
                (float(cols.mean()) + 0.5) * self._cell,
                (float(rows.mean()) + 0.5) * self._cell,
            )
        self._eclipse_cells = eclipse

        if state.shard_collected and not self._was_shard and terrain.shard_cell:
            col, row = terrain.shard_cell
            sparks.shard_taken((col + 0.5) * self._cell, (row + 0.5) * self._cell)
        self._was_shard = state.shard_collected

        for side in (LUMEN, UMBRA):
            spent = bool(state.form_spent[side])
            if spent and not self._was_spent[side]:
                sparks.form_left(*self._position(side))
            self._was_spent[side] = spent

        if state.echo_found and not self._was_echo:
            lumen_x, lumen_y = self._position(LUMEN)
            umbra_x, umbra_y = self._position(UMBRA)
            sparks.echo((lumen_x + umbra_x) / 2.0, (lumen_y + umbra_y) / 2.0)
        self._was_echo = state.echo_found

        if state.outcome != self._was_outcome:
            if state.outcome == OUTCOME_FAILED:
                # Quem morreu nao esta no estado -- so a mensagem sabe. Emitir
                # nos DOIS e honesto: no contato os dois morrem mesmo, e nas
                # outras mortes a faisca do sobrevivente cai junto da dele.
                for side, lumen in ((LUMEN, True), (UMBRA, False)):
                    sparks.died(*self._position(side), lumen=lumen)
            self._was_outcome = state.outcome

    _last_eclipse_center = (0.0, 0.0)
