"""
O sistema que E o jogo: calcula a luz e, com ela, reescreve o chao dos dois.

Toda fase de Penumbra e uma unica pergunta -- "onde ha luz agora?" -- porque
a resposta decide, celula por celula, qual dos dois seres tem chao ali. Este
sistema responde a pergunta uma vez por frame e escreve o resultado nas DUAS
`Grid2D` que os dois `TileCollisionSystem` consomem (ver
`penumbra.composition`), o que faz a acao de um ser desfazer literalmente o
terreno do outro sem que nenhum sistema de gameplay saiba disso.
"""
from __future__ import annotations

import math

import numpy as np

from ouroboros.core.grid2d import Grid2D
from ouroboros.core.systems.base_system import ISystem
from ouroboros.core.world import World

from penumbra.state import DualityState, LUMEN, UMBRA
from penumbra.terrain import Terrain
from penumbra.tuning import DualityTuning

_DISPLAY_WALL_FALLOFF = 0.85
"""Fracao da luz do vizinho mais claro que uma celula BLOQUEADORA exibe.
Puramente cosmetico (`DualityState.display_light`): uma parede iluminada de
um lado precisa parecer iluminada, mesmo que a luz nao a atravesse. Nenhuma
regra de jogo le `display_light`."""


class LightFieldSystem(ISystem):
    """
    Propaga luz e sombra pela grade e recompoe as duas grades de colisao.

    O campo e um flood geodesico relaxado: cada passe empurra a luz UMA
    celula pra cada um dos 4 vizinhos, perdendo `decay_per_cell` no
    caminho, e nunca atravessa rocha ou porta trancada. Isso da, de graca,
    tres propriedades que uma soma de discos euclidianos nao daria: a luz
    contorna paredes em vez de vazar por elas, o alcance de uma fonte sai
    direto da sua intensidade (`(I - solid_threshold) * falloff_radius_cells`
    celulas), e a sombra da Umbra obedece a mesma geometria da luz (o mesmo
    flood roda duas vezes, com sementes diferentes).

    Ordem de escrita, que importa: a sombra e resolvida ANTES da luz, pois
    o bolsao de escuridao da Umbra apaga fontes luminosas dentro dele
    ("absorve luz ao redor") -- entao ele precisa existir antes de a luz
    ser semeada, nao depois.

    Zero-GC: todo buffer intermediario e alocado no `__init__`; `update()`
    so faz ufuncs NumPy com `out=`.
    """

    def __init__(
        self,
        terrain: Terrain,
        state: DualityState,
        tuning: DualityTuning,
        lumen_grid: Grid2D,
        umbra_grid: Grid2D,
        transform_pool_name: str = "transform",
    ) -> None:
        self._terrain = terrain
        self._state = state
        self._tuning = tuning
        self._lumen_grid = lumen_grid
        self._umbra_grid = umbra_grid
        self._transform_pool_name = transform_pool_name
        self._transform_pool = None

        shape = (terrain.rows, terrain.cols)
        self._scratch = np.zeros(shape, dtype=np.float32)
        self._diagonal_scratch = np.zeros(shape, dtype=np.float32)
        self._seed = np.zeros(shape, dtype=np.float32)
        self._shadow = np.zeros(shape, dtype=np.float32)
        self._open_solid = np.zeros(shape, dtype=np.float32)
        self._open_light = np.zeros(shape, dtype=np.float32)
        self._blocked = np.zeros(shape, dtype=bool)
        self._mask_a = np.zeros(shape, dtype=bool)
        self._mask_b = np.zeros(shape, dtype=bool)
        self._dist_x = np.zeros(shape, dtype=np.float32)
        self._dist_y = np.zeros(shape, dtype=np.float32)

        light = tuning.light
        self._decay = np.float32(light.decay_per_cell)
        self._diagonal_decay = np.float32(light.decay_per_cell * math.sqrt(2.0))
        self._passes = int(light.relaxation_passes)
        # Intensidade que faz o flood da sombra alcancar exatamente
        # `absorb_radius_cells` celulas antes de cair abaixo do limiar de
        # solidez -- assim o raio de absorcao continua um numero ajustavel
        # no JSON de dificuldade, sem virar uma segunda lei de propagacao.
        self._absorb_seed = np.float32(
            light.solid_threshold + light.absorb_radius_cells * light.decay_per_cell
        )

    def update(self, world: World, delta_time: float) -> None:
        del delta_time
        if self._transform_pool is None:
            self._transform_pool = world.get_pool(self._transform_pool_name)

        state, terrain, light_tuning = self._state, self._terrain, self._tuning.light
        self._refresh_character_cells()

        # --- celulas que bloqueiam qualquer propagacao ---
        # A crosta entra aqui, e nao so na colisao: e opaca, e e disso que
        # o verbo da Umbra vive. O buraco que ela abre pra passar deixa
        # entrar a luz que a crosta barrava -- e e ela quem se dissolve na
        # luz. Sem a crosta ocluir, romper seria so abrir passagem.
        np.logical_and(terrain.door, not state.door_open, out=self._mask_a)
        np.logical_or(terrain.rock, terrain.crust, out=self._blocked)
        np.logical_or(self._blocked, self._mask_a, out=self._blocked)
        np.logical_not(self._blocked, out=self._mask_b)
        np.copyto(self._open_solid, self._mask_b)

        # --- sombra da Umbra (antes da luz: ela apaga as fontes) ---
        self._seed[:] = 0.0
        if state.ability_on[UMBRA]:
            col, row = int(state.cell[UMBRA, 0]), int(state.cell[UMBRA, 1])
            self._seed[row, col] = self._absorb_seed
        self._relax(self._shadow, self._open_solid)
        np.greater_equal(self._shadow, light_tuning.solid_threshold, out=state.absorbed)

        # --- luz: lampadas + facho da Lumen, suprimidos pela sombra ---
        np.logical_not(state.absorbed, out=self._mask_a)
        np.multiply(self._open_solid, self._mask_a, out=self._open_light)

        np.multiply(terrain.lamp, light_tuning.lamp_intensity, out=self._seed)
        if state.ability_on[LUMEN]:
            col, row = int(state.cell[LUMEN, 0]), int(state.cell[LUMEN, 1])
            self._seed[row, col] = max(float(self._seed[row, col]), light_tuning.beam_intensity)
        np.multiply(self._seed, self._open_light, out=self._seed)
        self._relax(state.light, self._open_light)

        np.greater_equal(state.light, light_tuning.solid_threshold, out=state.lit)

        self._compose_collision_grids()
        self._compose_display_light()

    # ------------------------------------------------------------------
    # internos
    # ------------------------------------------------------------------

    def _refresh_character_cells(self) -> None:
        """Atualiza `state.cell` a partir das posicoes JA resolvidas deste
        frame (este sistema roda depois de
        `PhysicsSystem`/`TileCollisionSystem`/`GravitySystem`). Dois seres
        -- laco Python de 2 iteracoes, nao um por entidade."""
        pool = self._transform_pool
        view = pool.active_view()
        cell_size = self._terrain.cell_size
        max_col = self._terrain.cols - 1
        max_row = self._terrain.rows - 1
        for side in (LUMEN, UMBRA):
            row_index = pool.dense_row_of(int(self._state.entity_index[side]))
            col = int(float(view["position_x"][row_index]) // cell_size)
            row = int(float(view["position_y"][row_index]) // cell_size)
            # Clamp defensivo: `Grid2D` trata fora-dos-limites como solido,
            # entao ninguem escapa da grade de verdade, mas um unico frame
            # exatamente na borda nao pode virar IndexError aqui.
            self._state.cell[side, 0] = 0 if col < 0 else (max_col if col > max_col else col)
            self._state.cell[side, 1] = 0 if row < 0 else (max_row if row > max_row else row)

    def _relax(self, field: np.ndarray, open_mask: np.ndarray) -> None:
        """
        Flood geodesico de 8 vizinhos a partir de `self._seed`, com
        `self._passes` passes de Jacobi -- cada passe avanca exatamente uma
        celula, por isso `relaxation_passes` precisa ser >=
        `falloff_radius_cells` (validado no JSON de dificuldade).

        Os 4 vizinhos diagonais custam `decay * sqrt(2)` em vez de `decay`,
        e nao sao um detalhe cosmetico: com so os 4 vizinhos ortogonais a
        distancia resultante e a de Manhattan, e uma lampada acende um
        LOSANGO. Um losango e impossivel de projetar contra -- a mesma
        lampada que alcanca 6 celulas na horizontal alcanca 3 na diagonal
        -- e faria cada fase depender de contas que o jogador nao tem como
        intuir olhando a tela. Com as diagonais, o campo aproxima a
        distancia euclidiana (erro de chanfro ~4%) e o alcance de uma fonte
        e, na pratica, um circulo.

        `open_mask` e 1.0 onde a propagacao pode passar e 0.0 onde nao --
        aplicado tanto ao que SAI de uma celula quanto ao que fica nela,
        entao uma celula bloqueada nunca guarda nem repassa luz.
        """
        np.copyto(field, self._seed)
        straight = self._scratch
        diagonal = self._diagonal_scratch
        for _ in range(self._passes):
            np.subtract(field, self._decay, out=straight)
            np.maximum(straight, 0.0, out=straight)
            np.multiply(straight, open_mask, out=straight)
            np.subtract(field, self._diagonal_decay, out=diagonal)
            np.maximum(diagonal, 0.0, out=diagonal)
            np.multiply(diagonal, open_mask, out=diagonal)

            np.maximum(field[:, 1:], straight[:, :-1], out=field[:, 1:])
            np.maximum(field[:, :-1], straight[:, 1:], out=field[:, :-1])
            np.maximum(field[1:, :], straight[:-1, :], out=field[1:, :])
            np.maximum(field[:-1, :], straight[1:, :], out=field[:-1, :])

            np.maximum(field[1:, 1:], diagonal[:-1, :-1], out=field[1:, 1:])
            np.maximum(field[1:, :-1], diagonal[:-1, 1:], out=field[1:, :-1])
            np.maximum(field[:-1, 1:], diagonal[1:, :-1], out=field[:-1, 1:])
            np.maximum(field[:-1, :-1], diagonal[1:, 1:], out=field[:-1, :-1])

            np.multiply(field, open_mask, out=field)

    def _compose_collision_grids(self) -> None:
        """Escreve as duas `Grid2D` lidas pelos dois `TileCollisionSystem`.

        Rocha, crosta e porta trancada sao solidas pros DOIS -- e o chao
        neutro que torna as fases solveis. O eter e solido so pra um: pra Lumen onde
        esta aceso, pra Umbra onde esta apagado. Nenhuma celula e chao dos
        dois ao mesmo tempo, o que e exatamente o ponto."""
        terrain, state = self._terrain, self._state
        np.logical_and(terrain.ether, state.lit, out=self._mask_a)
        np.logical_or(self._blocked, self._mask_a, out=self._mask_b)
        self._lumen_grid.cells[:] = self._mask_b

        np.logical_not(state.lit, out=self._mask_a)
        np.logical_and(terrain.ether, self._mask_a, out=self._mask_a)
        np.logical_or(self._blocked, self._mask_a, out=self._mask_b)
        self._umbra_grid.cells[:] = self._mask_b

    def _compose_display_light(self) -> None:
        """So apresentacao: as celulas bloqueadoras herdam o vizinho mais
        claro, pra que uma parede com luz de um lado nao pareca vazia."""
        light, scratch = self._state.light, self._scratch
        scratch[:] = 0.0
        np.maximum(scratch[:, 1:], light[:, :-1], out=scratch[:, 1:])
        np.maximum(scratch[:, :-1], light[:, 1:], out=scratch[:, :-1])
        np.maximum(scratch[1:, :], light[:-1, :], out=scratch[1:, :])
        np.maximum(scratch[:-1, :], light[1:, :], out=scratch[:-1, :])
        np.multiply(scratch, _DISPLAY_WALL_FALLOFF, out=scratch)
        np.copyto(self._state.display_light, light)
        np.copyto(self._state.display_light, scratch, where=self._blocked)
