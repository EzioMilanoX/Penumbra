"""
O controle, testado sem controle nenhum.

Nao ha joystick nesta maquina nem no CI, e mesmo que houvesse ninguem
apertaria um botao no meio de um `pytest`. Entao o que entra aqui e a parte
que de fato pode estar errada: o **mapeamento** (qual botao vira qual acao,
qual controle vira qual jogador), as **bordas** (uma por frame, e so depois
do frame terminar) e a **histerese** do analogico. A camada que fala pygame e
um punhado de `try/except` em volta de tres chamadas, e ela e justamente a
parte que nao da pra afirmar nada sem hardware.

Os `_FakePads` sao um controle de mentira porque o outro lado -- deixar o
pygame decidir -- testaria o pygame, e nao isto aqui.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from penumbra.gamepad import (GamepadInput, _ENGAGE, _RELEASE,
                              load_gamepad_bindings)
from penumbra.hud import _control_line

_DATA = Path(__file__).resolve().parents[1] / "data" / "input_bindings"


class _FakePads:
    """Um ou dois controles cujos botoes e eixos o teste escreve a mao."""

    def __init__(self, pads: int = 1) -> None:
        self.pads = pads
        self.buttons = {}
        self.axes = {}

    def refresh(self) -> None:
        pass

    def count(self) -> int:
        return self.pads

    def pressed(self, pad, button) -> bool:
        return bool(self.buttons.get((pad, button)))

    def axis(self, pad, axis) -> float:
        return float(self.axes.get((pad, axis), 0.0))


class _FakeKeyboard:
    """O provider de dentro. Sempre solto, salvo o que o teste segurar."""

    def __init__(self) -> None:
        self.held = set()
        self.quit = False
        self.polls = 0
        self.rumbles = []

    def load_bindings(self, path): self.loaded = path
    def poll(self): self.polls += 1
    def is_action_pressed(self, name): return name in self.held
    def is_action_held(self, name): return name in self.held
    def is_action_released(self, name): return False
    def get_axis(self, name): return 0.0
    def get_cursor_position(self): return (0.0, 0.0)
    def wants_quit(self): return self.quit
    def set_rumble(self, low, high, seconds): self.rumbles.append((low, high, seconds))


class _Recorder:
    """So o bastante pra saber o que foi escrito na tela."""

    def __init__(self) -> None:
        self.texts = []

    def get_viewport_size(self): return (896, 616)
    def draw_ui_rect(self, *a, **k): pass
    def draw_text(self, x, y, text, size, rgba, anchor="topleft"): self.texts.append(text)
    def wrote(self, needle): return any(needle in t for t in self.texts)


def _build(pads, **kwargs):
    bindings = load_gamepad_bindings(_DATA / "penumbra_gamepad.json")
    keyboard = _FakeKeyboard()
    return keyboard, GamepadInput(keyboard, bindings, pads=pads, **kwargs)


class TestTheBindingsFileIsComplete:
    def test_as_duas_listas_de_acoes_sao_a_mesma(self):
        """Uma acao que existe no teclado e nao no controle nao levanta erro
        nenhum: ela simplesmente nao funciona no controle, e o jogador
        conclui que o controle esta quebrado. E o mesmo tipo de falha da
        chave de comentario que derrubou o jogo na abertura -- um arquivo de
        bindings errado nao avisa, so age errado."""
        teclado = json.loads((_DATA / "penumbra_keyboard.json").read_text(encoding="utf-8"))
        controle = json.loads((_DATA / "penumbra_gamepad.json").read_text(encoding="utf-8"))
        assert set(teclado) == set(controle)

    def test_todo_codigo_do_arquivo_e_reconhecido(self):
        """Um `PAD_LT` que ninguem resolve e descartado em silencio pelo
        construtor -- o jogo abre e aquela acao nunca chega."""
        from penumbra.gamepad import _BUTTONS, _DIRECTIONS

        bindings = load_gamepad_bindings(_DATA / "penumbra_gamepad.json")
        for action, code in bindings.items():
            assert code in _BUTTONS or code in _DIRECTIONS, f"{action}: {code} nao existe"

    def test_as_acoes_do_jogador_um_e_dois_nao_dividem_controle(self):
        pads = _FakePads(pads=2)
        _, game_input = _build(pads)

        pads.buttons[(0, 0)] = True          # A no controle do jogador 1
        assert game_input.is_action_held("jump")
        assert not game_input.is_action_held("p2_jump")

        game_input.end_frame()
        pads.buttons.clear()
        pads.buttons[(1, 0)] = True          # A no controle do jogador 2
        assert game_input.is_action_held("p2_jump")
        assert not game_input.is_action_held("jump")


class TestTheKeyboardNeverLoses:
    def test_o_teclado_continua_valendo_com_controle_ligado(self):
        """O controle e um OU, nao um substituto: no duo um jogador pode
        estar no controle e o outro nas setas, na mesma partida."""
        keyboard, game_input = _build(_FakePads(pads=1))
        keyboard.held.add("jump")
        assert game_input.is_action_held("jump")

    def test_sem_controle_nenhum_nada_muda_e_nada_levanta(self):
        keyboard, game_input = _build(_FakePads(pads=0))
        assert not game_input.is_action_held("jump")
        assert not game_input.is_action_pressed("move_left")
        keyboard.held.add("move_left")
        assert game_input.is_action_held("move_left")

    def test_o_que_nao_e_acao_passa_direto(self):
        keyboard, game_input = _build(_FakePads(pads=1))
        keyboard.quit = True
        assert game_input.wants_quit()
        game_input.poll()
        assert keyboard.polls == 1
        game_input.set_rumble(0.5, 0.5, 0.2)
        assert keyboard.rumbles == [(0.5, 0.5, 0.2)]


class TestEdgesHappenOncePerFrame:
    def test_segurar_o_botao_produz_UMA_borda(self):
        """Os menus inteiros andam por `is_action_pressed`. Sem a borda ser
        uma so, descer um item viraria descer a lista toda."""
        pads = _FakePads()
        _, game_input = _build(pads)
        pads.buttons[(0, 0)] = True

        assert game_input.is_action_pressed("jump")
        assert game_input.is_action_pressed("jump"), "a mesma consulta, no mesmo frame"

        game_input.end_frame()
        assert not game_input.is_action_pressed("jump"), "o botao nao foi solto e nem reapertado"
        assert game_input.is_action_held("jump")

    def test_soltar_produz_a_borda_de_soltar(self):
        pads = _FakePads()
        _, game_input = _build(pads)
        pads.buttons[(0, 0)] = True
        game_input.is_action_pressed("jump")

        game_input.end_frame()
        pads.buttons[(0, 0)] = False
        assert game_input.is_action_released("jump")

        game_input.end_frame()
        assert not game_input.is_action_released("jump")

    def test_arrancar_o_controle_nao_deixa_a_borda_presa(self):
        """O defeito que eu escrevi e nao vi: com o controle desconectado, o
        frame seguinte via o estado vazio, nao mexia em nada, e a borda de
        soltar se repetia ate o fim da partida -- um `restart` disparando
        sozinho a cada frame."""
        pads = _FakePads()
        _, game_input = _build(pads)
        pads.buttons[(0, 6)] = True
        game_input.is_action_held("restart")

        game_input.end_frame()
        pads.pads = 0                                   # arrancado
        assert game_input.is_action_released("restart"), "um frame, e so"

        for _ in range(3):
            game_input.end_frame()
            assert not game_input.is_action_released("restart")

    def test_nada_e_amostrado_ate_o_frame_terminar(self):
        """A amostragem se prende ao frame por `end_frame`, e nao por um
        relogio: apertar e soltar entre dois frames nao pode virar duas
        bordas dentro de um."""
        pads = _FakePads()
        _, game_input = _build(pads)
        assert not game_input.is_action_pressed("jump")

        pads.buttons[(0, 0)] = True
        assert not game_input.is_action_pressed("jump"), "o frame ainda e o mesmo"

        game_input.end_frame()
        assert game_input.is_action_pressed("jump")


class TestTheStickDoesNotChatter:
    def test_o_analogico_engata_e_solta_em_soleiras_diferentes(self):
        pads = _FakePads()
        _, game_input = _build(pads)

        pads.axes[(0, 0)] = 0.40                        # entre as duas
        assert not game_input.is_action_held("move_right"), "0.40 nao engata"

        game_input.end_frame()
        pads.axes[(0, 0)] = 0.70
        assert game_input.is_action_held("move_right")

        game_input.end_frame()
        pads.axes[(0, 0)] = 0.40                        # a mesma leitura de antes
        assert game_input.is_action_held("move_right"), "engatado, 0.40 ainda segura"

        game_input.end_frame()
        pads.axes[(0, 0)] = 0.20
        assert not game_input.is_action_held("move_right")

    def test_um_polegar_parado_na_fronteira_nao_manda_bordas(self):
        """O motivo de a histerese existir. Um analogico em repouso treme
        perto da soleira; com uma soleira so, o menu atravessaria a lista
        sozinho. Aqui o tremor inteiro cabe entre 0.30 e 0.55."""
        pads = _FakePads()
        _, game_input = _build(pads)
        bordas = 0
        for i in range(40):
            pads.axes[(0, 1)] = 0.42 + (0.04 if i % 2 else -0.04)
            if game_input.is_action_pressed("menu_down"):
                bordas += 1
            game_input.end_frame()
        assert bordas == 0

    def test_as_duas_soleiras_nao_se_cruzam(self):
        assert _RELEASE < _ENGAGE, "sem vao nao ha histerese"

    def test_cima_no_analogico_e_cima_no_menu(self):
        """O analogico reporta CIMA como negativo. Com o sinal trocado, o
        menu andaria ao contrario -- e nada no codigo diria qual dos dois
        esta errado."""
        pads = _FakePads()
        _, game_input = _build(pads)
        pads.axes[(0, 1)] = -0.9
        assert game_input.is_action_held("menu_up")
        assert not game_input.is_action_held("menu_down")


class TestTheCountReachesTheScreens:
    """Estado escrito e nunca lido, pela terceira vez neste projeto.

    A contagem existia no provider, as telas sabiam desenha-la, e no meio o
    `PenumbraFlow` nao guardava o provider -- `flow.pads` levantava
    `AttributeError` no primeiro frame da tela de titulo. Nenhum dos 271
    testes de entao passava por ali: todos desenhavam as telas DIRETO, com o
    numero na mao. Por isso estes dois desenham pelo caminho de verdade."""

    @pytest.fixture
    def flow(self, simulation, input_provider, tmp_path):
        from penumbra.scenes import PenumbraFlow
        from penumbra.terrain import Terrain
        from penumbra.progress import Progress
        from tests.conftest import CELL_SIZE, GRID_COLS, GRID_ROWS
        from tests.test_shipped_levels import _FakeGameLoop

        self.pads = _FakePads(pads=0)
        bindings = load_gamepad_bindings(_DATA / "penumbra_gamepad.json")
        game_input = GamepadInput(input_provider, bindings, pads=self.pads)
        return PenumbraFlow(
            _FakeGameLoop(), simulation.runtime, simulation.state,
            simulation.catalog, simulation.tuning, game_input,
            preview_terrain=Terrain(GRID_COLS, GRID_ROWS, CELL_SIZE),
            progress=Progress(simulation.catalog.count, tmp_path / "progress.json"),
        )

    def test_a_tela_de_titulo_desenha_sem_levantar_e_muda_de_texto(self, flow, simulation):
        renderer = _Recorder()
        flow.show_title()
        flow._game_loop.current_scene.render(simulation.world, renderer)
        assert renderer.wrote("ESPAÇO pular"), "sem controle, teclas"

        self.pads.pads = 1
        renderer = _Recorder()
        flow._game_loop.current_scene.render(simulation.world, renderer)
        assert renderer.wrote("A pular"), "com controle, botoes"
        assert not renderer.wrote("ESPAÇO pular")
        # O card do modo solo ENSINA a tecla que alterna entre os dois seres,
        # que e a mecanica central daquele modo. Com o controle na mao, "TAB"
        # ali e a promessa mais cara da tela.
        assert not renderer.wrote("TAB alterna")
        assert renderer.wrote("RB alterna")

    def test_o_provider_nulo_nao_finge_ter_controle(self, simulation, input_provider, tmp_path):
        """Todo teste headless usa o provider nulo, que nao tem `pad_count`.
        Levantar ali derrubaria a suite; mentir um numero faria as telas
        prometerem botoes que nao existem."""
        from penumbra.scenes import PenumbraFlow
        from penumbra.terrain import Terrain
        from penumbra.progress import Progress
        from tests.conftest import CELL_SIZE, GRID_COLS, GRID_ROWS
        from tests.test_shipped_levels import _FakeGameLoop

        flow = PenumbraFlow(
            _FakeGameLoop(), simulation.runtime, simulation.state,
            simulation.catalog, simulation.tuning, input_provider,
            preview_terrain=Terrain(GRID_COLS, GRID_ROWS, CELL_SIZE),
            progress=Progress(simulation.catalog.count, tmp_path / "progress.json"),
        )
        assert flow.pads == 0


class TestTheFooterTellsTheTruth:
    """Uma dica de controle que MENTE e pior que dica nenhuma: quem esta com o
    controle na mao lendo "ESPACO pular" conclui que o controle nao funciona."""

    def test_sem_controle_o_rodape_fala_de_teclas(self):
        assert "A/D" in _control_line(duo=False, pads=0)
        assert "ESPAÇO" in _control_line(duo=False, pads=0)

    def test_com_controle_o_rodape_fala_de_botoes(self):
        linha = _control_line(duo=False, pads=1)
        assert "A pular" in linha and "X habilidade" in linha
        assert "ESPAÇO" not in linha

    def test_com_um_controle_so_no_duo_cada_jogador_le_o_seu(self):
        """O arranjo de um sofa com um controle: o jogador 1 no controle, o 2
        nas setas. Dizer "controle" para os dois mandaria o jogador 2 procurar
        um controle que nao existe."""
        linha = _control_line(duo=True, pads=1)
        assert "J1: controle" in linha
        assert "setas" in linha

    def test_com_dois_controles_o_duo_nao_fala_mais_de_teclado(self):
        linha = _control_line(duo=True, pads=2)
        assert "setas" not in linha and "A/D" not in linha
        assert linha.count("controle") == 2

    def test_o_rodape_cabe_na_janela(self):
        """A linha e desenhada em x=14 com corpo 11 numa janela de 896. O
        rodape ja teve dois textos somando mais que a largura da tela."""
        for duo in (False, True):
            for pads in (0, 1, 2):
                largura = 14.0 + len(_control_line(duo, pads)) * 11 * 0.6
                assert largura <= 896, f"duo={duo} pads={pads}: {largura:.0f}px"
