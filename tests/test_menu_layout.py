"""
O realce tem de ficar EM CIMA do texto que ele realca.

`IRenderer.draw_text` aceita `anchor`, e a diferenca entre os valores nao e
cosmetica: com `"topleft"` o `y` e o TOPO do texto; com `"center"`, o CENTRO
vertical. Escrever a faixa de realce a partir de `y` como se fosse topo, e o
texto com `anchor="center"`, joga a faixa inteira pra baixo da palavra -- foi
exatamente o que aconteceu no menu principal e na pausa, e nenhum dos 207
testes viu, porque nenhum deles olhava pixel nenhum.

Estes testes olham. Um renderer de mentira grava as chamadas de desenho, e a
verificacao e a unica que importa: o texto realcado cabe dentro do retangulo
que o realca.
"""
from __future__ import annotations

import pytest

from penumbra.menu import MainMenuScreen, OptionsScreen, PauseScreen

_CARD_SELECTED = (34, 32, 44, 255)


class _RecordingRenderer:
    """Grava `draw_ui_rect` e `draw_text` em vez de desenhar.

    A altura do texto e estimada pelo tamanho da fonte. E aproximacao, mas de
    sobra pro que se quer pegar: o defeito que motivou este arquivo punha a
    faixa inteira FORA do texto, nao alguns pixels fora."""

    def __init__(self, width: int = 896, height: int = 616) -> None:
        self.size = (width, height)
        self.rects = []
        self.texts = []

    def get_viewport_size(self):
        return self.size

    def draw_ui_rect(self, x, y, w, h, rgba):
        self.rects.append((float(x), float(y), float(w), float(h), tuple(rgba)))

    def draw_text(self, x, y, text, size, rgba, anchor="topleft"):
        height = float(size)
        if anchor == "center":
            top = float(y) - height / 2.0
        else:
            top = float(y)
        self.texts.append({
            "text": text, "size": size, "anchor": anchor,
            "x": float(x), "top": top, "bottom": top + height,
            "middle": top + height / 2.0,
        })

    # ------------------------------------------------------------------

    def find_text(self, needle):
        for entry in self.texts:
            if entry["text"] == needle:
                return entry
        raise AssertionError(f"texto {needle!r} nao foi desenhado")

    def highlight_rects(self):
        """Os retangulos de fundo de item selecionado."""
        return [r for r in self.rects if r[4] == _CARD_SELECTED]


def _assert_inside(entry, rect, label):
    left, top, width, height, _ = rect
    assert top <= entry["top"] and entry["bottom"] <= top + height, (
        f"{label}: o texto ocupa {entry['top']:.0f}..{entry['bottom']:.0f} e a faixa "
        f"{top:.0f}..{top + height:.0f} -- o realce nao cobre a palavra"
    )
    assert left <= entry["x"] <= left + width, f"{label}: fora da faixa na horizontal"


class TestMainMenuHighlight:
    def test_a_faixa_cobre_o_item_escolhido(self):
        """O defeito exato que apareceu na tela: a faixa desenhada abaixo da
        palavra, porque `anchor="center"` ancora o centro e nao o topo."""
        for choice, label in enumerate(("JOGAR", "CONQUISTAS", "OPÇÕES", "SAIR")):
            screen = MainMenuScreen()
            screen.selected = choice
            renderer = _RecordingRenderer()
            screen.draw(renderer, completed=0, total=30, unlocked=0, achievement_total=10)

            highlights = renderer.highlight_rects()
            assert len(highlights) == 1, f"{label}: um item selecionado, uma faixa"
            _assert_inside(renderer.find_text(label), highlights[0], label)

    def test_so_o_item_escolhido_ganha_faixa(self):
        renderer = _RecordingRenderer()
        MainMenuScreen().draw(renderer, completed=0, total=30, unlocked=0, achievement_total=10)
        assert len(renderer.highlight_rects()) == 1


class TestPauseHighlight:
    def test_a_faixa_cobre_a_opcao_escolhida(self):
        for choice, label in enumerate(("CONTINUAR", "REINICIAR A FASE", "VOLTAR AO MENU")):
            screen = PauseScreen()
            screen.selected = choice
            renderer = _RecordingRenderer()
            screen.draw(renderer, level_name="A Crosta", duo=False)

            highlights = renderer.highlight_rects()
            assert len(highlights) == 1, label
            _assert_inside(renderer.find_text(label), highlights[0], label)


class TestOptionsHighlight:
    def test_a_faixa_cobre_a_linha_escolhida(self):
        """Aqui o texto usa `topleft`, e por isso a linha ja estava certa --
        o teste existe pra que ela continue certa se alguem uniformizar as
        ancoras sem olhar a faixa."""
        for choice, label in enumerate(("SOM", "VOLUME", "TELA CHEIA", "APAGAR PROGRESSO")):
            screen = OptionsScreen()
            screen.selected = choice
            renderer = _RecordingRenderer()
            screen.draw(renderer, sound_on=True, volume=0.7, fullscreen=False,
                        completed=3, total=30)

            highlights = renderer.highlight_rects()
            assert len(highlights) == 1, label
            _assert_inside(renderer.find_text(label), highlights[0], label)


class TestNothingLeavesTheWindow:
    def test_nenhuma_tela_desenha_fora_da_janela(self):
        """Uma linha a mais numa lista empurra a ultima pra fora da tela, e
        headless ninguem ve. Vale pras tres telas novas."""
        width, height = 896, 616
        screens = (
            ("raiz", lambda r: MainMenuScreen().draw(r, 0, 30, 0, 10)),
            ("pausa", lambda r: PauseScreen().draw(r, "A Crosta", False)),
            ("opcoes", lambda r: OptionsScreen().draw(r, True, 0.7, False, 3, 30)),
        )
        for name, draw in screens:
            renderer = _RecordingRenderer(width, height)
            draw(renderer)
            for entry in renderer.texts:
                assert 0.0 <= entry["top"] and entry["bottom"] <= height, (
                    f"{name}: {entry['text']!r} sai da janela na vertical"
                )
            for left, top, w, h, _ in renderer.rects:
                assert top >= 0.0 and top + h <= height, f"{name}: retangulo fora da janela"
