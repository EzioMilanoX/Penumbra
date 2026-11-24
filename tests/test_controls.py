"""
O que o jogo PROMETE sobre os controles, e para quem.

O adaptador de controle morava aqui, e nao devia: `PygameInputProvider` agora
resolve `PAD_*` nos proprios bindings, entao mapeamento, bordas e histerese
sao testados na engine, contra o backend de verdade. Este arquivo ficou com a
parte que so existe em Penumbra -- **o que as telas dizem**.

Uma dica de controle que MENTE e pior que dica nenhuma: quem esta com o
controle na mao lendo "ESPACO pular" conclui que o controle nao funciona, e
ele funciona. E no duo cada jogador le a sua metade, porque com UM controle o
jogador 1 esta no controle e o 2 nas setas -- que e o arranjo real de um sofa
com um controle.
"""
from __future__ import annotations

import json
from pathlib import Path

from penumbra.hud import _control_line

_BINDINGS = (Path(__file__).resolve().parents[1]
             / "data" / "input_bindings" / "penumbra_keyboard.json")


class _Recorder:
    """So o bastante pra saber o que foi escrito na tela."""

    def __init__(self) -> None:
        self.texts = []

    def get_viewport_size(self): return (896, 616)
    def draw_ui_rect(self, *a, **k): pass
    def draw_text(self, x, y, text, size, rgba, anchor="topleft"): self.texts.append(text)
    def wrote(self, needle): return any(needle in t for t in self.texts)


class _PadCounter:
    """Um provider que so sabe contar controles -- que e tudo que as telas
    perguntam."""

    def __init__(self, pads: int = 0) -> None:
        self.pads = pads

    def connected_pads(self): return self.pads
    def is_action_pressed(self, name): return False
    def is_action_held(self, name): return False
    def is_action_released(self, name): return False


class TestEveryActionWorksOnBothArrangements:
    def test_toda_acao_tem_tecla_E_botao(self):
        """A lista dupla e o que faz teclado e controle conviverem na mesma
        partida. Uma acao com so um dos dois nao levanta erro nenhum: ela
        simplesmente nao funciona num dos arranjos, e quem joga conclui que o
        arranjo inteiro esta quebrado."""
        bindings = json.loads(_BINDINGS.read_text(encoding="utf-8"))
        for action, codes in bindings.items():
            assert isinstance(codes, list), f"{action}: precisa de tecla e botao"
            prefixes = {code.split("_")[0].rstrip("0123456789") for code in codes}
            assert "KEY" in prefixes, f"{action} nao tem tecla"
            assert "PAD" in prefixes, f"{action} nao tem botao"

    def test_o_jogador_dois_usa_o_SEGUNDO_controle(self):
        """Sem o digito, os dois seres responderiam ao mesmo controle e o duo
        viraria um jogador comandando os dois."""
        bindings = json.loads(_BINDINGS.read_text(encoding="utf-8"))
        for action, codes in bindings.items():
            pad = next(c for c in codes if c.startswith("PAD"))
            if action.startswith("p2_"):
                assert pad.startswith("PAD2_"), f"{action} -> {pad}"
            else:
                assert not pad.startswith("PAD2_"), f"{action} -> {pad}"


class TestTheCountReachesTheScreens:
    """Estado escrito e nunca lido, pela terceira vez neste projeto.

    A contagem existia no provider, as telas sabiam desenha-la, e no meio o
    `PenumbraFlow` nao guardava o provider -- a tela de titulo levantava
    `AttributeError` no primeiro frame, com 271 testes verdes. Nenhum deles
    passava por ali: todos desenhavam as telas DIRETO, com o numero na mao.
    Por isso estes desenham pelo caminho de verdade."""

    def _flow(self, simulation, tmp_path, input_provider):
        from penumbra.progress import Progress
        from penumbra.scenes import PenumbraFlow
        from penumbra.terrain import Terrain
        from tests.conftest import CELL_SIZE, GRID_COLS, GRID_ROWS
        from tests.test_shipped_levels import _FakeGameLoop

        return PenumbraFlow(
            _FakeGameLoop(), simulation.runtime, simulation.state,
            simulation.catalog, simulation.tuning, input_provider,
            preview_terrain=Terrain(GRID_COLS, GRID_ROWS, CELL_SIZE),
            progress=Progress(simulation.catalog.count, tmp_path / "progress.json"),
        )

    def test_a_tela_de_titulo_desenha_sem_levantar_e_muda_de_texto(
            self, simulation, tmp_path):
        pads = _PadCounter(0)
        flow = self._flow(simulation, tmp_path, pads)
        flow.show_title()

        renderer = _Recorder()
        flow._game_loop.current_scene.render(simulation.world, renderer)
        assert renderer.wrote("ESPAÇO pular"), "sem controle, teclas"

        pads.pads = 1
        renderer = _Recorder()
        flow._game_loop.current_scene.render(simulation.world, renderer)
        assert renderer.wrote("A pular"), "com controle, botoes"
        assert not renderer.wrote("ESPAÇO pular")
        # O card do modo solo ENSINA a tecla que alterna entre os dois seres,
        # que e a mecanica central daquele modo. Com o controle na mao, "TAB"
        # ali e a promessa mais cara da tela.
        assert not renderer.wrote("TAB alterna")
        assert renderer.wrote("RB alterna")

    def test_o_provider_nulo_responde_zero_e_nao_levanta(
            self, simulation, tmp_path, input_provider):
        """Todo teste headless usa o provider nulo. `connected_pads` responde
        0 por default no proprio contrato, entao ele nao precisa saber de
        nada -- e as telas voltam a falar de teclas."""
        assert self._flow(simulation, tmp_path, input_provider).pads == 0


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
