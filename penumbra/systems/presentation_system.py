"""
Traducao do estado para pixels: uma entidade visual por celula da grade.

Paleta deliberadamente minima -- preto, branco e um terceiro tom dourado. O
dourado nao decora: ele aparece SO no que exige os dois seres ao mesmo tempo
(zonas de polaridade, a porta que elas destrancam, os dois portais). Quando
a tela mostra dourado, o jogador esta olhando para o unico tipo de problema
que nenhum dos dois resolve sozinho.

As celulas nao sao redesenhadas por um laco Python: as 880 entidades de
celula existem do primeiro ao ultimo frame do processo (nenhuma e criada ou
destruida nem quando a fase troca), suas linhas densas sao resolvidas uma
vez na composicao, e este sistema so reescreve colunas inteiras de tint/
escala com ufuncs NumPy.
"""
from __future__ import annotations

import math

import numpy as np

from ouroboros.core.systems.base_system import ISystem
from ouroboros.core.world import World
from ouroboros.interfaces.renderer import SHAPE_CIRCLE, SHAPE_RECT, SHAPE_RING

from penumbra.state import DualityState, LUMEN, UMBRA
from penumbra.terrain import (
    ROLE_DOOR,
    ROLE_EMPTY,
    ROLE_ETHER,
    ROLE_LAMP,
    ROLE_LUMEN_GOAL,
    ROLE_PLATE,
    ROLE_SHARD,
    ROLE_ROCK,
    ROLE_BEACON,
    ROLE_COUNTER_ETHER,
    ROLE_CRUST,
    ROLE_ECLIPSE,
    ROLE_UMBRA_GOAL,
    ROLE_ZONE_LIGHT,
    ROLE_ZONE_SHADOW,
    ROLE_ALTAR,
    ROLE_WANDER,
    ROLE_VEIL,
    ROLE_GLASS,
    ROLE_SOURCE,
    ROLE_SOURCE_ALT,
    ROLE_LEVER,
    Terrain,
)
from penumbra.tuning import DualityTuning

# --- terceiro tom: dourado, reservado ao que e cooperativo ---
GOLD_DIM = (96, 76, 38)
GOLD = (196, 158, 82)
GOLD_BRIGHT = (247, 214, 138)

# --- rocha: o chao neutro, cinza-azulado ---
ROCK_UNLIT = (52, 54, 66)
ROCK_LIT = (170, 174, 190)
"""A rocha apagada precisa ser VISIVEL, nao apenas existir. Ela e o chao
neutro -- o unico lugar onde um ser espera em seguranca enquanto o jogador
comanda o outro -- entao saber onde ela esta e a informacao com que o
jogador planeja a sequencia inteira. A primeira versao usava (25,25,33)
sobre um fundo (8,8,14): num nivel majoritariamente apagado nao se enxergava
onde estava o chao."""

# --- eter: a materia potencial, o unico terreno que troca de dono ---
ETHER_SHADOW_DEEP = (58, 54, 78)
ETHER_SHADOW_EDGE = (104, 98, 132)
ETHER_LIT_EDGE = (170, 176, 210)
ETHER_LIT_FULL = (244, 248, 255)

# --- luz no ar: branco frio, translucido ---
AIR_GLOW = (206, 218, 255)
AIR_GLOW_MAX_ALPHA = 100.0
"""Quanto a luz no ar pode brilhar.

Era 62, e era baixo POR CAUSA da grade: com a luz desenhada em quadrados de
32 px, qualquer valor mais alto escancarava o tabuleiro. Com o fundo em
resolucao dobrada essa amarra caiu, e o ar pode finalmente parecer aceso.

O teto e 140: acima disso o escuro perde profundidade e o bolsao de escuridao
que a Umbra carrega deixa de se distinguir do fundo -- e ele e a unica coisa
na tela que diz onde ela sobrevive."""
"""O brilho no ar e atmosfera, nao informacao. A 118 ele era o elemento mais
claro da tela e lia como neblina por cima do nivel, abafando justamente o
terreno que o jogador precisa ver."""

# --- crosta: o unico terreno que a Umbra rompe ---
CRUST_UNLIT = (78, 64, 56)
CRUST_LIT = (198, 172, 146)
"""Tom QUENTE, e e a unica quebra deliberada da paleta preto/branco/dourado
no terreno. Rocha e eter ja se distinguem por forma (massa continua contra
blocos recuados); uma terceira forma seria fina demais pra ler no escuro, e
a crosta e justamente o terreno em que o jogador precisa reconhecer de
longe -- e a unica coisa no jogo que so um dos dois resolve. Quente contra o
cinza-azulado da rocha se le mesmo com pouca luz."""

LAMP_ON = (255, 250, 232)
LAMP_SNUFFED = (74, 70, 86)
BEACON_OFF = (92, 88, 104)

PLATE_IDLE = (108, 88, 46)
PLATE_PRESSED = (247, 214, 138)
SHARD = (247, 214, 138)

ECLIPSE_CALM = (168, 136, 72)
ECLIPSE_URGENT = (250, 222, 150)
"""A zona de eclipse e a unica celula que aceita os DOIS -- e por isso o
unico terreno em dourado, o tom que o jogo reserva ao que exige os dois ao
mesmo tempo. Ela clareia e pulsa mais rapido conforme o prazo se esgota: o
aviso tem de estar no proprio chao, nao so numa barra do HUD, porque e no
chao que o jogador esta olhando."""

LUMEN_BODY = (250, 250, 255)
LUMEN_FADING = (104, 104, 134)
UMBRA_BODY = (32, 30, 44)
UMBRA_DISSOLVING = (164, 154, 196)
UMBRA_RIM = (138, 136, 162)

ALTAR_EMPTY = (96, 92, 120)
ALTAR_CHARGING = (206, 186, 134)
ALTAR_LUMEN = (250, 246, 226)
ALTAR_UMBRA = (58, 50, 84)
"""Um altar vazio e pedra fria; carregando, esquenta; e depois fica com a cor
do que guarda -- branco se a Lumen deixou a luz, quase-preto se a Umbra deixou
a escuridao. A cor final nao e enfeite: e o unico jeito de o jogador olhar a
tela e lembrar QUAL das duas formas ele ja gastou."""

RAIL = (52, 50, 68)
"""O trilho da lanterna, apagado. Ele so precisa dizer 'a luz passa por aqui e
volta' -- se competisse em brilho com a propria lanterna, a unica coisa que
importa (onde ela esta AGORA) ficaria mais dificil de achar."""

VEIL = (30, 26, 44)
VEIL_EDGE = (72, 64, 104)
"""O veu e a unica celula que se atravessa a pe e nao se atravessa com luz.
Ele precisa ler como CORTINA e nao como parede: por isso preenche a celula
inteira (como a rocha) mas num roxo fechado, quase sem contraste com o
fundo -- o que ele comunica e "aqui nao chega nada", nao "aqui voce para"."""

GLASS = (146, 168, 196)
"""Vidro: chao dos dois, e a luz passa. Fica numa fita FINA no meio da
celula, e nao preenchendo-a, porque a leitura que ele precisa entregar e
"da pra pisar, e da pra ver atraves" -- uma celula cheia diria o contrario
das duas coisas."""

SOURCE_CALM = (120, 104, 150)
SOURCE_FULL = (255, 246, 226)

LEVER_IDLE = (116, 106, 150)
LEVER_THROWN = (214, 176, 240)
"""A alavanca e o unico objeto do jogo cujo estado nao se le no terreno ao
redor: eter e contra-eter trocados continuam sendo eter e contra-eter. Ela
mesma tem de dizer de que lado esta, e por isso muda de cor em vez de so
pulsar."""

_ROLE_COUNT = 22
_CELL_SPRITE_UNIT = 8.0
"""`PygameRenderer.draw_batch` converte `transform.scale` em pixels
multiplicando por 8 (a unidade de forma primitiva do Pilar 2) -- uma celula
de `cell_size` px pede, portanto, `scale = cell_size / 8`."""

BACKDROP_FACTOR = 2
"""Quantos sub-quadros por lado cada celula do fundo vira.

Medido, nao escolhido: a 1x a luz le como um tabuleiro de xadrez, a 2x ela
ja le como luz, e a 4x fica lisa de verdade -- e custa 21 ms so de desenho,
contra os 16,7 ms que um frame inteiro tem. `PygameRenderer.draw_batch` e um
laco Python a 2,8 us por entidade, entao a resolucao do fundo e um orcamento,
nao um gosto. A 2x sao 1904 sub-quadros e ~5 ms no pior caso; na pratica bem
menos, porque `_draw_shape` sai cedo com alpha zero e a maior parte de um
nivel esta no escuro."""

_AIR_STRETCH = (0.30, 0.12)
"""Quanto cada ser se alonga no ar, por (Lumen, Umbra).

A assimetria dos dois so existia em NUMERO -- velocidade, altura de salto,
tempo de medidor. O jogador lia "agil" e "pesada" numa tabela de tuning e via
dois blocos deslizando igual. A Lumen se estica no ar porque e leve; a Umbra
quase nao, porque peso nao flutua."""

_LAND_SQUASH = (0.22, 0.28)
"""E quanto cada uma AMASSA ao pousar. Aqui a ordem se inverte de proposito:
a que mal se estica no ar e a que chega ao chao com tudo. E o mesmo fato --
massa -- dito nos dois momentos em que ele aparece."""

_LAND_RECOVER = (0.13, 0.30)
"""Segundos ate a amassada passar. A Umbra leva mais que o dobro: a diferenca
entre um quique e um baque nao esta na profundidade, esta em quanto tempo o
corpo leva pra voltar. Uma amassada funda que some rapido le como elastico,
que e o contrario do que ela e."""

_LAND_TRIGGER = 90.0
"""Velocidade de queda (px/s) abaixo da qual o pouso nao merece amassada.
Descer um degrau nao e um baque, e amassar a cada passo faria o corpo tremer
sem parar -- o oposto de peso."""

_STILL_FALL = _LAND_TRIGGER * 0.25
"""Abaixo disto o ser conta como PARADO, na vertical.

Nao e zero, e a diferenca importa: parado no chao, a gravidade do frame ainda
escreve uns 18 px/s antes de a colisao zerar. Medindo contra zero, os dois
ficavam permanentemente 1% esticados e 1% estreitos -- pequeno demais pra
alguem apontar, e presente em todo frame de todas as trinta fases. Um corpo
em repouso tem de ter o tamanho dele."""

_STRETCH_LIMITS = (0.72, 1.34)
"""Teto e piso do alongamento, e o piso tem uma razao exata.

O sprite escala em torno do CENTRO -- a posicao da entidade e o centro dela, e
posicao e estado de jogo, que a apresentacao nao move. Entao toda amassada
levanta os pes do chao em `half_height * (1 - escala)`: a 0.66 a Umbra
flutuaria 4,7 px sobre a rocha, quase um sexto do corpo, e o baque leria como
pulinho. A 0.72 sao 3,9 px, e por baixo de 4 px isso e o borrao de um impacto
em vez de um ser solto no ar.

O teto e outra coisa: sem ele uma queda longa o bastante viraria um risco
vertical, e a silhueta e a unica coisa que diz QUEM e cada um."""

_PULSE_HZ = 1.15


class PresentationSystem(ISystem):
    """
    Reescreve `sprite`/`transform` das entidades puramente visuais.

    Nao le input, nao move ninguem, nao decide nada: se este sistema fosse
    removido, o jogo continuaria funcionando exatamente igual e ficaria
    invisivel. E por isso que ele e o ultimo da lista.
    """

    def __init__(
        self,
        terrain: Terrain,
        state: DualityState,
        tuning: DualityTuning,
        cell_entity_indices: np.ndarray,
        aura_entity_indices: np.ndarray,
        backdrop_entity_indices: np.ndarray = None,
    ) -> None:
        self._terrain = terrain
        self._state = state
        self._tuning = tuning
        self._cell_entity_indices = cell_entity_indices
        self._aura_entity_indices = aura_entity_indices
        self._backdrop_entity_indices = backdrop_entity_indices
        self._backdrop_sprite_rows = None
        self._sprite_pool = None
        self._transform_pool = None
        self._cell_sprite_rows = None
        self._cell_transform_rows = None
        self._elapsed = 0.0

        cell_count = terrain.rows * terrain.cols
        self._red = np.zeros(cell_count, dtype=np.float32)
        self._green = np.zeros(cell_count, dtype=np.float32)
        self._blue = np.zeros(cell_count, dtype=np.float32)
        self._alpha = np.zeros(cell_count, dtype=np.float32)
        self._ramp = np.zeros(cell_count, dtype=np.float32)
        self._channel = np.zeros(cell_count, dtype=np.float32)
        self._mask = np.zeros(cell_count, dtype=bool)
        self._mask_alt = np.zeros(cell_count, dtype=bool)

        self._make_backdrop_buffers(terrain)

        # Memoria de APRESENTACAO: nenhuma regra do jogo pergunta com que
        # forca alguem pousou no frame passado.
        self._velocity_pool = None
        self._impact = np.zeros(2, dtype=np.float32)
        self._last_fall = np.zeros(2, dtype=np.float32)
        self._shaped_level = -1
        self._base_scale = (
            (tuning.lumen.half_width * 2.0 / _CELL_SPRITE_UNIT,
             tuning.lumen.half_height * 2.0 / _CELL_SPRITE_UNIT),
            (tuning.umbra.half_width * 2.0 / _CELL_SPRITE_UNIT,
             tuning.umbra.half_height * 2.0 / _CELL_SPRITE_UNIT),
        )
        # A velocidade de salto e a escala natural do movimento vertical de
        # cada um: cair mais rapido do que se consegue saltar e o que conta
        # como queda de verdade. `abs` porque saltar e para CIMA, e para cima
        # e negativo.
        self._fall_reference = (
            abs(float(tuning.lumen.jump_velocity_y)),
            abs(float(tuning.umbra.jump_velocity_y)),
        )

        # role -> forma primitiva / fracao de uma celula ocupada. Escritos
        # a cada frame por `np.take` (a fase pode trocar sem que este
        # sistema saiba: nao existe gancho de "fase carregada" aqui).
        self._shape_by_role = np.full(_ROLE_COUNT, SHAPE_RECT, dtype=np.uint32)
        self._shape_by_role[ROLE_LAMP] = SHAPE_CIRCLE
        self._shape_by_role[ROLE_LUMEN_GOAL] = SHAPE_RING
        self._shape_by_role[ROLE_UMBRA_GOAL] = SHAPE_RING
        # Zonas ficam RECT (placa no chao), portais ficam RING (destino).
        # Como aneis os dois eram dourados e quase do mesmo tamanho, e nada
        # na tela dizia qual era onde pisar e qual era onde terminar.
        self._size_by_role = np.ones(_ROLE_COUNT, dtype=np.float32)
        self._size_by_role[ROLE_LAMP] = 0.62
        self._size_by_role[ROLE_LUMEN_GOAL] = 0.92
        self._size_by_role[ROLE_UMBRA_GOAL] = 0.92
        self._size_by_role[ROLE_ZONE_LIGHT] = 0.8
        self._size_by_role[ROLE_ZONE_SHADOW] = 0.8
        # Eter RECUADO na celula, rocha sangrando ate a borda: a distincao
        # mais importante da tela nao pode depender so de brilho, porque os
        # dois terrenos passam a maior parte do tempo apagados e a essa
        # altura nenhum matiz se le. Recuado, o eter mostra uma grade de
        # blocos soltos; a rocha, uma massa continua.
        self._size_by_role[ROLE_ETHER] = 0.82
        self._size_by_role[ROLE_CRUST] = 0.9
        self._size_by_role[ROLE_BEACON] = 0.62
        # Contra-eter: mesma familia do eter, recuado AINDA mais (rede fina
        # em vez de blocos), e com o gradiente invertido -- claro no escuro,
        # escuro na luz. A inversao tem de se ver de longe, porque a regra
        # dele e literalmente a do eter ao contrario.
        self._size_by_role[ROLE_COUNTER_ETHER] = 0.6
        self._size_by_role[ROLE_PLATE] = 0.86
        self._size_by_role[ROLE_SHARD] = 0.52
        self._shape_by_role[ROLE_SHARD] = SHAPE_RING
        self._shape_by_role[ROLE_BEACON] = SHAPE_CIRCLE
        # Altar: anel de pedra, do tamanho de uma placa. Anel e nao retangulo
        # porque ele e um RECIPIENTE -- a leitura tem de ser 'cabe algo aqui'.
        self._shape_by_role[ROLE_ALTAR] = SHAPE_RING
        self._size_by_role[ROLE_ALTAR] = 0.78
        # Trilho: fita fina no meio da celula, pra nao parecer chao.
        self._size_by_role[ROLE_WANDER] = 0.3
        # Vidro: fita fina TAMBEM, mas larga e clara -- e chao, so que se ve
        # atraves. Trilho e vidro nunca aparecem na mesma linha.
        self._size_by_role[ROLE_GLASS] = 0.44
        self._shape_by_role[ROLE_SOURCE] = SHAPE_CIRCLE
        self._size_by_role[ROLE_SOURCE] = 0.74
        self._shape_by_role[ROLE_SOURCE_ALT] = SHAPE_CIRCLE
        self._size_by_role[ROLE_SOURCE_ALT] = 0.74
        self._size_by_role[ROLE_LEVER] = 0.7
        self._cell_scale = np.float32(terrain.cell_size / _CELL_SPRITE_UNIT)
        self._eclipse_seconds = tuning.flow.eclipse_collapse_seconds
        self._echo_seconds = tuning.flow.echo_seconds
        self._source_min = tuning.flow.source_min_intensity
        self._source_max = tuning.flow.source_max_intensity

    def update(self, world: World, delta_time: float) -> None:
        if self._sprite_pool is None:
            self._resolve_pools(world)
        self._elapsed += delta_time
        self._paint_backdrop()
        self._paint_cells()
        self._paint_characters()
        self._shape_characters(delta_time)
        self._paint_auras()

    # ------------------------------------------------------------------
    # composicao tardia
    # ------------------------------------------------------------------

    def _resolve_pools(self, world: World) -> None:
        """As linhas densas das celulas sao resolvidas UMA vez e guardadas.

        Isso e seguro -- e nao um cache que pode envelhecer -- porque
        nenhuma entidade de Penumbra e destruida em nenhum momento: sem
        `detach`, o swap-remove que invalidaria estas linhas nunca
        acontece. Trocar de fase recarrega mascaras, nao entidades."""
        self._sprite_pool = world.get_pool("sprite")
        self._transform_pool = world.get_pool("transform")
        self._velocity_pool = world.get_pool("velocity")
        self._cell_sprite_rows = self._sprite_pool.dense_rows_of(self._cell_entity_indices)
        self._cell_transform_rows = self._transform_pool.dense_rows_of(self._cell_entity_indices)
        if self._backdrop_entity_indices is not None:
            self._backdrop_sprite_rows = self._sprite_pool.dense_rows_of(
                self._backdrop_entity_indices)

    # ------------------------------------------------------------------
    # o fundo: ar e rocha, em resolucao dobrada
    # ------------------------------------------------------------------

    def _make_backdrop_buffers(self, terrain) -> None:
        """Pre-aloca tudo que `_paint_backdrop` toca.

        A interpolacao e SEPARAVEL -- uma passada vertical e uma horizontal,
        em vez das quatro formulas de canto -- porque assim cada peso vira um
        `np.multiply(..., out=)` sobre um buffer que ja existe, e o sistema
        continua sem alocar nada por frame."""
        factor = BACKDROP_FACTOR
        rows, cols = terrain.rows, terrain.cols
        fine_rows, fine_cols = rows * factor, cols * factor
        fine_count = fine_rows * fine_cols

        # Bordas repetidas (`mode="edge"`): fora da grade o mundo e solido,
        # e repetir a borda evita uma orla escura falsa no limite da tela.
        self._pad = np.zeros((rows + 2, cols + 2), dtype=np.float32)
        self._tall = np.zeros((fine_rows, cols + 2), dtype=np.float32)
        self._tall_a = np.zeros((rows, cols + 2), dtype=np.float32)
        self._tall_b = np.zeros((rows, cols + 2), dtype=np.float32)
        self._fine = np.zeros((fine_rows, fine_cols), dtype=np.float32)
        self._fine_a = np.zeros((fine_rows, cols), dtype=np.float32)
        self._fine_b = np.zeros((fine_rows, cols), dtype=np.float32)
        self._fine_role = np.zeros((fine_rows, fine_cols), dtype=np.uint8)

        self._bd_red = np.zeros(fine_count, dtype=np.float32)
        self._bd_green = np.zeros(fine_count, dtype=np.float32)
        self._bd_blue = np.zeros(fine_count, dtype=np.float32)
        self._bd_alpha = np.zeros(fine_count, dtype=np.float32)
        self._bd_ramp = np.zeros(fine_count, dtype=np.float32)
        self._bd_channel = np.zeros(fine_count, dtype=np.float32)
        self._bd_mask = np.zeros(fine_count, dtype=bool)

    def _refine(self, field: np.ndarray) -> np.ndarray:
        """Interpola `field` (uma grade de celulas) para a grade fina.

        O valor de uma celula vale no CENTRO dela, entao o centro de cada
        sub-quadro cai a um quarto de celula do centro -- pesos 0.75 e 0.25.
        E so isso que separa uma luz que parece luz de um tabuleiro de
        xadrez: sem interpolar, cada celula e um degrau de 32 px."""
        pad = self._pad
        pad[1:-1, 1:-1] = field
        pad[0, 1:-1] = field[0]
        pad[-1, 1:-1] = field[-1]
        pad[1:-1, 0] = field[:, 0]
        pad[1:-1, -1] = field[:, -1]
        # Os quatro cantos tambem: zera-los punha uma mancha escura em cada
        # canto da tela -- pequena, permanente, e sem nada no jogo que a
        # explicasse.
        pad[0, 0] = field[0, 0]
        pad[0, -1] = field[0, -1]
        pad[-1, 0] = field[-1, 0]
        pad[-1, -1] = field[-1, -1]

        center, above, below = pad[1:-1], pad[:-2], pad[2:]
        np.multiply(center, 0.75, out=self._tall_a)
        np.multiply(above, 0.25, out=self._tall_b)
        np.add(self._tall_a, self._tall_b, out=self._tall[0::2])
        np.multiply(below, 0.25, out=self._tall_b)
        np.add(self._tall_a, self._tall_b, out=self._tall[1::2])

        middle, left, right = self._tall[:, 1:-1], self._tall[:, :-2], self._tall[:, 2:]
        np.multiply(middle, 0.75, out=self._fine_a)
        np.multiply(left, 0.25, out=self._fine_b)
        np.add(self._fine_a, self._fine_b, out=self._fine[:, 0::2])
        np.multiply(right, 0.25, out=self._fine_b)
        np.add(self._fine_a, self._fine_b, out=self._fine[:, 1::2])
        return self._fine

    def _paint_backdrop(self) -> None:
        """Ar e rocha, e mais nada.

        Sao os DOIS unicos papeis da grade que nao carregam decisao: o ar nao
        e chao de ninguem, a rocha e chao dos dois, sempre. Todo o resto --
        eter, contra-eter, crosta, placa, portal -- responde "de quem e este
        chao, agora?", e essa resposta tem de ser lida na celula exata. Por
        isso o fundo interpola e as celulas nao: suavizar o que o jogador
        precisa medir seria trocar atmosfera por erro.

        O papel e repetido sem interpolar (a silhueta da rocha continua na
        aresta da celula); so a LUZ e interpolada."""
        if self._backdrop_sprite_rows is None:
            return
        terrain, state = self._terrain, self._state

        fine = self._refine(state.display_light).reshape(-1)
        role_grid = terrain.role
        self._fine_role[0::2, 0::2] = role_grid
        self._fine_role[0::2, 1::2] = role_grid
        self._fine_role[1::2, 0::2] = role_grid
        self._fine_role[1::2, 1::2] = role_grid
        role = self._fine_role.reshape(-1)

        np.clip(fine, 0.0, 1.0, out=self._bd_ramp)
        self._bd_alpha[:] = 0.0

        # rocha: opaca, revelada pela luz que a banha
        np.equal(role, ROLE_ROCK, out=self._bd_mask)
        self._bd_fill(ROCK_UNLIT, ROCK_LIT)
        np.copyto(self._bd_alpha, 255.0, where=self._bd_mask)

        # ar: a luz em si, translucida sobre o vazio
        np.equal(role, ROLE_EMPTY, out=self._bd_mask)
        self._bd_fill(AIR_GLOW, AIR_GLOW)
        np.multiply(self._bd_ramp, AIR_GLOW_MAX_ALPHA, out=self._bd_channel)
        np.copyto(self._bd_alpha, self._bd_channel, where=self._bd_mask)

        sprite_view = self._sprite_pool.active_view()
        rows = self._backdrop_sprite_rows
        sprite_view["tint_r"][rows] = self._bd_red
        sprite_view["tint_g"][rows] = self._bd_green
        sprite_view["tint_b"][rows] = self._bd_blue
        sprite_view["tint_a"][rows] = self._bd_alpha

    def _bd_fill(self, color_low, color_high) -> None:
        """`_fill` da grade fina -- mesma conta, outros buffers."""
        for channel, low, high in (
            (self._bd_red, color_low[0], color_high[0]),
            (self._bd_green, color_low[1], color_high[1]),
            (self._bd_blue, color_low[2], color_high[2]),
        ):
            if low == high:
                np.copyto(channel, float(low), where=self._bd_mask)
                continue
            np.multiply(self._bd_ramp, float(high - low), out=self._bd_channel)
            np.add(self._bd_channel, float(low), out=self._bd_channel)
            np.copyto(channel, self._bd_channel, where=self._bd_mask)

    # ------------------------------------------------------------------
    # celulas
    # ------------------------------------------------------------------

    def _paint_cells(self) -> None:
        state, terrain = self._state, self._terrain
        light = state.display_light.reshape(-1)
        role = terrain.role.reshape(-1)
        threshold = self._tuning.light.solid_threshold
        pulse = 0.5 + 0.5 * math.sin(self._elapsed * _PULSE_HZ * math.tau)

        self._red[:] = 0.0
        self._green[:] = 0.0
        self._blue[:] = 0.0
        self._alpha[:] = 0.0

        # Ar e rocha nao sao pintados aqui: sao o FUNDO, desenhado em
        # resolucao dobrada por `_paint_backdrop`. Ficam com alpha zero, e
        # `_draw_shape` sai cedo sem desenhar nada.

        # eter aceso: chao da Lumen
        np.equal(role, ROLE_ETHER, out=self._mask)
        np.logical_and(self._mask, state.lit.reshape(-1), out=self._mask_alt)
        self._ramp_between(light, threshold, 1.0)
        self._fill(self._mask_alt, ETHER_LIT_EDGE, ETHER_LIT_FULL)
        np.copyto(self._alpha, 255.0, where=self._mask_alt)

        # eter apagado: chao da Umbra
        np.logical_and(self._mask, np.logical_not(state.lit.reshape(-1)), out=self._mask_alt)
        self._ramp_between(light, 0.0, threshold)
        self._fill(self._mask_alt, ETHER_SHADOW_DEEP, ETHER_SHADOW_EDGE)
        np.copyto(self._alpha, 255.0, where=self._mask_alt)

        # lampadas: acesas, ou engolidas pelo bolsao de escuridao da Umbra
        np.equal(role, ROLE_LAMP, out=self._mask)
        np.logical_and(self._mask, np.logical_not(state.absorbed.reshape(-1)), out=self._mask_alt)
        self._fill(self._mask_alt, LAMP_ON, LAMP_ON)
        np.copyto(self._alpha, 255.0, where=self._mask_alt)
        np.logical_and(self._mask, state.absorbed.reshape(-1), out=self._mask_alt)
        self._fill(self._mask_alt, LAMP_SNUFFED, LAMP_SNUFFED)
        np.copyto(self._alpha, 190.0, where=self._mask_alt)

        # crosta: quente, e encolhendo enquanto a Umbra a empurra
        np.equal(role, ROLE_CRUST, out=self._mask)
        np.clip(light, 0.0, 1.0, out=self._ramp)
        self._fill(self._mask, CRUST_UNLIT, CRUST_LIT)
        np.copyto(self._alpha, 255.0, where=self._mask)

        # contra-eter: o espelho do eter, com o gradiente ao contrario
        np.equal(role, ROLE_COUNTER_ETHER, out=self._mask)
        np.logical_and(self._mask, np.logical_not(state.lit.reshape(-1)), out=self._mask_alt)
        self._ramp_between(light, threshold, 0.0)
        self._fill(self._mask_alt, ETHER_LIT_EDGE, ETHER_LIT_FULL)
        np.copyto(self._alpha, 255.0, where=self._mask_alt)
        np.logical_and(self._mask, state.lit.reshape(-1), out=self._mask_alt)
        self._ramp_between(light, 1.0, threshold)
        self._fill(self._mask_alt, ETHER_SHADOW_DEEP, ETHER_SHADOW_EDGE)
        np.copyto(self._alpha, 255.0, where=self._mask_alt)

        # placa de pressao: acende enquanto alguem esta em cima
        np.equal(role, ROLE_PLATE, out=self._mask)
        pressed = PLATE_PRESSED if state.door_open else PLATE_IDLE
        self._fill(self._mask, pressed, pressed)
        np.copyto(self._alpha, 235.0 if state.door_open else 130.0, where=self._mask)

        # fragmento da fonte: some quando apanhado
        np.equal(role, ROLE_SHARD, out=self._mask)
        self._fill(self._mask, SHARD, SHARD)
        np.copyto(self._alpha, 0.0 if state.shard_collected else (170.0 + 70.0 * pulse), where=self._mask)

        # farol: aceso como lampada, apagado como brasa
        np.equal(role, ROLE_BEACON, out=self._mask)
        if state.beacon_on:
            self._fill(self._mask, LAMP_ON, LAMP_ON)
            np.copyto(self._alpha, 255.0, where=self._mask)
        else:
            self._fill(self._mask, BEACON_OFF, BEACON_OFF)
            np.copyto(self._alpha, 190.0, where=self._mask)

        # veu: cortina que a luz nao atravessa e os pes atravessam
        np.equal(role, ROLE_VEIL, out=self._mask)
        self._fill(self._mask, VEIL, VEIL_EDGE)
        np.copyto(self._alpha, 218.0, where=self._mask)

        # vidro: chao transparente, revelado pela luz que o atravessa
        np.equal(role, ROLE_GLASS, out=self._mask)
        np.clip(light, 0.0, 1.0, out=self._ramp)
        self._fill(self._mask, GLASS, GLASS)
        np.copyto(self._alpha, 210.0, where=self._mask)

        # as duas fontes: cada uma clareia e incha junto com o proprio raio
        np.equal(role, ROLE_SOURCE, out=self._mask)
        self._ramp[:] = self._source_breath(state.source_intensity)
        self._fill(self._mask, SOURCE_CALM, SOURCE_FULL)
        np.copyto(self._alpha, 255.0, where=self._mask)

        np.equal(role, ROLE_SOURCE_ALT, out=self._mask)
        self._ramp[:] = self._source_breath(state.source_alt_intensity)
        self._fill(self._mask, SOURCE_CALM, SOURCE_FULL)
        np.copyto(self._alpha, 255.0, where=self._mask)

        # alavanca: a cor diz de que lado o mundo esta
        np.equal(role, ROLE_LEVER, out=self._mask)
        thrown = LEVER_THROWN if state.polarity_swapped else LEVER_IDLE
        self._fill(self._mask, thrown, thrown)
        np.copyto(self._alpha, 190.0 + 60.0 * pulse, where=self._mask)

        # trilho da lanterna (a lanterna em si e escrita no flush)
        np.equal(role, ROLE_WANDER, out=self._mask)
        self._fill(self._mask, RAIL, RAIL)
        np.copyto(self._alpha, 150.0, where=self._mask)

        # altar: pedra fria, esquentando enquanto recebe, e depois a forma
        np.equal(role, ROLE_ALTAR, out=self._mask)
        self._paint_altars(pulse)

        # zona de eclipse: dourada, clareando conforme o prazo se esgota
        np.equal(role, ROLE_ECLIPSE, out=self._mask)
        urgency = self._eclipse_urgency(pulse)
        self._ramp[:] = urgency
        self._fill(self._mask, ECLIPSE_CALM, ECLIPSE_URGENT)
        np.copyto(self._alpha, 255.0, where=self._mask)

        # porta: parede dourada enquanto trancada, contorno tenue depois
        np.equal(role, ROLE_DOOR, out=self._mask)
        if state.door_open:
            self._fill(self._mask, GOLD_DIM, GOLD_DIM)
            np.copyto(self._alpha, 52.0, where=self._mask)
        else:
            np.clip(light, 0.0, 1.0, out=self._ramp)
            self._fill(self._mask, GOLD_DIM, GOLD_BRIGHT)
            np.copyto(self._alpha, 255.0, where=self._mask)

        # zonas de polaridade: acendem quando a condicao delas e cumprida
        self._paint_zone(role, ROLE_ZONE_LIGHT, state.lit.reshape(-1), satisfied_when_lit=True)
        self._paint_zone(role, ROLE_ZONE_SHADOW, state.lit.reshape(-1), satisfied_when_lit=False)

        # portais: os dois pulsam, e ficam solidos quando ocupados
        self._paint_goal(role, ROLE_LUMEN_GOAL, LUMEN, pulse)
        self._paint_goal(role, ROLE_UMBRA_GOAL, UMBRA, pulse)

        self._flush_cells(role, pulse)

    def _source_breath(self, intensity: float) -> float:
        """0..1 entre as duas intensidades de uma fonte. O corpo dela clareia
        e incha junto com o raio que projeta -- sem isso o jogador leria a
        borda do chao aceso mexendo e nao teria onde olhar pra prever o
        proximo instante. Com duas fontes em contratempo isso deixa de ser
        conforto e passa a ser a unica leitura possivel da sala."""
        low, high = self._source_min, self._source_max
        if high <= low:
            return 1.0
        return min(1.0, max(0.0, (intensity - low) / (high - low)))

    def _paint_altars(self, pulse: float) -> None:
        """Tres estados num unico papel de celula: vazio, recebendo, cheio.

        `self._mask` ja chega marcada com os altares. O estado 'recebendo'
        vale so para o altar sob o ser que esta depositando AGORA -- um por
        ser, no maximo -- entao ele e escrito celula a celula (duas
        escalares) em vez de com mais uma mascara de 476 posicoes."""
        state = self._state
        altars = self._mask
        self._fill(altars, ALTAR_EMPTY, ALTAR_EMPTY)
        np.copyto(self._alpha, 120.0 + 50.0 * pulse, where=altars)

        light_flat = state.altar_light.reshape(-1)
        shadow_flat = state.altar_shadow.reshape(-1)
        np.logical_and(altars, light_flat > 0.0, out=self._mask_alt)
        self._fill(self._mask_alt, ALTAR_LUMEN, ALTAR_LUMEN)
        np.copyto(self._alpha, 255.0, where=self._mask_alt)
        np.logical_and(altars, shadow_flat > 0.0, out=self._mask_alt)
        self._fill(self._mask_alt, ALTAR_UMBRA, ALTAR_UMBRA)
        np.copyto(self._alpha, 255.0, where=self._mask_alt)

        cols = self._terrain.cols
        for side in (LUMEN, UMBRA):
            progress = float(state.altar_progress[side])
            if progress <= 0.0:
                continue
            slot = int(state.cell[side, 1]) * cols + int(state.cell[side, 0])
            self._red[slot] = _mix(ALTAR_EMPTY[0], ALTAR_CHARGING[0], progress)
            self._green[slot] = _mix(ALTAR_EMPTY[1], ALTAR_CHARGING[1], progress)
            self._blue[slot] = _mix(ALTAR_EMPTY[2], ALTAR_CHARGING[2], progress)
            self._alpha[slot] = 255.0

    def _eclipse_urgency(self, pulse: float) -> float:
        """0 antes de alguem pisar, subindo ate 1 no fim do prazo -- com um
        pulso que fica mais forte junto. Antes do primeiro toque a zona fica
        no tom calmo: o relogio dela ainda nao anda, e mostrar urgencia seria
        mentir."""
        state = self._state
        if not state.eclipse_touched or self._eclipse_seconds <= 0.0:
            return 0.0
        spent = 1.0 - max(0.0, state.eclipse_seconds_left) / self._eclipse_seconds
        return min(1.0, spent * (0.65 + 0.35 * pulse) + 0.2 * spent)

    def _paint_zone(
        self, role: np.ndarray, role_id: int, lit_flat: np.ndarray, satisfied_when_lit: bool
    ) -> None:
        np.equal(role, role_id, out=self._mask)
        if satisfied_when_lit:
            np.logical_and(self._mask, lit_flat, out=self._mask_alt)
        else:
            np.logical_and(self._mask, np.logical_not(lit_flat), out=self._mask_alt)
        # Uma zona precisa ser vista ANTES de ser cumprida -- e antes que
        # o jogador saiba onde ficar de pe, nao depois. A 44 de alpha ela
        # era invisivel exatamente quando importava, e a porta da fase 4
        # ficava sem pista nenhuma de como abrir.
        self._fill(self._mask, GOLD, GOLD)
        np.copyto(self._alpha, 120.0, where=self._mask)
        self._fill(self._mask_alt, GOLD_BRIGHT, GOLD_BRIGHT)
        np.copyto(self._alpha, 225.0, where=self._mask_alt)

    def _paint_goal(self, role: np.ndarray, role_id: int, side: int, pulse: float) -> None:
        np.equal(role, role_id, out=self._mask)
        occupied = bool(self._state.reached_goal[side])
        color = GOLD_BRIGHT if occupied else GOLD
        self._fill(self._mask, color, color)
        np.copyto(self._alpha, 255.0 if occupied else (150.0 + 70.0 * pulse), where=self._mask)

    def _flush_cells(self, role: np.ndarray, pulse: float) -> None:
        sprite_view = self._sprite_pool.active_view()
        rows = self._cell_sprite_rows
        sprite_view["tint_r"][rows] = self._red
        sprite_view["tint_g"][rows] = self._green
        sprite_view["tint_b"][rows] = self._blue
        sprite_view["tint_a"][rows] = self._alpha
        sprite_view["texture_id"][rows] = np.take(self._shape_by_role, role)

        # Escala: fracao da celula por papel, com os portais respirando.
        np.take(self._size_by_role, role, out=self._channel)
        np.multiply(self._channel, self._cell_scale, out=self._channel)
        np.equal(role, ROLE_LUMEN_GOAL, out=self._mask)
        np.logical_or(self._mask, np.equal(role, ROLE_UMBRA_GOAL), out=self._mask)
        np.multiply(self._channel, 0.88 + 0.16 * pulse, out=self._ramp)
        np.copyto(self._channel, self._ramp, where=self._mask)

        # A celula que a Umbra esta rompendo encolhe conforme o esforco
        # sobe: e o unico aviso de que uma acao IRREVERSIVEL esta em curso,
        # e o que a torna deliberada em vez de acidental.
        state = self._state
        terrain = self._terrain
        if terrain.has_source:
            for role_id, intensity in ((ROLE_SOURCE, state.source_intensity),
                                       (ROLE_SOURCE_ALT, state.source_alt_intensity)):
                np.equal(role, role_id, out=self._mask)
                np.multiply(self._channel, 0.7 + 0.5 * self._source_breath(intensity),
                            out=self._ramp)
                np.copyto(self._channel, self._ramp, where=self._mask)

        if terrain.has_wanderer:
            # A lanterna nao tem papel de celula proprio: ela e UMA celula do
            # trilho repintada aqui. Um papel novo exigiria reescrever `role`
            # a cada frame -- 476 posicoes por causa de uma celula que mudou
            # -- e `role` e do terreno, nao do relogio.
            col = int(round(state.wander_col))
            col = max(terrain.wander_min_col, min(terrain.wander_max_col, col))
            slot = terrain.wander_row * terrain.cols + col
            self._channel[slot] = self._cell_scale * 0.62
            sprite_view["texture_id"][rows[slot]] = SHAPE_CIRCLE
            sprite_view["tint_r"][rows[slot]] = LAMP_ON[0]
            sprite_view["tint_g"][rows[slot]] = LAMP_ON[1]
            sprite_view["tint_b"][rows[slot]] = LAMP_ON[2]
            sprite_view["tint_a"][rows[slot]] = 255.0

        if state.crust_target_col >= 0:
            slot = state.crust_target_row * self._terrain.cols + state.crust_target_col
            shrink = 1.0 - 0.72 * min(1.0, max(0.0, state.crust_progress))
            self._channel[slot] *= shrink

        transform_view = self._transform_pool.active_view()
        transform_rows = self._cell_transform_rows
        transform_view["scale_x"][transform_rows] = self._channel
        transform_view["scale_y"][transform_rows] = self._channel

    # ------------------------------------------------------------------
    # seres e auras
    # ------------------------------------------------------------------

    def _paint_characters(self) -> None:
        """Cada ser escurece (Lumen) ou clareia (Umbra) conforme o medidor
        de perigo sobe -- a morte por polaridade errada e telegrafada no
        corpo, nao so na barra do HUD."""
        state = self._state
        sprite_view = self._sprite_pool.active_view()
        for side, dark, bright in (
            (LUMEN, LUMEN_FADING, LUMEN_BODY),
            (UMBRA, UMBRA_BODY, UMBRA_DISSOLVING),
        ):
            row = self._sprite_pool.dense_row_of(int(state.entity_index[side]))
            peril = float(state.peril[side])
            ratio = peril if side == UMBRA else 1.0 - peril
            sprite_view["tint_r"][row] = _mix(dark[0], bright[0], ratio)
            sprite_view["tint_g"][row] = _mix(dark[1], bright[1], ratio)
            sprite_view["tint_b"][row] = _mix(dark[2], bright[2], ratio)

    def _shape_characters(self, delta_time: float) -> None:
        """Estica no ar, amassa ao pousar -- e nada mais que isso.

        Puramente visual: a escala do `transform` e o que se DESENHA; quem
        colide e o `hitbox`, que este sistema nao toca. Um ser amassado ocupa
        na simulacao exatamente o mesmo espaco de sempre, e tem de ser assim
        -- a geometria das trinta fases foi medida com o corpo inteiro.

        Nao ha consulta de "esta no chao": o `TileCollisionSystem` zera a
        velocidade vertical ao encostar, entao vinha-caindo-e-parou E o
        pouso, e ler isso do proprio movimento evita uma dependencia deste
        sistema para com os dois sistemas de colisao."""
        if self._velocity_pool is None:
            return
        state = self._state
        if state.level_index != self._shaped_level:
            # Trocar de fase teleporta os dois. Sem zerar aqui, a queda do
            # frame anterior viraria uma amassada no primeiro frame da fase
            # seguinte -- um baque que nunca aconteceu.
            self._shaped_level = state.level_index
            self._impact[:] = 0.0
            self._last_fall[:] = 0.0

        velocity = self._velocity_pool.active_view()
        transform = self._transform_pool.active_view()

        for side in (LUMEN, UMBRA):
            entity_index = int(state.entity_index[side])
            velocity_row = self._velocity_pool.dense_row_of(entity_index)
            fall = float(velocity["linear_y"][velocity_row])

            if self._last_fall[side] > _LAND_TRIGGER and fall <= _STILL_FALL:
                impact = min(1.0, self._last_fall[side] / self._fall_reference[side])
                self._impact[side] = max(self._impact[side], impact)
            self._last_fall[side] = fall

            recover = _LAND_RECOVER[side]
            self._impact[side] = max(0.0, self._impact[side] - delta_time / recover)

            air = max(0.0, abs(fall) - _STILL_FALL) / self._fall_reference[side]
            air = min(1.0, air)
            stretch = 1.0 + _AIR_STRETCH[side] * air - _LAND_SQUASH[side] * self._impact[side]
            stretch = min(_STRETCH_LIMITS[1], max(_STRETCH_LIMITS[0], stretch))

            base_x, base_y = self._base_scale[side]
            transform_row = self._transform_pool.dense_row_of(entity_index)
            transform["scale_y"][transform_row] = base_y * stretch
            # A largura espelha a altura: esticado afina, amassado espalha.
            # Sem isso o ser so cresce e encolhe, que le como zoom e nao como
            # corpo.
            transform["scale_x"][transform_row] = base_x * (2.0 - stretch)

    def _paint_auras(self) -> None:
        """
        Tres entidades de acompanhamento: o alcance do facho da Lumen, o do
        bolsao da Umbra, e o anel dourado que marca quem o jogador comanda.

        Os dois primeiros sao ANEIS, nao discos. A primeira versao desenhava
        o facho como um disco translucido cheio, e ele saia como uma mancha
        cinza de borda dura por cima do nivel -- lia como artefato, e ainda
        competia com o campo de luz que era justamente o que ele deveria
        representar. Um anel na borda do alcance nao compete com nada e
        entrega a informacao que o jogador de fato precisa: **ate onde** a
        habilidade solidifica terreno. E o unico jeito de saber isso sem
        contar celulas na tela.
        """
        state, tuning = self._state, self._tuning
        cell_size = self._terrain.cell_size
        transform_view = self._transform_pool.active_view()
        sprite_view = self._sprite_pool.active_view()

        lumen_x, lumen_y = self._character_position(LUMEN)
        umbra_x, umbra_y = self._character_position(UMBRA)
        pulse = 0.5 + 0.5 * math.sin(self._elapsed * _PULSE_HZ * math.tau)

        beam_reach = (
            tuning.light.beam_intensity - tuning.light.solid_threshold
        ) * tuning.light.falloff_radius_cells
        absorb_reach = tuning.light.absorb_radius_cells

        # Desligada, a aura encolhe ate virar so o contorno do corpo -- some
        # da tela sem sumir de vez, e o jogador ve a habilidade "recolher".
        beam_on = bool(state.ability_on[LUMEN])
        absorb_on = bool(state.ability_on[UMBRA])
        halo_cells = beam_reach if beam_on else 0.9
        rim_cells = absorb_reach if absorb_on else 0.9

        self._place_aura(0, lumen_x, lumen_y, halo_cells * 2.0 * cell_size, SHAPE_RING,
                         AIR_GLOW, 104.0 if beam_on else 70.0,
                         transform_view, sprite_view)
        self._place_aura(1, umbra_x, umbra_y, rim_cells * 2.0 * cell_size, SHAPE_RING,
                         UMBRA_RIM, 150.0 if absorb_on else 112.0,
                         transform_view, sprite_view)

        # O terceiro anel tem dois trabalhos, e o segundo tem prioridade.
        #
        # De costume ele marca quem esta sob comando (e some no duo, onde nao
        # existe "quem" -- os dois estao). Mas enquanto o Instante carrega ele
        # abandona os dois e vai pro MEIO deles, crescendo: o segredo precisa
        # ser visto antes de ser entendido, senao e indistinguivel de nao
        # existir. Ver `penumbra.systems.echo_system`.
        echo = min(1.0, state.echo_seconds / max(1e-6, self._echo_seconds))
        if echo > 0.0:
            self._place_aura(
                2, (lumen_x + umbra_x) / 2.0, (lumen_y + umbra_y) / 2.0,
                (0.8 + 2.2 * echo) * cell_size, SHAPE_RING,
                GOLD_BRIGHT, 90.0 + 165.0 * echo, transform_view, sprite_view,
            )
            return

        active_x, active_y = (lumen_x, lumen_y) if state.active == LUMEN else (umbra_x, umbra_y)
        self._place_aura(2, active_x, active_y, (1.55 + 0.18 * pulse) * cell_size, SHAPE_RING,
                         GOLD_BRIGHT, 0.0 if state.duo else 205.0, transform_view, sprite_view)

    def _place_aura(
        self, slot: int, x: float, y: float, diameter: float, shape: int,
        color, alpha: float, transform_view, sprite_view,
    ) -> None:
        entity_index = int(self._aura_entity_indices[slot])
        transform_row = self._transform_pool.dense_row_of(entity_index)
        transform_view["position_x"][transform_row] = x
        transform_view["position_y"][transform_row] = y
        transform_view["scale_x"][transform_row] = diameter / _CELL_SPRITE_UNIT
        transform_view["scale_y"][transform_row] = diameter / _CELL_SPRITE_UNIT

        sprite_row = self._sprite_pool.dense_row_of(entity_index)
        sprite_view["texture_id"][sprite_row] = shape
        sprite_view["tint_r"][sprite_row] = color[0]
        sprite_view["tint_g"][sprite_row] = color[1]
        sprite_view["tint_b"][sprite_row] = color[2]
        sprite_view["tint_a"][sprite_row] = int(alpha)

    def _character_position(self, side: int):
        pool = self._transform_pool
        row = pool.dense_row_of(int(self._state.entity_index[side]))
        view = pool.active_view()
        return float(view["position_x"][row]), float(view["position_y"][row])

    # ------------------------------------------------------------------
    # utilitarios de cor
    # ------------------------------------------------------------------

    def _fill(self, mask: np.ndarray, color_low, color_high) -> None:
        """Escreve `color_low + ramp * (color_high - color_low)` nas celulas
        de `mask`, usando o `self._ramp` corrente. Passar a mesma cor duas
        vezes e o caso "cor fixa" (o ramp e ignorado)."""
        for channel, low, high in (
            (self._red, color_low[0], color_high[0]),
            (self._green, color_low[1], color_high[1]),
            (self._blue, color_low[2], color_high[2]),
        ):
            if low == high:
                np.copyto(channel, float(low), where=mask)
                continue
            np.multiply(self._ramp, float(high - low), out=self._channel)
            np.add(self._channel, float(low), out=self._channel)
            np.copyto(channel, self._channel, where=mask)

    def _ramp_between(self, values: np.ndarray, low: float, high: float) -> None:
        """Normaliza `values` para 0..1 dentro da faixa `[low, high]`, no
        `self._ramp` -- e assim que os dois lados do eter ganham gradiente
        proprio em vez de uma cor chapada."""
        span = high - low
        np.subtract(values, low, out=self._ramp)
        np.multiply(self._ramp, 1.0 / span if span else 0.0, out=self._ramp)
        np.clip(self._ramp, 0.0, 1.0, out=self._ramp)


def _mix(low: int, high: int, ratio: float) -> int:
    ratio = 0.0 if ratio < 0.0 else (1.0 if ratio > 1.0 else ratio)
    return int(low + (high - low) * ratio)
