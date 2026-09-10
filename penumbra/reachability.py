"""
Alcance geometrico: onde cada ser consegue chegar de pe.

Existe porque um puzzle-platformer tem duas maneiras independentes de ser
insolvel, e `tools/audit_levels.py` so cobria uma. A primeira e de
POLARIDADE (o eter nao acende onde precisa, o facho vaza ate a zona de
sombra) -- aquela auditoria mede isso. A segunda e de GEOMETRIA: o degrau
esta alto demais, ou -- o caso que de fato escapou -- ha um bloco
exatamente sobre a cabeca do ser, e o salto morre no teto antes de servir
pra nada.

O modelo aqui e deliberadamente CONSERVADOR: ele so afirma que um caminho
existe quando existe mesmo. Se ele diz "nao alcanca", pode ser limitacao do
modelo (ele ignora, por exemplo, deriva longa durante uma queda) -- mas se
ele diz "alcanca", o caminho e real.
"""
from __future__ import annotations

from math import sqrt
from typing import Dict, Iterable, List, Set, Tuple

import numpy as np

from penumbra.tuning import CharacterTuning, WorldTuning

Cell = Tuple[int, int]
"""`(col, row)` -- a mesma ordem de `Grid2D.world_to_cell`."""


class JumpModel:
    """
    Quanto um ser consegue subir, e quanto anda na horizontal enquanto esta
    la em cima.

    A altura maxima de um salto (`v0^2 / 2g`) e a parte facil e a que
    engana: o que decide se um degrau e subivel nao e alcancar a altura
    dele, e sim **continuar** naquela altura tempo suficiente pra andar as
    colunas que faltam. Subir num degrau exige pelo menos 1 celula de
    deslocamento horizontal -- o topo do degrau nunca esta na coluna onde o
    ser esta, porque essa coluna esta vazia (e onde ele esta de pe).

    E por isso que a Umbra, que alcanca 2,06 celulas de altura, sobe apenas
    degraus de UMA celula: a 2 celulas ela desloca 0,47 -- ela chega la e
    nao tem pra onde ir.
    """

    def __init__(self, world: WorldTuning, character: CharacterTuning) -> None:
        self._cell_size = world.cell_size
        self._gravity = world.gravity_y
        self._jump_speed = abs(character.jump_velocity_y)
        self._move_speed = character.move_speed
        self.max_climb = 0
        self._reach_by_climb: Dict[int, float] = {}
        for climb in range(1, 8):
            reach = self.horizontal_reach(climb)
            if reach < 1.0:
                break
            self._reach_by_climb[climb] = reach
            self.max_climb = climb

    def horizontal_reach(self, climb_cells: int) -> float:
        """Colunas percorridas enquanto o ser esta AO MENOS `climb_cells`
        celulas acima de onde saltou. Zero se ele nem chega nessa altura."""
        height = climb_cells * self._cell_size
        discriminant = self._jump_speed * self._jump_speed - 2.0 * self._gravity * height
        if discriminant <= 0.0:
            return 0.0
        seconds_above = 2.0 * sqrt(discriminant) / self._gravity
        return self._move_speed * seconds_above / self._cell_size

    def reach_for(self, climb_cells: int) -> float:
        return self._reach_by_climb.get(climb_cells, 0.0)

    def fall_drift(self, fall_cells: int) -> float:
        """Colunas de deriva durante uma queda de `fall_cells` celulas -- o
        ser mantem a velocidade horizontal no ar."""
        seconds = sqrt(2.0 * fall_cells * self._cell_size / self._gravity)
        return self._move_speed * seconds / self._cell_size


class TraversalGraph:
    """
    Grafo de celulas onde da pe ficar de pe, sobre uma mascara de solidos.

    A mascara e OTIMISTA de proposito -- rocha, eter e porta trancada
    contam como solidos para os dois seres. Otimista porque a Lumen pode
    acender qualquer eter com o facho e a Umbra pode apagar qualquer eter
    absorvendo: se um ser nao alcanca um lugar nem podendo escolher a
    polaridade de cada celula, ele nao alcanca de jeito nenhum. Se a
    polaridade especifica de uma fase impede um caminho que aqui parece
    existir, isso e o que `tools/audit_levels.py` mede.
    """

    def __init__(self, solid: np.ndarray, model: JumpModel) -> None:
        self._solid = solid
        self._model = model
        self._rows, self._cols = solid.shape
        self._standable = self._compute_standable()

    @property
    def standable(self) -> Set[Cell]:
        return self._standable

    def _free(self, col: int, row: int) -> bool:
        if not (0 <= col < self._cols and 0 <= row < self._rows):
            return False
        return not bool(self._solid[row, col])

    def _is_standable(self, col: int, row: int) -> bool:
        return self._free(col, row) and not self._free(col, row + 1)

    def _compute_standable(self) -> Set[Cell]:
        return {
            (col, row)
            for row in range(self._rows)
            for col in range(self._cols)
            if self._is_standable(col, row)
        }

    def neighbors(self, cell: Cell) -> Iterable[Cell]:
        yield from self._walk_neighbors(cell)
        yield from self._climb_neighbors(cell)
        yield from self._fall_neighbors(cell)

    def _walk_neighbors(self, cell: Cell) -> Iterable[Cell]:
        col, row = cell
        for step in (-1, 1):
            if self._is_standable(col + step, row):
                yield (col + step, row)

    def _climb_neighbors(self, cell: Cell) -> Iterable[Cell]:
        """Saltos que sobem. Duas exigencias que se confundem facilmente: a
        coluna ACIMA do ser tem de estar livre por toda a subida (senao ha
        um teto, e o salto acaba antes de servir), e a linha do apice tem de
        estar livre ate a coluna de destino."""
        col, row = cell
        for climb in range(1, self._model.max_climb + 1):
            apex_row = row - climb
            if any(not self._free(col, row - k) for k in range(1, climb + 1)):
                break  # teto: nenhuma subida maior tambem passa
            reach = int(self._model.reach_for(climb))
            for step in (-1, 1):
                for distance in range(1, reach + 1):
                    target_col = col + step * distance
                    if not self._free(target_col, apex_row):
                        break
                    if self._is_standable(target_col, apex_row):
                        yield (target_col, apex_row)

    def _fall_neighbors(self, cell: Cell) -> Iterable[Cell]:
        """Andar ate a borda e cair, com a deriva horizontal que a
        velocidade dele garante no ar."""
        col, row = cell
        for step in (-1, 1):
            distance = 1
            while True:
                edge_col = col + step * distance
                if not self._free(edge_col, row):
                    break
                if not self._free(edge_col, row + 1):
                    distance += 1
                    continue  # ainda ha chao: e caminhada, nao queda
                landing = self._land_from(edge_col, row)
                if landing is not None:
                    yield landing
                    drift = int(self._model.fall_drift(landing[1] - row))
                    for drift_step in range(1, drift + 1):
                        for drift_dir in (-1, 1):
                            drifted = self._land_from(edge_col + drift_dir * drift_step, row)
                            if drifted is not None:
                                yield drifted
                break

    def _land_from(self, col: int, row: int) -> Cell | None:
        """Primeira celula onde da pe ficar de pe caindo reto da coluna
        `col` a partir de `row`."""
        if not self._free(col, row):
            return None
        current = row
        while self._free(col, current + 1):
            current += 1
            if current >= self._rows:
                return None
        return (col, current) if self._is_standable(col, current) else None

    def reachable_from(self, origin: Cell) -> Set[Cell]:
        """Fecho transitivo por BFS. `origin` nao precisa ser um ponto de
        apoio (um spawn no ar cai primeiro)."""
        start = origin if origin in self._standable else self._land_from(*origin)
        if start is None:
            return set()
        seen = {start}
        queue: List[Cell] = [start]
        while queue:
            cell = queue.pop()
            for neighbor in self.neighbors(cell):
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)
        return seen


def solid_mask(terrain, door_open: bool, crust_broken: bool = False) -> np.ndarray:
    """
    Mascara otimista de solidos: rocha + eter + crosta + porta, se trancada.

    `crust_broken=True` responde a pergunta do outro lado -- "e depois de a
    Umbra romper tudo que ela consegue romper?". As duas respostas importam:
    com a crosta intacta se mede se a fase e atravessavel SEM gastar o
    irreversivel; com ela rompida, se romper de fato abre o caminho.
    """
    mask = terrain.rock | terrain.ether
    if not crust_broken:
        mask = mask | terrain.crust
    if not door_open:
        mask = mask | terrain.door
    return mask


def standing_cell_above(terrain, cell: Cell) -> Cell:
    """Marcadores de fase (`A`/`X`/`L`/...) sao celulas de ar; o ser fica de
    pe na propria celula do marcador quando ha chao logo abaixo."""
    return cell
