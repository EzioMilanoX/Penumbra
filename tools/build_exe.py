"""
Monta o executavel.

    python -m tools.build_exe

Ate aqui, jogar Penumbra exigia Python 3.14 E clonar a OuroborosEngine ao
lado E rodar `python -m penumbra.main` da raiz certa. Tres condicoes que
valem pra quem desenvolve e nenhuma que valha pra quem so quer jogar -- e e a
diferenca entre "meu projeto" e "algo que eu mando pra alguem".

Antes de empacotar, o script confere as duas coisas que produzem um
executavel que abre e morre em silencio (`console=False` engole o traceback):
os dados estao onde o spec espera, e o jogo monta com o diretorio atual em
outro lugar -- que e exatamente a situacao de um `.exe` clicado.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SPEC = _ROOT / "penumbra.spec"
_REQUIRED = (
    Path("penumbra") / "config.json",
    Path("data") / "levels",
    Path("data") / "difficulties" / "penumbra" / "basic.json",
    Path("data") / "input_bindings" / "penumbra_keyboard.json",
    Path("data") / "archetypes" / "penumbra",
)


def check_inputs() -> None:
    missing = [str(item) for item in _REQUIRED if not (_ROOT / item).exists()]
    if missing:
        raise SystemExit(f"faltando no repositorio: {missing}")
    if not _SPEC.is_file():
        raise SystemExit(f"sem receita: {_SPEC}")


def check_runs_from_anywhere() -> None:
    """Monta o jogo headless com o diretorio atual em outro lugar.

    E a falha que um executavel produz por padrao, e a mais dificil de
    diagnosticar depois: sem console, o `.exe` abre, nao acha os dados, e
    fecha sem dizer nada.
    """
    # O `sys.path` vem antes do `chdir` de proposito: num executavel o pacote
    # e achado pelo bundle, nao pelo diretorio atual, e e essa situacao que se
    # quer reproduzir -- codigo achavel, dados a procurar.
    script = (
        "import os, sys, tempfile;"
        f"sys.path.insert(0, {str(_ROOT)!r});"
        "os.chdir(tempfile.gettempdir());"
        "from ouroboros.bootstrap.engine_config import EngineConfig;"
        "from penumbra.composition import build_simulation;"
        "from penumbra.paths import resource;"
        "s = build_simulation(EngineConfig.from_json(str(resource('penumbra','config.json'))));"
        "print('fases:', s.catalog.count)"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=str(_ROOT),
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise SystemExit(
            "o jogo nao monta fora da raiz -- um executavel morreria aqui:\n"
            + result.stderr.strip()
        )
    print("  " + result.stdout.strip().splitlines()[-1])


def build() -> Path:
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(_SPEC)],
        cwd=str(_ROOT), check=True,
    )
    produced = _ROOT / "dist" / ("Penumbra.exe" if sys.platform == "win32" else "Penumbra")
    if not produced.is_file():
        raise SystemExit(f"o PyInstaller terminou mas {produced.name} nao apareceu")
    return produced


def main() -> int:
    print("conferindo os dados...")
    check_inputs()
    print("conferindo que o jogo monta fora da raiz...")
    check_runs_from_anywhere()
    print("empacotando (leva alguns minutos)...")
    executable = build()
    size = executable.stat().st_size / (1024 * 1024)
    print(f"\npronto: {executable}  ({size:.1f} MB)")
    print("nao precisa de Python nem da engine -- da pra mandar o arquivo sozinho.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
