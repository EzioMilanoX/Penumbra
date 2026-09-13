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

from dataclasses import replace

from ouroboros.bootstrap.engine_config import EngineConfig

from penumbra.composition import build_game
from penumbra.paths import resolve, resource

_CONFIG_PATH = resource("penumbra", "config.json")


def main() -> int:
    config = EngineConfig.from_json(str(_CONFIG_PATH))
    # O `CompositionRoot` carrega os bindings sozinho, e faria isso contra o
    # diretorio atual. Absolutizar aqui e o unico lugar possivel: e o ultimo
    # ponto antes de o caminho sair das nossas maos.
    config = replace(config, input_bindings_path=resolve(config.input_bindings_path))
    game_loop = build_game(config)
    game_loop.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
