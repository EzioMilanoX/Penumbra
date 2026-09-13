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
from dataclasses import MISSING, dataclass


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
    crust_break_seconds: float = 0.0
    """Segundos empurrando pra romper uma celula de crosta. So a Umbra
    rompe, entao so a secao dela precisa declarar isto -- o default zerado
    do lado da Lumen nunca e lido (`CrustBreakSystem` so olha a Umbra)."""
    coyote_seconds: float = 0.10
    """Quanto tempo depois de sair da beira o salto ainda vale.

    Sem isto, sair da plataforma um frame antes de apertar custa o salto --
    e o jogador nao tem como saber que apertou tarde, porque a diferenca e
    de 16 ms. Nao abre caminho novo: a janela e menor que o tempo de queda
    de meia celula."""
    jump_buffer_seconds: float = 0.12
    """Quanto tempo antes de encostar no chao o salto ainda e lembrado.

    O espelho do coyote: apertar um frame ANTES de pousar tambem custava o
    salto. Os dois juntos cobrem os dois lados do mesmo erro de 16 ms, que e
    o unico erro de plataforma que o jogador nao consegue ver."""


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
    """Duracao dos avisos de fim de fase, e os dois relogios do mundo
    (ver `penumbra.systems.world_clock_system`)."""

    overlay_seconds: float
    overlay_min_seconds: float
    beacon_on_seconds: float = 2.6
    beacon_off_seconds: float = 2.0
    eclipse_collapse_seconds: float = 6.5
    wanderer_speed_cells: float = 2.1
    form_sacrifice_seconds: float = 1.1
    source_period_seconds: float = 5.2
    source_min_intensity: float = 0.45
    source_max_intensity: float = 1.0


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
    fields = schema.__dataclass_fields__
    expected = tuple(fields)
    # Campos com default sao opcionais no JSON; os demais, obrigatorios.
    required = [
        name for name, field in fields.items()
        if field.default is MISSING and field.default_factory is MISSING
    ]
    missing = [field for field in required if field not in section]
    if missing:
        raise TuningDefinitionError(f"{path}: secao {key!r} sem os campos obrigatorios {missing}")
    return {field: section[field] for field in expected if field in section}


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
    flow = tuning.flow
    if flow.beacon_on_seconds <= 0.0 or flow.beacon_off_seconds <= 0.0:
        raise TuningDefinitionError(f"{path}: 'flow' precisa de um ciclo de farol com as duas metades positivas")
    if flow.eclipse_collapse_seconds <= 0.0:
        raise TuningDefinitionError(f"{path}: 'flow.eclipse_collapse_seconds' precisa ser positivo")
    if flow.wanderer_speed_cells <= 0.0:
        raise TuningDefinitionError(f"{path}: 'flow.wanderer_speed_cells' precisa ser positivo")
    if flow.source_period_seconds <= 0.0:
        raise TuningDefinitionError(f"{path}: 'flow.source_period_seconds' precisa ser positivo")
    if not (0.0 <= flow.source_min_intensity < flow.source_max_intensity):
        raise TuningDefinitionError(
            f"{path}: a fonte precisa de source_min_intensity < source_max_intensity "
            f"(recebido {flow.source_min_intensity} / {flow.source_max_intensity}) -- "
            f"iguais, ela seria uma lampada comum e nada respiraria"
        )
    if flow.form_sacrifice_seconds <= 0.0:
        raise TuningDefinitionError(
            f"{path}: 'flow.form_sacrifice_seconds' precisa ser positivo -- deixar a forma e "
            f"irreversivel, entao nao pode acontecer num frame"
        )
    for who, character in (("lumen", tuning.lumen), ("umbra", tuning.umbra)):
        if character.half_width > world.half_cell or character.half_height > world.half_cell:
            raise TuningDefinitionError(
                f"{path}: {who!r} tem hitbox maior que metade do cell_size ({world.half_cell}) -- "
                f"TileCollisionSystem v1 nao suporta isso"
            )
        if character.jump_velocity_y >= 0.0:
            raise TuningDefinitionError(f"{path}: '{who}.jump_velocity_y' precisa ser negativo (+y = baixo)")
        if character.crust_break_seconds < 0.0:
            raise TuningDefinitionError(f"{path}: '{who}.crust_break_seconds' nao pode ser negativo")
        if character.coyote_seconds < 0.0 or character.jump_buffer_seconds < 0.0:
            raise TuningDefinitionError(f"{path}: {who!r} nao pode ter coyote/buffer negativo")
        if character.peril_seconds <= 0.0 or character.ability_charge_seconds <= 0.0:
            raise TuningDefinitionError(f"{path}: {who!r} precisa de peril_seconds/ability_charge_seconds positivos")
