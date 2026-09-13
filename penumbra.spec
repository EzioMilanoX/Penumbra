# -*- mode: python ; coding: utf-8 -*-
"""
Receita do executavel (PyInstaller).

    python -m tools.build_exe        # ou: pyinstaller penumbra.spec

Tres coisas precisam entrar no bundle, e as tres estao fora do pacote
`penumbra`:

* **`data/`** -- as trinta fases, a dificuldade, os bindings e os arquetipos.
  Sao dados de verdade (Regra 3 da Constituicao da engine: nada de
  balanceamento hardcoded), entao nao viajam dentro do codigo.
* **`penumbra/config.json`** -- o unico arquivo de dados que mora dentro do
  pacote, e que o PyInstaller nao levaria sozinho: ele empacota `.py`.
* **a OuroborosEngine** -- ela vive num repositorio IRMAO, instalada em modo
  editavel. Para quem clona os dois repositorios isso e o certo; para quem
  recebe um executavel, ela simplesmente precisa estar dentro.

`onefile` de proposito: um unico `.exe` e o que da pra mandar pra alguem.
`resource_root()` (ver `penumbra/paths.py`) resolve `sys._MEIPASS`, que e a
pasta temporaria onde o bundle se descompacta -- e e por isso que o jogo nao
pode depender do diretorio atual.
"""
from pathlib import Path

import ouroboros
from PyInstaller.utils.hooks import collect_submodules

SPEC_DIR = Path(SPECPATH).resolve()

# A engine esta instalada em modo EDITAVEL: o que existe no site-packages e um
# ponteiro pro repositorio irmao, e o PyInstaller nao o segue sozinho. Sem
# isto o executavel monta, abre e morre com `No module named 'ouroboros'` --
# e, sem console, morre em silencio.
ENGINE_ROOT = Path(ouroboros.__file__).resolve().parent.parent

datas = [
    (str(SPEC_DIR / "data"), "data"),
    (str(SPEC_DIR / "penumbra" / "config.json"), "penumbra"),
]

icon_path = SPEC_DIR / "assets" / "penumbra.ico"

analysis = Analysis(
    [str(SPEC_DIR / "penumbra" / "main.py")],
    pathex=[str(SPEC_DIR), str(ENGINE_ROOT)],
    binaries=[],
    datas=datas,
    # `collect_submodules` e nao `["ouroboros"]`: nomear o pacote raiz nao
    # traz `ouroboros.bootstrap.*` nem os adaptadores, e varios deles so sao
    # importados por nome em tempo de composicao.
    #
    # Menos `ouroboros.rhythm.offline`: e a metade de AUTORIA do modulo de
    # ritmo, importa `scipy`, e Penumbra nao tem uma nota musical. Sozinho ele
    # levava o executavel de 20 MB para 163.
    hiddenimports=[
        name for name in collect_submodules("ouroboros")
        if not name.startswith("ouroboros.rhythm.offline")
    ],
    hookspath=[],
    runtime_hooks=[],
    # `numpy.testing` e `pygame.tests` dobram o tamanho do bundle e nenhum
    # frame do jogo passa por eles.
    excludes=[
        "tkinter", "unittest", "pytest", "numpy.testing", "pygame.tests",
        # Nenhum frame do jogo passa por aqui, e `scipy` sozinho e oito vezes
        # o tamanho do jogo inteiro.
        "scipy", "matplotlib", "ouroboros.rhythm.offline",
    ],
    noarchive=False,
)
pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="Penumbra",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    # Sem console: o jogo abre uma janela, e um terminal preto atras dela
    # seria a primeira coisa que quem recebe o arquivo veria.
    console=False,
    icon=str(icon_path) if icon_path.is_file() else None,
)
