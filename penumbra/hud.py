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

from penumbra.state import (
    DualityState,
    LevelRuntime,
    LUMEN,
    OUTCOME_COMPLETE,
    OUTCOME_PLAYING,
    UMBRA,
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
    ) -> None:
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
        self._draw_character_meters(renderer)
        self._draw_footer(renderer)
        if self._state.outcome != OUTCOME_PLAYING:
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

        renderer.draw_text(
            14.0, top + _LINE_1,
            f"{state.level_index + 1}/{self._runtime.count}  {level.name}",
            14, _TEXT,
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
        controls = (
            "J1: A/D  ESPAÇO  S       J2: setas  CIMA  BAIXO       R reiniciar   ESC sair"
            if state.duo else
            "A/D mover   ESPAÇO pular   S habilidade   TAB trocar   R reiniciar   ESC sair"
        )
        renderer.draw_text(14.0, top + _LINE_3, controls, 11, _TEXT_FAINT)

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
        renderer.draw_text(
            center_x, y + 86.0,
            "ESPAÇO para continuar" if won else "ESPAÇO para tentar de novo",
            11, _TEXT_DIM, anchor="center",
        )
