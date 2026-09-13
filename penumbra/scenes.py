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
from penumbra.menu import EndingScreen, LevelCardGrid, MenuChrome, TitleScreen
from penumbra.terrain import Terrain
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
        preview_terrain: Terrain,
    ) -> None:
        self._game_loop = game_loop
        self._runtime = runtime
        self._state = state
        self._catalog = catalog
        self.completed: List[bool] = [False] * catalog.count
        self.shards: List[bool] = [False] * catalog.count
        self.ending_choice: Optional[str] = None
        """O que o jogador escolheu no fim, ou `None` se ainda nao chegou la.
        Mora aqui, e nao no `DualityState`, pela mesma razao que o modo: e uma
        decisao da SESSAO, e o `World` nao tem opiniao sobre ela."""
        self.title = TitleScene(self, input_provider)
        self.menu = MenuScene(self, catalog, preview_terrain, input_provider)
        self.gameplay = PenumbraScene(self, runtime, state, tuning, input_provider)
        self.ending = EndingScene(self, input_provider)

    def show_title(self) -> None:
        self._game_loop.reset_scenes(self.title)

    def show_menu(self, message: str = "") -> None:
        self.menu.message = message
        self._game_loop.reset_scenes(self.menu)

    def show_ending(self) -> None:
        """Depois da ultima fase. Nao e uma tela de parabens: e a pergunta que
        o jogo passou dezoito fases fazendo sem dizer em voz alta."""
        self.ending.restart()
        self._game_loop.reset_scenes(self.ending)

    @property
    def duo(self) -> bool:
        """Um ou dois jogadores. Mora na tela de titulo -- e a primeira
        decisao da sessao, e a tela que a apresenta e a dona dela. Nao vive
        no `DualityState` porque e escolha de SESSAO, nao de partida: trocar
        de fase nao devia devolver o jogador ao modo solo."""
        return self.title.duo

    def toggle_duo(self) -> None:
        self.title.duo = not self.title.duo

    @property
    def progress(self):
        """(fases vencidas, fragmentos apanhados, total) -- a tela de titulo
        mostra isso pra que voltar ao jogo depois de um tempo diga, de cara,
        onde voce parou."""
        return (sum(1 for done in self.completed if done),
                sum(1 for got in self.shards if got),
                len(self.completed))

    def start_level(self, level_index: int) -> None:
        # O modo entra ANTES do load: a mesma fase pode ser um problema
        # diferente nos dois, e `LevelRuntime.load` escolhe a variante pelo
        # `state.duo`. Na ordem inversa, o duo comecava na fase do solo.
        self._state.duo = self.duo
        self._runtime.load(level_index)
        self._game_loop.reset_scenes(self.gameplay)

    def finish_level(self, level_index: int) -> None:
        """Marca como vencida e segue pra proxima. Depois da ultima, volta ao
        menu -- em vez de reiniciar o ciclo em silencio, como fazia antes.

        O fragmento e registrado aqui, e nao no instante em que e apanhado:
        so conta se a fase foi CONCLUIDA com ele. Pegar e morrer nao vale --
        senao o desvio deixaria de ser um risco."""
        self.completed[level_index] = True
        if self._state.shard_collected:
            self.shards[level_index] = True
        if level_index + 1 < self._catalog.count:
            self.start_level(level_index + 1)
        else:
            self.show_ending()

    def quit(self) -> None:
        self._game_loop.stop()

    @property
    def hud_visible(self) -> bool:
        """O HUD e um callback GLOBAL de `GameLoop.set_on_draw_ui` (roda
        independente da cena no topo), entao ele precisa saber quando calar a
        boca -- senao desenha a faixa de rodape e os medidores dos seres por
        cima do menu."""
        return self._game_loop.current_scene is self.gameplay


class TitleScene(IScene):
    """
    Abertura: escolher entre um e dois jogadores, com dois botoes grandes.

    Antes o modo era um atalho de TAB no canto do menu de fases -- quem nunca
    leu o rodape jamais descobriria que o jogo tem multiplayer local. Aqui
    ele e a primeira pergunta que o jogo faz.
    """

    def __init__(self, flow: "PenumbraFlow", input_provider: IInputProvider) -> None:
        self._flow = flow
        self._input = input_provider
        self._screen = TitleScreen()

    @property
    def duo(self) -> bool:
        return self._screen.duo

    @duo.setter
    def duo(self, value: bool) -> None:
        self._screen.duo = value

    def update(self, world: World, delta_time: float) -> None:
        del world, delta_time
        if self._input.is_action_pressed("move_left"):
            self._screen.move(-1)
        if self._input.is_action_pressed("move_right"):
            self._screen.move(1)
        if self._input.is_action_pressed("switch"):
            self._flow.toggle_duo()
        if self._input.is_action_pressed("jump"):
            self._flow.show_menu()
        elif self._input.is_action_pressed("quit"):
            self._flow.quit()

    def render(self, world: World, renderer: IRenderer) -> None:
        del world
        completed, shards, total = self._flow.progress
        self._screen.draw(renderer, completed, shards, total)


class EndingScene(IScene):
    """
    A escolha do fim, e o epilogo dela.

    Duas telas numa: a pergunta, e depois a consequencia escrita. O ESPACO
    serve as duas -- confirmar e, no segundo toque, voltar ao menu -- porque
    um epilogo que exigisse outra tecla faria o jogador procurar qual.

    Nao chama `world.step()`: o mundo fica parado onde a ultima fase parou.
    """

    def __init__(self, flow: "PenumbraFlow", input_provider: IInputProvider) -> None:
        self._flow = flow
        self._input = input_provider
        self._screen = EndingScreen()

    def restart(self) -> None:
        self._screen = EndingScreen()

    @property
    def screen(self) -> EndingScreen:
        return self._screen

    def update(self, world: World, delta_time: float) -> None:
        del world, delta_time
        screen = self._screen
        if self._input.is_action_pressed("move_left"):
            screen.move(-1)
        if self._input.is_action_pressed("move_right"):
            screen.move(1)
        if self._input.is_action_pressed("jump"):
            if screen.confirmed:
                self._flow.show_menu()
            else:
                screen.confirmed = True
                self._flow.ending_choice = screen.choice
        elif self._input.is_action_pressed("quit"):
            self._flow.show_menu()

    def render(self, world: World, renderer: IRenderer) -> None:
        del world
        _, shards, total = self._flow.progress
        self._screen.draw(renderer, shards, total)


class MenuScene(IScene):
    """
    Selecao de fase em grade de cards, com a fase desenhada em miniatura.

    Nenhuma fase e trancada: com fases curtas, poder repetir a que ensinou
    uma mecanica vale mais que a cerimonia de desbloquear -- e cada card ja
    diz, com selos, o que voce fez nela.

    Nao chama `world.step()`: o mundo fica exatamente onde estava.
    """

    def __init__(
        self,
        flow: "PenumbraFlow",
        catalog: LevelCatalog,
        preview_terrain: Terrain,
        input_provider: IInputProvider,
    ) -> None:
        self._flow = flow
        self._input = input_provider
        self._grid = LevelCardGrid(catalog, preview_terrain)
        self._chrome = MenuChrome()

    @property
    def message(self) -> str:
        return self._chrome.message

    @message.setter
    def message(self, value: str) -> None:
        self._chrome.message = value

    @property
    def selected(self) -> int:
        return self._grid.selected

    def update(self, world: World, delta_time: float) -> None:
        del world, delta_time
        if self._input.is_action_pressed("move_left"):
            self._grid.move(-1, 0)
        if self._input.is_action_pressed("move_right"):
            self._grid.move(1, 0)
        if self._input.is_action_pressed("menu_up"):
            self._grid.move(0, -1)
        if self._input.is_action_pressed("menu_down"):
            self._grid.move(0, 1)
        if self._input.is_action_pressed("switch"):
            self._flow.toggle_duo()
        if self._input.is_action_pressed("jump"):
            self._flow.start_level(self._grid.selected)
        elif self._input.is_action_pressed("quit"):
            self._flow.show_title()

    def render(self, world: World, renderer: IRenderer) -> None:
        del world
        self._chrome.draw(
            renderer, self._flow.duo,
            sum(1 for got in self._flow.shards if got), len(self._flow.shards),
        )
        self._grid.draw(renderer, self._flow.completed, self._flow.shards, self._flow.duo)


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
