"""
Estado escrito que ninguem le.

Duas vezes seguidas o mesmo defeito apareceu neste projeto: um campo gravado
com cuidado, salvo em disco, e nunca mostrado. `flow.unlocked` (as conquistas
destravavam em silencio) e depois `ending_choice` -- o jogo faz uma pergunta
grave na ultima tela, guarda a resposta, e nunca mais a menciona. Nenhum dos
dois produz erro; os dois transformam uma decisao em formalidade.

Nao da pra testar "aparece na tela" sem desenhar, entao estes testes desenham
-- num renderer de mentira, e conferem que o texto existe. Uma tela que
esqueceu de mostrar algo e um teste que falha, nao uma inspecao visual que
alguem talvez faca.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from penumbra.menu import MainMenuScreen
from penumbra.state import UMBRA

from tests.conftest import advance, load_custom, place

_BINDINGS = Path(__file__).resolve().parents[1] / "data" / "input_bindings" / "penumbra_keyboard.json"


class _TextRecorder:
    """So o suficiente pra saber o que foi escrito na tela."""

    def __init__(self) -> None:
        self.texts = []

    def get_viewport_size(self):
        return (896, 616)

    def draw_ui_rect(self, *args, **kwargs):
        pass

    def draw_text(self, x, y, text, size, rgba, anchor="topleft"):
        self.texts.append(text)

    def wrote(self, needle: str) -> bool:
        return any(needle in text for text in self.texts)


class TestTheEndingChoiceIsRemembered:
    def test_a_raiz_diz_o_que_foi_escolhido(self):
        """O jogo perguntava se os dois queriam se fundir, gravava a resposta
        e nunca mais a mencionava."""
        for choice, expected in (("fundidos", "se fundiram"), ("separados", "seguiram dois")):
            renderer = _TextRecorder()
            MainMenuScreen().draw(renderer, completed=30, total=30,
                                  unlocked=11, achievement_total=11, ending=choice)
            assert renderer.wrote(expected), f"a raiz nao diz nada sobre {choice!r}"

    def test_sem_ter_chegado_ao_fim_a_raiz_nao_inventa(self):
        """Quem nunca terminou nao pode ver uma escolha que nao fez."""
        renderer = _TextRecorder()
        MainMenuScreen().draw(renderer, completed=0, total=30,
                              unlocked=0, achievement_total=11, ending="")
        assert not renderer.wrote("fundiram")
        assert not renderer.wrote("seguiram")


class TestPlayerTwoCanRestart:
    def test_o_jogador_dois_tem_tecla_de_reinicio(self):
        bindings = json.loads(_BINDINGS.read_text(encoding="utf-8"))
        assert "p2_restart" in bindings
        assert bindings["p2_restart"] != bindings["restart"], (
            "duas acoes, duas teclas -- senao o jogador 2 depende do teclado do 1"
        )

    def test_no_duo_a_tecla_do_jogador_dois_reinicia(self, simulation, input_provider):
        """Com `restart` so no R, quem se encurralava no duo dependia do
        outro -- e no duo o normal e que os dois se encurralem juntos."""
        load_custom(simulation, {
            12: "..A.....B..........X......Y.",
            13: "############################",
        })
        state = simulation.state
        state.duo = True
        input_provider.set_action_held("p2_restart", True)
        advance(simulation, input_provider, frames=2)

        assert state.restart_requested

    def test_no_solo_a_tecla_do_jogador_dois_nao_faz_nada(self, simulation, input_provider):
        """As acoes `p2_*` so existem quando ha um jogador 2. No solo, END e
        uma tecla como outra qualquer."""
        load_custom(simulation, {
            12: "..A.....B..........X......Y.",
            13: "############################",
        })
        state = simulation.state
        state.duo = False
        input_provider.set_action_held("p2_restart", True)
        advance(simulation, input_provider, frames=2)

        assert not state.restart_requested


class TestNoDeadPublicCode:
    def test_o_sistema_do_segredo_nao_expoe_o_que_ninguem_le(self):
        """`EchoSystem.progress` existia e a apresentacao calculava o proprio
        valor a partir do estado. Codigo publico que ninguem chama e uma
        promessa que ninguem cumpre."""
        from penumbra.systems.echo_system import EchoSystem

        assert not hasattr(EchoSystem, "progress")

    def test_a_reachability_nao_tem_ajudante_orfao(self):
        from penumbra import reachability

        assert not hasattr(reachability, "standing_cell_above")
