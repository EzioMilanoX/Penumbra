"""
Terreno de uma fase: mascaras densas `[row, col]` parseadas do ASCII.

`Terrain` e alocado UMA vez na composicao (todas as fases tem exatamente as
mesmas dimensoes, ver `WorldTuning`) e RECARREGADO no lugar a cada troca de
fase via `load_rows` -- nenhuma entidade e criada/destruida numa transicao
de fase, o que mantem a Regra 1 (Zero-GC no gameplay) valendo tambem para o
fluxo entre fases, nao so para o frame.

Container de dados puro, no mesmo espirito de `ouroboros.core.grid2d.Grid2D`:
nao conhece `World`, nao conhece luz, nao decide o que e solido. Quem
compoe as duas grades de colisao a partir daqui e
`penumbra.systems.light_field_system`.
"""
from __future__ import annotations

from typing import Tuple

import numpy as np

ROCK_CHAR = "#"
EMPTY_CHAR = "."
ETHER_CHAR = "~"
LAMP_CHAR = "*"
DOOR_CHAR = "D"
ZONE_LIGHT_CHAR = "L"
ZONE_SHADOW_CHAR = "S"
LUMEN_SPAWN_CHAR = "A"
UMBRA_SPAWN_CHAR = "B"
LUMEN_GOAL_CHAR = "X"
UMBRA_GOAL_CHAR = "Y"

# Papel visual de cada celula, consumido por
# `penumbra.systems.terrain_presentation_system` como um indice inteiro
# (nunca um `str` por celula -- 880 comparacoes de string por frame seriam
# exatamente o laco Python por entidade que a Constituicao proibe).
ROLE_EMPTY = 0
ROLE_ROCK = 1
ROLE_ETHER = 2
ROLE_LAMP = 3
ROLE_DOOR = 4
ROLE_ZONE_LIGHT = 5
ROLE_ZONE_SHADOW = 6
ROLE_LUMEN_GOAL = 7
ROLE_UMBRA_GOAL = 8

_MARKER_CHARS = frozenset(
    {LUMEN_SPAWN_CHAR, UMBRA_SPAWN_CHAR, LUMEN_GOAL_CHAR, UMBRA_GOAL_CHAR}
)


class TerrainDefinitionError(Exception):
    """Levantado quando o ASCII de uma fase esta malformado (dimensao
    errada, caractere desconhecido, marcador faltando/duplicado, porta sem
    zonas, ultima linha nao vazia). Falha alto e cedo, no carregamento --
    nunca como uma fase silenciosamente insolvel."""


class Terrain:
    """
    Mascaras de uma fase, todas com shape `(rows, cols)` e alocadas uma
    unica vez.

    `rock` e `door` sao os dois tipos de celula que bloqueiam luz; `rock`
    e solida para os DOIS seres (a rocha e o unico chao neutro do mundo
    fragmentado, e e ela que torna as fases solveis), `door` e solida
    enquanto a porta de polaridade estiver trancada. `ether` e a materia
    potencial: solida so para quem tem a polaridade da luz que a banha
    naquele instante -- e o conflito central do jogo.

    A ultima linha da grade e sempre o vazio (validado): e por ali que um
    ser cai pra fora do mundo, ja que `Grid2D.batch_get` trata tudo fora
    dos limites como solido e portanto ninguem cai "pra fora" de verdade.
    """

    def __init__(self, cols: int, rows: int, cell_size: float) -> None:
        self._cols = int(cols)
        self._rows = int(rows)
        self._cell_size = float(cell_size)
        shape = (self._rows, self._cols)

        self.rock = np.zeros(shape, dtype=bool)
        self.ether = np.zeros(shape, dtype=bool)
        self.door = np.zeros(shape, dtype=bool)
        self.zone_light = np.zeros(shape, dtype=bool)
        self.zone_shadow = np.zeros(shape, dtype=bool)
        self.lamp = np.zeros(shape, dtype=np.float32)
        self.role = np.zeros(shape, dtype=np.int8)

        # Centro de mundo de cada celula, pre-computado uma vez: o disco de
        # absorcao da Umbra e testado contra estes arrays a cada frame, sem
        # nenhum `meshgrid` novo dentro de `update()`.
        col_centers = (np.arange(self._cols, dtype=np.float32) + 0.5) * self._cell_size
        row_centers = (np.arange(self._rows, dtype=np.float32) + 0.5) * self._cell_size
        self.center_x = np.broadcast_to(col_centers[None, :], shape).copy()
        self.center_y = np.broadcast_to(row_centers[:, None], shape).copy()

        self.lumen_spawn_cell = (0, 0)
        self.umbra_spawn_cell = (0, 0)
        self.lumen_goal_cell = (0, 0)
        self.umbra_goal_cell = (0, 0)
        self.has_door = False

    @property
    def cols(self) -> int:
        return self._cols

    @property
    def rows(self) -> int:
        return self._rows

    @property
    def cell_size(self) -> float:
        return self._cell_size

    def cell_center(self, cell: Tuple[int, int]) -> Tuple[float, float]:
        """Converte um `(col, row)` de marcador para o centro de mundo da
        celula -- mesma ordem `(col, row)` de `Grid2D.world_to_cell`, pra
        nunca inverter X/Y silenciosamente."""
        col, row = cell
        return ((col + 0.5) * self._cell_size, (row + 0.5) * self._cell_size)

    def load_rows(self, rows: Tuple[str, ...]) -> None:
        """
        Reescreve TODAS as mascaras a partir do ASCII de uma fase, no
        lugar (sem realocar nada). Valida antes de escrever qualquer
        coisa para nunca deixar o terreno meio carregado.

        Levanta `TerrainDefinitionError` em: dimensao diferente da grade
        alocada, caractere desconhecido, marcador (`A`/`B`/`X`/`Y`)
        ausente ou duplicado, ultima linha nao vazia, ou porta (`D`) sem
        ao menos uma zona de luz (`L`) e uma de sombra (`S`) -- uma porta
        sem zonas seria uma parede eterna.
        """
        self._validate_shape(rows)

        self.rock[:] = False
        self.ether[:] = False
        self.door[:] = False
        self.zone_light[:] = False
        self.zone_shadow[:] = False
        self.lamp[:] = 0.0
        self.role[:] = ROLE_EMPTY

        markers: dict = {}
        for row_index, row in enumerate(rows):
            for col_index, char in enumerate(row):
                if char == EMPTY_CHAR:
                    continue
                if char == ROCK_CHAR:
                    self.rock[row_index, col_index] = True
                    self.role[row_index, col_index] = ROLE_ROCK
                elif char == ETHER_CHAR:
                    self.ether[row_index, col_index] = True
                    self.role[row_index, col_index] = ROLE_ETHER
                elif char == LAMP_CHAR:
                    self.lamp[row_index, col_index] = 1.0
                    self.role[row_index, col_index] = ROLE_LAMP
                elif char == DOOR_CHAR:
                    self.door[row_index, col_index] = True
                    self.role[row_index, col_index] = ROLE_DOOR
                elif char == ZONE_LIGHT_CHAR:
                    self.zone_light[row_index, col_index] = True
                    self.role[row_index, col_index] = ROLE_ZONE_LIGHT
                elif char == ZONE_SHADOW_CHAR:
                    self.zone_shadow[row_index, col_index] = True
                    self.role[row_index, col_index] = ROLE_ZONE_SHADOW
                elif char in _MARKER_CHARS:
                    if char in markers:
                        raise TerrainDefinitionError(f"marcador {char!r} aparece mais de uma vez na fase")
                    markers[char] = (col_index, row_index)
                    if char == LUMEN_GOAL_CHAR:
                        self.role[row_index, col_index] = ROLE_LUMEN_GOAL
                    elif char == UMBRA_GOAL_CHAR:
                        self.role[row_index, col_index] = ROLE_UMBRA_GOAL
                else:
                    raise TerrainDefinitionError(
                        f"caractere de fase desconhecido {char!r} em (col={col_index}, row={row_index})"
                    )

        for char in (LUMEN_SPAWN_CHAR, UMBRA_SPAWN_CHAR, LUMEN_GOAL_CHAR, UMBRA_GOAL_CHAR):
            if char not in markers:
                raise TerrainDefinitionError(f"fase sem o marcador obrigatorio {char!r}")

        self.lumen_spawn_cell = markers[LUMEN_SPAWN_CHAR]
        self.umbra_spawn_cell = markers[UMBRA_SPAWN_CHAR]
        self.lumen_goal_cell = markers[LUMEN_GOAL_CHAR]
        self.umbra_goal_cell = markers[UMBRA_GOAL_CHAR]
        self.has_door = bool(self.door.any())

        if self.has_door and not (self.zone_light.any() and self.zone_shadow.any()):
            raise TerrainDefinitionError(
                "fase com porta de polaridade ('D') precisa de ao menos uma zona de luz ('L') "
                "e uma de sombra ('S') -- sem as duas a porta nunca abriria"
            )
        if (self.zone_light.any() or self.zone_shadow.any()) and not self.has_door:
            raise TerrainDefinitionError("fase com zona 'L'/'S' mas sem nenhuma celula de porta ('D')")

    def _validate_shape(self, rows: Tuple[str, ...]) -> None:
        if len(rows) != self._rows:
            raise TerrainDefinitionError(
                f"fase com {len(rows)} linhas -- a grade alocada tem {self._rows} "
                f"(todas as fases compartilham as mesmas dimensoes, ver WorldTuning)"
            )
        for row_index, row in enumerate(rows):
            if len(row) != self._cols:
                raise TerrainDefinitionError(
                    f"linha {row_index} tem {len(row)} colunas -- a grade alocada tem {self._cols}"
                )
        if set(rows[-1]) - {EMPTY_CHAR}:
            raise TerrainDefinitionError(
                "a ultima linha da fase precisa ser inteiramente vazia ('.') -- e o abismo por onde "
                "um ser cai pra fora do mundo (Grid2D trata fora-dos-limites como solido, "
                "entao sem essa linha ninguem cairia de verdade)"
            )
