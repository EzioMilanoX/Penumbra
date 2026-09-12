"""
Catalogo de fases, lido de `data/levels/*.json` (Regra 3 da Constituicao).

Diferente do vertical slice do Platformer -- que assumiu um unico nivel
ASCII hardcoded em Python e deixou o formato data-driven como debito
declarado -- aqui as fases sao dados desde o inicio: quatro arquivos, um
por fase, carregados em ordem de nome de arquivo.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

from penumbra.terrain import Terrain, TerrainDefinitionError


class LevelCatalogError(Exception):
    """Levantado quando o diretorio de fases esta vazio ou um arquivo de
    fase esta malformado. Falha na composicao, nunca no meio de uma
    partida."""


@dataclass(frozen=True)
class LevelDefinition:
    """Uma fase: identidade, o que ela ensina, o capitulo e o ASCII cru."""

    level_id: str
    name: str
    hint: str
    chapter: int
    rows: Tuple[str, ...]
    teaches: str = ""
    """A mecanica que esta fase APRESENTA, quando ela apresenta alguma.

    E dado, e nao deducao do ASCII, porque duas das fases do primeiro
    capitulo ensinam HABILIDADES -- o facho e a absorcao -- e nenhuma delas
    traz um caractere de terreno que a fase anterior ja nao tivesse."""


@dataclass(frozen=True)
class Chapter:
    """Um bloco de fases com uma FUNCAO, nao um tema.

    O menu pagina por isto, e nao por um tamanho fixo, porque os tres
    capitulos nao tem o mesmo tamanho nem deveriam ter: aprender uma mecanica
    de cada vez custa uma fase por mecanica, misturar custa menos, e as
    especiais sao poucas de proposito."""

    number: int
    title: str
    subtitle: str
    first: int
    count: int

    @property
    def last(self) -> int:
        return self.first + self.count - 1


_CHAPTER_TITLES = {
    1: ("APRENDER", "uma mecanica de cada vez"),
    2: ("MISTURAR", "duas ou mais, ao mesmo tempo"),
    3: ("ESPECIAIS", "as que quebram a propria regra"),
}


def _build_chapters(levels: Tuple[LevelDefinition, ...]) -> Tuple[Chapter, ...]:
    chapters = []
    for index, level in enumerate(levels):
        if chapters and chapters[-1][0] == level.chapter:
            chapters[-1][2] += 1
            continue
        if any(existing[0] == level.chapter for existing in chapters):
            raise LevelCatalogError(
                f"fase {level.level_id!r}: o capitulo {level.chapter} aparece em dois "
                f"blocos separados -- o menu pagina por capitulo e nao tem como "
                f"mostrar um capitulo partido"
            )
        chapters.append([level.chapter, index, 1])
    return tuple(
        Chapter(
            number=number,
            title=_CHAPTER_TITLES.get(number, (f"CAPITULO {number}", ""))[0],
            subtitle=_CHAPTER_TITLES.get(number, ("", ""))[1],
            first=first,
            count=count,
        )
        for number, first, count in chapters
    )


class LevelCatalog:
    """
    Lista imutavel e ordenada de `LevelDefinition`.

    `validate_all` existe porque uma fase invalida descoberta na
    TRANSICAO (depois de o jogador ter resolvido a anterior) seria a pior
    hora possivel pra descobrir: o catalogo inteiro e parseado contra o
    `Terrain` real na composicao, entao qualquer erro de dimensao,
    caractere ou marcador aparece antes do primeiro frame.
    """

    def __init__(self, levels: Tuple[LevelDefinition, ...]) -> None:
        if not levels:
            raise LevelCatalogError("catalogo de fases vazio")
        self._levels = levels
        self._chapters = _build_chapters(levels)

    @property
    def count(self) -> int:
        return len(self._levels)

    def at(self, index: int) -> LevelDefinition:
        return self._levels[index]

    @property
    def chapters(self) -> Tuple["Chapter", ...]:
        """Os capitulos, derivados do campo `chapter` das fases.

        Exige que as fases de um capitulo sejam CONTIGUAS -- o catalogo e
        ordenado por nome de arquivo, entao um capitulo partido em dois
        pedacos seria um erro de numeracao, nao um layout desejado, e o menu
        nao teria como paginar.
        """
        return self._chapters

    def chapter_of(self, index: int) -> "Chapter":
        for chapter in self._chapters:
            if chapter.first <= index <= chapter.last:
                return chapter
        return self._chapters[-1]

    @staticmethod
    def load_from_directory(levels_directory: Path) -> "LevelCatalog":
        """Le todos os `*.json` de `levels_directory` em ordem de nome de
        arquivo (o prefixo numerico dos arquivos define a progressao)."""
        directory = Path(levels_directory)
        paths = sorted(directory.glob("*.json"))
        if not paths:
            raise LevelCatalogError(f"nenhum arquivo de fase encontrado em {directory}")

        levels = []
        seen_ids = set()
        for path in paths:
            with path.open("r", encoding="utf-8") as handle:
                try:
                    raw = json.load(handle)
                except json.JSONDecodeError as exc:
                    raise LevelCatalogError(f"JSON invalido em {path}: {exc}") from exc

            if not isinstance(raw, dict):
                raise LevelCatalogError(f"{path}: arquivo de fase precisa ser um objeto JSON")
            for field in ("id", "name", "hint", "chapter", "rows"):
                if field not in raw:
                    raise LevelCatalogError(f"{path}: campo obrigatorio {field!r} ausente")
            if not isinstance(raw["rows"], list) or not all(isinstance(row, str) for row in raw["rows"]):
                raise LevelCatalogError(f"{path}: 'rows' precisa ser uma lista de strings")

            level_id = str(raw["id"])
            if level_id in seen_ids:
                raise LevelCatalogError(f"{path}: id de fase duplicado {level_id!r}")
            seen_ids.add(level_id)

            levels.append(
                LevelDefinition(
                    level_id=level_id,
                    name=str(raw["name"]),
                    hint=str(raw["hint"]),
                    chapter=int(raw.get("chapter", 1)),
                    rows=tuple(raw["rows"]),
                    teaches=str(raw.get("teaches", "")),
                )
            )

        return LevelCatalog(tuple(levels))

    def validate_all(self, terrain: Terrain) -> None:
        """Parseia cada fase do catalogo no `terrain` fornecido so pra
        provar que ela carrega. Deixa `terrain` com o conteudo da ULTIMA
        fase -- o chamador e responsavel por carregar a fase inicial
        depois (ver `penumbra.state.LevelRuntime.load`)."""
        for level in self._levels:
            try:
                terrain.load_rows(level.rows)
            except TerrainDefinitionError as exc:
                raise LevelCatalogError(f"fase {level.level_id!r} invalida: {exc}") from exc
