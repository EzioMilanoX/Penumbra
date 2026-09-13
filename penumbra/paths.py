"""
Onde estao os dados -- rodando do repositorio ou de dentro de um executavel.

Penumbra so rodava a partir da raiz do projeto. Os caminhos de `config.json`
(`data/difficulties/...`, `data/input_bindings/...`) sao relativos, e Python
os resolve contra o DIRETORIO ATUAL -- entao abrir o jogo de qualquer outro
lugar morria no boot, com um erro sobre um arquivo que esta ali do lado:

    TuningDefinitionError: nao foi possivel ler data/difficulties/...

Isso nunca incomodou porque o unico jeito de jogar era `python -m
penumbra.main` da raiz. Um executavel nao tem raiz de projeto nenhuma, e o
diretorio atual passa a ser onde quer que a pessoa tenha clicado -- entao a
mesma falha que era um detalhe vira a unica coisa que acontece.

A resposta e nunca depender do diretorio atual. Tres casos, um lugar so:

* **Repositorio** -- a pasta que contem o pacote `penumbra`.
* **PyInstaller onefile** -- `sys._MEIPASS`, a pasta temporaria onde o
  bundle se descompacta.
* **PyInstaller onedir** -- a pasta do proprio executavel.
"""
from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    """Rodando de dentro de um executavel empacotado."""
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    """A pasta que contem `data/` e `assets/`, venha de onde vier.

    Nunca o diretorio atual: um jogo que so abre se voce estiver na pasta
    certa nao e um jogo que da pra mandar pra alguem.
    """
    if is_frozen():
        # `_MEIPASS` so existe no modo onefile; no onedir, os dados ficam ao
        # lado do executavel.
        bundle = getattr(sys, "_MEIPASS", None)
        return Path(bundle) if bundle else Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource(*parts: str) -> Path:
    """Um caminho absoluto dentro dos dados empacotados."""
    return resource_root().joinpath(*parts)


def resolve(path_like) -> str:
    """Torna absoluto um caminho vindo do `config.json`.

    Absolutos passam intactos -- quem apontou para fora do bundle sabia o que
    estava fazendo (uma dificuldade de teste, por exemplo).
    """
    path = Path(path_like)
    return str(path if path.is_absolute() else resource_root() / path)
