"""
Controle dos dois seres: um sob o comando do jogador, o outro esperando.

Uma unica classe cuida dos dois lados de proposito. A assimetria entre
Lumen e Umbra e inteiramente numerica (`CharacterTuning`, carregado de
`data/difficulties/penumbra/*.json`) -- se ela virasse dois sistemas
duplicados, a proxima regra nova teria que ser escrita duas vezes e podia
divergir em um dos lados sem ninguem notar.
"""
from __future__ import annotations

from typing import Tuple

from ouroboros.core.systems.base_system import ISystem
from ouroboros.core.systems.tile_collision_system import TileCollisionSystem
from ouroboros.core.world import World
from ouroboros.interfaces.input_provider import IInputProvider

from penumbra.state import DualityState, LUMEN, UMBRA
from penumbra.tuning import DualityTuning

_PLAYER_TWO_PREFIX = "p2_"
"""Prefixo das acoes do segundo jogador em
`data/input_bindings/penumbra_keyboard.json`. O modo duo nao duplica logica
nenhuma: o mesmo `_drive` recebe o prefixo e o resto e identico."""

_MIN_CHARGE_TO_ENGAGE = 0.08
"""Carga minima pra LIGAR a habilidade. Sem esse piso, uma carga
praticamente vazia permitiria ligar e desligar por um frame, o que
solidificaria eter por tempo demais curto pra ser lido na tela mas longo
o bastante pra derrubar o outro ser -- uma morte que o jogador nao teria
como ver chegando."""


class DualityControlSystem(ISystem):
    """
    Le o input e escreve `velocity`. Dois modos, um caminho de codigo.

    **Solo**: comanda o ser ATIVO e zera a horizontal do inativo -- ele
    espera parado, mas continua sujeito a gravidade e ao proprio chao. Se a
    polaridade do terreno sob ele mudar enquanto o jogador cuida do outro,
    ele cai, e e disso que as fases vivem.

    **Duo** (dois jogadores locais): cada ser tem seu proprio conjunto de
    acoes (`p2_*` para o segundo), os dois se movem ao mesmo tempo, ninguem
    espera, e o TAB nao faz nada -- nao existe "ativo" pra alternar. O
    contato entre eles continua aniquilando os dois: no solo era uma
    armadilha ocasional, no duo e a fonte principal de desastre, e de graca.

    Os dois modos passam pelo MESMO `_drive`, que recebe so o prefixo das
    acoes -- uma regra nova de movimento nao pode divergir entre eles.

    Roda DEPOIS de `PhysicsSystem`/`TileCollisionSystem`/`GravitySystem` (e
    o unico lugar possivel: `CompositionRoot` registra os tres primeiro).
    Isso e o mesmo contrato do vertical slice do Platformer, e e o que
    mantem valida a reconstrucao de posicao pre-movimento do
    `TileCollisionSystem`: quando ele roda no frame seguinte, a unica coisa
    que tocou `velocity` desde a ultima integracao foi este sistema e o
    `GravitySystem`, nessa ordem.
    """

    def __init__(
        self,
        input_provider: IInputProvider,
        state: DualityState,
        tuning: DualityTuning,
        tile_collision_systems: Tuple[TileCollisionSystem, TileCollisionSystem],
        velocity_pool_name: str = "velocity",
    ) -> None:
        self._input = input_provider
        self._state = state
        self._sides = (tuning.lumen, tuning.umbra)
        self._tile_collision_systems = tile_collision_systems
        self._velocity_pool_name = velocity_pool_name
        self._velocity_pool = None

    def update(self, world: World, delta_time: float) -> None:
        if self._velocity_pool is None:
            self._velocity_pool = world.get_pool(self._velocity_pool_name)

        state = self._state
        if self._input.is_action_pressed("restart"):
            state.restart_requested = True

        if state.duo:
            # Dois jogadores: cada um comanda o seu, e ninguem espera. O TAB
            # nao faz nada aqui -- nao ha "ativo" pra alternar.
            for side, prefix in ((LUMEN, ""), (UMBRA, _PLAYER_TWO_PREFIX)):
                if self._input.is_action_pressed(f"{prefix}ability"):
                    self._toggle_ability(side)
            self._update_charges(delta_time)
            for side, prefix in ((LUMEN, ""), (UMBRA, _PLAYER_TWO_PREFIX)):
                self._drive(side, prefix)
            return

        if self._input.is_action_pressed("switch"):
            state.active = UMBRA if state.active == LUMEN else LUMEN
        if self._input.is_action_pressed("ability"):
            self._toggle_ability(state.active)

        self._update_charges(delta_time)
        self._drive(state.active, "")
        self._park_inactive()

    # ------------------------------------------------------------------
    # internos
    # ------------------------------------------------------------------

    def _toggle_ability(self, side: int) -> None:
        state = self._state
        if state.ability_on[side]:
            state.ability_on[side] = False
        elif state.charge[side] >= _MIN_CHARGE_TO_ENGAGE:
            state.ability_on[side] = True

    def _update_charges(self, delta_time: float) -> None:
        """Drena a carga da habilidade ligada, recompoe a da desligada, e
        desliga sozinha quem chegou a zero -- os dois lados, ligado ou nao,
        ativo ou nao (o facho da Lumen continua queimando enquanto o
        jogador comanda a Umbra, e e por isso que ele custa)."""
        state = self._state
        for side in (LUMEN, UMBRA):
            tuning = self._sides[side]
            if state.ability_on[side]:
                remaining = float(state.charge[side]) - delta_time / tuning.ability_charge_seconds
                if remaining <= 0.0:
                    state.charge[side] = 0.0
                    state.ability_on[side] = False
                else:
                    state.charge[side] = remaining
            else:
                refilled = float(state.charge[side]) + tuning.ability_refill_per_second * delta_time
                state.charge[side] = 1.0 if refilled > 1.0 else refilled

    def _drive(self, side: int, prefix: str) -> None:
        """Move UM ser a partir de um conjunto de acoes. `prefix` e ""
        para o jogador 1 e `"p2_"` para o 2 -- o mesmo caminho de codigo
        serve ao solo e ao duo, e e por isso que uma regra nova de
        movimento nao pode divergir entre os modos."""
        state = self._state
        tuning = self._sides[side]
        entity_index = int(state.entity_index[side])
        pool = self._velocity_pool
        row = pool.dense_row_of(entity_index)
        view = pool.active_view()

        moving_left = self._input.is_action_held(f"{prefix}move_left")
        moving_right = self._input.is_action_held(f"{prefix}move_right")
        if moving_left and not moving_right:
            view["linear_x"][row] = -tuning.move_speed
        elif moving_right and not moving_left:
            view["linear_x"][row] = tuning.move_speed
        else:
            view["linear_x"][row] = 0.0

        jumped = self._input.is_action_pressed(f"{prefix}jump")
        if jumped and self._tile_collision_systems[side].is_grounded(entity_index):
            view["linear_y"][row] = tuning.jump_velocity_y

    def _park_inactive(self) -> None:
        state = self._state
        side = UMBRA if state.active == LUMEN else LUMEN
        pool = self._velocity_pool
        row = pool.dense_row_of(int(state.entity_index[side]))
        pool.active_view()["linear_x"][row] = 0.0
