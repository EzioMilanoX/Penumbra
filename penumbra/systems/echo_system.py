"""
O Instante -- o segredo do jogo, e a unica coisa que ele nunca pediu.

Penumbra tem uma regra inviolavel: **os dois nao podem se tocar**. Trinta
fases foram desenhadas em volta dela, e todo o desenho de nivel existe pra
mante-los separados -- pistas em andares diferentes, corredores atravessados
em turnos, portais afastados o bastante pra que chegar junto nao anule os
dois.

O segredo e o contrario disso: parar os dois **o mais perto que da sem se
tocarem**, lado a lado, no chao, e ficar quieto. Uma celula de distancia --
32 px, contra os 23 que aniquilam -- e nada mais acontecendo.

E o unico momento do jogo em que a coisa certa a fazer e nao fazer nada. Nao
da fase nenhuma, nao abre caminho nenhum, nao esta escrito em lugar nenhum:
so reconhece que alguem entendeu o que o jogo e sobre e quis chegar perto
mesmo assim.

Funciona em qualquer fase que tenha chao compartilhado, o que inclui a
primeira -- de proposito. Um segredo que so existisse no fim seria um
premio; este e um convite, e esta la desde o comeco.
"""
from __future__ import annotations

from ouroboros.core.systems.base_system import ISystem
from ouroboros.core.systems.tile_collision_system import TileCollisionSystem
from ouroboros.core.world import World

from penumbra.state import DualityState, LUMEN, OUTCOME_PLAYING, UMBRA
from penumbra.tuning import DualityTuning

_STILL_SPEED = 6.0
"""Velocidade horizontal abaixo da qual os dois contam como parados. Nao e
zero: o `TileCollisionSystem` deixa residuos de um frame ao encostar, e
exigir zero exato faria o segredo depender de sorte."""

_SAME_ROW = 20.0
"""Diferenca vertical maxima entre os centros. Lado a lado, e nao um sobre o
outro -- um em cima do outro e so a colisao vertical que ja existe."""


class EchoSystem(ISystem):
    """
    Conta quanto tempo os dois estao parados, lado a lado, sem se tocar.

    Roda DEPOIS do `DualityControlSystem` porque le `velocity`, e depois do
    `TileCollisionSystem` porque le `is_grounded` -- as duas coisas so sao
    verdade no fim do frame.

    A janela de distancia tem um piso e um teto, e os dois importam. O piso
    e a propria regra de contato (somar as meias-larguras), entao chegar
    perto DEMAIS nao vira segredo, vira a morte de sempre. O teto e curto
    porque o que se reconhece aqui e a intencao de chegar perto: de longe,
    ficar parado lado a lado e o que dois seres fazem o tempo todo.
    """

    def __init__(
        self,
        state: DualityState,
        tuning: DualityTuning,
        tile_collision_systems,
        transform_pool_name: str = "transform",
        velocity_pool_name: str = "velocity",
    ) -> None:
        self._state = state
        self._tile_collision_systems = tile_collision_systems
        self._transform_pool_name = transform_pool_name
        self._velocity_pool_name = velocity_pool_name
        self._transform_pool = None
        self._velocity_pool = None

        contact = tuning.lumen.half_width + tuning.umbra.half_width
        self._min_gap = contact + 1.0
        self._max_gap = contact + tuning.world.cell_size * 0.7
        self._seconds = max(0.1, float(tuning.flow.echo_seconds))

    def update(self, world: World, delta_time: float) -> None:
        if self._transform_pool is None:
            self._transform_pool = world.get_pool(self._transform_pool_name)
            self._velocity_pool = world.get_pool(self._velocity_pool_name)

        state = self._state
        if state.outcome != OUTCOME_PLAYING or state.echo_found:
            return

        if not self._side_by_side():
            state.echo_seconds = 0.0
            return

        state.echo_seconds += delta_time
        if state.echo_seconds >= self._seconds:
            state.echo_found = True
            state.echo_seconds = self._seconds

    # ------------------------------------------------------------------

    def _side_by_side(self) -> bool:
        transform = self._transform_pool.active_view()
        velocity = self._velocity_pool.active_view()
        state = self._state

        positions = []
        for side in (LUMEN, UMBRA):
            entity_index = int(state.entity_index[side])
            if not self._tile_collision_systems[side].is_grounded(entity_index):
                return False
            row = self._velocity_pool.dense_row_of(entity_index)
            if abs(float(velocity["linear_x"][row])) > _STILL_SPEED:
                return False
            transform_row = self._transform_pool.dense_row_of(entity_index)
            positions.append(
                (float(transform["position_x"][transform_row]),
                 float(transform["position_y"][transform_row]))
            )

        (lumen_x, lumen_y), (umbra_x, umbra_y) = positions
        if abs(lumen_y - umbra_y) > _SAME_ROW:
            return False
        gap = abs(lumen_x - umbra_x)
        return self._min_gap <= gap <= self._max_gap
