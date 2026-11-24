"""
A voz do jogo: o que ele diz na porta de cada capitulo.

Trinta fases sem que o jogo dissesse uma vez do que e sobre, e a pergunta do
fim -- fundir ou seguir dois -- chegava sem preparo. As falas sao tres, uma
por capitulo, e cada uma prepara a seguinte: o prologo conta a regra (duas
metades de uma fonte, que nao podem se tocar), a do segundo capitulo conta o
conflito, e a do terceiro anuncia a pergunta.

Sao dados (`data/story/interludes.json`), como as fases: texto muda mais que
codigo, e quem o revisa nao deveria precisar abrir Python.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


class StoryError(Exception):
    """Arquivo de falas malformado. Falha na composicao, nunca no meio do jogo."""


@dataclass(frozen=True)
class Interlude:
    chapter: int
    title: str
    lines: tuple[str, ...]


def load_interludes(path: Path) -> dict[int, Interlude]:
    """Capitulo -> fala. Arquivo ausente vira nenhuma fala: o jogo continua
    inteiro, so mais calado."""
    path = Path(path)
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StoryError(f"{path}: {exc}") from exc
    entries = raw.get("interludes") if isinstance(raw, dict) else None
    if not isinstance(entries, list):
        raise StoryError(f"{path}: 'interludes' precisa ser uma lista")
    interludes: dict[int, Interlude] = {}
    for entry in entries:
        try:
            chapter = int(entry["chapter"])
            title = str(entry["title"])
            lines = tuple(str(line) for line in entry["lines"])
        except (KeyError, TypeError, ValueError) as exc:
            raise StoryError(f"{path}: fala malformada ({exc})") from exc
        if not lines:
            raise StoryError(f"{path}: a fala do capitulo {chapter} esta vazia")
        if chapter in interludes:
            raise StoryError(f"{path}: duas falas para o capitulo {chapter}")
        interludes[chapter] = Interlude(chapter, title, lines)
    return interludes
