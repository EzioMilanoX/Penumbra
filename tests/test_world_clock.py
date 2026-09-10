"""
As duas mecanicas que o mundo opera sozinho: o farol e o eclipse.

Sao as unicas coisas no jogo que mudam o chao sem o jogador pedir, e por isso
as unicas que podem quebrar sem nenhum sintoma na tela do desenvolvedor: um
farol que nao inverte a ponte vira decoracao, e um eclipse cujo prazo nao
cabe em duas travessias torna a fase insolvel.
"""
from __future__ import annotations

import numpy as np
import pytest

from penumbra.state import LUMEN, OUTCOME_PLAYING, UMBRA

from tests.conftest import advance, load_custom, place, position

# Ponte de eter sob um FAROL: o farol acende e apaga sozinho, e a ponte troca
# de dono com ele. Linha de apoio 12, chao 13.
_BEACON_BRIDGE = {
    12: ".A.......o...B......X....Y..",
    13: "#####~~~~~~~~###############",
    14: "#####........###############",
    15: "#####........###############",
}
"""Ponte de 8 celulas (5-12) com o farol na 9. Nao 9 celulas: o farol acende
ate 4,55, e a nona ficaria fora do alcance -- o mesmo defeito que
`test_o_farol_alcanca_toda_a_ponte_que_ele_governa` caca nas fases do jogo."""

# Ponte de ECLIPSE: solida para os dois, e com prazo.
_ECLIPSE_BRIDGE = {
    12: ".A...........B......X....Y..",
    13: "####=======#################",
    14: "####.......#################",
    15: "####.......#################",
}


class TestBeacon:
    def test_o_farol_inverte_a_ponte_sozinho(self, simulation, input_provider):
        """A propriedade que da sentido ao farol: a MESMA ponte pertence a um
        e depois ao outro, sem ninguem apertar nada. Ate aqui os dois sentidos
        do conflito exigiam duas habilidades e duas decisoes."""
        load_custom(simulation, _BEACON_BRIDGE)
        state, terrain = simulation.state, simulation.terrain
        assert terrain.has_beacon
        rows, cols = np.nonzero(terrain.ether)

        flow = simulation.tuning.flow
        period = flow.beacon_on_seconds + flow.beacon_off_seconds
        # O estado do farol so entra no campo de luz no frame seguinte (o
        # WorldClockSystem roda depois do LightFieldSystem), entao a amostra
        # compara a luz de agora com o farol do frame ANTERIOR.
        previous_on = state.beacon_on
        lit_by_phase: dict = {}
        for _ in range(int(period * 60) + 10):
            advance(simulation, input_provider, frames=1)
            lit = sum(1 for row, col in zip(rows, cols) if state.lit[row, col])
            lit_by_phase.setdefault(previous_on, set()).add(lit)
            previous_on = bool(state.beacon_on)

        total = int(terrain.ether.sum())
        assert lit_by_phase[True] == {total}, "com o farol aceso a ponte inteira e da Lumen"
        assert lit_by_phase[False] == {0}, "apagado, ela inteira volta a ser da Umbra"

    def test_o_ciclo_do_farol_respeita_o_arquivo_de_dados(self, simulation, input_provider):
        load_custom(simulation, _BEACON_BRIDGE)
        state, flow = simulation.state, simulation.tuning.flow

        on_frames = off_frames = 0
        period_frames = int((flow.beacon_on_seconds + flow.beacon_off_seconds) * 60)
        for _ in range(period_frames):
            advance(simulation, input_provider, frames=1)
            if state.beacon_on:
                on_frames += 1
            else:
                off_frames += 1

        assert on_frames / 60.0 == pytest.approx(flow.beacon_on_seconds, abs=0.15)
        assert off_frames / 60.0 == pytest.approx(flow.beacon_off_seconds, abs=0.15)

    def test_uma_fase_sem_farol_fica_permanentemente_acesa(self, simulation, input_provider):
        """Sem farol na fase, `beacon_on` tem de ficar `True` -- o campo de
        luz semeia `terrain.beacon` (vazio) por esse caminho, e um `False`
        preso apagaria nada, mas o HUD anunciaria um relogio inexistente."""
        load_custom(simulation, _ECLIPSE_BRIDGE)
        advance(simulation, input_provider, frames=30)
        assert simulation.state.beacon_on
        assert simulation.state.beacon_seconds_left == 0.0


class TestEclipse:
    def test_a_zona_de_eclipse_aceita_os_dois(self, simulation, input_provider):
        """A unica celula do jogo que e chao dos DOIS. Todo o resto do terreno
        pertence a exatamente um deles."""
        load_custom(simulation, _ECLIPSE_BRIDGE)
        place(simulation, LUMEN, 5, 12)
        place(simulation, UMBRA, 9, 12)

        advance(simulation, input_provider, frames=18)

        bridge_top = 13 * simulation.terrain.cell_size
        _, lumen_y = position(simulation, LUMEN)
        _, umbra_y = position(simulation, UMBRA)
        assert lumen_y < bridge_top, "Lumen fica de pe no eclipse"
        assert umbra_y < bridge_top, "e a Umbra tambem, ao mesmo tempo"

    def test_o_prazo_so_comeca_no_primeiro_toque(self, simulation, input_provider):
        """Deliberado: o jogador pode planejar a travessia com calma. Se o
        relogio andasse desde o inicio da fase, ele puniria quem esta
        pensando."""
        load_custom(simulation, _ECLIPSE_BRIDGE)
        state = simulation.state
        place(simulation, LUMEN, 1, 12)
        place(simulation, UMBRA, 13, 12)
        advance(simulation, input_provider, frames=60)
        assert not state.eclipse_touched
        assert simulation.terrain.eclipse.any(), "nada colapsa antes do primeiro passo"

        place(simulation, LUMEN, 6, 12)
        advance(simulation, input_provider, frames=4)
        assert state.eclipse_touched
        assert state.eclipse_seconds_left > 0.0

    def test_a_zona_colapsa_inteira_no_fim_do_prazo(self, simulation, input_provider):
        """A zona vai junta, nao celula por celula: e uma passagem unica com
        prazo compartilhado, e o drama e 'da tempo pros dois?'."""
        load_custom(simulation, _ECLIPSE_BRIDGE)
        state, terrain = simulation.state, simulation.terrain
        place(simulation, LUMEN, 6, 12)
        advance(simulation, input_provider, frames=4)
        assert state.eclipse_touched

        frames = int(simulation.tuning.flow.eclipse_collapse_seconds * 60) + 10
        advance(simulation, input_provider, frames=frames)

        assert not terrain.eclipse.any(), "a zona inteira deveria ter desaparecido"
        assert simulation.lumen_grid.cells[13, 6] == 0, "e sumido das duas grades"
        assert simulation.umbra_grid.cells[13, 6] == 0

    def test_recomecar_a_fase_devolve_a_zona(self, simulation, input_provider):
        """O colapso muta o `Terrain`, como a crosta -- e como ela, o reset
        recarrega o ASCII. Sem isso o jogador voltaria a uma fase sem ponte."""
        load_custom(simulation, _ECLIPSE_BRIDGE)
        terrain = simulation.terrain
        cells_before = int(terrain.eclipse.sum())
        place(simulation, LUMEN, 6, 12)
        advance(simulation, input_provider, frames=int(simulation.tuning.flow.eclipse_collapse_seconds * 60) + 10)
        assert not terrain.eclipse.any()

        simulation.runtime.reset()

        assert int(terrain.eclipse.sum()) == cells_before
        assert not simulation.state.eclipse_touched


class TestShippedWorldClockLevels:
    def test_o_prazo_do_eclipse_cabe_nas_duas_travessias(self, simulation):
        """A checagem de solvencia das fases com eclipse: o prazo tem de
        cobrir a travessia da Umbra (a lenta) MAIS a da Lumen. Um prazo curto
        nao gera erro nenhum -- a ponte simplesmente desaparece com alguem em
        cima, sempre."""
        tuning = simulation.tuning
        budget = tuning.flow.eclipse_collapse_seconds
        cell = tuning.world.cell_size
        found = 0
        for index in range(simulation.catalog.count):
            simulation.runtime.load(index)
            terrain = simulation.terrain
            if not terrain.has_eclipse:
                continue
            found += 1
            width = int(terrain.eclipse.any(axis=0).sum())
            needed = width * cell / tuning.umbra.move_speed + width * cell / tuning.lumen.move_speed
            assert needed < budget, (
                f"fase {index + 1} ({simulation.runtime.current.name}): a ponte de eclipse tem "
                f"{width} celulas, que pedem {needed:.1f}s de travessia, e o prazo e {budget}s"
            )
        assert found >= 1, "alguma fase deveria ensinar a zona de eclipse"

    def test_o_farol_alcanca_toda_a_ponte_que_ele_governa(self, simulation, input_provider):
        """Se o farol nao acende a ponte inteira, a Lumen cai exatamente na
        celula fora do alcance -- com o farol aceso e tudo, o que e o pior
        tipo de injustica. Foi o que aconteceu na primeira versao da fase 6."""
        state = simulation.state
        found = 0
        for index in range(simulation.catalog.count):
            simulation.runtime.load(index)
            terrain = simulation.terrain
            if not terrain.has_beacon or not terrain.ether.any():
                continue
            found += 1
            rows, cols = np.nonzero(terrain.ether)
            state.beacon_phase = 0.0
            state.beacon_on = True
            advance(simulation, input_provider, frames=3)
            dark = [
                (int(col), int(row))
                for row, col in zip(rows, cols)
                if not state.lit[row, col]
            ]
            assert not dark, (
                f"fase {index + 1} ({simulation.runtime.current.name}): com o farol aceso, o eter "
                f"em {dark} continua apagado -- fora do alcance dele"
            )
        assert found >= 1, "alguma fase deveria ensinar o farol"
