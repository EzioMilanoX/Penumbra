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
    ROLE_ROCK,
    ROLE_BEACON,
    ROLE_CRUST,
    ROLE_ECLIPSE,
    ROLE_UMBRA_GOAL,
    ROLE_ZONE_LIGHT,
    ROLE_ZONE_SHADOW,
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
AIR_GLOW_MAX_ALPHA = 62.0
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

_ROLE_COUNT = 12
_CELL_SPRITE_UNIT = 8.0
"""`PygameRenderer.draw_batch` converte `transform.scale` em pixels
multiplicando por 8 (a unidade de forma primitiva do Pilar 2) -- uma celula
de `cell_size` px pede, portanto, `scale = cell_size / 8`."""

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
    ) -> None:
        self._terrain = terrain
        self._state = state
        self._tuning = tuning
        self._cell_entity_indices = cell_entity_indices
        self._aura_entity_indices = aura_entity_indices
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
        self._shape_by_role[ROLE_BEACON] = SHAPE_CIRCLE
        self._cell_scale = np.float32(terrain.cell_size / _CELL_SPRITE_UNIT)
        self._eclipse_seconds = tuning.flow.eclipse_collapse_seconds

    def update(self, world: World, delta_time: float) -> None:
        if self._sprite_pool is None:
            self._resolve_pools(world)
        self._elapsed += delta_time
        self._paint_cells()
        self._paint_characters()
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
        self._cell_sprite_rows = self._sprite_pool.dense_rows_of(self._cell_entity_indices)
        self._cell_transform_rows = self._transform_pool.dense_rows_of(self._cell_entity_indices)

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

        # ar: a luz em si, translucida sobre o fundo
        np.equal(role, ROLE_EMPTY, out=self._mask)
        np.clip(light, 0.0, 1.0, out=self._ramp)
        self._fill(self._mask, AIR_GLOW, AIR_GLOW)
        np.multiply(self._ramp, AIR_GLOW_MAX_ALPHA, out=self._channel)
        np.copyto(self._alpha, self._channel, where=self._mask)

        # rocha: opaca, revelada pela luz que a banha
        np.equal(role, ROLE_ROCK, out=self._mask)
        np.clip(light, 0.0, 1.0, out=self._ramp)
        self._fill(self._mask, ROCK_UNLIT, ROCK_LIT)
        np.copyto(self._alpha, 255.0, where=self._mask)

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

        # farol: aceso como lampada, apagado como brasa
        np.equal(role, ROLE_BEACON, out=self._mask)
        if state.beacon_on:
            self._fill(self._mask, LAMP_ON, LAMP_ON)
            np.copyto(self._alpha, 255.0, where=self._mask)
        else:
            self._fill(self._mask, BEACON_OFF, BEACON_OFF)
            np.copyto(self._alpha, 190.0, where=self._mask)

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

        active_x, active_y = (lumen_x, lumen_y) if state.active == LUMEN else (umbra_x, umbra_y)
        self._place_aura(2, active_x, active_y, (1.55 + 0.18 * pulse) * cell_size, SHAPE_RING,
                         GOLD_BRIGHT, 205.0, transform_view, sprite_view)

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
