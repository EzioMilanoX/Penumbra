"""
Auditoria de balanceamento de luz das fases.

    python -m tools.audit_levels

Roda a simulacao REAL headless (`penumbra.composition.build_simulation`,
sem janela) e mede, fase por fase, as tres coisas que decidem se uma fase e
jogavel e que nao se enxergam olhando o ASCII:

* **Eter**: cada celula de eter esta acesa (chao da Lumen) ou apagada (chao
  da Umbra) com apenas as lampadas estaticas? Sem isso nao ha como saber de
  quem e cada ponte.
* **Sobrevivencia**: cada celula onde um ser pode ficar de pe esta dentro da
  faixa que ele aguenta -- luz >= `extinguish_below` pra Lumen, luz <=
  `dissolve_above` pra Umbra. Um trecho fora da faixa nao e
  necessariamente um erro (atravessar correndo e uma decisao valida, e o
  facho/absorcao existem pra isso), mas precisa ser uma escolha do design,
  nao uma surpresa.
* **Autossuporte**: com o facho ligado, a Lumen acende o eter sob os
  proprios pes? Se nao, aquela ponte e intransponivel pra ela por qualquer
  caminho.
* **Alcance geometrico**: os pes chegam? Um degrau alto demais, ou um bloco
  exatamente sobre a cabeca, torna uma fase insolvel sem nenhuma relacao com
  luz -- e sem gerar erro nenhum. Inclui a checagem de mao unica: de toda
  celula alcancavel ainda ha volta pra zona de polaridade?

Isto NAO e um teste (nao afirma nada, nao falha): e o instrumento que
respondeu as perguntas de projeto das quatro fases. Os testes de regressao
de verdade estao em `tests/`.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from ouroboros.bootstrap.engine_config import EngineConfig

from penumbra.composition import build_simulation
from penumbra.reachability import JumpModel, TraversalGraph, solid_mask
from penumbra.state import LUMEN, UMBRA

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "penumbra" / "config.json"

_LIGHT_GLYPHS = (
    (0.12, " "),   # abaixo disto a Lumen se apaga
    (0.35, "."),   # penumbra: eter apagado, os dois sobrevivem
    (0.60, ":"),   # eter aceso, Umbra ainda aguenta
    (0.85, "+"),   # Umbra se dissolve
    (99.0, "#"),
)


def light_glyph(value: float) -> str:
    for ceiling, glyph in _LIGHT_GLYPHS:
        if value < ceiling:
            return glyph
    return "#"


def settle(simulation, frames: int = 3) -> None:
    """Alguns frames pro campo de luz e as duas grades se estabilizarem
    (o campo do frame N e composto a partir das posicoes do frame N)."""
    for _ in range(frames):
        simulation.world.step(1.0 / 60.0)


def place(simulation, side: int, col: int, row: int) -> None:
    """Move um ser pra uma celula especifica, sem passar pelo input --
    ferramenta de sonda, nao gameplay."""
    pool = simulation.world.get_pool("transform")
    dense_row = pool.dense_row_of(int(simulation.state.entity_index[side]))
    view = pool.active_view()
    x, y = simulation.terrain.cell_center((col, row))
    view["position_x"][dense_row] = x
    view["position_y"][dense_row] = y


def audit_level(simulation, level_index: int) -> None:
    tuning = simulation.tuning
    light_tuning = tuning.light
    terrain = simulation.terrain
    state = simulation.state

    simulation.runtime.load(level_index)
    level = simulation.runtime.current
    state.ability_on[:] = False
    settle(simulation)

    print("=" * 78)
    print(f"FASE {level_index + 1}: {level.name}   ({level.level_id})")
    print(f"  {level.hint}")
    print("=" * 78)

    light = state.light.copy()
    print("\n  campo de luz  (' '<0.12 apaga Lumen | '.'<0.35 eter apagado | "
          "':'<0.60 eter aceso | '+'>=0.60 dissolve Umbra)")
    for row in range(terrain.rows):
        glyphs = "".join(light_glyph(float(light[row, col])) for col in range(terrain.cols))
        terrain_row = "".join(_terrain_glyph(terrain, row, col) for col in range(terrain.cols))
        print(f"   {row:2d} |{glyphs}|  {terrain_row}")

    _report_markers(terrain, state, light, light_tuning)
    _report_ether(terrain, state, light, light_tuning)
    _report_standing(terrain, light, light_tuning)
    _report_self_support(simulation, light_tuning)
    _report_door_feasibility(simulation, light_tuning)
    _report_reachability(simulation)
    print()


def _terrain_glyph(terrain, row: int, col: int) -> str:
    if terrain.rock[row, col]:
        return "#"
    if terrain.door[row, col]:
        return "D"
    if terrain.ether[row, col]:
        return "~"
    if terrain.lamp[row, col] > 0.0:
        return "*"
    if terrain.zone_light[row, col]:
        return "L"
    if terrain.zone_shadow[row, col]:
        return "S"
    return "."


def _report_markers(terrain, state, light, light_tuning) -> None:
    print("\n  marcadores:")
    markers = (
        ("A  spawn Lumen", terrain.lumen_spawn_cell, LUMEN),
        ("X  portal Lumen", terrain.lumen_goal_cell, LUMEN),
        ("B  spawn Umbra", terrain.umbra_spawn_cell, UMBRA),
        ("Y  portal Umbra", terrain.umbra_goal_cell, UMBRA),
    )
    for label, cell, side in markers:
        col, row = cell
        value = float(light[row, col])
        if side == LUMEN:
            verdict = "OK" if value >= light_tuning.extinguish_below else "APAGA (precisa do facho)"
        else:
            verdict = "OK" if value <= light_tuning.dissolve_above else "DISSOLVE (precisa absorver)"
        print(f"    {label:16s} col={col:2d} row={row:2d}  luz={value:.3f}  {verdict}")

    for label, mask, want_lit in (
        ("L  zona de luz", terrain.zone_light, True),
        ("S  zona de sombra", terrain.zone_shadow, False),
    ):
        for row, col in zip(*np.nonzero(mask)):
            value = float(light[row, col])
            is_lit = value >= light_tuning.solid_threshold
            if want_lit:
                verdict = "ja acesa (facho dispensavel)" if is_lit else "apagada -> exige o facho da Lumen"
            else:
                verdict = "apagada OK" if not is_lit else "ACESA -> a porta nunca abriria"
            print(f"    {label:16s} col={col:2d} row={row:2d}  luz={value:.3f}  {verdict}")


def _report_ether(terrain, state, light, light_tuning) -> None:
    """Os dois materiais que trocam de dono, cada um com a sua regra.

    O contra-eter entra aqui, e nao num relatorio a parte, porque a pergunta
    e a mesma -- "de quem e este chao agora?" -- e ve-los lado a lado e o
    unico jeito de notar que uma mudanca de luz serve um e atrapalha o outro
    no mesmo instante."""
    if not (terrain.ether.any() or terrain.counter_ether.any()):
        print("\n  eter: nenhum nesta fase")
        return
    for mask, title, lit_owner, dark_owner in (
        (terrain.ether, "eter (so lampadas estaticas)", "Lumen", "Umbra"),
        (terrain.counter_ether, "contra-eter (a regra invertida)", "Umbra", "Lumen"),
    ):
        rows, cols = np.nonzero(mask)
        if rows.size == 0:
            continue
        print(f"\n  {title}:")
        for row in sorted(set(rows.tolist())):
            row_cols = sorted(cols[rows == row].tolist())
            lit = [c for c in row_cols
                   if float(light[row, c]) >= light_tuning.solid_threshold]
            dark = [c for c in row_cols if c not in lit]
            print(f"    row {row:2d}  cols {_ranges(row_cols)}")
            print(f"              aceso (chao da {lit_owner}): {_ranges(lit) or '-'}")
            print(f"              apagado (chao da {dark_owner}): {_ranges(dark) or '-'}")


def _report_standing(terrain, light, light_tuning) -> None:
    """Toda celula vazia com chao solido logo abaixo -- onde um ser pode
    de fato ficar de pe -- classificada pelas faixas dos dois."""
    print("\n  onde da pe ficar de pe:")
    solid = (terrain.rock | terrain.ether | terrain.counter_ether
             | terrain.crust | terrain.eclipse | terrain.glass | terrain.door)
    for row in range(terrain.rows - 1):
        standable = [
            col for col in range(terrain.cols)
            if not solid[row, col] and solid[row + 1, col]
        ]
        if not standable:
            continue
        lumen_bad = [c for c in standable if float(light[row, c]) < light_tuning.extinguish_below]
        umbra_bad = [c for c in standable if float(light[row, c]) > light_tuning.dissolve_above]
        print(f"    row {row:2d}  cols {_ranges(standable)}")
        print(f"              Lumen se apaga em: {_ranges(lumen_bad) or '-'}")
        print(f"              Umbra se dissolve em: {_ranges(umbra_bad) or '-'}")


def _report_self_support(simulation, light_tuning) -> None:
    """Com o facho ligado e a Lumen de pe sobre cada celula de eter, aquela
    celula acende? Se alguma nao acender, a ponte e impossivel pra ela."""
    terrain, state = simulation.terrain, simulation.state
    rows, cols = np.nonzero(terrain.ether)
    if rows.size == 0:
        return
    failures = []
    state.ability_on[LUMEN] = True
    for row, col in zip(rows.tolist(), cols.tolist()):
        if row == 0:
            continue
        place(simulation, LUMEN, col, row - 1)
        state.charge[LUMEN] = 1.0
        settle(simulation, frames=2)
        if not bool(state.lit[row, col]):
            failures.append((col, row))
    state.ability_on[LUMEN] = False
    verdict = "-" if not failures else str(failures)
    print(f"\n  autossuporte da Lumen (facho ligado, de pe sobre cada eter): falhas = {verdict}")


def _report_door_feasibility(simulation, light_tuning) -> None:
    """
    A pergunta que decide se uma fase com porta e solvel: com a Lumen de pe
    na zona de luz e o facho ligado, a zona de sombra CONTINUA apagada?

    O facho e a unica forma de acender a zona dela, e ele alcanca longe. Se
    ele vazar ate a zona da Umbra, as duas condicoes nunca sao verdadeiras
    ao mesmo tempo e a porta nunca abre -- uma fase insolvel que nao gera
    erro nenhum em runtime. So a rocha entre as duas zonas impede isso, e
    se ela e suficiente nao se ve no ASCII.
    """
    terrain, state = simulation.terrain, simulation.state
    if not terrain.has_door:
        return

    light_cells = list(zip(*np.nonzero(terrain.zone_light)))
    shadow_cells = list(zip(*np.nonzero(terrain.zone_shadow)))
    print("\n  porta de polaridade (Lumen na zona de luz, facho ligado):")
    for light_row, light_col in light_cells:
        place(simulation, LUMEN, light_col, light_row)
        state.ability_on[LUMEN] = True
        state.ability_on[UMBRA] = False
        for shadow_row, shadow_col in shadow_cells:
            place(simulation, UMBRA, shadow_col, shadow_row)
            state.charge[:] = 1.0
            settle(simulation, frames=2)
            zone_lit = bool(state.lit[light_row, light_col])
            shadow_light = float(state.light[shadow_row, shadow_col])
            shadow_dark = shadow_light < light_tuning.solid_threshold
            umbra_safe = shadow_light <= light_tuning.dissolve_above
            verdict = "ABRE" if (zone_lit and shadow_dark) else "NAO ABRE"
            print(
                f"    L({light_col},{light_row}) acesa={zone_lit}"
                f"   S({shadow_col},{shadow_row}) luz={shadow_light:.3f}"
                f" apagada={shadow_dark} Umbra_sobrevive={umbra_safe}   -> {verdict}"
            )
    state.ability_on[:] = False


def _report_reachability(simulation) -> None:
    """
    Geometria, nao polaridade: os pes alcancam?

    Mede as duas coisas que o ASCII esconde. Primeiro, se cada ser sai do
    spawn e chega ao proprio portal. Segundo -- e e este que pegou o bug da
    fase 4 -- se de TODA celula alcancavel ainda ha volta pra zona de
    polaridade. Uma descida de mao unica nao mata, nao avisa e nao gera
    erro: ela so deixa o jogador na frente de uma porta que nunca abre.
    """
    terrain, tuning = simulation.terrain, simulation.tuning
    print("\n  alcance geometrico (rocha + eter + porta, otimista):")
    for who, spawn, goal, zones, side_tuning in (
        ("Lumen", terrain.lumen_spawn_cell, terrain.lumen_goal_cell,
         terrain.zone_light, tuning.lumen),
        ("Umbra", terrain.umbra_spawn_cell, terrain.umbra_goal_cell,
         terrain.zone_shadow, tuning.umbra),
    ):
        model = JumpModel(tuning.world, side_tuning)
        open_graph = TraversalGraph(solid_mask(terrain, door_open=True), model)
        reachable = open_graph.reachable_from(spawn)
        line = (
            f"    {who}: sobe {model.max_climb} celula(s) | "
            f"{len(reachable)} celulas alcancaveis | portal={'OK' if goal in reachable else 'INALCANCAVEL'}"
        )
        # So faz sentido com porta de ZONAS. Numa porta de PLACA o gatilho
        # e "alguem em cima agora", nao "voltar a um lugar" -- e a checagem
        # de mao unica dizia que as fases de placa travavam todas, porque
        # procurava uma zona que elas nao tem.
        if terrain.has_door and zones.any():
            closed_graph = TraversalGraph(solid_mask(terrain, door_open=False), model)
            closed_reachable = closed_graph.reachable_from(spawn)
            zone_cells = [(int(col), int(row)) for row, col in zip(*np.nonzero(zones))]
            one_way = [
                cell for cell in closed_reachable
                if not any(zone in closed_graph.reachable_from(cell) for zone in zone_cells)
            ]
            line += f" | sem volta pra zona: {len(one_way)}/{len(closed_reachable)}"
            if one_way:
                line += f"  <-- FASE TRAVA em {sorted(one_way)[:4]}"
        print(line)


def _ranges(values) -> str:
    values = sorted(values)
    if not values:
        return ""
    parts, start, previous = [], values[0], values[0]
    for value in values[1:]:
        if value == previous + 1:
            previous = value
            continue
        parts.append(f"{start}" if start == previous else f"{start}-{previous}")
        start = previous = value
    parts.append(f"{start}" if start == previous else f"{start}-{previous}")
    return ",".join(parts)


def main() -> int:
    config = EngineConfig.from_json(str(_CONFIG_PATH))
    simulation = build_simulation(config)
    light = simulation.tuning.light
    print(f"balanceamento: decaimento {light.decay_per_cell:.4f}/celula")
    print(
        f"  lampada deixa eter solido em raio {(light.lamp_intensity - light.solid_threshold) * light.falloff_radius_cells:.2f} cel"
        f" | Lumen segura em {(light.lamp_intensity - light.extinguish_below) * light.falloff_radius_cells:.2f} cel"
        f" | Umbra se dissolve em {(light.lamp_intensity - light.dissolve_above) * light.falloff_radius_cells:.2f} cel"
    )
    for level_index in range(simulation.catalog.count):
        audit_level(simulation, level_index)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
