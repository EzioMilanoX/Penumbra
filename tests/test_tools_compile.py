"""Os scripts de `tools/` nao sao importados pelo jogo, entao nenhum outro teste os carrega.

O `build_exe.py` chegou a ser commitado com um erro de sintaxe (um `\\n` que virou quebra de linha dentro de
uma f-string) e so apareceu na hora de gerar a release. Compilar cada script aqui pega isso no `pytest`.
"""
from __future__ import annotations

import py_compile
from pathlib import Path

import pytest

_TOOLS = sorted((Path(__file__).resolve().parent.parent / "tools").glob("*.py"))


@pytest.mark.parametrize("script", _TOOLS, ids=lambda p: p.name)
def test_tool_script_compiles(script: Path) -> None:
    py_compile.compile(str(script), doraise=True)
