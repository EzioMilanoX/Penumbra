"""
Ferramentas dos testes headless (Pilar 5 da OuroborosEngine).

Os testes rodam a simulacao DE VERDADE -- `penumbra.composition.build_simulation`
monta o mesmo `World`, os mesmos sistemas e a mesma ordem que o jogo com
janela, so sem renderer/input/audio concretos (via
`CompositionRoot.build_world`). Nenhum teste aqui reimplementa uma regra
para depois conferi-la contra si mesma.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

import pytest

from ouroboros.bootstrap.engine_config import EngineConfig
from ouroboros.interfaces.null.null_input_provider import NullInputProvider

from penumbra.composition import build_simulation
from penumbra.state import LUMEN, UMBRA
from penumbra.tuning import DualityTuning

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "penumbra" / "config.json"
DIFFICULTY_PATH = PROJECT_ROOT / "data" / "difficulties" / "penumbra" / "basic.json"

FRAME = 1.0 / 60.0

_WORLD = DualityTuning.from_json(str(DIFFICULTY_PATH)).world
GRID_COLS = _WORLD.grid_cols
GRID_ROWS = _WORLD.grid_rows
CELL_SIZE = _WORLD.cell_size
"""Dimensoes lidas do MESMO arquivo de dados que o jogo le. Nenhum teste
deve escrever 28 ou 17 na mao: quando a grade mudou de 40x22 pra 28x17, todo
numero literal espalhado pelos testes virou uma falha de manutencao em vez
de um sinal de regressao."""


@pytest.fixture
def config() -> EngineConfig:
    return EngineConfig.from_json(str(CONFIG_PATH))


@pytest.fixture
def input_provider() -> NullInputProvider:
    """`NullInputProvider` ja expoe `set_action_held` como auxiliar de
    teste -- os testes programam acoes por NOME, exatamente como o jogo as
    le, sem nenhum codigo de tecla."""
    return NullInputProvider()


@pytest.fixture
def simulation(config, input_provider):
    return build_simulation(config, input_provider)


def advance(simulation, input_provider, frames: int = 1, delta_time: float = FRAME) -> None:
    """Roda `frames` frames como `GameLoop.run` faria: `poll()` do input e
    entao `world.step()`. Chamar `step()` sem `poll()` congelaria as bordas
    de input (`is_action_pressed`) para sempre."""
    for _ in range(frames):
        input_provider.poll()
        simulation.world.step(delta_time)


def make_rows(spec: Dict[int, str], cols: int = GRID_COLS, rows: int = GRID_ROWS) -> Tuple[str, ...]:
    """Monta um ASCII de fase a partir de `{indice_da_linha: prefixo}`,
    completando com vazio a direita e as linhas omitidas. Permite que cada
    teste declare a geometria minima do que ele testa em duas ou tres
    linhas, em vez de 22 strings de 40 caracteres."""
    built = []
    for row in range(rows):
        content = spec.get(row, "")
        if len(content) > cols:
            raise ValueError(f"linha {row} tem {len(content)} colunas (max {cols})")
        built.append(content.ljust(cols, "."))
    return tuple(built)


def load_custom(simulation, spec: Dict[int, str]) -> None:
    """Recarrega o `Terrain` da simulacao com uma fase de teste e reinicia.

    Usa exatamente o caminho que o jogo usa pra trocar de fase (as
    mascaras sao reescritas no lugar, nenhuma entidade e criada ou
    destruida), o que tambem exercita esse caminho de graca.

    Passa por `LevelRuntime.load_rows` -- e nao por `terrain.load_rows`
    direto -- porque `reset()` restaura o ASCII carregado (a crosta rompida
    tem de voltar), e um cenario montado por fora do runtime seria
    descartado no primeiro reset."""
    simulation.runtime.load_rows(make_rows(spec))


def place(simulation, side: int, col: float, row: float) -> None:
    """Move um ser para o centro de uma celula, escrevendo direto na pool
    `transform` -- o mesmo que `LevelRuntime._place` faz, mas para uma
    celula arbitraria escolhida pelo teste."""
    pool = simulation.world.get_pool("transform")
    dense_row = pool.dense_row_of(int(simulation.state.entity_index[side]))
    view = pool.active_view()
    cell_size = simulation.terrain.cell_size
    view["position_x"][dense_row] = (col + 0.5) * cell_size
    view["position_y"][dense_row] = (row + 0.5) * cell_size


def position(simulation, side: int) -> Tuple[float, float]:
    pool = simulation.world.get_pool("transform")
    dense_row = pool.dense_row_of(int(simulation.state.entity_index[side]))
    view = pool.active_view()
    return float(view["position_x"][dense_row]), float(view["position_y"][dense_row])


__all__ = [
    "CELL_SIZE",
    "FRAME",
    "GRID_COLS",
    "GRID_ROWS",
    "LUMEN",
    "UMBRA",
    "advance",
    "load_custom",
    "make_rows",
    "place",
    "position",
    "DIFFICULTY_PATH",
]
