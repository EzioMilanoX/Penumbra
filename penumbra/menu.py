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

from ouroboros.interfaces.renderer import IRenderer

from penumbra import achievements
from penumbra.levels import LevelCatalog, LevelDefinition
from penumbra.terrain import (
    ROLE_ALTAR,
    ROLE_BEACON,
    ROLE_COUNTER_ETHER,
    ROLE_CRUST,
    ROLE_DOOR,
    ROLE_ECLIPSE,
    ROLE_ETHER,
    ROLE_GLASS,
    ROLE_LAMP,
    ROLE_LEVER,
    ROLE_LUMEN_GOAL,
    ROLE_PLATE,
    ROLE_ROCK,
    ROLE_SHARD,
    ROLE_SOURCE,
    ROLE_SOURCE_ALT,
    ROLE_UMBRA_GOAL,
    ROLE_VEIL,
    ROLE_WANDER,
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
_PERIL = (206, 88, 88, 255)
"""O unico vermelho do menu, e num lugar so: o aviso de apagar o
progresso. O dourado significa cooperacao -- o oposto do que esta
linha quer dizer."""

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
    ROLE_SOURCE_ALT: (214, 200, 255, 255),
    ROLE_LEVER: (170, 150, 220, 255),
}
"""Cor de cada papel na miniatura. Deliberadamente mais CLARAS que no jogo:
numa miniatura de 3 px por celula o contraste real do jogo (rocha quase preta
sobre fundo quase preto) desapareceria, e a silhueta da fase e a unica coisa
que o card precisa entregar."""

_COLUMNS = 5
_ROWS = 3
_CARD_WIDTH = 160.0
_CARD_HEIGHT = 126.0
_CARD_GAP_X = 14.0
_CARD_GAP_Y = 13.0
_GRID_TOP = 136.0
_CHAPTER_TAB_Y = 104.0
"""Quinze slots por pagina, em 5x3 -- o tamanho do maior capitulo.

A pagina e o CAPITULO, e nao um bloco de N fases, porque os tres nao tem o
mesmo tamanho nem deveriam ter: aprender uma mecânica de cada vez custa uma
fase por mecanica, misturar custa menos, e as especiais sao poucas de
proposito. Um capitulo mais curto deixa a grade pela metade, e isso e uma
informacao verdadeira -- nao um buraco.

O capitulo e pagina, nao tranca: nada fica bloqueado, e a seta anda de
capitulo como anda de card, virando pela borda da grade. Assim o menu
inteiro continua em quatro teclas."""


class LevelPreview:
    """
    Miniatura de uma fase, pre-computada uma vez.

    Guarda uma lista de `(coluna, linha, cor)` ja filtrada -- so as celulas
    que de fato desenham algo. Numa grade 28x17 isso costuma cortar mais da
    metade, e o menu desenha ate quinze cards por frame: sem o filtro seriam
    7140 retangulos por frame pra mostrar sobretudo vazio.
    """

    def __init__(self, level: LevelDefinition, terrain: Terrain, duo: bool = False) -> None:
        terrain.load_rows(level.rows_for(duo))
        self.cols = terrain.cols
        self.rows = terrain.rows
        self.cells: list[tuple[int, int, tuple[int, int, int, int]]] = []
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
    Grade de cards navegavel com W/A/S/D, paginada por CAPITULO.

    Cada card tem numerao, nome, a miniatura da fase e dois selos: um de
    fase vencida e um do fragmento. O fragmento fica dourado quando apanhado
    e um contorno vazio quando nao -- o mesmo dourado que no jogo significa
    "isto exige os dois", que e exatamente o que o desvio do fragmento
    costuma exigir.

    Andar pra esquerda na primeira coluna vira a pagina pro capitulo anterior
    (e pra direita na ultima, pro seguinte). Virar pela BORDA, e nao por uma
    tecla propria, mantem o menu inteiro em quatro teclas -- e e como todo
    seletor de fase de celular funciona, que e a referencia que o jogador
    traz pra ca.
    """

    def __init__(self, catalog: LevelCatalog, preview_terrain: Terrain) -> None:
        self._catalog = catalog
        # Duas miniaturas por fase, uma por modo. A fase que muda no duo tem
        # de MOSTRAR que muda -- um card que desenhasse sempre a versao solo
        # ensinaria a fase errada a metade dos jogadores.
        self.previews = {
            duo: [LevelPreview(catalog.at(index), preview_terrain, duo)
                  for index in range(catalog.count)]
            for duo in (False, True)
        }
        self.selected = 0
        self._viewport_width = 896.0

    @property
    def count(self) -> int:
        return self._catalog.count

    @property
    def chapter(self):
        return self._catalog.chapter_of(self.selected)

    @property
    def chapters(self):
        return self._catalog.chapters

    def move(self, columns: int, rows: int) -> None:
        """Anda na grade; na borda lateral, vira de capitulo.

        Nao circula em cima/embaixo nem depois do ultimo capitulo de
        proposito: num seletor 2D o wrap salta o cursor pra um canto oposto e
        o jogador perde de vista onde estava.
        """
        chapters = self._catalog.chapters
        chapter = self.chapter
        position = chapters.index(chapter)
        local = self.selected - chapter.first
        column = local % _COLUMNS
        row = local // _COLUMNS

        if columns < 0 and column == 0:
            if position == 0:
                return
            chapter = chapters[position - 1]
            column = _COLUMNS - 1
        elif columns > 0 and column == _COLUMNS - 1:
            if position >= len(chapters) - 1:
                return
            chapter = chapters[position + 1]
            column = 0
        else:
            column = max(0, min(_COLUMNS - 1, column + columns))

        last_row = max(0, (chapter.count - 1) // _COLUMNS)
        row = max(0, min(min(_ROWS - 1, last_row), row + rows))
        target = chapter.first + row * _COLUMNS + column
        # Um capitulo pode nao encher a fileira: cai pro card existente mais
        # proximo em vez de recusar o movimento, que ao jogador pareceria a
        # tecla ter falhado.
        while target > chapter.last and target > chapter.first:
            target -= 1
        self.selected = max(chapter.first, min(chapter.last, target))

    def card_rect(self, index: int) -> tuple[float, float, float, float]:
        local = index - self._catalog.chapter_of(index).first
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
        completed: list[bool],
        shards: list[bool],
        duo: bool = False,
        pads: int = 0,
    ) -> None:
        self._viewport_width, _ = renderer.get_viewport_size()
        self._draw_chapter_tabs(renderer, completed)
        chapter = self.chapter
        for index in range(chapter.first, chapter.last + 1):
            self._draw_card(renderer, index, completed[index], shards[index], duo)

    def _draw_chapter_tabs(self, renderer: IRenderer, completed: list[bool]) -> None:
        """Os capitulos numa linha, com o progresso de cada um.

        O capitulo corrente leva o nome por extenso e a legenda; os outros, so
        o numeral e a contagem. E o suficiente pra dizer "ha mais de um lado"
        sem competir com os cards, que sao o que o jogador veio ver."""
        chapters = self._catalog.chapters
        center = self._viewport_width / 2.0
        slot = min(220.0, (self._viewport_width - 40.0) / max(1, len(chapters)))
        left = center - (len(chapters) * slot) / 2.0
        for position, chapter in enumerate(chapters):
            x = left + position * slot + slot / 2.0
            current = chapter is self.chapter
            done = sum(1 for i in range(chapter.first, chapter.last + 1) if completed[i])
            if current:
                renderer.draw_text(x, _CHAPTER_TAB_Y - 16.0, chapter.title, 15, _GOLD,
                                   anchor="center")
                renderer.draw_text(x, _CHAPTER_TAB_Y + 4.0,
                                   f"{chapter.subtitle}    {done}/{chapter.count}",
                                   11, _TEXT_DIM, anchor="center")
                renderer.draw_ui_rect(x - slot / 2.0 + 16.0, _CHAPTER_TAB_Y + 22.0,
                                      slot - 32.0, 2.0, _GOLD)
            else:
                renderer.draw_text(x, _CHAPTER_TAB_Y - 16.0, chapter.title, 13, _TEXT_FAINT,
                                   anchor="center")
                renderer.draw_text(x, _CHAPTER_TAB_Y + 4.0, f"{done}/{chapter.count}", 11,
                                   _TEXT_FAINT, anchor="center")

    def _draw_card(self, renderer: IRenderer, index: int, done: bool, shard: bool,
                   duo: bool = False) -> None:
        x, y, width, height = self.card_rect(index)
        selected = index == self.selected
        level = self._catalog.at(index)

        renderer.draw_ui_rect(x, y, width, height, _CARD_SELECTED if selected else _CARD)
        if selected:
            renderer.draw_ui_rect(x, y, width, 2.0, _GOLD)
            renderer.draw_ui_rect(x, y + height - 2.0, width, 2.0, _GOLD)

        # numerao: o jeito mais rapido de achar a fase 15 numa grade de quinze
        renderer.draw_text(x + 9.0, y + 5.0, str(index + 1), 26,
                           _GOLD if selected else _NUMBER_IDLE)

        # miniatura do terreno real da fase
        preview_x = x + 44.0
        preview_y = y + 9.0
        preview_w = width - 53.0
        preview_h = height - 46.0
        renderer.draw_ui_rect(preview_x - 2.0, preview_y - 2.0, preview_w + 4.0, preview_h + 4.0, _VOID)
        self.previews[duo][index].draw(renderer, preview_x, preview_y, preview_w, preview_h)

        # A marca de fase que muda no duo fica sobre a miniatura, e nao junto
        # dos selos: ela e sobre o TERRENO desenhado ali, nao sobre o que voce
        # ja fez nela.
        if level.has_duo_variant:
            renderer.draw_text(preview_x + preview_w - 3.0, preview_y + 2.0, "2P", 10,
                               _GOLD if duo else _GOLD_DIM, anchor="topright")
        # E a fase que, sozinho, da para jogar em laco com o proprio eco.
        if level.has_echo and not duo:
            renderer.draw_text(preview_x + 3.0, preview_y + 2.0, "ECO", 10,
                               _GOLD if selected else _GOLD_DIM)

        renderer.draw_text(x + 9.0, y + height - 32.0, level.name, 12,
                           _TEXT if selected else _TEXT_DIM)

        # selos: fase vencida e fragmento
        seal_y = y + height - 15.0
        renderer.draw_text(x + 9.0, seal_y, "vencida" if done else "aberta", 10,
                           _GOLD if done else _TEXT_FAINT)
        renderer.draw_text(x + width - 9.0, seal_y, "frag" if shard else "frag?", 10,
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


def mode_controls(duo: bool, pads: int):
    """As duas linhas que a tela de escolha de modo mostra sobre as maos.

    E a tela mais importante para isto: e a ultima hora em que o jogador
    ainda pode mudar de ideia sabendo o que cada modo vai exigir dele. Com um
    controle na mao e "ESPAÇO pular" escrito na tela, ele larga o controle --
    e o controle funciona.

    No duo as duas linhas sao independentes de proposito: com UM controle so,
    o jogador 1 le o controle e o 2 le as setas. E o arranjo real de um sofa
    com um controle, e inventar um segundo controle na linha do jogador 2
    mandaria alguem procurar o que nao existe."""
    if duo:
        return (
            "JOGADOR 1   " + ("controle: direcional   A pular   X habilidade   SELECT reinicia"
                              if pads >= 1 else
                              "A/D mover   ESPAÇO pular   S habilidade   R reinicia"),
            "JOGADOR 2   " + ("controle: direcional   A pular   X habilidade   SELECT reinicia"
                              if pads >= 2 else
                              "setas mover   CIMA pular   BAIXO habilidade   END reinicia"),
        )
    if pads:
        return (
            "direcional mover   A pular   X habilidade",
            "RB alterna entre os dois seres   SELECT reinicia a fase",
        )
    return (
        "A/D mover   ESPAÇO pular   S habilidade",
        "TAB alterna entre os dois seres   R reinicia a fase",
    )


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

    def draw(self, renderer: IRenderer, completed: int, shards: int, total: int,
             achievements: int = 0, achievement_total: int = 0, pads: int = 0) -> None:
        width, height = renderer.get_viewport_size()
        renderer.draw_ui_rect(0.0, 0.0, width, height, _VOID)
        center = width / 2.0

        renderer.draw_text(center, 54.0, "PENUMBRA", 56, _TEXT, anchor="center")
        renderer.draw_text(center, 122.0, "Luz e Sombra: Dualidade", 16, _GOLD, anchor="center")
        renderer.draw_ui_rect(center - 210.0, 156.0, 420.0, 1.0, _RULE)

        top = 196.0
        total_width = 2 * _BUTTON_WIDTH + _BUTTON_GAP
        left = (width - total_width) / 2.0
        self._draw_button(renderer, left, top, duo=False, pads=pads)
        self._draw_button(renderer, left + _BUTTON_WIDTH + _BUTTON_GAP, top, duo=True, pads=pads)

        progress_y = top + _BUTTON_HEIGHT + 34.0
        renderer.draw_text(
            center, progress_y,
            f"{completed}/{total} fases    {shards}/{total} fragmentos"
            + (f"    {achievements}/{achievement_total} conquistas" if achievement_total else ""),
            14, _GOLD if shards == total else _TEXT_DIM, anchor="center",
        )

        # Os controles do modo ESCOLHIDO, na propria tela de escolha: e a
        # unica hora em que o jogador ainda pode mudar de ideia sabendo o que
        # cada modo exige das maos dele.
        renderer.draw_ui_rect(center - 210.0, progress_y + 40.0, 420.0, 1.0, _RULE)
        controls_y = progress_y + 58.0
        for offset, line in enumerate(mode_controls(self.duo, pads)):
            renderer.draw_text(center, controls_y + offset * 22.0, line,
                               13, _TEXT_DIM, anchor="center")

        renderer.draw_text(
            center, height - 40.0,
            "direcional escolher      A confirmar      START sair" if pads
            else "A/D escolher      ESPAÇO confirmar      ESC sair",
            13, _TEXT_FAINT, anchor="center")

    def _draw_button(self, renderer: IRenderer, x: float, y: float, duo: bool,
                     pads: int = 0) -> None:
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
            # A tecla que ALTERNA entre os dois seres e a mecanica central do
            # modo solo, e este card e onde ela e dita pela primeira vez.
            troca = "RB" if pads else "TAB"
            renderer.draw_text(center_x, figures_y, troca, 13,
                               _GOLD if selected else _TEXT_FAINT, anchor="center")
            hint = f"um por vez, {troca} alterna"
        renderer.draw_text(center_x, y + _BUTTON_HEIGHT - 28.0, hint, 12,
                           _TEXT_DIM if selected else _TEXT_FAINT, anchor="center")


class MenuChrome:
    """Titulo, rodape e o seletor de modo -- tudo que nao e card."""

    def __init__(self) -> None:
        self.message = ""

    def draw(self, renderer: IRenderer, duo: bool, collected: int, total: int,
             pads: int = 0, echo: bool = False) -> None:
        """`echo`: o card escolhido aceita o solo com eco -- o rodape passa a
        dizer a tecla, que e a unica porta de entrada do modo."""
        width, height = renderer.get_viewport_size()
        renderer.draw_ui_rect(0.0, 0.0, width, height, _VOID)
        center = width / 2.0

        renderer.draw_text(center, 22.0, "PENUMBRA", 34, _TEXT, anchor="center")
        renderer.draw_text(center, 62.0, "Luz e Sombra: Dualidade", 13, _GOLD, anchor="center")

        mode = "DOIS JOGADORES" if duo else "UM JOGADOR"
        renderer.draw_text(24.0, 30.0, f"modo: {mode}", 13, _GOLD if duo else _TEXT_DIM)
        renderer.draw_text(24.0, 50.0, "RB troca de modo" if pads else "TAB troca de modo",
                           11, _TEXT_FAINT)
        renderer.draw_text(width - 24.0, 30.0, f"fragmentos {collected}/{total}", 13, _GOLD,
                           anchor="topright")

        if self.message:
            renderer.draw_text(center, 88.0, self.message, 13, _GOLD, anchor="center")

        footer_y = height - 46.0
        renderer.draw_ui_rect(0.0, footer_y - 12.0, width, 1.0, _RULE)
        if echo:
            line = ("direcional escolher    A jogar    Y solo com eco    START sair" if pads
                    else "W/A/S/D escolher    ESPAÇO jogar    E solo com eco    ESC sair")
        else:
            line = ("direcional escolher      A jogar      START sair" if pads
                    else "W/A/S/D escolher      ESPAÇO jogar      ESC sair")
        renderer.draw_text(center, footer_y, line, 12, _GOLD if echo else _TEXT_DIM,
                           anchor="center")
        if duo:
            controls = (("J1: controle" if pads >= 1 else "J1: A/D  ESPAÇO  S")
                        + "          "
                        + ("J2: controle" if pads >= 2 else "J2: setas  cima  baixo"))
        elif pads:
            controls = "direcional mover   A pular   X habilidade   RB trocar de ser"
        else:
            controls = "A/D mover   ESPAÇO pular   S habilidade   TAB trocar de ser"
        renderer.draw_text(center, footer_y + 20.0, controls, 11, _TEXT_FAINT, anchor="center")


_ENDING_TITLE = "A FONTE"
_ENDING_LEAD = (
    "Vocês nasceram da mesma fonte, e ela está aberta.",
    "Podem voltar a ser uma coisa só -- e nunca mais precisar um do outro.",
    "Ou seguir dois, e continuar precisando.",
)

_ENDING_LINE_SIZE = 11
_ENDING_CHOICES = (
    ("FUNDIR", (
        "Uma luz só, sem polaridade.",
        "Ninguém cai porque o outro acende.",
        "E ninguém atravessa o impossível.",
    )),
    ("SEGUIR DOIS", (
        "Continuam sem poder se tocar.",
        "Continuam sem avançar sozinhos.",
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

    def __init__(self, whole: bool = True) -> None:
        self.whole = whole
        self.fused = False
        self.confirmed = False

    def move(self, step: int) -> None:
        """Fundir so e escolhivel com a fonte inteira. Nao e tranca: nenhuma
        fase fica bloqueada, e da pra voltar, apanhar os fragmentos que
        faltam e refazer a escolha -- mas nao se funde uma fonte que nunca
        foi remontada, e e disso que os trinta fragmentos vivem."""
        if step and not self.confirmed:
            if step < 0 and not self.whole:
                return
            self.fused = step < 0

    @property
    def choice(self) -> str:
        return "fundidos" if self.fused else "separados"

    def draw(self, renderer: IRenderer, shards: int, total: int) -> None:
        self.whole = shards >= total
        if not self.whole:
            self.fused = False
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
            locked = index == 0 and not self.whole
            renderer.draw_text(middle, top + 18.0, label, 20,
                               _TEXT_FAINT if locked else (_GOLD if selected else _TEXT_DIM),
                               anchor="center")
            if locked:
                # A razao de existirem trinta fragmentos, dita em uma linha.
                renderer.draw_text(middle, top + 60.0, "A fonte está incompleta.", 11,
                                   _TEXT_FAINT, anchor="center")
                renderer.draw_text(middle, top + 80.0, f"Faltam {total - shards} fragmentos.", 11,
                                   _GOLD_DIM, anchor="center")
                renderer.draw_text(middle, top + 100.0, "Nada fica trancado: volte e apanhe.", 11,
                                   _TEXT_FAINT, anchor="center")
                continue
            for line_index, line in enumerate(consequence):
                renderer.draw_text(middle, top + 56.0 + line_index * 20.0, line, _ENDING_LINE_SIZE,
                                   _TEXT_DIM if selected else _TEXT_FAINT, anchor="center")

        renderer.draw_text(center, 418.0, "A/D escolher      ESPAÇO confirmar", 13,
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
        renderer.draw_text(center, 430.0, "ESPAÇO volta ao menu", 13, _TEXT_FAINT, anchor="center")


_PAUSE_OPTIONS = ("CONTINUAR", "REINICIAR A FASE", "VOLTAR AO MENU")


class PauseScreen:
    """
    A pausa: um painel por cima da fase congelada.

    Antes, ESC no meio da fase voltava ao menu -- e custava a tentativa.
    Nao havia como so parar. O painel e estreito e escuro de proposito:
    a fase continua visivel em volta, porque o jogador pausou olhando
    alguma coisa e provavelmente quer continuar olhando.
    """

    def __init__(self) -> None:
        self.selected = 0

    def move(self, step: int) -> None:
        if step:
            self.selected = max(0, min(len(_PAUSE_OPTIONS) - 1, self.selected + step))

    def draw(self, renderer: IRenderer, level_name: str, duo: bool) -> None:
        width, height = renderer.get_viewport_size()
        center = width / 2.0

        # Veu sobre a fase inteira: escurece sem ESCONDER. A 190 o jogo
        # sumia -- as fases ja sao escuras, e o jogador pausou olhando alguma
        # coisa que provavelmente quer continuar olhando.
        renderer.draw_ui_rect(0.0, 0.0, width, height, (8, 8, 14, 124))

        panel_w, panel_h = 340.0, 236.0
        left = center - panel_w / 2.0
        top = height / 2.0 - panel_h / 2.0 - 20.0
        renderer.draw_ui_rect(left, top, panel_w, panel_h, _CARD)
        renderer.draw_ui_rect(left, top, panel_w, 2.0, _GOLD)

        renderer.draw_text(center, top + 22.0, "PAUSA", 26, _GOLD, anchor="center")
        renderer.draw_text(center, top + 58.0, level_name, 13, _TEXT_DIM, anchor="center")

        for index, label in enumerate(_PAUSE_OPTIONS):
            y = top + 96.0 + index * 34.0
            chosen = index == self.selected
            if chosen:
                # Mesma regra da raiz: texto centrado em `y`, faixa tambem.
                renderer.draw_ui_rect(left + 18.0, y - 14.0, panel_w - 36.0, 28.0,
                                      _CARD_SELECTED)
            renderer.draw_text(center, y, label, 15,
                               _GOLD if chosen else _TEXT_DIM, anchor="center")

        renderer.draw_text(center, top + panel_h - 24.0,
                           "W/S escolher   ESPAÇO confirmar   ESC continuar",
                           11, _TEXT_FAINT, anchor="center")


# ======================================================================
# A raiz do jogo: as quatro portas
# ======================================================================

_MAIN_ROW_HALF = 18.0
"""Meia altura da faixa de realce da raiz. O texto dela e desenhado com
`anchor="center"`, e a faixa e centrada no mesmo `y`."""

MAIN_PLAY = 0
MAIN_ACHIEVEMENTS = 1
MAIN_OPTIONS = 2
MAIN_QUIT = 3

_MAIN_ROWS = (
    ("JOGAR", "escolher o modo e a fase"),
    ("CONQUISTAS", "o que você já entendeu"),
    ("OPÇÕES", "som, tela e progresso"),
    ("SAIR", ""),
)


class MainMenuScreen:
    """
    A primeira tela, e a que faltava.

    Antes o jogo abria direto na escolha de modo, e nao havia porta nenhuma
    pra conquistas, opcoes ou sair -- ESC ali simplesmente fechava a janela.
    Uma tela que so faz uma pergunta ("um ou dois?") nao e uma raiz: e um
    passo do caminho, e passou a ser exatamente isso.

    Vertical, quatro itens, com a legenda do escolhido embaixo. O que um menu
    de quatro botoes precisa entregar e onde cada porta vai dar.
    """

    def __init__(self) -> None:
        self.selected = MAIN_PLAY

    def move(self, step: int) -> None:
        if step:
            self.selected = max(0, min(len(_MAIN_ROWS) - 1, self.selected + step))

    def draw(self, renderer: IRenderer, completed: int, total: int,
             unlocked: int, achievement_total: int, ending: str = "") -> None:
        width, height = renderer.get_viewport_size()
        renderer.draw_ui_rect(0.0, 0.0, width, height, _VOID)
        center = width / 2.0

        renderer.draw_text(center, 70.0, "PENUMBRA", 60, _TEXT, anchor="center")
        renderer.draw_text(center, 144.0, "Luz e Sombra: Dualidade", 16, _GOLD, anchor="center")
        renderer.draw_ui_rect(center - 210.0, 180.0, 420.0, 1.0, _RULE)

        top = 220.0
        for index, (label, _) in enumerate(_MAIN_ROWS):
            y = top + index * 46.0
            chosen = index == self.selected
            if chosen:
                # `anchor="center"` ancora o CENTRO vertical do texto, nao o
                # topo -- entao a faixa tem de ser centrada em `y` tambem.
                # Posiciona-la a partir de `y` como se fosse topo a joga
                # inteira pra baixo da palavra, que foi o que aconteceu.
                renderer.draw_ui_rect(center - 150.0, y - _MAIN_ROW_HALF, 300.0,
                                      2.0 * _MAIN_ROW_HALF, _CARD_SELECTED)
                renderer.draw_ui_rect(center - 150.0, y - _MAIN_ROW_HALF, 3.0,
                                      2.0 * _MAIN_ROW_HALF, _GOLD)
            renderer.draw_text(center, y, label, 22,
                               _GOLD if chosen else _TEXT_DIM, anchor="center")

        renderer.draw_text(center, top + len(_MAIN_ROWS) * 46.0 + 8.0,
                           _MAIN_ROWS[self.selected][1], 12, _TEXT_FAINT, anchor="center")

        # A escolha do fim era gravada e nunca mais dita. O jogo faz uma
        # pergunta grave na ultima tela e depois esquecia a resposta -- o que
        # transforma a decisao em formalidade. Ela fica aqui, na raiz, que e
        # onde se volta pra saber onde a gente parou.
        if ending:
            renderer.draw_text(
                center, top + len(_MAIN_ROWS) * 46.0 + 34.0,
                "no fim, vocês se fundiram" if ending == "fundidos"
                else "no fim, vocês seguiram dois",
                12, _GOLD, anchor="center",
            )

        renderer.draw_ui_rect(center - 210.0, height - 96.0, 420.0, 1.0, _RULE)
        renderer.draw_text(
            center, height - 78.0,
            f"{completed}/{total} fases      {unlocked}/{achievement_total} conquistas",
            13, _TEXT_DIM, anchor="center",
        )
        renderer.draw_text(center, height - 52.0, "W/S escolher      ESPAÇO confirmar",
                           12, _TEXT_FAINT, anchor="center")
        # Creditos. A engine e MPL-2.0 e o jogo a usa inteira; nao credita-la
        # dentro do proprio jogo seria uma omissao, nao uma economia de tela.
        renderer.draw_text(center, height - 28.0,
                           "sobre a OuroborosEngine  ·  EzioMilanoX", 10,
                           _TEXT_FAINT, anchor="center")


class AchievementsScreen:
    """
    As dez, e o que cada uma reconhece.

    As que faltam aparecem com titulo e descricao LEGIVEIS, e nao ocultas:
    elas sao a lista do que o jogo considera ter entendido alguma coisa.
    Escondidas, deixariam de ser um convite e virariam so um placar.
    """

    def draw(self, renderer: IRenderer, unlocked, shards: int, total: int) -> None:
        width, height = renderer.get_viewport_size()
        renderer.draw_ui_rect(0.0, 0.0, width, height, _VOID)
        center = width / 2.0

        renderer.draw_text(center, 22.0, "CONQUISTAS", 32, _TEXT, anchor="center")
        got = sum(1 for a in achievements.CATALOG if a.key in unlocked)
        whole = got == len(achievements.CATALOG)
        renderer.draw_text(center, 62.0, f"{got} de {len(achievements.CATALOG)}", 14,
                           _GOLD if whole else _TEXT_DIM, anchor="center")
        renderer.draw_ui_rect(center - 320.0, 88.0, 640.0, 1.0, _RULE)

        # Onze linhas tem de caber ACIMA do rodape. A decima primeira chegou
        # com o segredo, e a altura antiga (44) punha o fundo dela por cima do
        # texto de baixo -- o tipo de coisa que so aparece quando a lista
        # cresce, que e sempre depois de a tela estar pronta.
        top = 100.0
        row_height = 40.0
        for index, achievement in enumerate(achievements.CATALOG):
            y = top + index * row_height
            has = achievement.key in unlocked
            if has:
                renderer.draw_ui_rect(center - 320.0, y - 4.0, 640.0, row_height - 8.0, _CARD)
                renderer.draw_ui_rect(center - 320.0, y - 4.0, 3.0, row_height - 8.0, _GOLD)
            # A escondida so se revela depois de achada: uma lista que a
            # mostrasse deixaria de haver segredo, e uma que nunca a
            # mostrasse tiraria do jogador a chance de saber que achou algo
            # que o jogo guardava.
            secret = achievement.hidden and not has
            title = "???" if secret else achievement.title
            detail = "há algo que o jogo não conta." if secret else achievement.description
            renderer.draw_text(center - 306.0, y, title, 15,
                               _GOLD if has else _TEXT_FAINT)
            renderer.draw_text(center - 306.0, y + 19.0, detail, 11,
                               _TEXT_DIM if has else _TEXT_FAINT)
            renderer.draw_text(center + 306.0, y + 7.0, "feito" if has else "-", 12,
                               _GOLD if has else _GOLD_DIM, anchor="topright")

        renderer.draw_text(center, height - 40.0,
                           f"fragmentos da fonte  {shards}/{total}          ESC volta",
                           12, _TEXT_FAINT, anchor="center")


OPTION_SOUND = 0
OPTION_VOLUME = 1
OPTION_MUSIC = 2
OPTION_FULLSCREEN = 3
OPTION_ERASE = 4

_OPTION_ROWS = ("SOM", "EFEITOS", "MÚSICA", "TELA CHEIA", "APAGAR PROGRESSO")


class OptionsScreen:
    """
    Quatro linhas, e a ultima pede confirmacao.

    Apagar o progresso fica no mesmo lugar que o volume porque e ali que o
    jogador vai procurar -- mas exige um segundo ESPAÇO, com o aviso escrito
    na propria linha. Um menu que apaga trinta fases num toque e hostil; um
    que esconde a opcao e um menu que mente.
    """

    def __init__(self) -> None:
        self.selected = OPTION_SOUND
        self.confirm_erase = False

    def move(self, step: int) -> None:
        if step:
            self.selected = max(0, min(len(_OPTION_ROWS) - 1, self.selected + step))
            # Sair da linha cancela a confirmacao: voltar a ela e comecar de
            # novo, porque a intencao de apagar nao sobrevive a uma distracao.
            self.confirm_erase = False

    def draw(self, renderer: IRenderer, sound_on: bool, volume: float,
             fullscreen: bool, completed: int, total: int, music: float = 0.5) -> None:
        width, height = renderer.get_viewport_size()
        renderer.draw_ui_rect(0.0, 0.0, width, height, _VOID)
        center = width / 2.0

        renderer.draw_text(center, 44.0, "OPÇÕES", 34, _TEXT, anchor="center")
        renderer.draw_ui_rect(center - 260.0, 96.0, 520.0, 1.0, _RULE)

        values = (
            "ligado" if sound_on else "desligado",
            f"{int(round(volume * 100))}%",
            f"{int(round(music * 100))}%",
            "sim" if fullscreen else "não",
            f"{completed} de {total} fases vencidas",
        )
        top = 132.0
        for index, label in enumerate(_OPTION_ROWS):
            y = top + index * 56.0
            chosen = index == self.selected
            if chosen:
                renderer.draw_ui_rect(center - 260.0, y - 8.0, 520.0, 40.0, _CARD_SELECTED)
                renderer.draw_ui_rect(center - 260.0, y - 8.0, 3.0, 40.0, _GOLD)
            renderer.draw_text(center - 244.0, y, label, 16,
                               _GOLD if chosen else _TEXT_DIM)
            renderer.draw_text(center + 244.0, y, values[index], 15,
                               _TEXT if chosen else _TEXT_DIM, anchor="topright")

            if index in (OPTION_VOLUME, OPTION_MUSIC):
                # A barra e o unico valor daqui que se le melhor em forma que
                # em numero: sao as unicas linhas que mudam em passos pequenos.
                level = volume if index == OPTION_VOLUME else music
                bar_y = y + 26.0
                renderer.draw_ui_rect(center - 244.0, bar_y, 488.0, 4.0, _RULE)
                renderer.draw_ui_rect(center - 244.0, bar_y, 488.0 * level, 4.0,
                                      _GOLD if sound_on else _GOLD_DIM)

        if self.selected == OPTION_ERASE:
            warning = ("Aperte ESPAÇO de novo para apagar. Não tem volta."
                       if self.confirm_erase
                       else "Apaga fases, fragmentos e conquistas.")
            renderer.draw_text(center, top + OPTION_ERASE * 56.0 + 28.0, warning, 12,
                               _PERIL if self.confirm_erase else _TEXT_FAINT, anchor="center")

        renderer.draw_ui_rect(center - 260.0, height - 92.0, 520.0, 1.0, _RULE)
        renderer.draw_text(center, height - 72.0,
                           "W/S escolher      A/D ajustar      ESPAÇO alternar      ESC volta",
                           12, _TEXT_FAINT, anchor="center")


INTERLUDE_LINE_SECONDS = 1.6
"""Uma linha a cada 1,6 s: o tempo de ler uma frase curta e esperar a
proxima. Quem nao quer esperar aperta ESPAÇO e ve tudo de uma vez."""
_INTERLUDE_FADE = 0.7


class InterludeScreen:
    """A fala na porta de um capitulo: o titulo e as linhas, uma por vez.

    Preto, branco e dourado, como o resto: o titulo do capitulo em dourado (e
    a unica coisa da tela que pede os dois), o texto em branco baixo, e nada
    desenhado alem disso -- uma tela de fala que tivesse imagem competiria
    com a frase."""

    def draw(self, renderer: IRenderer, interlude, elapsed: float, pads: int = 0) -> None:
        width, height = renderer.get_viewport_size()
        renderer.draw_ui_rect(0.0, 0.0, width, height, _VOID)
        center = width / 2.0
        renderer.draw_text(center, 150.0, interlude.title, 22, _GOLD, anchor="center")
        renderer.draw_ui_rect(center - 160.0, 182.0, 320.0, 1.0, _RULE)

        for index, line in enumerate(interlude.lines):
            shown = elapsed - index * INTERLUDE_LINE_SECONDS
            if shown <= 0.0:
                break
            fade = min(1.0, shown / _INTERLUDE_FADE)
            tone = tuple(int(c * fade + v * (1.0 - fade)) for c, v in zip(_TEXT[:3], _VOID[:3])) + (255,)
            renderer.draw_text(center, 230.0 + index * 40.0, line, 16, tone, anchor="center")

        if interlude_done(interlude, elapsed):
            renderer.draw_text(center, height - 60.0,
                               "A continuar" if pads else "ESPAÇO continuar",
                               12, _TEXT_FAINT, anchor="center")


def interlude_done(interlude, elapsed: float) -> bool:
    """Todas as linhas ja apareceram."""
    return elapsed >= (len(interlude.lines) - 1) * INTERLUDE_LINE_SECONDS + _INTERLUDE_FADE
