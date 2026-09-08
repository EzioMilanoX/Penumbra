"""
Composicao de Penumbra: monta o `World`, os dois seres e a ordem dos sistemas.

O ponto nao-obvio deste arquivo e como dois seres podem ter chaos
DIFERENTES na mesma simulacao. `TileCollisionSystem` resolve toda entidade
com Transform+Velocity+Hitbox contra UMA grade -- e os nomes das tres pools
sao parametros do construtor dele. Entao Penumbra cria uma segunda pool de
hitbox (`hitbox_shadow`) e registra DOIS `TileCollisionSystem`: um contra a
grade da luz, olhando so quem tem `hitbox`; outro contra a grade da sombra,
olhando so quem tem `hitbox_shadow`. Lumen esta num conjunto, Umbra no
outro, e nenhum dos dois sistemas sabe que o outro existe.

Esse e o mesmo idioma que a propria engine documenta como saida para
"algumas entidades precisam de fisica diferente" (ver a docstring do
`GravitySystem` sobre entidades imunes a gravidade precisarem de uma pool
`velocity` separada) -- pools separadas, nao ramos condicionais dentro de um
sistema generico.

Dois pontos de entrada, um so caminho de montagem: `build_game` abre janela
e devolve um `GameLoop`; `build_simulation` monta a MESMA simulacao sem
tocar nenhum backend concreto (via `CompositionRoot.build_world`, que existe
exatamente pra isso), o que permite testar e auditar as fases de verdade,
headless. Os dois passam por `_assemble`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import numpy as np

from ouroboros.bootstrap.composition_root import CompositionRoot
from ouroboros.bootstrap.engine_config import EngineConfig
from ouroboros.bootstrap.game_loop import GameLoop
from ouroboros.core.components.schemas import HITBOX_DTYPE
from ouroboros.core.grid2d import Grid2D
from ouroboros.core.memory.component_pool import ComponentPool
from ouroboros.core.memory.handles import unpack_index
from ouroboros.core.systems.gravity_system import GravitySystem
from ouroboros.core.systems.tile_collision_system import TileCollisionSystem
from ouroboros.core.world import World
from ouroboros.interfaces.input_provider import IInputProvider
from ouroboros.interfaces.null.null_input_provider import NullInputProvider
from ouroboros.interfaces.renderer import SHAPE_CIRCLE, SHAPE_RECT
from ouroboros.roguelite.entities.archetype_loader import ArchetypeLoader

from penumbra.hud import PenumbraHud
from penumbra.levels import LevelCatalog
from penumbra.scenes import PenumbraScene
from penumbra.state import DualityState, LevelRuntime, LUMEN, UMBRA
from penumbra.systems.duality_control_system import DualityControlSystem
from penumbra.systems.light_field_system import LightFieldSystem
from penumbra.systems.outcome_system import OutcomeSystem
from penumbra.systems.polarity_door_system import PolarityDoorSystem
from penumbra.systems.presentation_system import PresentationSystem
from penumbra.systems.quit_on_action_system import QuitOnActionSystem
from penumbra.terrain import Terrain
from penumbra.tuning import DualityTuning

LUMEN_ARCHETYPE = "lumen"
UMBRA_ARCHETYPE = "umbra"
CELL_ARCHETYPE = "cell"
AURA_ARCHETYPE = "aura"

SHADOW_HITBOX_POOL = "hitbox_shadow"
"""Segunda pool de hitbox, com o MESMO `HITBOX_DTYPE` da generica. E o
unico motivo pelo qual Umbra pode pisar onde Lumen cai."""

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
ARCHETYPES_DIR = _PROJECT_ROOT / "data" / "archetypes" / "penumbra"
LEVELS_DIR = _PROJECT_ROOT / "data" / "levels"

_CELL_SPRITE_UNIT = 8.0
_LAYER_CELL = 5
_LAYER_CHARACTER = 20
_AURA_LAYERS = (15, 15, 25)
"""Camada de cada slot de aura: o halo da Lumen e a orla da Umbra ficam
ATRAS dos corpos (15 < 20); o anel dourado de "quem esta sob comando" fica
na frente de tudo (25), pra nunca ser encoberto pelo corpo que ele marca."""
_AURA_SLOTS = len(_AURA_LAYERS)


@dataclass(frozen=True)
class Simulation:
    """Tudo que uma simulacao de Penumbra precisa, montada e pronta pra
    `world.step()`. Devolvida pelo caminho headless; `build_game` guarda as
    mesmas pecas dentro do `GameLoop`."""

    world: World
    tuning: DualityTuning
    terrain: Terrain
    catalog: LevelCatalog
    state: DualityState
    runtime: LevelRuntime
    lumen_grid: Grid2D
    umbra_grid: Grid2D
    tile_collision_systems: Tuple[TileCollisionSystem, TileCollisionSystem]


class _WorldPoolRegistry:
    """
    Adapta o `World` a superficie que `TileCollisionSystem`/`GravitySystem`
    de fato consomem do `MemoryManager` que recebem: `get_pool(name)`,
    chamado uma unica vez, no `__init__` deles -- nunca em `update()`.

    Existe porque `CompositionRoot` guarda o `MemoryManager` pra si (a
    docstring dele diz, textualmente, que nenhum script de composicao de
    produto precisa de acesso direto a ele, so a `world.get_pool(...)`) e so
    constroi UM `TileCollisionSystem`, com a grade passada em
    `build(tile_grid=...)`. Penumbra precisa de um segundo, e precisa
    registra-lo entre o primeiro e o `GravitySystem` -- ordem que
    `world.register_system` (que so faz append) obriga a montar aqui, nao
    la.

    Passar o proprio `World` funcionaria por acaso, ja que ele tem
    `get_pool` com a mesma assinatura; este adaptador existe pra que isso
    seja uma escolha declarada em vez de uma coincidencia de nomes.
    """

    def __init__(self, world: World) -> None:
        self._world = world

    def get_pool(self, name: str) -> ComponentPool:
        return self._world.get_pool(name)


def build_game(config: EngineConfig) -> GameLoop:
    """Monta Penumbra inteira, com janela, e devolve um `GameLoop` pronto
    para `.run()`."""
    tuning, terrain, catalog = _load_data(config)
    lumen_grid, umbra_grid = _make_grid(tuning.world), _make_grid(tuning.world)

    # `tile_grid=` monta o TileCollisionSystem da Lumen na posicao certa da
    # ordem; `gravity_y` e deliberadamente OMITIDO pra que o GravitySystem
    # possa ser registrado depois do segundo TileCollisionSystem.
    game_loop = CompositionRoot(config).build(tile_grid=lumen_grid)
    simulation = _assemble(
        game_loop.world, config, tuning, terrain, catalog,
        lumen_grid, umbra_grid, game_loop.input_provider,
    )

    world = simulation.world
    world.register_system(QuitOnActionSystem(game_loop.input_provider, game_loop))
    game_loop.set_on_draw_ui(
        PenumbraHud(
            simulation.state, simulation.runtime, tuning,
            world.get_pool("transform"), game_loop.renderer.get_viewport_size(),
        )
    )
    game_loop.reset_scenes(
        PenumbraScene(simulation.runtime, simulation.state, tuning, game_loop.input_provider)
    )
    return game_loop


def build_simulation(
    config: EngineConfig, input_provider: Optional[IInputProvider] = None
) -> Simulation:
    """
    Monta a mesma simulacao de `build_game` SEM abrir janela nem tocar
    `pygame`, via `CompositionRoot.build_world` (o ponto que a engine
    oferece justamente pra quem precisa de um `World` completo no Pilar 1
    sem renderer/input/audio).

    E isto que torna possivel testar as regras da dualidade e auditar o
    balanceamento de luz das fases de verdade -- rodando a simulacao real,
    nao uma reimplementacao das mesmas contas dentro do teste.
    """
    tuning, terrain, catalog = _load_data(config)
    lumen_grid, umbra_grid = _make_grid(tuning.world), _make_grid(tuning.world)
    world = CompositionRoot(config).build_world(tile_grid=lumen_grid)
    return _assemble(
        world, config, tuning, terrain, catalog, lumen_grid, umbra_grid,
        input_provider if input_provider is not None else NullInputProvider(),
    )


# ----------------------------------------------------------------------
# montagem compartilhada
# ----------------------------------------------------------------------


def _assemble(
    world: World,
    config: EngineConfig,
    tuning: DualityTuning,
    terrain: Terrain,
    catalog: LevelCatalog,
    lumen_grid: Grid2D,
    umbra_grid: Grid2D,
    input_provider: IInputProvider,
) -> Simulation:
    """
    Registra tudo que e especifico de Penumbra por cima do `World` que a
    engine ja montou. Ordem dos sistemas, e por que ela e essa:

    1. `PhysicsSystem`        (engine) -- integra posicao
    2. `CollisionSystem`      (engine) -- ocioso aqui, so Lumen tem `hitbox`
    3. `TileCollisionSystem`  (engine, `tile_grid=`) -- Lumen contra a grade da luz
    4. `TileCollisionSystem`  (aqui) -- Umbra contra a grade da sombra
    5. `GravitySystem`        (aqui) -- fecha o contrato Physics -> Tile* -> Gravity
    6. `DualityControlSystem` -- escreve `velocity` depois de tudo acima,
       a unica posicao valida pra um sistema de input (o mesmo contrato do
       vertical slice do Platformer)
    7. `LightFieldSystem`     -- recalcula a luz e as duas grades
    8. `PolarityDoorSystem`   -- le a luz deste frame
    9. `OutcomeSystem`        -- le posicoes ja resolvidas
    10. `PresentationSystem`  -- so pixels; removivel sem mudar o jogo
    """
    world.create_pool(SHADOW_HITBOX_POOL, HITBOX_DTYPE)
    ArchetypeLoader(ARCHETYPES_DIR).load_and_register_all(world)

    state = DualityState(terrain)
    state.entity_index[LUMEN] = _spawn_character(world, LUMEN_ARCHETYPE, tuning.lumen, "hitbox", SHAPE_CIRCLE)
    state.entity_index[UMBRA] = _spawn_character(
        world, UMBRA_ARCHETYPE, tuning.umbra, SHADOW_HITBOX_POOL, SHAPE_RECT
    )
    cell_entity_indices = _spawn_cells(world, terrain)
    aura_entity_indices = _spawn_auras(world)

    registry = _WorldPoolRegistry(world)
    umbra_tile_collision = TileCollisionSystem(
        registry, umbra_grid, config.entity_capacity, hitbox_pool_name=SHADOW_HITBOX_POOL
    )
    world.register_system(umbra_tile_collision)
    world.register_system(GravitySystem(registry, tuning.world.gravity_y))

    lumen_tile_collision = _find_lumen_tile_collision(world, umbra_tile_collision)
    tile_collision_systems = (lumen_tile_collision, umbra_tile_collision)

    world.register_system(DualityControlSystem(input_provider, state, tuning, tile_collision_systems))
    world.register_system(LightFieldSystem(terrain, state, tuning, lumen_grid, umbra_grid))
    world.register_system(PolarityDoorSystem(terrain, state))
    world.register_system(OutcomeSystem(terrain, state, tuning))
    world.register_system(
        PresentationSystem(terrain, state, tuning, cell_entity_indices, aura_entity_indices)
    )

    runtime = LevelRuntime(world, terrain, catalog, state, tuning)
    runtime.load(0)

    return Simulation(
        world=world,
        tuning=tuning,
        terrain=terrain,
        catalog=catalog,
        state=state,
        runtime=runtime,
        lumen_grid=lumen_grid,
        umbra_grid=umbra_grid,
        tile_collision_systems=tile_collision_systems,
    )


def _load_data(config: EngineConfig):
    """Carrega e valida TODO o conteudo data-driven antes de qualquer
    entidade existir: balanceamento, dimensoes da grade e as quatro fases
    (cada uma parseada de verdade -- ver `LevelCatalog.validate_all`)."""
    tuning = DualityTuning.from_json(config.difficulty_path)
    terrain = Terrain(tuning.world.grid_cols, tuning.world.grid_rows, tuning.world.cell_size)
    catalog = LevelCatalog.load_from_directory(LEVELS_DIR)
    catalog.validate_all(terrain)
    return tuning, terrain, catalog


def _make_grid(world_tuning) -> Grid2D:
    return Grid2D(
        cols=world_tuning.grid_cols,
        rows=world_tuning.grid_rows,
        cell_size=world_tuning.cell_size,
    )


def _find_lumen_tile_collision(world: World, umbra_system: TileCollisionSystem) -> TileCollisionSystem:
    """Recupera o `TileCollisionSystem` que a engine ja registrou (o da
    Lumen) -- `DualityControlSystem` precisa consultar `is_grounded()` da
    MESMA instancia do frame corrente, nunca de uma segunda construida a
    parte. Mesmo idioma de `_find_collision_system` no Roguelite e
    `_find_tile_collision_system` no Platformer, so que aqui ha dois
    candidatos e o nosso e o que NAO acabamos de registrar."""
    for system in world.systems:
        if isinstance(system, TileCollisionSystem) and system is not umbra_system:
            return system
    raise RuntimeError("build_world(tile_grid=...) deveria ter registrado um TileCollisionSystem")


def _spawn_character(world: World, archetype: str, character_tuning, hitbox_pool: str, shape: int) -> int:
    """Cria um dos dois seres. Posicao e velocidade ficam por conta de
    `LevelRuntime.reset()` (que roda a cada fase e a cada morte); aqui se
    escreve so o que nunca muda: hitbox, forma e camada."""
    index = unpack_index(world.create_entity(archetype, clear=True))

    hitbox_pool_ref = world.get_pool(hitbox_pool)
    hitbox_row = hitbox_pool_ref.dense_row_of(index)
    hitbox_view = hitbox_pool_ref.active_view()
    hitbox_view["half_width"][hitbox_row] = character_tuning.half_width
    hitbox_view["half_height"][hitbox_row] = character_tuning.half_height
    hitbox_view["collision_layer"][hitbox_row] = 1
    hitbox_view["collision_mask"][hitbox_row] = 0

    transform_pool = world.get_pool("transform")
    transform_row = transform_pool.dense_row_of(index)
    transform_view = transform_pool.active_view()
    transform_view["rotation_rad"][transform_row] = 0.0
    transform_view["scale_x"][transform_row] = (character_tuning.half_width * 2.0) / _CELL_SPRITE_UNIT
    transform_view["scale_y"][transform_row] = (character_tuning.half_height * 2.0) / _CELL_SPRITE_UNIT

    sprite_pool = world.get_pool("sprite")
    sprite_row = sprite_pool.dense_row_of(index)
    sprite_view = sprite_pool.active_view()
    sprite_view["texture_id"][sprite_row] = shape
    sprite_view["tint_a"][sprite_row] = 255
    sprite_view["layer_z"][sprite_row] = _LAYER_CHARACTER

    return index


def _spawn_cells(world: World, terrain: Terrain) -> np.ndarray:
    """Uma entidade visual por celula, em ordem row-major -- a MESMA ordem
    de `terrain.role.reshape(-1)`, que e o que permite ao
    `PresentationSystem` pintar a grade inteira com ufuncs em vez de um laco
    por celula. Estas entidades nunca sao destruidas, nem quando a fase
    troca: so as mascaras do `Terrain` sao recarregadas."""
    entity_indices = np.zeros(terrain.rows * terrain.cols, dtype=np.int64)
    transform_pool = world.get_pool("transform")
    sprite_pool = world.get_pool("sprite")

    slot = 0
    for row in range(terrain.rows):
        for col in range(terrain.cols):
            index = unpack_index(world.create_entity(CELL_ARCHETYPE, clear=True))
            entity_indices[slot] = index
            slot += 1

            center_x, center_y = terrain.cell_center((col, row))
            transform_row = transform_pool.dense_row_of(index)
            transform_view = transform_pool.active_view()
            transform_view["position_x"][transform_row] = center_x
            transform_view["position_y"][transform_row] = center_y

            sprite_pool.active_view()["layer_z"][sprite_pool.dense_row_of(index)] = _LAYER_CELL

    return entity_indices


def _spawn_auras(world: World) -> np.ndarray:
    """Halo da Lumen, orla da Umbra e o anel que marca quem esta sob
    comando -- posicao, forma e cor sao reescritas todo frame pelo
    `PresentationSystem`."""
    entity_indices = np.zeros(_AURA_SLOTS, dtype=np.int64)
    sprite_pool = world.get_pool("sprite")
    for slot in range(_AURA_SLOTS):
        index = unpack_index(world.create_entity(AURA_ARCHETYPE, clear=True))
        entity_indices[slot] = index
        sprite_pool.active_view()["layer_z"][sprite_pool.dense_row_of(index)] = _AURA_LAYERS[slot]
    return entity_indices
