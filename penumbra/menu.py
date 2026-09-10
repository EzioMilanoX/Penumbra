"""
O menu de fases: uma grade de cards, cada um com a fase desenhada dentro.

A pre-visualizacao nao e enfeite. A lista de texto que existia antes obrigava
o jogador a decorar oito nomes pra saber onde estava a fase da crosta ou a do
farol -- e "O Mesmo Chao" nao diz nada sobre a forma dela. Um card com a fase
desenhada em miniatura responde na hora, e e por isso que jogos de fase
fechada quase sempre mostram o mapa em vez do nome.

A miniatura e o TERRENO REAL da fase, parseado pelo mesmo `Terrain` que o
jogo usa -- nao uma imagem exportada a mao que envelheceria no primeiro
ajuste de nivel. Cada celula vira um retangulo de poucos pixels, com as
mesmas cores da paleta do jogo, entao um terreno novo aparece no menu de
graca.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from ouroboros.interfaces.renderer import IRenderer

from penumbra.levels import LevelCatalog, LevelDefinition
from penumbra.terrain import (
    ROLE_BEACON,
    ROLE_COUNTER_ETHER,
    ROLE_CRUST,
    ROLE_DOOR,
    ROLE_ECLIPSE,
    ROLE_ETHER,
    ROLE_LAMP,
    ROLE_LUMEN_GOAL,
    ROLE_PLATE,
    ROLE_ROCK,
    ROLE_SHARD,
    ROLE_UMBRA_GOAL,
    ROLE_ZONE_LIGHT,
    ROLE_ZONE_SHADOW,
    Terrain,
)

_VOID = (8, 8, 14, 255)
_CARD = (20, 20, 28, 255)
_CARD_SELECTED = (34, 32, 44, 255)
_RULE = (58, 56, 72, 255)
_TEXT = (206, 208, 224, 255)
_TEXT_DIM = (128, 130, 148, 255)
_TEXT_FAINT = (100, 102, 120, 255)
_GOLD = (247, 214, 138, 255)
_GOLD_DIM = (110, 90, 48, 255)
_NUMBER_IDLE = (74, 74, 92, 255)

_PREVIEW_COLORS = {
    ROLE_ROCK: (86, 90, 106, 255),
    ROLE_ETHER: (150, 156, 190, 255),
    ROLE_COUNTER_ETHER: (120, 108, 160, 255),
    ROLE_CRUST: (150, 126, 104, 255),
    ROLE_ECLIPSE: (196, 158, 82, 255),
    ROLE_DOOR: (150, 122, 66, 255),
    ROLE_PLATE: (150, 122, 66, 255),
    ROLE_LAMP: (255, 250, 232, 255),
    ROLE_BEACON: (222, 214, 190, 255),
    ROLE_ZONE_LIGHT: (150, 122, 66, 255),
    ROLE_ZONE_SHADOW: (150, 122, 66, 255),
    ROLE_LUMEN_GOAL: (247, 214, 138, 255),
    ROLE_UMBRA_GOAL: (247, 214, 138, 255),
    ROLE_SHARD: (247, 214, 138, 255),
}
"""Cor de cada papel na miniatura. Deliberadamente mais CLARAS que no jogo:
numa miniatura de 3 px por celula o contraste real do jogo (rocha quase preta
sobre fundo quase preto) desapareceria, e a silhueta da fase e a unica coisa
que o card precisa entregar."""

_COLUMNS = 4
_CARD_WIDTH = 196.0
_CARD_HEIGHT = 130.0
_CARD_GAP_X = 20.0
_CARD_GAP_Y = 13.0
_GRID_TOP = 102.0
"""Doze fases em 4x3. As medidas sao apertadas de proposito: com cards de 148
de altura a terceira fileira invadia o rodape, e o texto de controles
aparecia por tras dos cards -- numa grade de tres fileiras a altura do card
nao e escolha estetica, e o que decide se a ultima fileira caibe."""


class LevelPreview:
    """
    Miniatura de uma fase, pre-computada uma vez.

    Guarda uma lista de `(coluna, linha, cor)` ja filtrada -- so as celulas
    que de fato desenham algo. Numa grade 28x17 isso costuma cortar mais da
    metade, e o menu desenha 8 cards por frame: sem o filtro seriam 3808
    retangulos por frame pra mostrar sobretudo vazio.
    """

    def __init__(self, level: LevelDefinition, terrain: Terrain) -> None:
        terrain.load_rows(level.rows)
        self.cols = terrain.cols
        self.rows = terrain.rows
        self.cells: List[Tuple[int, int, Tuple[int, int, int, int]]] = []
        role = terrain.role
        for row in range(terrain.rows):
            for col in range(terrain.cols):
                color = _PREVIEW_COLORS.get(int(role[row, col]))
                if color is not None:
                    self.cells.append((col, row, color))

    def draw(self, renderer: IRenderer, x: float, y: float, width: float, height: float) -> None:
        cell_w = width / self.cols
        cell_h = height / self.rows
        # Um pixel a mais em cada celula: sem isso o arredondamento do
        # backend abre fendas entre celulas vizinhas e a rocha continua
        # aparece tracejada.
        draw_w = max(1.0, cell_w + 1.0)
        draw_h = max(1.0, cell_h + 1.0)
        for col, row, color in self.cells:
            renderer.draw_ui_rect(x + col * cell_w, y + row * cell_h, draw_w, draw_h, color)


class LevelCardGrid:
    """
    Grade de cards navegavel com W/A/S/D.

    Cada card tem numerao, nome, a miniatura da fase e dois selos: um de
    fase vencida e um do fragmento. O fragmento fica dourado quando apanhado
    e um contorno vazio quando nao -- o mesmo dourado que no jogo significa
    "isto exige os dois", que e exatamente o que o desvio do fragmento
    costuma exigir.
    """

    def __init__(self, catalog: LevelCatalog, preview_terrain: Terrain) -> None:
        self._catalog = catalog
        self.previews = [
            LevelPreview(catalog.at(index), preview_terrain) for index in range(catalog.count)
        ]
        self.selected = 0

    @property
    def count(self) -> int:
        return self._catalog.count

    def move(self, columns: int, rows: int) -> None:
        """Anda na grade sem sair dela. Nao circula de proposito: numa grade
        2D o wrap salta o cursor pra um canto oposto e o jogador perde de
        vista onde estava."""
        column = self.selected % _COLUMNS
        row = self.selected // _COLUMNS
        last_row = (self.count - 1) // _COLUMNS

        column = max(0, min(_COLUMNS - 1, column + columns))
        row = max(0, min(last_row, row + rows))
        target = row * _COLUMNS + column
        if target < self.count:
            self.selected = target

    def card_rect(self, index: int) -> Tuple[float, float, float, float]:
        column = index % _COLUMNS
        row = index // _COLUMNS
        total_width = _COLUMNS * _CARD_WIDTH + (_COLUMNS - 1) * _CARD_GAP_X
        left = (self._viewport_width - total_width) / 2.0
        return (
            left + column * (_CARD_WIDTH + _CARD_GAP_X),
            _GRID_TOP + row * (_CARD_HEIGHT + _CARD_GAP_Y),
            _CARD_WIDTH,
            _CARD_HEIGHT,
        )

    def draw(
        self,
        renderer: IRenderer,
        completed: List[bool],
        shards: List[bool],
    ) -> None:
        self._viewport_width, _ = renderer.get_viewport_size()
        for index in range(self.count):
            self._draw_card(renderer, index, completed[index], shards[index])

    def _draw_card(self, renderer: IRenderer, index: int, done: bool, shard: bool) -> None:
        x, y, width, height = self.card_rect(index)
        selected = index == self.selected
        level = self._catalog.at(index)

        renderer.draw_ui_rect(x, y, width, height, _CARD_SELECTED if selected else _CARD)
        if selected:
            renderer.draw_ui_rect(x, y, width, 2.0, _GOLD)
            renderer.draw_ui_rect(x, y + height - 2.0, width, 2.0, _GOLD)

        # numerao: o jeito mais rapido de achar a fase 6 numa grade de oito
        renderer.draw_text(x + 13.0, y + 6.0, str(index + 1), 32, _GOLD if selected else _NUMBER_IDLE)

        # miniatura do terreno real da fase
        preview_x = x + 56.0
        preview_y = y + 12.0
        preview_w = width - 68.0
        preview_h = height - 52.0
        renderer.draw_ui_rect(preview_x - 2.0, preview_y - 2.0, preview_w + 4.0, preview_h + 4.0, _VOID)
        self.previews[index].draw(renderer, preview_x, preview_y, preview_w, preview_h)

        renderer.draw_text(x + 13.0, y + height - 34.0, level.name, 14, _TEXT if selected else _TEXT_DIM)

        # selos: fase vencida e fragmento
        seal_y = y + height - 16.0
        renderer.draw_text(x + 13.0, seal_y, "vencida" if done else "aberta", 11,
                           _GOLD if done else _TEXT_FAINT)
        renderer.draw_text(x + width - 13.0, seal_y,
                           "fragmento" if shard else "fragmento?", 11,
                           _GOLD if shard else _GOLD_DIM, anchor="topright")


class MenuChrome:
    """Titulo, rodape e o seletor de modo -- tudo que nao e card."""

    def __init__(self) -> None:
        self.message = ""

    def draw(self, renderer: IRenderer, duo: bool, collected: int, total: int) -> None:
        width, height = renderer.get_viewport_size()
        renderer.draw_ui_rect(0.0, 0.0, width, height, _VOID)
        center = width / 2.0

        renderer.draw_text(center, 22.0, "PENUMBRA", 34, _TEXT, anchor="center")
        renderer.draw_text(center, 62.0, "Luz e Sombra: Dualidade", 13, _GOLD, anchor="center")

        mode = "DOIS JOGADORES" if duo else "UM JOGADOR"
        renderer.draw_text(24.0, 30.0, f"modo: {mode}", 13, _GOLD if duo else _TEXT_DIM)
        renderer.draw_text(24.0, 50.0, "TAB troca de modo", 11, _TEXT_FAINT)
        renderer.draw_text(width - 24.0, 30.0, f"fragmentos {collected}/{total}", 13, _GOLD,
                           anchor="topright")

        if self.message:
            renderer.draw_text(center, 88.0, self.message, 13, _GOLD, anchor="center")

        footer_y = height - 46.0
        renderer.draw_ui_rect(0.0, footer_y - 12.0, width, 1.0, _RULE)
        renderer.draw_text(center, footer_y, "W/A/S/D escolher      ESPACO jogar      ESC sair",
                           12, _TEXT_DIM, anchor="center")
        controls = (
            "J1: A/D  ESPACO  J          J2: setas  cima  baixo"
            if duo
            else "A/D mover   ESPACO pular   J habilidade   TAB trocar de ser"
        )
        renderer.draw_text(center, footer_y + 20.0, controls, 11, _TEXT_FAINT, anchor="center")
