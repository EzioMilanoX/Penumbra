"""
As cenas de Penumbra e o fluxo entre elas.

`PenumbraScene` substitui a `GameplayScene` padrao no topo da pilha (via
`GameLoop.reset_scenes`) mas nao duplica nada dela -- `GameplayScene` e
documentada como stateless e reutilizavel exatamente pra isso, entao o
`render` daqui e uma delegacao direta. O que estas cenas acrescentam e
apenas: quando `world.step()` NAO deve ser chamado, e o que aparece na tela
quando o mundo esta parado.

Trocar de fase e recomecar sao feitos aqui, entre dois `step()`, e nunca de
dentro de um `ISystem`: reposicionar um ser no meio da cadeia
`PhysicsSystem -> TileCollisionSystem -> GravitySystem` invalidaria a
reconstrucao de posicao pre-movimento que o `TileCollisionSystem` faz.

Input das cenas e lido DIRETO do `IInputProvider`, nao por um `ISystem`: o
menu existe justamente enquanto o `World` nao esta rodando, e um sistema so
roda dentro de `world.step()`.
"""
from __future__ import annotations

from typing import List, Optional

from ouroboros.bootstrap.game_loop import GameLoop
from ouroboros.bootstrap.scene import GameplayScene, IScene
from ouroboros.core.world import World
from ouroboros.interfaces.input_provider import IInputProvider
from ouroboros.interfaces.renderer import IRenderer

from penumbra.levels import LevelCatalog
from penumbra.state import DualityState, LevelRuntime, OUTCOME_COMPLETE, OUTCOME_PLAYING
from penumbra.tuning import DualityTuning

_DISMISS_ACTIONS = ("jump", "ability", "switch")

_PANEL = (12, 12, 18, 236)
_RULE = (58, 56, 72, 255)
_TEXT = (206, 208, 224, 255)
_TEXT_DIM = (128, 130, 148, 255)
_TEXT_FAINT = (100, 102, 120, 255)
_GOLD = (247, 214, 138, 255)
_GOLD_DIM = (150, 122, 66, 255)


class PenumbraFlow:
    """
    Dono das transicoes: menu -> fase -> menu.

    Existe porque as duas cenas precisam saber uma da outra e nenhuma das
    duas deveria conhecer a outra diretamente. Guarda tambem o progresso da
    sessao (quais fases foram vencidas) -- estado de META, nao de simulacao,
    e por isso fora do `DualityState`: o `World` nao tem opiniao sobre o que
    o jogador ja terminou.
    """

    def __init__(
        self,
        game_loop: GameLoop,
        runtime: LevelRuntime,
        state: DualityState,
        catalog: LevelCatalog,
        tuning: DualityTuning,
        input_provider: IInputProvider,
    ) -> None:
        self._game_loop = game_loop
        self._runtime = runtime
        self._state = state
        self._catalog = catalog
        self.completed: List[bool] = [False] * catalog.count
        self.menu = MenuScene(self, catalog, input_provider)
        self.gameplay = PenumbraScene(self, runtime, state, tuning, input_provider)

    def show_menu(self, message: str = "") -> None:
        self.menu.message = message
        self._game_loop.reset_scenes(self.menu)

    def start_level(self, level_index: int) -> None:
        self._runtime.load(level_index)
        self._game_loop.reset_scenes(self.gameplay)

    def finish_level(self, level_index: int) -> None:
        """Marca como vencida e segue pra proxima. Depois da ultima, volta ao
        menu -- em vez de reiniciar o ciclo em silencio, como fazia antes."""
        self.completed[level_index] = True
        if level_index + 1 < self._catalog.count:
            self.start_level(level_index + 1)
        else:
            self.show_menu("Voce atravessou as duas polaridades ate o fim.")

    def quit(self) -> None:
        self._game_loop.stop()

    @property
    def hud_visible(self) -> bool:
        """O HUD e um callback GLOBAL de `GameLoop.set_on_draw_ui` (roda
        independente da cena no topo), entao ele precisa saber quando calar a
        boca -- senao desenha a faixa de rodape e os medidores dos seres por
        cima do menu."""
        return self._game_loop.current_scene is self.gameplay


class MenuScene(IScene):
    """
    Titulo e selecao de fase. Nenhuma fase e trancada: com oito fases curtas,
    poder repetir a que ensinou uma mecanica vale mais que a cerimonia de
    desbloquear -- e o proprio jogo diz, no rodape, quais voce ja venceu.

    Nao chama `world.step()`: o mundo fica exatamente onde estava.
    """

    def __init__(self, flow: PenumbraFlow, catalog: LevelCatalog, input_provider: IInputProvider) -> None:
        self._flow = flow
        self._catalog = catalog
        self._input = input_provider
        self._selected = 0
        self.message = ""

    def on_enter(self, world: World, renderer: IRenderer) -> None:
        del world, renderer

    def update(self, world: World, delta_time: float) -> None:
        del world, delta_time
        if self._input.is_action_pressed("menu_down"):
            self._selected = (self._selected + 1) % self._catalog.count
        if self._input.is_action_pressed("menu_up"):
            self._selected = (self._selected - 1) % self._catalog.count
        if self._input.is_action_pressed("jump"):
            self._flow.start_level(self._selected)
        elif self._input.is_action_pressed("quit"):
            self._flow.quit()

    def render(self, world: World, renderer: IRenderer) -> None:
        del world
        width, height = renderer.get_viewport_size()
        renderer.draw_ui_rect(0.0, 0.0, width, height, (8, 8, 14, 255))

        center = width / 2.0
        renderer.draw_text(center, 44.0, "PENUMBRA", 40, _TEXT, anchor="center")
        renderer.draw_text(center, 92.0, "Luz e Sombra: Dualidade", 15, _GOLD, anchor="center")
        renderer.draw_ui_rect(center - 190.0, 118.0, 380.0, 1.0, _RULE)

        if self.message:
            renderer.draw_text(center, 134.0, self.message, 13, _GOLD, anchor="center")

        top = 168.0
        row_height = 30.0
        for index in range(self._catalog.count):
            level = self._catalog.at(index)
            selected = index == self._selected
            y = top + index * row_height
            if selected:
                renderer.draw_ui_rect(center - 250.0, y - 5.0, 500.0, row_height - 4.0, (26, 24, 34, 255))
                renderer.draw_ui_rect(center - 250.0, y - 5.0, 3.0, row_height - 4.0, _GOLD)
            mark = "o" if self._flow.completed[index] else "-"
            tone = _TEXT if selected else _TEXT_DIM
            renderer.draw_text(center - 232.0, y, f"{mark}  {index + 1}. {level.name}", 15, tone)

        footer = top + self._catalog.count * row_height + 22.0
        renderer.draw_text(center, footer, "W/S escolher    ESPACO jogar    ESC sair", 12, _TEXT_FAINT, anchor="center")
        renderer.draw_text(
            center, footer + 22.0,
            "'o' marca as fases que voce ja venceu nesta sessao",
            11, _TEXT_FAINT, anchor="center",
        )


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
        flow: PenumbraFlow,
        runtime: LevelRuntime,
        state: DualityState,
        tuning: DualityTuning,
        input_provider: IInputProvider,
    ) -> None:
        self._flow = flow
        self._runtime = runtime
        self._state = state
        self._tuning = tuning
        self._input = input_provider
        self._gameplay = GameplayScene()
        self._frozen_seconds = 0.0

    def on_enter(self, world: World, renderer: IRenderer) -> None:
        del world, renderer
        self._frozen_seconds = 0.0

    def update(self, world: World, delta_time: float) -> None:
        if self._state.outcome != OUTCOME_PLAYING:
            self._update_frozen(delta_time)
            return

        if self._input.is_action_pressed("quit"):
            self._flow.show_menu()
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

        readable = self._frozen_seconds >= flow.overlay_min_seconds
        if readable and self._input.is_action_pressed("quit"):
            self._flow.show_menu()
            return

        dismissed = readable and any(
            self._input.is_action_pressed(action) for action in _DISMISS_ACTIONS
        )
        if not dismissed and self._frozen_seconds < flow.overlay_seconds:
            return

        if self._state.outcome == OUTCOME_COMPLETE:
            self._flow.finish_level(self._state.level_index)
        else:
            self._runtime.reset()
        self._frozen_seconds = 0.0
