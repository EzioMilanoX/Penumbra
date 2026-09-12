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
    ROLE_ALTAR,
    ROLE_WANDER,
    ROLE_VEIL,
    ROLE_GLASS,
    ROLE_SOURCE,
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
    ROLE_ALTAR: (170, 158, 200, 255),
    ROLE_WANDER: (128, 122, 158, 255),
    ROLE_VEIL: (74, 66, 106, 255),
    ROLE_GLASS: (166, 188, 216, 255),
    ROLE_SOURCE: (255, 246, 226, 255),
}
"""Cor de cada papel na miniatura. Deliberadamente mais CLARAS que no jogo:
numa miniatura de 3 px por celula o contraste real do jogo (rocha quase preta
sobre fundo quase preto) desapareceria, e a silhueta da fase e a unica coisa
que o card precisa entregar."""

_COLUMNS = 3
_ROWS = 2
_PER_ACT = _COLUMNS * _ROWS
_CARD_WIDTH = 250.0
_CARD_HEIGHT = 180.0
_CARD_GAP_X = 22.0
_CARD_GAP_Y = 18.0
_GRID_TOP = 136.0
_ACT_TAB_Y = 104.0
"""Seis cards por ato, em 3x2. Dezoito fases numa grade so nao cabem na
janela, e encolher o card ate caberem transformaria a miniatura -- que e a
unica coisa que faz o card valer mais que uma lista de nomes -- em manchinha.

Paginar tambem diz algo verdadeiro sobre o jogo: as mecanicas chegam em tres
levas, e cada ato e uma delas. O ato e uma pagina, nao uma tranca: nada e
bloqueado, e a seta anda de ato como anda de card."""

_ACTS = (
    ("ATO I", "ALTERNANCIA", "andar, acender, apagar"),
    ("ATO II", "CONSEQUENCIA", "o que nao volta atras"),
    ("ATO III", "RENUNCIA", "o que se deixa pra tras"),
    ("ATO IV", "A FONTE", "a luz de um serve ao outro"),
)


class LevelPreview:
    """
    Miniatura de uma fase, pre-computada uma vez.

    Guarda uma lista de `(coluna, linha, cor)` ja filtrada -- so as celulas
    que de fato desenham algo. Numa grade 28x17 isso costuma cortar mais da
    metade, e o menu desenha seis cards por frame: sem o filtro seriam 2856
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
    Grade de cards navegavel com W/A/S/D, paginada em atos.

    Cada card tem numerao, nome, a miniatura da fase e dois selos: um de
    fase vencida e um do fragmento. O fragmento fica dourado quando apanhado
    e um contorno vazio quando nao -- o mesmo dourado que no jogo significa
    "isto exige os dois", que e exatamente o que o desvio do fragmento
    costuma exigir.

    Andar pra esquerda na primeira coluna vira a pagina pro ato anterior (e
    pra direita na ultima, pro seguinte). Virar pela BORDA, e nao por uma
    tecla propria, mantem o menu inteiro em quatro teclas -- e e como todo
    seletor de fase de celular funciona, que e a referencia que o jogador
    traz pra ca.
    """

    def __init__(self, catalog: LevelCatalog, preview_terrain: Terrain) -> None:
        self._catalog = catalog
        self.previews = [
            LevelPreview(catalog.at(index), preview_terrain) for index in range(catalog.count)
        ]
        self.selected = 0
        self._viewport_width = 896.0

    @property
    def count(self) -> int:
        return self._catalog.count

    @property
    def act(self) -> int:
        return self.selected // _PER_ACT

    @property
    def act_count(self) -> int:
        return (self.count + _PER_ACT - 1) // _PER_ACT

    def move(self, columns: int, rows: int) -> None:
        """Anda na grade; na borda lateral, vira de ato.

        Nao circula em cima/embaixo nem no ultimo ato de proposito: num
        seletor 2D o wrap salta o cursor pra um canto oposto e o jogador
        perde de vista onde estava.
        """
        act = self.act
        local = self.selected - act * _PER_ACT
        column = local % _COLUMNS
        row = local // _COLUMNS

        if columns < 0 and column == 0:
            if act == 0:
                return
            act -= 1
            column = _COLUMNS - 1
        elif columns > 0 and column == _COLUMNS - 1:
            if act >= self.act_count - 1:
                return
            act += 1
            column = 0
        else:
            column = max(0, min(_COLUMNS - 1, column + columns))

        row = max(0, min(_ROWS - 1, row + rows))
        target = act * _PER_ACT + row * _COLUMNS + column
        # O ultimo ato pode estar incompleto: cai pro card existente mais
        # proximo em vez de recusar o movimento, que ao jogador pareceria
        # a tecla ter falhado.
        while target >= self.count and target > act * _PER_ACT:
            target -= 1
        if target < self.count:
            self.selected = target

    def card_rect(self, index: int) -> Tuple[float, float, float, float]:
        local = index % _PER_ACT
        column = local % _COLUMNS
        row = local // _COLUMNS
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
        self._draw_act_tabs(renderer, completed)
        first = self.act * _PER_ACT
        for index in range(first, min(first + _PER_ACT, self.count)):
            self._draw_card(renderer, index, completed[index], shards[index])

    def _draw_act_tabs(self, renderer: IRenderer, completed: List[bool]) -> None:
        """Os tres atos numa linha, com o progresso de cada um.

        O ato corrente leva o nome por extenso e a legenda; os outros, so o
        numeral. E o suficiente pra dizer 'ha mais de um lado' sem competir
        com os cards, que sao o que o jogador veio ver."""
        center = self._viewport_width / 2.0
        total = self.act_count
        slot = min(190.0, (self._viewport_width - 40.0) / max(1, total))
        left = center - (total * slot) / 2.0
        for index in range(total):
            numeral, title, subtitle = _ACTS[index] if index < len(_ACTS) else (f"ATO {index + 1}", "", "")
            x = left + index * slot + slot / 2.0
            current = index == self.act
            done = sum(1 for i in range(index * _PER_ACT, min((index + 1) * _PER_ACT, self.count))
                       if completed[i])
            size = min(_PER_ACT, self.count - index * _PER_ACT)
            if current:
                renderer.draw_text(x, _ACT_TAB_Y - 16.0, f"{numeral}  {title}", 15, _GOLD,
                                   anchor="center")
                renderer.draw_text(x, _ACT_TAB_Y + 4.0, subtitle, 11, _TEXT_DIM, anchor="center")
                renderer.draw_ui_rect(x - 84.0, _ACT_TAB_Y + 22.0, 168.0, 2.0, _GOLD)
            else:
                renderer.draw_text(x, _ACT_TAB_Y - 16.0, numeral, 13, _TEXT_FAINT, anchor="center")
                renderer.draw_text(x, _ACT_TAB_Y + 4.0, f"{done}/{size}", 11, _TEXT_FAINT,
                                   anchor="center")

    def _draw_card(self, renderer: IRenderer, index: int, done: bool, shard: bool) -> None:
        x, y, width, height = self.card_rect(index)
        selected = index == self.selected
        level = self._catalog.at(index)

        renderer.draw_ui_rect(x, y, width, height, _CARD_SELECTED if selected else _CARD)
        if selected:
            renderer.draw_ui_rect(x, y, width, 2.0, _GOLD)
            renderer.draw_ui_rect(x, y + height - 2.0, width, 2.0, _GOLD)

        # numerao: o jeito mais rapido de achar a fase 15 numa grade de seis
        renderer.draw_text(x + 14.0, y + 8.0, str(index + 1), 36, _GOLD if selected else _NUMBER_IDLE)

        # miniatura do terreno real da fase
        preview_x = x + 66.0
        preview_y = y + 14.0
        preview_w = width - 80.0
        preview_h = height - 60.0
        renderer.draw_ui_rect(preview_x - 2.0, preview_y - 2.0, preview_w + 4.0, preview_h + 4.0, _VOID)
        self.previews[index].draw(renderer, preview_x, preview_y, preview_w, preview_h)

        renderer.draw_text(x + 14.0, y + height - 38.0, level.name, 15, _TEXT if selected else _TEXT_DIM)

        # selos: fase vencida e fragmento
        seal_y = y + height - 18.0
        renderer.draw_text(x + 14.0, seal_y, "vencida" if done else "aberta", 11,
                           _GOLD if done else _TEXT_FAINT)
        renderer.draw_text(x + width - 14.0, seal_y,
                           "fragmento" if shard else "fragmento?", 11,
                           _GOLD if shard else _GOLD_DIM, anchor="topright")


_BUTTON_WIDTH = 268.0
_BUTTON_HEIGHT = 180.0
_BUTTON_GAP = 40.0


_BLOB_BANDS = (0.52, 0.86, 1.0, 0.86, 0.52)
"""Largura relativa de cada faixa horizontal da Lumen, de cima pra baixo.
Cinco faixas bastam: o que o botao precisa dizer e "esta e redonda, aquela e
quadrada", e mais faixas so custam retangulos."""


def _blob(renderer: IRenderer, center_x: float, center_y: float, size: float, color) -> None:
    """Desenha a Lumen: um circulo aproximado por faixas. `draw_ui_rect` so
    faz retangulo, e a diferenca entre ela (redonda) e a Umbra (quadrada) e a
    unica coisa que identifica cada ser nos botoes."""
    band_height = size / len(_BLOB_BANDS)
    top = center_y - size / 2.0
    for index, width_ratio in enumerate(_BLOB_BANDS):
        band_width = size * width_ratio
        renderer.draw_ui_rect(
            center_x - band_width / 2.0,
            top + index * band_height,
            band_width,
            band_height + 1.0,   # +1: sem isso o arredondamento abre fendas
            color,
        )


def _block(renderer: IRenderer, center_x: float, center_y: float, size: float, fill, rim) -> None:
    """A Umbra: bloco escuro com orla. Sem a orla ela some no fundo -- a mesma
    razao de ela ter orla no jogo."""
    half = size / 2.0
    renderer.draw_ui_rect(center_x - half - 2.0, center_y - half - 2.0, size + 4.0, size + 4.0, rim)
    renderer.draw_ui_rect(center_x - half, center_y - half, size, size, fill)


class TitleScreen:
    """
    Tela de abertura com a escolha de modo em dois botoes grandes.

    Existe porque a versao anterior escondia o modo num atalho de TAB no
    canto do menu de fases: quem nunca leu o rodape jamais descobriria que o
    jogo tem dois jogadores. Modo e a primeira decisao da sessao -- ela
    merece uma tela, nao uma legenda.

    Os botoes mostram os DOIS seres nos dois casos, porque em ambos os modos
    eles existem; o que muda e quem os comanda, e e isso que o desenho diz:
    num jogador, uma seta de TAB entre eles; em dois, um rotulo J1 e J2.
    """

    def __init__(self) -> None:
        self.duo = False

    def move(self, step: int) -> None:
        if step:
            self.duo = step > 0

    def draw(self, renderer: IRenderer, completed: int, shards: int, total: int) -> None:
        width, height = renderer.get_viewport_size()
        renderer.draw_ui_rect(0.0, 0.0, width, height, _VOID)
        center = width / 2.0

        renderer.draw_text(center, 54.0, "PENUMBRA", 56, _TEXT, anchor="center")
        renderer.draw_text(center, 122.0, "Luz e Sombra: Dualidade", 16, _GOLD, anchor="center")
        renderer.draw_ui_rect(center - 210.0, 156.0, 420.0, 1.0, _RULE)

        top = 196.0
        total_width = 2 * _BUTTON_WIDTH + _BUTTON_GAP
        left = (width - total_width) / 2.0
        self._draw_button(renderer, left, top, duo=False)
        self._draw_button(renderer, left + _BUTTON_WIDTH + _BUTTON_GAP, top, duo=True)

        progress_y = top + _BUTTON_HEIGHT + 34.0
        renderer.draw_text(center, progress_y, f"{completed}/{total} fases    {shards}/{total} fragmentos",
                           14, _TEXT_DIM, anchor="center")

        # Os controles do modo ESCOLHIDO, na propria tela de escolha: e a
        # unica hora em que o jogador ainda pode mudar de ideia sabendo o que
        # cada modo exige das maos dele.
        renderer.draw_ui_rect(center - 210.0, progress_y + 40.0, 420.0, 1.0, _RULE)
        controls_y = progress_y + 58.0
        if self.duo:
            renderer.draw_text(center, controls_y, "JOGADOR 1   A/D mover   ESPACO pular   J habilidade",
                               13, _TEXT_DIM, anchor="center")
            renderer.draw_text(center, controls_y + 22.0, "JOGADOR 2   setas mover   CIMA pular   BAIXO habilidade",
                               13, _TEXT_DIM, anchor="center")
        else:
            renderer.draw_text(center, controls_y, "A/D mover   ESPACO pular   J habilidade",
                               13, _TEXT_DIM, anchor="center")
            renderer.draw_text(center, controls_y + 22.0, "TAB alterna entre os dois seres   R reinicia a fase",
                               13, _TEXT_DIM, anchor="center")

        renderer.draw_text(center, height - 40.0, "A/D escolher      ESPACO confirmar      ESC sair",
                           13, _TEXT_FAINT, anchor="center")

    def _draw_button(self, renderer: IRenderer, x: float, y: float, duo: bool) -> None:
        selected = duo == self.duo
        renderer.draw_ui_rect(x, y, _BUTTON_WIDTH, _BUTTON_HEIGHT,
                              _CARD_SELECTED if selected else _CARD)
        if selected:
            for edge in (0.0, _BUTTON_HEIGHT - 3.0):
                renderer.draw_ui_rect(x, y + edge, _BUTTON_WIDTH, 3.0, _GOLD)
            for edge in (0.0, _BUTTON_WIDTH - 3.0):
                renderer.draw_ui_rect(x + edge, y, 3.0, _BUTTON_HEIGHT, _GOLD)

        center_x = x + _BUTTON_WIDTH / 2.0
        label = "2 JOGADORES" if duo else "1 JOGADOR"
        renderer.draw_text(center_x, y + 22.0, label, 26,
                           _GOLD if selected else _TEXT_DIM, anchor="center")

        figures_y = y + 96.0
        tone = 255 if selected else 150
        lumen = (tone, tone, min(255, tone + 5), 255)
        umbra_fill = (46, 44, 60, 255)
        umbra_rim = (tone - 60, tone - 62, tone - 40, 255)
        _blob(renderer, center_x - 46.0, figures_y, 38.0, lumen)
        _block(renderer, center_x + 46.0, figures_y, 38.0, umbra_fill, umbra_rim)

        if duo:
            renderer.draw_text(center_x - 46.0, figures_y + 34.0, "J1", 13,
                               _GOLD if selected else _TEXT_FAINT, anchor="center")
            renderer.draw_text(center_x + 46.0, figures_y + 34.0, "J2", 13,
                               _GOLD if selected else _TEXT_FAINT, anchor="center")
            hint = "cada um no seu"
        else:
            renderer.draw_text(center_x, figures_y, "TAB", 13,
                               _GOLD if selected else _TEXT_FAINT, anchor="center")
            hint = "um por vez, TAB alterna"
        renderer.draw_text(center_x, y + _BUTTON_HEIGHT - 28.0, hint, 12,
                           _TEXT_DIM if selected else _TEXT_FAINT, anchor="center")


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


_ENDING_TITLE = "A FONTE"
_ENDING_LEAD = (
    "Voces nasceram da mesma fonte, e ela esta aberta.",
    "Podem voltar a ser uma coisa so -- e nunca mais precisar um do outro.",
    "Ou seguir dois, e continuar precisando.",
)

_ENDING_LINE_SIZE = 11
_ENDING_CHOICES = (
    ("FUNDIR", (
        "Uma luz so, sem polaridade.",
        "Ninguem cai porque o outro acende.",
        "E ninguem atravessa o impossivel.",
    )),
    ("SEGUIR DOIS", (
        "Continuam sem poder se tocar.",
        "Continuam sem avancar sozinhos.",
        "Era isso que os levava adiante.",
    )),
)
"""Cada linha cabe na largura do botao: a 11 px a fonte monoespacada do
backend gasta ~0,6 em por glifo, entao 268 px de card levam 40 caracteres.
A primeira versao tinha linhas de 56 -- elas saiam do card e as duas colunas
se sobrepunham no meio da tela. `tests/` mede isso agora."""


class EndingScreen:
    """
    A escolha do fim: fundir os dois, ou segui-los separados.

    O documento de design sempre previu este final, e ate agora a ultima fase
    simplesmente devolvia o jogador ao menu -- dezoito fases sobre depender do
    outro terminavam sem dizer nada sobre isso.

    Nao ha final certo, e por isso nenhum dos dois e recompensado: fundir
    resolve o problema do jogo eliminando o jogo, e seguir dois mantem o
    problema porque ele e a razao de os dois existirem. A tela so os coloca
    lado a lado, com a consequencia escrita embaixo de cada um.
    """

    def __init__(self) -> None:
        self.fused = False
        self.confirmed = False

    def move(self, step: int) -> None:
        if step and not self.confirmed:
            self.fused = step < 0

    @property
    def choice(self) -> str:
        return "fundidos" if self.fused else "separados"

    def draw(self, renderer: IRenderer, shards: int, total: int) -> None:
        width, height = renderer.get_viewport_size()
        renderer.draw_ui_rect(0.0, 0.0, width, height, _VOID)
        center = width / 2.0

        renderer.draw_text(center, 58.0, _ENDING_TITLE, 44, _GOLD, anchor="center")
        renderer.draw_ui_rect(center - 180.0, 118.0, 360.0, 1.0, _RULE)

        if self.confirmed:
            self._draw_epilogue(renderer, center, shards, total)
            return

        for index, line in enumerate(_ENDING_LEAD):
            renderer.draw_text(center, 146.0 + index * 24.0, line, 14, _TEXT_DIM, anchor="center")

        top = 246.0
        total_width = 2 * _BUTTON_WIDTH + _BUTTON_GAP
        left = (width - total_width) / 2.0
        for index, (label, consequence) in enumerate(_ENDING_CHOICES):
            x = left + index * (_BUTTON_WIDTH + _BUTTON_GAP)
            selected = (index == 0) == self.fused
            renderer.draw_ui_rect(x, top, _BUTTON_WIDTH, 132.0,
                                  _CARD_SELECTED if selected else _CARD)
            if selected:
                renderer.draw_ui_rect(x, top, _BUTTON_WIDTH, 2.0, _GOLD)
                renderer.draw_ui_rect(x, top + 130.0, _BUTTON_WIDTH, 2.0, _GOLD)
            middle = x + _BUTTON_WIDTH / 2.0
            renderer.draw_text(middle, top + 18.0, label, 20,
                               _GOLD if selected else _TEXT_DIM, anchor="center")
            for line_index, line in enumerate(consequence):
                renderer.draw_text(middle, top + 56.0 + line_index * 20.0, line, _ENDING_LINE_SIZE,
                                   _TEXT_DIM if selected else _TEXT_FAINT, anchor="center")

        renderer.draw_text(center, 418.0, "A/D escolher      ESPACO confirmar", 13,
                           _TEXT_FAINT, anchor="center")

    def _draw_epilogue(self, renderer: IRenderer, center: float, shards: int, total: int) -> None:
        label, consequence = _ENDING_CHOICES[0 if self.fused else 1]
        renderer.draw_text(center, 152.0, label, 22, _GOLD, anchor="center")
        for index, line in enumerate(consequence):
            renderer.draw_text(center, 202.0 + index * 26.0, line, 15, _TEXT, anchor="center")

        renderer.draw_ui_rect(center - 180.0, 306.0, 360.0, 1.0, _RULE)
        renderer.draw_text(center, 330.0, f"{total} fases atravessadas", 14, _TEXT_DIM,
                           anchor="center")
        renderer.draw_text(center, 354.0, f"{shards}/{total} fragmentos da fonte", 14,
                           _GOLD if shards == total else _TEXT_DIM, anchor="center")
        if shards < total:
            renderer.draw_text(center, 386.0,
                               "Os fragmentos que faltam continuam la. Nada fica trancado.",
                               12, _TEXT_FAINT, anchor="center")
        renderer.draw_text(center, 430.0, "ESPACO volta ao menu", 13, _TEXT_FAINT, anchor="center")
