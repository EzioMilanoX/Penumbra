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

import itertools

from penumbra import achievements
from penumbra.menu import (
    AchievementsScreen,
    MainMenuScreen,
    OptionsScreen,
    PauseScreen,
    TitleScreen,
)


def TitleScreenWithMode(duo: bool):
    """A tela de titulo no modo pedido. `duo` mora na propria tela (e a
    primeira decisao da sessao), entao nao da pra passa-lo no `draw`."""
    screen = TitleScreen()
    screen.duo = duo
    return screen

_CARD_SELECTED = (34, 32, 44, 255)


def _title_draw(duo: bool, pads: int):
    """A tela de titulo de um modo e de um numero de controles, pronta para
    desenhar -- com os dois valores presos na hora, e nao no fim do laco."""
    return lambda r: TitleScreenWithMode(duo).draw(r, 0, 0, 30, 0, 11, pads=pads)


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
        # Largura estimada pelo glifo monoespacado do backend (~0,6 em).
        width = len(text) * size * 0.6
        if anchor == "center":
            left = float(x) - width / 2.0
        elif anchor == "topright":
            left = float(x) - width
        else:
            left = float(x)
        self.texts.append({
            "text": text, "size": size, "anchor": anchor,
            "x": float(x), "top": top, "bottom": top + height,
            "left": left, "right": left + width,
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
        for choice, label in enumerate(("SOM", "EFEITOS", "MÚSICA", "TELA CHEIA", "APAGAR PROGRESSO")):
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
        every = {a.key for a in achievements.CATALOG}
        screens = (
            ("raiz", lambda r: MainMenuScreen().draw(r, 0, 30, 0, 10)),
            ("pausa", lambda r: PauseScreen().draw(r, "A Crosta", False)),
            ("opcoes", lambda r: OptionsScreen().draw(r, True, 0.7, False, 3, 30)),
            # A lista de conquistas CRESCE: cada uma nova empurra a ultima pra
            # baixo, e foi assim que a decima primeira encostou no rodape.
            ("conquistas vazia", lambda r: AchievementsScreen().draw(r, set(), 0, 30)),
            ("conquistas cheia", lambda r: AchievementsScreen().draw(r, every, 30, 30)),
            # A tela de titulo ENSINA os controles, e as linhas mudam com
            # quantos controles estao ligados -- quatro textos diferentes no
            # mesmo lugar, e o do controle e o mais longo dos quatro.
            *[(f"titulo duo={d} pads={n}", _title_draw(d, n))
              for d in (False, True) for n in (0, 1, 2)],
        )
        for name, draw in screens:
            renderer = _RecordingRenderer(width, height)
            draw(renderer)
            for entry in renderer.texts:
                assert 0.0 <= entry["top"] and entry["bottom"] <= height, (
                    f"{name}: {entry['text']!r} sai da janela na vertical"
                )
                # A horizontal faltava, e a falta tinha consequencia: as
                # linhas mais longas do jogo sao justamente as que LISTAM
                # controles, centradas, e uma lista de botoes de controle e
                # mais comprida que a de teclas. Sair pelos lados nao empurra
                # nada -- so corta, e headless ninguem ve.
                assert 0.0 <= entry["left"] and entry["right"] <= width, (
                    f"{name}: {entry['text']!r} sai da janela na horizontal"
                )
            for _left, top, _w, h, _ in renderer.rects:
                assert top >= 0.0 and top + h <= height, f"{name}: retangulo fora da janela"

    def test_nenhum_texto_cai_por_cima_de_outro(self):
        """O defeito que o teste de limites NAO pegava.

        A decima primeira conquista nao saiu da janela -- ela encostou no
        rodape, e os dois textos ficaram no mesmo lugar. Uma lista que cresce
        empurra a ultima linha pra cima da proxima coisa muito antes de
        empurra-la pra fora da tela, e e a colisao que se ve, nao o limite."""
        every = {a.key for a in achievements.CATALOG}
        screens = (
            ("raiz", lambda r: MainMenuScreen().draw(r, 0, 30, 0, 10)),
            ("pausa", lambda r: PauseScreen().draw(r, "A Crosta", False)),
            ("opcoes", lambda r: OptionsScreen().draw(r, True, 0.7, False, 3, 30)),
            ("conquistas cheia", lambda r: AchievementsScreen().draw(r, every, 30, 30)),
            # A tela de titulo ENSINA os controles, e as linhas mudam com
            # quantos controles estao ligados -- quatro textos diferentes no
            # mesmo lugar, e o do controle e o mais longo dos quatro.
            *[(f"titulo duo={d} pads={n}", _title_draw(d, n))
              for d in (False, True) for n in (0, 1, 2)],
        )
        for name, draw in screens:
            renderer = _RecordingRenderer()
            draw(renderer)
            for first, second in itertools.combinations(renderer.texts, 2):
                vertical = first["top"] < second["bottom"] and second["top"] < first["bottom"]
                horizontal = first["left"] < second["right"] and second["left"] < first["right"]
                assert not (vertical and horizontal), (
                    f"{name}: {first['text']!r} e {second['text']!r} se sobrepoem"
                )
