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
    """Uma fase: identidade, o que ela ensina, e o ASCII cru."""

    level_id: str
    name: str
    hint: str
    rows: Tuple[str, ...]


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

    @property
    def count(self) -> int:
        return len(self._levels)

    def at(self, index: int) -> LevelDefinition:
        return self._levels[index]

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
            for field in ("id", "name", "hint", "rows"):
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
                    rows=tuple(raw["rows"]),
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
