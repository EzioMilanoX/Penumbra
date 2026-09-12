"""
Ponto de entrada de Penumbra.

Rodar SEMPRE como modulo, a partir da raiz do projeto (mesma convencao dos
vertical slices da OuroborosEngine) -- nunca como script solto: este modulo
usa imports absolutos (`from penumbra...`) que exigem a raiz na
`sys.path`, o que so acontece automaticamente no modo `-m`. Os caminhos de
`config.json` (`data/difficulties/...`, `data/input_bindings/...`) tambem
sao relativos a raiz do projeto.

    python -m penumbra.main

Controles: A/D mover, ESPACO pular, S habilidade (facho da Lumen / absorcao
da Umbra), TAB trocar de ser, R reiniciar a fase, ESC sair.
"""
from __future__ import annotations

from pathlib import Path

from ouroboros.bootstrap.engine_config import EngineConfig

from penumbra.composition import build_game

_CONFIG_PATH = Path(__file__).resolve().parent / "config.json"


def main() -> int:
    config = EngineConfig.from_json(str(_CONFIG_PATH))
    game_loop = build_game(config)
    game_loop.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
