"""
Ninguem fica preso, e nenhuma descida e de mao unica.

Um puzzle-platformer tem duas maneiras independentes de ser insolvel.
`test_shipped_levels.py` cobre a de POLARIDADE (o eter nao acende onde
precisa, o facho vaza ate a zona de sombra). Esta cobre a de GEOMETRIA, que
escapou de tudo: os degraus da fase 4 estavam empilhados na MESMA coluna, o
de cima era teto do de baixo, e a Lumen que descia da saliencia nao tinha
como voltar -- a porta nunca abria e a parede era literalmente impossivel.

Nenhum teste falhava. A fase carregava, o eter acendia, os portais estavam
onde deviam, e a suite inteira passava verde: ela provava que a fase era
solvel em polaridade e nunca perguntou se os pes alcancavam.
"""
from __future__ import annotations

import numpy as np
import pytest

from penumbra.reachability import JumpModel, TraversalGraph, solid_mask
from penumbra.terrain import Terrain

from tests.conftest import GRID_COLS, GRID_ROWS, make_rows


def _graph(
    simulation, side_tuning, door_open: bool = True, crust_broken: bool = True
) -> TraversalGraph:
    """Grafo otimista por default: porta aberta e crosta rompida. Os dois
    sao coisas que os seres CONSEGUEM fazer, entao a pergunta "ele alcanca?"
    tem de considerar que ja foram feitas -- senao a fase 2, onde a crosta
    tranca o caminho da Umbra de proposito, apareceria como insolvel."""
    model = JumpModel(simulation.tuning.world, side_tuning)
    return TraversalGraph(solid_mask(simulation.terrain, door_open, crust_broken), model)


class TestJumpModel:
    def test_o_alcance_horizontal_cai_com_a_altura(self, simulation):
        """Nao e a altura maxima que decide se um degrau e subivel, e quanto
        tempo o ser FICA naquela altura: perto do apice a velocidade
        vertical vai a zero e o deslocamento horizontal disponivel com
        ela."""
        model = JumpModel(simulation.tuning.world, simulation.tuning.lumen)
        reaches = [model.horizontal_reach(k) for k in (1, 2, 3)]
        assert reaches == sorted(reaches, reverse=True)
        assert model.horizontal_reach(99) == 0.0

    def test_a_umbra_sobe_menos_degraus_que_a_lumen(self, simulation):
        """Subir num degrau exige >= 1 celula de deslocamento horizontal --
        o topo do degrau nunca esta na coluna onde o ser esta de pe, porque
        essa coluna e a que ela ocupa.

        A altura maxima do salto engana: o que decide e quanto tempo o ser
        FICA naquela altura. Este teste nao fixa os numeros (eles vem do
        JSON de dificuldade e mudam com balanceamento) -- fixa a relacao que
        precisa continuar valendo: a Lumen sobe estritamente mais, e a Umbra
        sobe ao menos um degrau, senao o design vertical fecha pra ela."""
        world = simulation.tuning.world
        umbra_climb = JumpModel(world, simulation.tuning.umbra).max_climb
        lumen_climb = JumpModel(world, simulation.tuning.lumen).max_climb
        assert umbra_climb >= 1, "sem subir nada, a Umbra so sabe andar"
        assert lumen_climb > umbra_climb, "a agilidade da Lumen tem de significar algo"

    def test_um_bloco_sobre_a_cabeca_transforma_a_plataforma_em_beco(self, simulation):
        """O bug da fase 4, isolado: dois blocos na mesma coluna. De pe no
        de baixo, a celula acima esta solida -- o salto morre nela, e nao
        importa que o ser alcance a altura do de cima."""
        terrain = Terrain(cols=GRID_COLS, rows=GRID_ROWS, cell_size=simulation.tuning.world.cell_size)
        empilhados = make_rows({
            14: "..A.....B.........X....Y..",
            15: "#" * 28,
            13: "..........#",
            11: "..........#",
        })
        terrain.load_rows(empilhados)
        model = JumpModel(simulation.tuning.world, simulation.tuning.lumen)
        graph = TraversalGraph(solid_mask(terrain, door_open=True), model)

        plataforma = (10, 12)
        assert plataforma in graph.standable
        alcancavel_do_chao = graph.reachable_from((2, 14))
        assert plataforma in alcancavel_do_chao, "ela chega na plataforma de baixo"
        assert (10, 10) not in graph.reachable_from(plataforma), (
            "mas o bloco de cima e teto: dali nao se sobe pra lugar nenhum"
        )

    def test_degraus_escalonados_sao_subiveis(self, simulation):
        """A correcao: deslocar as colunas. Mesmo alcance de salto, mesma
        altura, e agora o caminho existe."""
        terrain = Terrain(cols=GRID_COLS, rows=GRID_ROWS, cell_size=simulation.tuning.world.cell_size)
        escalonados = make_rows({
            14: "..A.....B.........X....Y..",
            15: "#" * 28,
            13: "..........#",
            11: "............#",
        })
        terrain.load_rows(escalonados)
        model = JumpModel(simulation.tuning.world, simulation.tuning.lumen)
        graph = TraversalGraph(solid_mask(terrain, door_open=True), model)

        assert (10, 12) in graph.reachable_from((2, 14))
        assert (12, 10) in graph.reachable_from((10, 12))


class TestShippedLevelGeometry:
    def _levels(self, simulation):
        for index in range(simulation.catalog.count):
            simulation.runtime.load(index)
            yield index, simulation.runtime.current

    def test_cada_ser_alcanca_o_proprio_portal(self, simulation):
        for index, level in self._levels(simulation):
            terrain = simulation.terrain
            for who, spawn, goal, side_tuning in (
                ("Lumen", terrain.lumen_spawn_cell, terrain.lumen_goal_cell, simulation.tuning.lumen),
                ("Umbra", terrain.umbra_spawn_cell, terrain.umbra_goal_cell, simulation.tuning.umbra),
            ):
                graph = _graph(simulation, side_tuning, door_open=True)
                assert goal in graph.reachable_from(spawn), (
                    f"fase {index + 1} ({level.name}): {who} nao alcanca o portal dela "
                    f"de {spawn} ate {goal}"
                )

    def test_a_crosta_e_de_fato_obrigatoria_em_alguma_fase(self, simulation):
        """O verbo da Umbra tem de ser estruturalmente necessario, nao
        situacional -- era esse o problema que ele veio resolver: a absorcao
        dela era obrigatoria em 1 de 4 fases e o facho da Lumen em 3.

        Se nenhuma fase ficar intransponivel com a crosta intacta, romper
        virou decoracao."""
        obrigatoria_em = []
        for index, level in self._levels(simulation):
            terrain = simulation.terrain
            if not terrain.crust.any():
                continue
            graph = _graph(simulation, simulation.tuning.umbra, crust_broken=False)
            if terrain.umbra_goal_cell not in graph.reachable_from(terrain.umbra_spawn_cell):
                obrigatoria_em.append(level.name)
        assert obrigatoria_em, (
            "nenhuma fase exige romper a crosta -- o verbo da Umbra voltou a ser opcional"
        )

    def test_cada_ser_alcanca_a_propria_zona_de_polaridade(self, simulation):
        """Com a porta ainda TRANCADA -- e o estado em que a zona precisa
        ser alcancavel, ja que e ela que destranca."""
        for index, level in self._levels(simulation):
            terrain = simulation.terrain
            if not terrain.has_door or terrain.has_plate:
                continue  # fase de placa nao tem zonas; ver o teste seguinte
            for who, spawn, zones, side_tuning in (
                ("Lumen", terrain.lumen_spawn_cell, terrain.zone_light, simulation.tuning.lumen),
                ("Umbra", terrain.umbra_spawn_cell, terrain.zone_shadow, simulation.tuning.umbra),
            ):
                graph = _graph(simulation, side_tuning, door_open=False)
                reachable = graph.reachable_from(spawn)
                cells = [(int(col), int(row)) for row, col in zip(*np.nonzero(zones))]
                assert any(cell in reachable for cell in cells), (
                    f"fase {index + 1} ({level.name}): {who} nao alcanca nenhuma zona dela"
                )

    def test_toda_placa_de_pressao_e_alcancavel_com_a_porta_fechada(self, simulation):
        """A placa e o gatilho: se ninguem a alcanca com a porta fechada, a
        fase e uma parede. E ao menos UMA placa precisa estar do lado de ca
        -- a de tras so serve depois que alguem passou."""
        for index, level in self._levels(simulation):
            terrain = simulation.terrain
            if not terrain.has_plate:
                continue
            plates = [(int(col), int(row)) for row, col in zip(*np.nonzero(terrain.plate))]
            reached = False
            for spawn, side_tuning in (
                (terrain.lumen_spawn_cell, simulation.tuning.lumen),
                (terrain.umbra_spawn_cell, simulation.tuning.umbra),
            ):
                graph = _graph(simulation, side_tuning, door_open=False)
                reachable = graph.reachable_from(spawn)
                if any(plate in reachable for plate in plates):
                    reached = True
            assert reached, (
                f"fase {index + 1} ({level.name}): nenhuma placa e alcancavel com a porta fechada"
            )

    def test_nenhuma_zona_de_polaridade_fica_sem_volta(self, simulation):
        """
        O teste que faltava. Nao basta a zona ser alcancavel do spawn: ela
        precisa continuar alcancavel de TODO lugar que o ser consegue
        pisar. Senao um passo natural -- descer pra olhar a porta de perto
        -- torna a fase insolvel para sempre, sem aviso, sem morte, sem
        mensagem. So um jogador parado na frente de uma parede que nao abre.

        Era exatamente isso que acontecia: 21 das 31 celulas que a Lumen
        alcancava na fase 4 nao tinham volta pra zona de luz.
        """
        for index, level in self._levels(simulation):
            terrain = simulation.terrain
            if not terrain.has_door:
                continue
            if terrain.has_plate:
                continue  # a placa nao trava: sair de cima dela e reversivel
            for who, spawn, zones, side_tuning in (
                ("Lumen", terrain.lumen_spawn_cell, terrain.zone_light, simulation.tuning.lumen),
                ("Umbra", terrain.umbra_spawn_cell, terrain.zone_shadow, simulation.tuning.umbra),
            ):
                graph = _graph(simulation, side_tuning, door_open=False)
                reachable = graph.reachable_from(spawn)
                cells = [(int(col), int(row)) for row, col in zip(*np.nonzero(zones))]
                sem_volta = [
                    cell for cell in sorted(reachable)
                    if not any(zone in graph.reachable_from(cell) for zone in cells)
                ]
                assert not sem_volta, (
                    f"fase {index + 1} ({level.name}): de {len(sem_volta)} das {len(reachable)} "
                    f"celulas que {who} alcanca nao ha volta pra zona dela -- "
                    f"pisar em qualquer uma trava a fase (ex.: {sem_volta[:4]})"
                )

    def test_o_portal_continua_alcancavel_depois_de_abrir_a_porta(self, simulation):
        """Simetria da anterior: destrancar a porta nao pode custar o
        caminho de volta pra ela."""
        for index, level in self._levels(simulation):
            terrain = simulation.terrain
            if not terrain.has_door:
                continue
            if terrain.has_plate:
                continue
            for who, zones, goal, side_tuning in (
                ("Lumen", terrain.zone_light, terrain.lumen_goal_cell, simulation.tuning.lumen),
                ("Umbra", terrain.zone_shadow, terrain.umbra_goal_cell, simulation.tuning.umbra),
            ):
                graph = _graph(simulation, side_tuning, door_open=True)
                cells = [(int(col), int(row)) for row, col in zip(*np.nonzero(zones))]
                for zone in cells:
                    assert goal in graph.reachable_from(zone), (
                        f"fase {index + 1} ({level.name}): {who} nao sai da zona {zone} "
                        f"pro portal {goal} nem com a porta aberta"
                    )
