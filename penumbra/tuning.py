"""
Balanceamento de Penumbra, lido de `data/difficulties/penumbra/*.json`.

Existe para satisfazer de VERDADE a Regra 3 da Constituicao da
OuroborosEngine ("dificuldades ... vem de data/*.json, nunca hardcoded em
codigo Python") no campo `EngineConfig.difficulty_path` -- que o vertical
slice do Platformer deixou como debito declarado (o arquivo existia so pra
satisfazer o campo obrigatorio e nunca era lido). Aqui ele e a UNICA fonte
de todo numero de gameplay: nenhum sistema de `penumbra.systems` carrega
uma constante de balanceamento propria.
"""
from __future__ import annotations

import json
from dataclasses import dataclass


class TuningDefinitionError(Exception):
    """Levantado quando o JSON de dificuldade esta malformado ou tem um
    valor fora de faixa. Falha alto e cedo, na composicao -- nunca como
    um jogo silenciosamente injogavel (ex.: gravidade zero)."""


@dataclass(frozen=True)
class WorldTuning:
    """Dimensoes da grade e gravidade -- fixas para TODAS as fases (a
    `Grid2D` e as entidades de celula sao alocadas uma unica vez na
    composicao e reusadas a cada troca de fase, ver `penumbra.terrain`)."""

    cell_size: float
    grid_cols: int
    grid_rows: int
    gravity_y: float

    @property
    def half_cell(self) -> float:
        """Teto de `hitbox.half_width`/`half_height` imposto pelo
        `TileCollisionSystem` v1 (uma AABB nunca pode cobrir mais de
        2 colunas/2 linhas) -- validado por `_validate`."""
        return self.cell_size / 2.0


@dataclass(frozen=True)
class CharacterTuning:
    """Um dos dois seres. Os dois lados sao deliberadamente simetricos em
    ESTRUTURA (mesmos campos) e assimetricos em VALOR -- Lumen corre e
    salta mais, Umbra aguenta mais tempo na polaridade errada."""

    move_speed: float
    jump_velocity_y: float
    half_width: float
    half_height: float
    ability_charge_seconds: float
    ability_refill_per_second: float
    peril_seconds: float
    peril_recovery_per_second: float


@dataclass(frozen=True)
class LightTuning:
    """
    Parametros do campo de luz (ver `penumbra.systems.light_field_system`).

    `falloff_radius_cells` define o decaimento por celula
    (`1 / falloff_radius_cells`); uma semente de intensidade `I` deixa
    solida (`>= solid_threshold`) toda celula a distancia geodesica
    `<= (I - solid_threshold) * falloff_radius_cells`, contornando rocha.

    As tres faixas nunca coincidem, e e disso que o jogo vive:
    `extinguish_below` < `solid_threshold` < `dissolve_above`. Entre
    `extinguish_below` e `dissolve_above` existe uma penumbra em que os
    DOIS sobrevivem -- sem ela, toda celula mataria um dos dois e nenhuma
    fase seria solvel.
    """

    falloff_radius_cells: float
    solid_threshold: float
    lamp_intensity: float
    beam_intensity: float
    absorb_radius_cells: float
    extinguish_below: float
    dissolve_above: float
    relaxation_passes: int

    @property
    def decay_per_cell(self) -> float:
        return 1.0 / self.falloff_radius_cells


@dataclass(frozen=True)
class FlowTuning:
    """Duracao dos avisos de fase completa/falha."""

    overlay_seconds: float
    overlay_min_seconds: float


@dataclass(frozen=True)
class DualityTuning:
    """Raiz do balanceamento, montada por `from_json`."""

    name: str
    world: WorldTuning
    lumen: CharacterTuning
    umbra: CharacterTuning
    light: LightTuning
    flow: FlowTuning

    @staticmethod
    def from_json(difficulty_path: str) -> "DualityTuning":
        """Carrega e VALIDA o JSON de dificuldade apontado por
        `EngineConfig.difficulty_path`. Levanta `TuningDefinitionError`
        em qualquer campo ausente ou fora de faixa."""
        try:
            with open(difficulty_path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise TuningDefinitionError(f"nao foi possivel ler {difficulty_path}: {exc}") from exc

        tuning = DualityTuning(
            name=str(raw.get("name", "sem-nome")),
            world=WorldTuning(**_section(raw, "world", WorldTuning, difficulty_path)),
            lumen=CharacterTuning(**_section(raw, "lumen", CharacterTuning, difficulty_path)),
            umbra=CharacterTuning(**_section(raw, "umbra", CharacterTuning, difficulty_path)),
            light=LightTuning(**_section(raw, "light", LightTuning, difficulty_path)),
            flow=FlowTuning(**_section(raw, "flow", FlowTuning, difficulty_path)),
        )
        _validate(tuning, difficulty_path)
        return tuning


def _section(raw: dict, key: str, schema: type, path: str) -> dict:
    """Extrai `raw[key]` e mantem so as chaves declaradas na dataclass
    `schema` -- chaves de documentacao dentro do JSON (`_nota`, idioma ja
    usado pelos arquivos de dados da engine) sao descartadas, chaves
    obrigatorias ausentes viram `TuningDefinitionError`."""
    section = raw.get(key)
    if not isinstance(section, dict):
        raise TuningDefinitionError(f"{path}: secao obrigatoria {key!r} ausente ou nao e um objeto")
    expected = tuple(schema.__dataclass_fields__)
    missing = [field for field in expected if field not in section]
    if missing:
        raise TuningDefinitionError(f"{path}: secao {key!r} sem os campos obrigatorios {missing}")
    return {field: section[field] for field in expected}


def _validate(tuning: DualityTuning, path: str) -> None:
    """Barra as combinacoes que produziriam um jogo injogavel em vez de um
    erro visivel -- em particular a ordem das tres faixas de luz, a unica
    invariante do jogo que um arquivo de dados pode quebrar sem causar
    nenhuma excecao em runtime."""
    world, light = tuning.world, tuning.light
    if world.cell_size <= 0.0 or world.grid_cols <= 0 or world.grid_rows <= 0:
        raise TuningDefinitionError(f"{path}: 'world' precisa de cell_size/grid_cols/grid_rows positivos")
    if world.gravity_y <= 0.0:
        raise TuningDefinitionError(f"{path}: 'world.gravity_y' precisa ser positivo (+y = baixo nesta engine)")
    if light.falloff_radius_cells <= 0.0 or light.relaxation_passes <= 0:
        raise TuningDefinitionError(f"{path}: 'light' precisa de falloff_radius_cells/relaxation_passes positivos")
    if not (light.extinguish_below < light.solid_threshold < light.dissolve_above):
        raise TuningDefinitionError(
            f"{path}: 'light' exige extinguish_below < solid_threshold < dissolve_above "
            f"(recebido {light.extinguish_below} / {light.solid_threshold} / {light.dissolve_above}) -- "
            f"sem essa penumbra intermediaria nenhuma fase e solvel"
        )
    for who, character in (("lumen", tuning.lumen), ("umbra", tuning.umbra)):
        if character.half_width > world.half_cell or character.half_height > world.half_cell:
            raise TuningDefinitionError(
                f"{path}: {who!r} tem hitbox maior que metade do cell_size ({world.half_cell}) -- "
                f"TileCollisionSystem v1 nao suporta isso"
            )
        if character.jump_velocity_y >= 0.0:
            raise TuningDefinitionError(f"{path}: '{who}.jump_velocity_y' precisa ser negativo (+y = baixo)")
        if character.peril_seconds <= 0.0 or character.ability_charge_seconds <= 0.0:
            raise TuningDefinitionError(f"{path}: {who!r} precisa de peril_seconds/ability_charge_seconds positivos")
