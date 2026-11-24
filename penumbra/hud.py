"""
HUD e avisos de fim de fase.

Vive fora de qualquer `ISystem` de proposito: `IRenderer.draw_text`/
`draw_ui_rect` alocam (cache de fontes e superficies dentro do adapter), o
que a Regra 1 da Constituicao proibe dentro de `World.step()`. A engine
oferece exatamente um lugar legitimo pra isso -- o callback global de
`GameLoop.set_on_draw_ui`, chamado depois do `render()` da cena e antes do
`end_frame()` -- e e ele que este modulo implementa.
"""
from __future__ import annotations

from ouroboros.interfaces.renderer import IRenderer

from penumbra import achievements
from penumbra.state import (
    LUMEN,
    OUTCOME_COMPLETE,
    OUTCOME_PLAYING,
    TAPE_OFF,
    TAPE_RECORD,
    UMBRA,
    DualityState,
    LevelRuntime,
)
from penumbra.tuning import DualityTuning

_PANEL = (12, 12, 18, 236)
_RULE = (58, 56, 72, 255)
_TEXT = (206, 208, 224, 255)
_TEXT_DIM = (128, 130, 148, 255)
_GOLD = (247, 214, 138, 255)
_GOLD_DIM = (186, 158, 96, 255)
"""Um dourado mais baixo: a nota do duo ocupa a linha da dica e nao pode
competir com o dourado cheio dos medidores e do painel de fim."""
_LUMEN_TONE = (250, 250, 255, 255)
_UMBRA_TONE = (150, 146, 178, 255)
_PERIL = (206, 88, 88, 255)
"""Unico tom fora da paleta preto/branco/dourado do jogo, e so aqui: o
medidor de perigo precisa ser lido antes de ser pensado. O dourado nao
podia servir -- ele significa cooperacao, o oposto do que este medidor
avisa."""

_TEXT_FAINT = (100, 102, 120, 255)

_LINE_1 = 8.0
_LINE_2 = 29.0
_LINE_3 = 50.0
"""Tres linhas de rodape. `config.json` reserva a altura para elas
(`window_height - grid_rows * cell_size`); mexer numa coisa sem a outra
corta a ultima linha."""

_BAR_WIDTH = 30.0
_BAR_HEIGHT = 3.0
_BAR_GAP = 2.0


def _control_line(duo: bool, pads: int) -> str:
    """A linha de controles do rodape, para quem esta de fato jogando.

    Uma dica de controle que MENTE e pior que dica nenhuma: um jogador com o
    controle na mao lendo "ESPACO pular" conclui que o controle nao funciona --
    e ele funciona. Como o controle e um `ou` sobre o teclado, o que muda aqui
    nao e a verdade, e qual metade dela vale a pena ocupar a linha.

    No duo cada jogador tem a sua metade, e elas sao independentes: com UM
    controle so, o jogador 1 le o controle e o 2 le as setas, que e exatamente
    o arranjo de um sofa com um controle."""
    if duo:
        um = "J1: controle" if pads >= 1 else "J1: A/D  ESPAÇO  S   R"
        dois = "J2: controle" if pads >= 2 else "J2: setas  CIMA  BAIXO  END"
        sair = "START/ESC sair" if pads else "ESC sair"
        return f"{um}      {dois}      {sair}"
    if pads:
        return ("direcional mover   A pular   X habilidade   "
                "RB trocar   SELECT reiniciar   START sair")
    return ("A/D mover   ESPAÇO pular   S habilidade   "
            "TAB trocar   R reiniciar   ESC sair")


def echo_control_line(recording: bool, pads: int) -> str:
    """A linha de controles do solo com eco. As teclas sao as do solo -- o
    que muda e de QUEM elas sao em cada momento, e o que TAB e R fazem."""
    if pads:
        move = "direcional  A  X"
        swap, again, leave = "RB", "SELECT", "START"
    else:
        move = "A/D  ESPAÇO  S"
        swap, again, leave = "TAB", "R", "ESC"
    if recording:
        return f"{move}: Lumen     {swap} rebobinar     {again} regravar     {leave} pausa"
    return f"{move}: Umbra     {swap} regravar a Lumen     {again} recomeçar     {leave} pausa"


_TRAIL_STEP = 6
"""Um ponto do caminho gravado a cada 6 ticks (0,1 s): denso o bastante para
ler a rota, ralo o bastante para nao virar uma linha que esconde o terreno."""


class PenumbraHud:
    """Callable registrado em `GameLoop.set_on_draw_ui`.

    Desenha tres coisas, nessa ordem: os medidores flutuantes sobre cada
    ser, a faixa de rodape com a fase corrente, e -- quando a fase acabou
    -- o painel central. Coordenadas de mundo e de tela coincidem aqui (o
    jogo cabe numa tela, nao ha camera), entao os medidores podem ser
    posicionados direto pela posicao do ser.
    """

    def __init__(
        self,
        state: DualityState,
        runtime: LevelRuntime,
        tuning: DualityTuning,
        transform_pool,
        viewport_size,
        visible=None,
        unlocked=None,
        pads=None,
        tape=None,
    ) -> None:
        self._unlocked = unlocked
        self._tape = tape
        """O solo com eco, para o caminho gravado e o relogio da fita. O HUD so
        LE a sessao; quem decide e a cena."""
        # Quantos controles estao ligados AGORA -- e um callable, nao um
        # numero, porque um controle pode ser ligado com o jogo aberto e o
        # rodape tem de passar a falar dele no frame seguinte.
        self._pads = pads if pads is not None else (lambda: 0)
        self._state = state
        self._runtime = runtime
        self._tuning = tuning
        self._transform_pool = transform_pool
        self._width, self._height = viewport_size
        self._playfield_height = tuning.world.grid_rows * tuning.world.cell_size
        self._sides = (tuning.lumen, tuning.umbra)
        self._visible = visible if visible is not None else (lambda: True)

    def __call__(self, renderer: IRenderer) -> None:
        if not self._visible():
            return
        echo = self._tape is not None and self._state.tape_phase != TAPE_OFF
        if echo:
            self._draw_echo_trail(renderer)
        self._draw_character_meters(renderer)
        if echo:
            self._draw_echo_footer(renderer)
        else:
            self._draw_footer(renderer)
        if self._state.outcome != OUTCOME_PLAYING:
            if self._state.tape_paradox:
                self._draw_paradox(renderer)
            else:
                self._draw_outcome_panel(renderer)

    # ------------------------------------------------------------------

    def _draw_character_meters(self, renderer: IRenderer) -> None:
        state = self._state
        view = self._transform_pool.active_view()
        for side, tone in ((LUMEN, _LUMEN_TONE), (UMBRA, _UMBRA_TONE)):
            row = self._transform_pool.dense_row_of(int(state.entity_index[side]))
            x = float(view["position_x"][row])
            y = float(view["position_y"][row]) - self._sides[side].half_height - 14.0
            left = x - _BAR_WIDTH / 2.0

            self._bar(renderer, left, y, float(state.charge[side]), tone)
            if state.ability_on[side]:
                renderer.draw_ui_rect(left - 7.0, y, 4.0, _BAR_HEIGHT, _GOLD)
            peril = float(state.peril[side])
            if peril > 0.02:
                self._bar(renderer, left, y + _BAR_HEIGHT + _BAR_GAP, peril, _PERIL)

    def _bar(self, renderer: IRenderer, x: float, y: float, ratio: float, rgba) -> None:
        renderer.draw_ui_rect(x - 1.0, y - 1.0, _BAR_WIDTH + 2.0, _BAR_HEIGHT + 2.0, (10, 10, 16, 190))
        filled = max(0.0, min(1.0, ratio)) * _BAR_WIDTH
        if filled >= 1.0:
            renderer.draw_ui_rect(x, y, filled, _BAR_HEIGHT, rgba)

    # ------------------------------------------------------------------

    def _draw_footer(self, renderer: IRenderer) -> None:
        """Uma linha para cada coisa.

        A primeira versao punha a dica da fase e a lista de controles na
        MESMA linha, uma ancorada a esquerda e outra a direita: as duas
        somavam mais que a largura da janela e se sobrepunham no meio, nas
        quatro fases. Texto de largura variavel nunca cabe em duas ancoras
        opostas -- ou cada um tem sua linha, ou um deles tem de ser
        truncado. Aqui cada um tem sua linha, e o rodape foi dimensionado
        para as tres."""
        state, level = self._state, self._runtime.current
        top = self._playfield_height
        renderer.draw_ui_rect(0.0, top, self._width, self._height - top, _PANEL)
        renderer.draw_ui_rect(0.0, top, self._width, 1.0, _RULE)

        title = f"{state.level_index + 1}/{self._runtime.count}  {level.name}"
        renderer.draw_text(14.0, top + _LINE_1, title, 14, _TEXT)
        # O fragmento DESTA tentativa. Antes so aparecia no menu, depois --
        # tarde demais pra decidir se vale voltar buscar.
        if self._runtime.terrain.shard_cell is not None:
            renderer.draw_text(
                14.0 + len(title) * 8.4 + 12.0, top + _LINE_1 + 2.0,
                "fragmento" if state.shard_collected else "fragmento?", 12,
                _GOLD if state.shard_collected else _GOLD_DIM,
            )
        # No duo nao existe "quem esta sob comando": os dois estao. Dizer
        # "comando: LUMEN" ali seria mentira, e e a unica linha do rodape que
        # o jogador consulta pra saber de quem sao as teclas.
        renderer.draw_text(
            self._width - 14.0, top + _LINE_1,
            "J1 LUMEN   J2 UMBRA" if state.duo else f"comando: {state.active_name.upper()}",
            14, _GOLD, anchor="topright",
        )
        # No duo, a fase que MUDA diz o que mudou -- no lugar da dica, e nao
        # depois dela: sao duas frases sobre a mesma fase e so uma cabe na
        # linha. A que importa e a do modo que esta sendo jogado.
        if state.duo and level.duo_note:
            renderer.draw_text(14.0, top + _LINE_2, level.duo_note, 12, _GOLD_DIM)
        else:
            renderer.draw_text(14.0, top + _LINE_2, level.hint, 12, _TEXT_DIM)
        self._draw_world_clock(renderer, top)
        renderer.draw_text(14.0, top + _LINE_3,
                           _control_line(state.duo, self._pads()), 11, _TEXT_FAINT)

    def _draw_world_clock(self, renderer: IRenderer, top: float) -> None:
        """Os dois relogios do mundo, quando a fase tem um deles. O farol e o
        eclipse mudam o chao sem o jogador pedir, entao "quanto falta" e
        informacao de planejamento, nao enfeite -- sem isso o jogador so
        descobre a virada quando ela acontece embaixo dele."""
        state = self._state
        terrain = self._runtime.terrain
        if terrain.has_beacon:
            label = "farol ACESO" if state.beacon_on else "farol apagado"
            tone = _GOLD if state.beacon_on else _TEXT_DIM
            renderer.draw_text(
                self._width - 14.0, top + _LINE_2,
                f"{label}  {state.beacon_seconds_left:.1f}s", 12, tone, anchor="topright",
            )
        if terrain.has_eclipse and state.eclipse_touched:
            renderer.draw_text(
                self._width - 14.0, top + _LINE_3,
                f"eclipse colapsa em {state.eclipse_seconds_left:.1f}s",
                12, _PERIL, anchor="topright",
            )

    # ------------------------------------------------------------------

    def _draw_outcome_panel(self, renderer: IRenderer) -> None:
        state = self._state
        won = state.outcome == OUTCOME_COMPLETE
        panel_width, panel_height = 520.0, 116.0
        x = (self._width - panel_width) / 2.0
        y = (self._playfield_height - panel_height) / 2.0

        renderer.draw_ui_rect(x, y, panel_width, panel_height, _PANEL)
        renderer.draw_ui_rect(x, y, panel_width, 2.0, _GOLD if won else _RULE)

        center_x = self._width / 2.0
        renderer.draw_text(
            center_x, y + 26.0,
            "ECLIPSE" if won else "DISSONANCIA",
            20, _GOLD if won else _PERIL, anchor="center",
        )
        renderer.draw_text(center_x, y + 58.0, state.message, 13, _TEXT, anchor="center")
        # As conquistas destravavam em SILENCIO: `flow.unlocked` era escrito
        # e ninguem lia, entao o jogador so descobria indo ao menu depois.
        unlocked = self._unlocked() if self._unlocked else ()
        if won and unlocked:
            names = "  ·  ".join(achievements.title_of(key) for key in unlocked)
            renderer.draw_text(center_x, y + 84.0, f"conquista:  {names}", 11,
                               _GOLD, anchor="center")
            renderer.draw_text(center_x, y + 102.0,
                               "ESPAÇO para continuar", 11, _TEXT_DIM, anchor="center")
            return
        renderer.draw_text(
            center_x, y + 86.0,
            "ESPAÇO para continuar" if won else "ESPAÇO para tentar de novo",
            11, _TEXT_DIM, anchor="center",
        )

    # ------------------------------------------------------------------
    # solo com eco
    # ------------------------------------------------------------------

    def _draw_echo_trail(self, renderer: IRenderer) -> None:
        """O caminho que a Lumen gravada ainda vai fazer, em pontos.

        Jogando a Umbra, o problema e saber onde a luz VAI estar -- e o eco so
        mostra onde ela esta. O que falta do caminho, desenhado, e o passado
        lido como mapa. O que ja foi percorrido nao aparece: ja esta na tela
        como o proprio eco."""
        tape, state = self._tape, self._state
        if state.tape_phase == TAPE_RECORD:
            return
        start = max(0, tape.replay_tick + 1)
        start += (-start) % _TRAIL_STEP
        trail = tape.trail
        for index in range(start, tape.trail_count, _TRAIL_STEP):
            x, y = float(trail[index, 0]), float(trail[index, 1])
            renderer.draw_ui_rect(x - 1.5, y - 1.5, 3.0, 3.0, (236, 236, 250, 90))
        if tape.trail_count:
            end_x, end_y = float(trail[tape.trail_count - 1, 0]), float(trail[tape.trail_count - 1, 1])
            renderer.draw_ui_circle(end_x, end_y, 7.0, (236, 236, 250, 110), 1)

    def _draw_echo_footer(self, renderer: IRenderer) -> None:
        """O rodape do laco: em que tempo voce esta, quanto da fita ja foi, e
        as teclas do momento. "comando: LUMEN" seria verdade e nao bastaria --
        a pergunta aqui e QUANDO."""
        state, tape, level = self._state, self._tape, self._runtime.current
        top = self._playfield_height
        renderer.draw_ui_rect(0.0, top, self._width, self._height - top, _PANEL)
        renderer.draw_ui_rect(0.0, top, self._width, 1.0, _RULE)

        title = f"{state.level_index + 1}/{self._runtime.count}  {level.name}  ·  solo com eco"
        renderer.draw_text(14.0, top + _LINE_1, title, 14, _TEXT)

        recording = state.tape_phase == TAPE_RECORD
        if recording and tape.replaying_prefix:
            left = (tape.prefix_ticks - tape.recorded_ticks) / 60.0
            label, tone = f"o passado se repete... sua vez em {left:.1f}s", _GOLD_DIM
        elif recording:
            label = f"GRAVANDO A LUMEN  {tape.recorded_seconds:4.1f}/{tape.capacity / 60.0:.0f}s"
            tone = _PERIL
        else:
            played = min(max(0, tape.replay_tick + 1), tape.trail_count) / 60.0
            label = f"UMBRA + ECO  {played:4.1f}/{tape.trail_count / 60.0:.1f}s"
            tone = _GOLD
        renderer.draw_text(self._width - 14.0, top + _LINE_1, label, 14, tone, anchor="topright")

        note = level.echo_note if not recording else (
            "Ela ainda está sozinha: grave o caminho que a Umbra vai precisar.")
        renderer.draw_text(14.0, top + _LINE_2, note, 12, _GOLD_DIM)
        self._draw_world_clock(renderer, top)
        renderer.draw_text(14.0, top + _LINE_3, echo_control_line(recording, self._pads()),
                           11, _TEXT_FAINT)

    def _draw_paradox(self, renderer: IRenderer) -> None:
        """O paradoxo: onde o eco quebrou, onde ele devia estar, e a escolha.

        O ponto marcado e a informacao toda. Sem ele, "o passado mudou" e uma
        frase; com ele, o jogador ve que foi a escuridao DELE que apagou a
        ponte embaixo da Lumen -- e sabe o que mudar."""
        state, tape = self._state, self._tape
        x, y = state.tape_paradox_x, state.tape_paradox_y
        renderer.draw_ui_circle(x, y, 18.0, _PERIL, 2)
        renderer.draw_ui_line(x - 10.0, y - 10.0, x + 10.0, y + 10.0, _PERIL, 2)
        renderer.draw_ui_line(x - 10.0, y + 10.0, x + 10.0, y - 10.0, _PERIL, 2)
        index = tape.paradox_tick
        if 0 <= index < tape.trail_count:
            gx, gy = float(tape.trail[index, 0]), float(tape.trail[index, 1])
            renderer.draw_ui_circle(gx, gy, 10.0, _GOLD, 1)

        panel_width, panel_height = 560.0, 120.0
        px = (self._width - panel_width) / 2.0
        py = 24.0
        renderer.draw_ui_rect(px, py, panel_width, panel_height, _PANEL)
        renderer.draw_ui_rect(px, py, panel_width, 2.0, _PERIL)
        center_x = self._width / 2.0
        renderer.draw_text(center_x, py + 24.0, "PARADOXO", 20, _PERIL, anchor="center")
        reason = state.message.removeprefix("Paradoxo: ")
        renderer.draw_text(center_x, py + 54.0, reason[:1].upper() + reason[1:], 13, _TEXT, anchor="center")
        pads = self._pads()
        retry = "A" if pads else "ESPAÇO"
        rerecord = "RB" if pads else "TAB"
        renderer.draw_text(center_x, py + 80.0,
                           f"{retry}: tentar o presente de novo", 11, _TEXT_DIM, anchor="center")
        renderer.draw_text(center_x, py + 98.0,
                           f"{rerecord}: regravar a Lumen desde 1 s antes do ponto marcado",
                           11, _GOLD_DIM, anchor="center")
