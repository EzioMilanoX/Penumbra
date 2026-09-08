"""
Gera `assets/penumbra.ico` -- o icone do atalho de area de trabalho.

    python -m tools.generate_icon

Um circulo partido ao meio: metade branca (Lumen), metade escura com orla
(Umbra), e a costura dourada entre as duas -- o terceiro tom, que no jogo
aparece so no que exige os dois ao mesmo tempo. E a forma mais simples que
ainda diz "dualidade" a 16x16, que e o tamanho em que um icone de fato e
lido na barra de tarefas.

Desenhado com supersampling 4x e reduzido para cada tamanho, porque
`ImageDraw` nao tem antialiasing proprio: um circulo de 16 px desenhado
direto sai serrilhado.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

# Mesma paleta de penumbra/systems/presentation_system.py.
LUMEN_BODY = (242, 246, 255, 255)
UMBRA_BODY = (32, 30, 44, 255)
UMBRA_RIM = (138, 136, 162, 255)
GOLD = (196, 158, 82, 255)
VOID = (8, 8, 14, 255)

_ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)
_SUPERSAMPLE = 4
_MASTER = 256 * _SUPERSAMPLE

_OUTPUT = Path(__file__).resolve().parent.parent / "assets" / "penumbra.ico"


def render_master() -> Image.Image:
    """Desenha o icone no tamanho mestre, com tudo em multiplos de
    `_SUPERSAMPLE` pra reducao limpa."""
    image = Image.new("RGBA", (_MASTER, _MASTER), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    margin = _MASTER // 12
    box = (margin, margin, _MASTER - margin - 1, _MASTER - margin - 1)
    center_x = _MASTER // 2
    rim_width = max(1, _MASTER // 42)
    seam_width = max(1, _MASTER // 30)

    # Disco do vazio por baixo: garante que a metade escura tenha corpo
    # proprio em vez de deixar a area de trabalho aparecer atraves dela.
    draw.ellipse(box, fill=VOID)
    # Metade da sombra (direita) e metade da luz (esquerda).
    draw.pieslice(box, start=-90, end=90, fill=UMBRA_BODY)
    draw.pieslice(box, start=90, end=270, fill=LUMEN_BODY)
    # Orla: da contorno a metade escura, que sem ela desapareceria num
    # fundo escuro -- o mesmo motivo pelo qual a Umbra tem orla no jogo.
    draw.ellipse(box, outline=UMBRA_RIM, width=rim_width)
    # Costura dourada, so dentro do disco.
    draw.line(
        [(center_x, margin + rim_width), (center_x, _MASTER - margin - rim_width)],
        fill=GOLD,
        width=seam_width,
    )
    return image


def main() -> int:
    master = render_master()
    _OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    # A imagem BASE tem de ser a maior: o plugin ICO do Pillow gera cada
    # tamanho pedido reduzindo a base, e nunca amplia -- salvar a partir do
    # frame de 16 px produz um .ico com 16x16 e mais nada.
    frames = [master.resize((size, size), Image.LANCZOS) for size in sorted(_ICON_SIZES, reverse=True)]
    frames[0].save(
        _OUTPUT,
        format="ICO",
        sizes=[(size, size) for size in sorted(_ICON_SIZES, reverse=True)],
        append_images=frames[1:],
    )

    written = sorted(Image.open(_OUTPUT).info["sizes"])
    if len(written) != len(_ICON_SIZES):
        raise SystemExit(f"o .ico saiu com {written}, esperado {sorted((s, s) for s in _ICON_SIZES)}")
    print(f"escrito {_OUTPUT} ({', '.join(f'{w}x{h}' for w, h in written)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
