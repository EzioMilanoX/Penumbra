"""
A cena de Penumbra: quando o mundo anda, e quando ele congela.

Substitui a `GameplayScene` padrao no topo da pilha (via
`GameLoop.reset_scenes`) mas nao duplica nada dela -- `GameplayScene` e
documentada como stateless e reutilizavel exatamente pra isso, entao o
`render` daqui e uma delegacao direta. O que esta cena acrescenta e apenas
o momento em que `world.step()` NAO deve ser chamado.

Trocar de fase e recomecar sao feitos aqui, entre dois `step()`, e nunca de
dentro de um `ISystem`: reposicionar um ser no meio da cadeia
`PhysicsSystem -> TileCollisionSystem -> GravitySystem` invalidaria a
reconstrucao de posicao pre-movimento que o `TileCollisionSystem` faz.
"""
from __future__ import annotations

from ouroboros.bootstrap.scene import GameplayScene, IScene
from ouroboros.core.world import World
from ouroboros.interfaces.input_provider import IInputProvider
from ouroboros.interfaces.renderer import IRenderer

from penumbra.state import DualityState, LevelRuntime, OUTCOME_COMPLETE, OUTCOME_PLAYING
from penumbra.tuning import DualityTuning

_DISMISS_ACTIONS = ("jump", "ability", "switch")


class PenumbraScene(IScene):
    """
    Simula enquanto a fase esta em andamento; congela quando ela termina.

    O congelamento e deliberado e nao e uma pausa generica: no instante em
    que Lumen se apaga ou os dois portais respondem, a ultima imagem do
    mundo continua na tela por baixo do painel. O jogador ve a causa da
    morte parada, em vez de um corte para um menu.
    """

    def __init__(
        self,
        runtime: LevelRuntime,
        state: DualityState,
        tuning: DualityTuning,
        input_provider: IInputProvider,
    ) -> None:
        self._runtime = runtime
        self._state = state
        self._tuning = tuning
        self._input = input_provider
        self._gameplay = GameplayScene()
        self._frozen_seconds = 0.0

    def update(self, world: World, delta_time: float) -> None:
        if self._state.outcome != OUTCOME_PLAYING:
            self._update_frozen(delta_time)
            return

        world.step(delta_time)

        if self._state.restart_requested:
            self._runtime.reset()
            return
        if self._state.outcome != OUTCOME_PLAYING:
            self._frozen_seconds = 0.0

    def render(self, world: World, renderer: IRenderer) -> None:
        self._gameplay.render(world, renderer)

    # ------------------------------------------------------------------

    def _update_frozen(self, delta_time: float) -> None:
        """Segura o resultado na tela por `flow.overlay_seconds`, ou ate o
        jogador confirmar -- o que vier primeiro. `overlay_min_seconds`
        existe pra que a tecla de pulo ainda pressionada no frame da morte
        nao dispense o aviso antes de ele ser lido."""
        flow = self._tuning.flow
        self._frozen_seconds += delta_time

        dismissed = self._frozen_seconds >= flow.overlay_min_seconds and any(
            self._input.is_action_pressed(action) for action in _DISMISS_ACTIONS
        )
        if not dismissed and self._frozen_seconds < flow.overlay_seconds:
            return

        if self._state.outcome == OUTCOME_COMPLETE:
            self._runtime.advance()
        else:
            self._runtime.reset()
        self._frozen_seconds = 0.0
