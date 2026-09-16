"""
Onde estao os dados de Penumbra.

A mecanica disto -- caminho relativo resolvido contra a raiz e nao contra o
diretorio atual, `sys._MEIPASS` dentro de um bundle onefile, pasta do
executavel no onedir -- e a mesma para todo produto da engine, e todo produto
a encontra ao empacotar o primeiro `.exe`. Por isso ela vive em
`ouroboros.bootstrap.resources`, e nao aqui.

O que sobra e a unica coisa que so Penumbra sabe: **qual e a raiz**. A pasta
que contem o pacote `penumbra`, e dentro dela `data/` e `assets/`.
"""
from __future__ import annotations

from pathlib import Path

from ouroboros.bootstrap.resources import ResourceRoot, frozen_root, is_frozen

RESOURCES = ResourceRoot(Path(__file__).resolve().parent.parent)

resource = RESOURCES
"""`resource("data", "levels")` -- um caminho absoluto dentro dos dados."""

resolve = RESOURCES.resolve
"""Torna absoluto um caminho vindo do `config.json`."""


def resource_root() -> Path:
    """A pasta que contem `data/` e `assets/`, venha de onde vier."""
    return RESOURCES.root
