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

from penumbra import achievements
from penumbra import audio as audio_ids
from penumbra.levels import LevelCatalog
from penumbra.progress import Progress
from penumbra.menu import (
    MAIN_ACHIEVEMENTS, MAIN_OPTIONS, MAIN_PLAY,
    OPTION_ERASE, OPTION_FULLSCREEN, OPTION_SOUND, OPTION_VOLUME,
    AchievementsScreen, EndingScreen, LevelCardGrid, MainMenuScreen, MenuChrome,
    OptionsScreen, PauseScreen, TitleScreen,
)
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
        audio=None,
        progress: Optional[Progress] = None,
    ) -> None:
        self._game_loop = game_loop
        self._runtime = runtime
        self._state = state
        self._catalog = catalog
        self.audio = audio
        self.progress = progress if progress is not None else Progress(catalog.count)
        self._clean_run = True
        """A tentativa corrente chegou ate aqui sem morte e sem `R`. Vive no
        fluxo e nao no `DualityState` porque atravessa RESETS -- e a memoria
        de que houve um reset que a conquista reconhece."""
        self.unlocked: List[str] = []
        """Conquistas destravadas na ultima vitoria, pro menu anunciar."""
        # Guardado tambem aqui, e nao so repassado as cenas: `flow.pads` e
        # lido pelas telas que ENSINAM os controles, e elas perguntam ao
        # fluxo, nao ao provider.
        self._input = input_provider
        self.title = TitleScene(self, input_provider)
        self.menu = MenuScene(self, catalog, preview_terrain, input_provider)
        self.gameplay = PenumbraScene(self, runtime, state, tuning, input_provider)
        self.ending = EndingScene(self, input_provider)
        self.pause = PauseScene(self, input_provider)
        self.main = MainMenuScene(self, input_provider)
        self.achievements = AchievementsScene(self, input_provider)
        self.options = OptionsScene(self, input_provider)
        self.title.duo = self.progress.duo
        self.apply_audio_settings()

    def show_main(self) -> None:
        """A raiz. O jogo abria na escolha de MODO, que e um passo do caminho
        e nao uma raiz -- e por isso nao havia porta nenhuma pras conquistas,
        pras opcoes nem pra sair."""
        self._game_loop.reset_scenes(self.main)

    def show_achievements(self) -> None:
        self._game_loop.reset_scenes(self.achievements)

    def show_options(self) -> None:
        self.options.restart()
        self._game_loop.reset_scenes(self.options)

    def apply_audio_settings(self) -> None:
        """Leva som e volume do progresso pro motor. Chamado na abertura e a
        cada ajuste -- o `PenumbraAudio` nao le o progresso sozinho, pra que
        o audio continue removivel sem que nada mais saiba disso."""
        if self.audio is None:
            return
        self.audio.enabled = bool(self.progress.sound_on) and self.audio.has_engine
        self.audio.volume = float(self.progress.volume)

    def erase_progress(self) -> None:
        """Apaga tudo menos os ajustes: quem apaga o progresso raramente
        quer o volume de volta no padrao."""
        progress = self.progress
        progress.completed = [False] * progress.level_count
        progress.shards = [False] * progress.level_count
        progress.achievements = set()
        progress.ending_choice = None
        progress.save()

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
    def completed(self) -> List[bool]:
        return self.progress.completed

    @property
    def shards(self) -> List[bool]:
        return self.progress.shards

    @property
    def ending_choice(self) -> Optional[str]:
        return self.progress.ending_choice

    @ending_choice.setter
    def ending_choice(self, value: Optional[str]) -> None:
        self.progress.ending_choice = value
        self.progress.save()

    @property
    def source_is_whole(self) -> bool:
        """Todos os fragmentos apanhados.

        Nao se funde uma fonte que nunca foi remontada -- e essa e a unica
        consequencia que os fragmentos tem, e a razao de eles existirem. Nao
        e tranca: nenhuma fase fica bloqueada, e da pra voltar, apanhar os
        que faltam e refazer a escolha."""
        return all(self.progress.shards)

    def play(self, sound_id: str, volume: float = 1.0) -> None:
        """Som de interface. As cenas rodam com o mundo PARADO, fora de
        qualquer `world.step()`, entao elas nao passam pelo `AudioSystem`."""
        if self.audio is not None:
            self.audio.play(sound_id, volume)

    @property
    def duo(self) -> bool:
        """Um ou dois jogadores. Mora na tela de titulo -- e a primeira
        decisao da sessao, e a tela que a apresenta e a dona dela. Nao vive
        no `DualityState` porque e escolha de SESSAO, nao de partida: trocar
        de fase nao devia devolver o jogador ao modo solo."""
        return self.title.duo

    @property
    def pads(self) -> int:
        """Quantos controles estao ligados -- 0 quando o provider e o do
        teclado puro, que e o caso de todo teste headless.

        As telas que ENSINAM os controles leem isto. E a unica hora em que o
        jogador ainda esta decidindo o que fazer com as maos, e alguem com o
        controle na mao lendo "ESPACO pular" conclui que o controle nao
        funciona -- quando ele funciona."""
        return getattr(self._input, "pad_count", 0)

    def toggle_duo(self) -> None:
        self.title.duo = not self.title.duo
        self.progress.duo = self.title.duo
        self.progress.save()

    @property
    def summary(self):
        """(fases vencidas, fragmentos apanhados, total) -- a tela de titulo
        mostra isso pra que voltar ao jogo depois de um tempo diga, de cara,
        onde voce parou."""
        return (sum(1 for done in self.completed if done),
                sum(1 for got in self.shards if got),
                len(self.completed))

    @property
    def current_level_name(self) -> str:
        return self._catalog.at(self._state.level_index).name

    def show_pause(self) -> None:
        """Empilha a pausa POR CIMA da fase, em vez de trocar de cena: o
        mundo fica exatamente onde estava e volta sem recarregar nada.

        Antes, ESC no meio da fase voltava ao menu e custava a tentativa --
        nao havia como so PARAR."""
        self.pause.restart()
        self._game_loop.push_scene(self.pause)

    def resume(self) -> None:
        self._game_loop.pop_scene()

    def restart_level(self) -> None:
        self._clean_run = False
        self._runtime.reset()
        self.resume()

    def note_echo(self) -> None:
        """O Instante. Concede a conquista escondida e grava na hora -- um
        segredo que so valesse ao terminar a fase se perderia junto com a
        primeira morte depois dele."""
        fresh = achievements.ECHO not in self.progress.achievements
        self.progress.achievements.add(achievements.ECHO)
        if fresh:
            self.progress.save()
        self.play(audio_ids.ECHO, 1.0)

    def note_failure(self) -> None:
        """Morreu ou reiniciou: a tentativa deixa de ser limpa. Chamado pela
        cena, que e quem ve o desfecho."""
        self._clean_run = False

    def start_level(self, level_index: int) -> None:
        self._clean_run = True
        self.unlocked = []
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
        self.progress.completed[level_index] = True
        if self._state.shard_collected:
            self.progress.shards[level_index] = True
        self.unlocked = achievements.evaluate(
            self._catalog, self.progress, level_index, self._state,
            clean_run=self._clean_run, duo=self.duo,
        )
        self.progress.save()
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


class MainMenuScene(IScene):
    """
    A raiz: jogar, conquistas, opcoes, sair.

    O jogo abria direto na escolha de modo, e ESC ali fechava a janela --
    nao havia porta nenhuma pras conquistas nem pras opcoes, e a unica saida
    era um atalho que ninguem descobriria. A escolha de modo continua
    existindo; virou o passo seguinte a "JOGAR", que e o que ela sempre foi.

    Nao chama `world.step()`: o mundo fica parado.
    """

    def __init__(self, flow: "PenumbraFlow", input_provider: IInputProvider) -> None:
        self._flow = flow
        self._input = input_provider
        self._screen = MainMenuScreen()

    @property
    def screen(self) -> MainMenuScreen:
        return self._screen

    def update(self, world: World, delta_time: float) -> None:
        del world, delta_time
        if self._input.is_action_pressed("menu_up"):
            self._screen.move(-1)
            self._flow.play(audio_ids.MENU_MOVE, 0.5)
        if self._input.is_action_pressed("menu_down"):
            self._screen.move(1)
            self._flow.play(audio_ids.MENU_MOVE, 0.5)

        if self._input.is_action_pressed("quit"):
            self._flow.quit()
            return
        if not self._input.is_action_pressed("jump"):
            return

        self._flow.play(audio_ids.MENU_PICK, 0.7)
        chosen = self._screen.selected
        if chosen == MAIN_PLAY:
            self._flow.show_title()
        elif chosen == MAIN_ACHIEVEMENTS:
            self._flow.show_achievements()
        elif chosen == MAIN_OPTIONS:
            self._flow.show_options()
        else:
            self._flow.quit()

    def render(self, world: World, renderer: IRenderer) -> None:
        del world
        completed, _, total = self._flow.summary
        self._screen.draw(
            renderer, completed, total,
            len(self._flow.progress.achievements), len(achievements.CATALOG),
            ending=self._flow.ending_choice or "",
        )


class AchievementsScene(IScene):
    """So mostra. A unica tecla e ESC, porque nao ha nada a decidir aqui."""

    def __init__(self, flow: "PenumbraFlow", input_provider: IInputProvider) -> None:
        self._flow = flow
        self._input = input_provider
        self._screen = AchievementsScreen()

    def update(self, world: World, delta_time: float) -> None:
        del world, delta_time
        if self._input.is_action_pressed("quit") or self._input.is_action_pressed("jump"):
            self._flow.show_main()

    def render(self, world: World, renderer: IRenderer) -> None:
        del world
        _, shards, total = self._flow.summary
        self._screen.draw(renderer, self._flow.progress.achievements, shards, total)


class OptionsScene(IScene):
    """
    Som, volume, tela cheia e apagar progresso.

    Grava a cada mudanca em vez de ao sair: fechar o jogo pela janela nao
    passa por aqui, e um ajuste perdido por causa disso seria exatamente o
    tipo de coisa que o jogador nao reporta -- so deixa de mexer.

    A tela cheia e aplicada no `render`, que e o unico lugar com o renderer
    em maos; `set_fullscreen` e idempotente, entao comparar com o estado ja
    aplicado basta pra nao recriar a janela sessenta vezes por segundo.
    """

    def __init__(self, flow: "PenumbraFlow", input_provider: IInputProvider) -> None:
        self._flow = flow
        self._input = input_provider
        self._screen = OptionsScreen()
        self._applied_fullscreen = None

    @property
    def screen(self) -> OptionsScreen:
        return self._screen

    def restart(self) -> None:
        self._screen = OptionsScreen()

    def update(self, world: World, delta_time: float) -> None:
        del world, delta_time
        progress, screen = self._flow.progress, self._screen

        if self._input.is_action_pressed("menu_up"):
            screen.move(-1)
            self._flow.play(audio_ids.MENU_MOVE, 0.5)
        if self._input.is_action_pressed("menu_down"):
            screen.move(1)
            self._flow.play(audio_ids.MENU_MOVE, 0.5)

        if self._input.is_action_pressed("quit"):
            self._flow.show_main()
            return

        step = 0
        if self._input.is_action_pressed("move_left"):
            step = -1
        elif self._input.is_action_pressed("move_right"):
            step = 1

        if step and screen.selected == OPTION_VOLUME:
            progress.volume = min(1.0, max(0.0, progress.volume + 0.1 * step))
            self._flow.apply_audio_settings()
            self._flow.play(audio_ids.MENU_PICK, 0.8)   # ouvir o que se ajusta
            progress.save()
            return
        if step and screen.selected in (OPTION_SOUND, OPTION_FULLSCREEN):
            self._toggle(screen.selected)
            return

        if self._input.is_action_pressed("jump"):
            self._confirm(screen.selected)

    def _toggle(self, row: int) -> None:
        progress = self._flow.progress
        if row == OPTION_SOUND:
            progress.sound_on = not progress.sound_on
            self._flow.apply_audio_settings()
            self._flow.play(audio_ids.MENU_PICK, 0.7)
        elif row == OPTION_FULLSCREEN:
            progress.fullscreen = not progress.fullscreen
        progress.save()

    def _confirm(self, row: int) -> None:
        screen = self._screen
        if row == OPTION_ERASE:
            if not screen.confirm_erase:
                # Um menu que apaga trinta fases num toque e hostil. O
                # segundo ESPAÇO existe pra que a intencao seja dita duas
                # vezes, com o aviso na tela entre as duas.
                screen.confirm_erase = True
                self._flow.play(audio_ids.MENU_MOVE, 0.6)
                return
            screen.confirm_erase = False
            self._flow.erase_progress()
            self._flow.play(audio_ids.FAIL, 0.7)
            return
        self._toggle(row)

    def render(self, world: World, renderer: IRenderer) -> None:
        del world
        progress = self._flow.progress
        if self._applied_fullscreen != progress.fullscreen:
            renderer.set_fullscreen(progress.fullscreen)
            self._applied_fullscreen = progress.fullscreen
        completed, _, total = self._flow.summary
        self._screen.draw(renderer, progress.sound_on, progress.volume,
                          progress.fullscreen, completed, total)


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
            self._flow.play(audio_ids.MENU_PICK, 0.7)
            self._flow.show_menu()
        elif self._input.is_action_pressed("quit"):
            self._flow.show_main()

    def render(self, world: World, renderer: IRenderer) -> None:
        del world
        completed, shards, total = self._flow.summary
        self._screen.draw(
            renderer, completed, shards, total,
            achievements=len(self._flow.progress.achievements),
            achievement_total=len(achievements.CATALOG),
            pads=self._flow.pads,
        )


class PauseScene(IScene):
    """
    Parar sem perder a tentativa.

    Fica EMPILHADA por cima da fase (`push_scene`), nao no lugar dela: o
    mundo congela onde estava e volta sem recarregar nada. Por isso ela
    tambem desenha a fase por baixo do proprio painel -- o `GameLoop`
    renderiza so o topo da pilha.

    Nao chama `world.step()`, que e o que "pausa" quer dizer aqui.
    """

    def __init__(self, flow: "PenumbraFlow", input_provider: IInputProvider) -> None:
        self._flow = flow
        self._input = input_provider
        self._screen = PauseScreen()
        self._gameplay = GameplayScene()

    def restart(self) -> None:
        self._screen.selected = 0

    @property
    def screen(self) -> PauseScreen:
        return self._screen

    def update(self, world: World, delta_time: float) -> None:
        del world, delta_time
        if self._input.is_action_pressed("menu_up"):
            self._screen.move(-1)
            self._flow.play(audio_ids.MENU_MOVE, 0.5)
        if self._input.is_action_pressed("menu_down"):
            self._screen.move(1)
            self._flow.play(audio_ids.MENU_MOVE, 0.5)

        if self._input.is_action_pressed("quit"):
            self._flow.resume()
            return
        if not self._input.is_action_pressed("jump"):
            return

        self._flow.play(audio_ids.MENU_PICK, 0.6)
        chosen = self._screen.selected
        if chosen == 0:
            self._flow.resume()
        elif chosen == 1:
            self._flow.restart_level()
        else:
            self._flow.resume()
            self._flow.show_menu()

    def render(self, world: World, renderer: IRenderer) -> None:
        self._gameplay.render(world, renderer)
        self._screen.draw(renderer, self._flow.current_level_name, self._flow.duo)


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
        _, shards, total = self._flow.summary
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
        before = self._grid.selected
        if self._input.is_action_pressed("move_left"):
            self._grid.move(-1, 0)
        if self._input.is_action_pressed("move_right"):
            self._grid.move(1, 0)
        if self._input.is_action_pressed("menu_up"):
            self._grid.move(0, -1)
        if self._input.is_action_pressed("menu_down"):
            self._grid.move(0, 1)
        if self._grid.selected != before:
            self._flow.play(audio_ids.MENU_MOVE, 0.5)
        if self._input.is_action_pressed("switch"):
            self._flow.toggle_duo()
        if self._input.is_action_pressed("jump"):
            self._flow.play(audio_ids.MENU_PICK, 0.7)
            self._flow.start_level(self._grid.selected)
        elif self._input.is_action_pressed("quit"):
            self._flow.show_title()

    def render(self, world: World, renderer: IRenderer) -> None:
        del world
        self._chrome.draw(
            renderer, self._flow.duo,
            sum(1 for got in self._flow.shards if got), len(self._flow.shards),
            pads=self._flow.pads,
        )
        self._grid.draw(renderer, self._flow.completed, self._flow.shards, self._flow.duo,
                        pads=self._flow.pads)


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
        self._echo_noted = False

    def on_enter(self, world: World, renderer: IRenderer) -> None:
        del world, renderer
        self._frozen_seconds = 0.0
        self._echo_noted = False

    def update(self, world: World, delta_time: float) -> None:
        if self._state.outcome != OUTCOME_PLAYING:
            self._update_frozen(delta_time)
            return

        if self._input.is_action_pressed("quit"):
            self._flow.show_pause()
            return

        world.step(delta_time)

        # O segredo e concedido no instante em que acontece, e nao no fim da
        # fase: quem o encontrou parou de proposito e merece saber agora.
        if self._state.echo_found and not self._echo_noted:
            self._echo_noted = True
            self._flow.note_echo()

        if self._state.restart_requested:
            self._flow.note_failure()
            self._runtime.reset()
            return
        if self._state.outcome != OUTCOME_PLAYING:
            if self._state.outcome != OUTCOME_COMPLETE:
                self._flow.note_failure()
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
