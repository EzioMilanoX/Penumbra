"""
As quatro fases do jogo continuam jogaveis.

Estes testes guardam as respostas que `tools/audit_levels.py` deu ao
desenhar as fases. Um ajuste de balanceamento -- mexer no alcance da luz,
no limiar de solidez, na carga -- pode tornar uma fase insolvel sem gerar
nenhum erro: o eter para de acender sob os pes da Lumen, ou o facho vaza
ate a zona de sombra e a porta nunca abre. E exatamente o tipo de regressao
que so um teste pega.
"""
from __future__ import annotations

import numpy as np
import pytest

from penumbra.scenes import PenumbraScene
from penumbra.state import (
    LUMEN,
    OUTCOME_COMPLETE,
    OUTCOME_FAILED,
    OUTCOME_PLAYING,
    UMBRA,
)

from tests.conftest import FRAME, advance, place, position


def _level_indices(simulation):
    return list(range(simulation.catalog.count))


class TestEveryLevelIsPlayable:
    def test_ninguem_morre_parado_no_spawn(self, simulation, input_provider):
        """O ponto de partida de cada fase tem que estar dentro da faixa que
        os DOIS aguentam. Um spawn fora dela mataria o jogador antes de ele
        tocar em qualquer tecla."""
        for level_index in _level_indices(simulation):
            simulation.runtime.load(level_index)
            advance(simulation, input_provider, frames=60)
            assert simulation.state.outcome == OUTCOME_PLAYING, (
                f"fase {level_index + 1} ({simulation.runtime.current.name}) mata quem fica parado: "
                f"{simulation.state.message}"
            )

    def test_a_lumen_acende_todo_eter_sob_os_proprios_pes(self, simulation, input_provider):
        """Com o facho ligado, cada celula de eter tem que ficar solida pra
        ela. Uma celula que nao acenda e uma ponte intransponivel por
        qualquer caminho -- nao ha outra fonte de luz portatil no jogo."""
        state = simulation.state
        for level_index in _level_indices(simulation):
            simulation.runtime.load(level_index)
            rows, cols = np.nonzero(simulation.terrain.ether)
            assert rows.size > 0 or not simulation.terrain.ether.any()

            state.ability_on[LUMEN] = True
            for row, col in zip(rows.tolist(), cols.tolist()):
                place(simulation, LUMEN, col, row - 1)
                state.charge[LUMEN] = 1.0
                advance(simulation, input_provider, frames=2)
                assert bool(state.lit[row, col]), (
                    f"fase {level_index + 1}: o facho nao acende o eter em (col={col}, row={row})"
                )
            state.ability_on[LUMEN] = False

    def test_o_eter_de_cada_fase_pertence_a_exatamente_um_ser(self, simulation, input_provider):
        for level_index in _level_indices(simulation):
            simulation.runtime.load(level_index)
            advance(simulation, input_provider, frames=3)

            ether = simulation.terrain.ether
            lumen_solid = simulation.lumen_grid.cells[ether].astype(bool)
            umbra_solid = simulation.umbra_grid.cells[ether].astype(bool)
            assert np.all(lumen_solid ^ umbra_solid), f"fase {level_index + 1}"

    def test_toda_porta_de_polaridade_e_de_fato_abrivel(self, simulation, input_provider):
        """A checagem que decide se uma fase com porta e solvel: com a Lumen
        na zona de luz e o facho ligado, a zona de sombra CONTINUA apagada?
        O facho alcanca longe; so a rocha entre as duas zonas impede o
        vazamento, e se ela basta nao se ve olhando o ASCII."""
        state = simulation.state
        levels_with_doors = 0
        for level_index in _level_indices(simulation):
            simulation.runtime.load(level_index)
            terrain = simulation.terrain
            if not terrain.has_door:
                continue
            levels_with_doors += 1

            light_cells = list(zip(*np.nonzero(terrain.zone_light)))
            shadow_cells = list(zip(*np.nonzero(terrain.zone_shadow)))
            opened = False
            for light_row, light_col in light_cells:
                for shadow_row, shadow_col in shadow_cells:
                    simulation.runtime.reset()
                    place(simulation, LUMEN, light_col, light_row)
                    place(simulation, UMBRA, shadow_col, shadow_row)
                    state.ability_on[LUMEN] = True
                    state.charge[:] = 1.0
                    advance(simulation, input_provider, frames=3)
                    if state.door_open:
                        opened = True
            assert opened, (
                f"fase {level_index + 1} ({simulation.runtime.current.name}): nenhuma combinacao de "
                f"zonas abre a porta -- o facho da Lumen esta vazando ate a zona de sombra"
            )
        assert levels_with_doors >= 1, "o slice deveria ensinar a porta de polaridade em alguma fase"

    def test_os_portais_estao_longe_o_bastante_pra_nao_haver_contato(self, simulation):
        """Os dois precisam estar nos portais NO MESMO frame -- se os
        portais estiverem perto demais, chegar la aniquila os dois e a fase
        e impossivel de terminar."""
        lumen, umbra = simulation.tuning.lumen, simulation.tuning.umbra
        for level_index in _level_indices(simulation):
            simulation.runtime.load(level_index)
            terrain = simulation.terrain
            lumen_x, lumen_y = terrain.cell_center(terrain.lumen_goal_cell)
            umbra_x, umbra_y = terrain.cell_center(terrain.umbra_goal_cell)
            separated = (
                abs(lumen_x - umbra_x) >= (lumen.half_width + umbra.half_width)
                or abs(lumen_y - umbra_y) >= (lumen.half_height + umbra.half_height)
            )
            assert separated, f"fase {level_index + 1}: os dois portais se sobrepoem"


class TestPlaythrough:
    """A prova final: a fase 1 termina jogando, so com input."""

    def _press(self, simulation, input_provider, action: str) -> None:
        """Um toque -- as acoes de borda (`switch`, `ability`) so disparam na
        transicao de solto pra pressionado."""
        input_provider.set_action_held(action, True)
        advance(simulation, input_provider, frames=1)
        input_provider.set_action_held(action, False)
        advance(simulation, input_provider, frames=1)

    def _walk_to(self, simulation, input_provider, target_col: int, max_frames: int = 900) -> None:
        """Conduz o ser ATIVO ate uma coluna, soltando as teclas ao chegar --
        um jogador rudimentar, nao um teleporte. Se este laco nao chega, a
        fase de fato nao e caminhavel."""
        target_x = (target_col + 0.5) * simulation.terrain.cell_size
        side = simulation.state.active
        for _ in range(max_frames):
            current_x, _ = position(simulation, side)
            offset = target_x - current_x
            if abs(offset) <= 3.0:
                break
            input_provider.set_action_held("move_right", offset > 0.0)
            input_provider.set_action_held("move_left", offset < 0.0)
            advance(simulation, input_provider, frames=1)
            assert simulation.state.outcome != OUTCOME_FAILED, (
                f"morreu no caminho para a coluna {target_col}: {simulation.state.message}"
            )
        input_provider.set_action_held("move_right", False)
        input_provider.set_action_held("move_left", False)
        advance(simulation, input_provider, frames=1)

    def test_a_fase_1_e_completavel_so_andando(self, simulation, input_provider):
        """'Duas Polaridades' e a fase de leitura: ela ensina que o mesmo
        material e chao de um e abismo do outro, e precisa ser vencivel sem
        nenhuma habilidade -- so TAB e as setas. Se algum dia ela exigir o
        facho, o jogo perdeu sua porta de entrada."""
        simulation.runtime.load(0)
        terrain = simulation.terrain
        assert simulation.state.active == LUMEN

        self._walk_to(simulation, input_provider, terrain.lumen_goal_cell[0])
        assert bool(simulation.state.reached_goal[LUMEN]), "Lumen deveria estar no portal dela"
        assert simulation.state.outcome == OUTCOME_PLAYING, "um portal so nao termina a fase"

        self._press(simulation, input_provider, "switch")
        assert simulation.state.active == UMBRA
        self._walk_to(simulation, input_provider, terrain.umbra_goal_cell[0])

        assert simulation.state.outcome == OUTCOME_COMPLETE, (
            f"a fase 1 deveria terminar so andando (estado: {simulation.state.message!r})"
        )

    def _release(self, input_provider) -> None:
        for action in ("move_right", "move_left", "jump"):
            input_provider.set_action_held(action, False)

    def _climb_to(
        self, simulation, input_provider, target_col: int, target_row: int, max_frames: int = 600
    ) -> bool:
        """Conduz o ser ATIVO ate uma celula podendo SALTAR, e so considera
        que chegou estando de pe (`is_grounded`) na linha certa -- checar so
        a linha aceitaria um apice de salto de passagem e o teste passaria
        com o ser caindo de volta no frame seguinte."""
        side = simulation.state.active
        tile_collision = simulation.tile_collision_systems[side]
        entity_index = int(simulation.state.entity_index[side])
        cell_size = simulation.terrain.cell_size
        target_x = (target_col + 0.5) * cell_size
        pulsing = False

        for _ in range(max_frames):
            current_x, current_y = position(simulation, side)
            row = int(current_y // cell_size)
            grounded = tile_collision.is_grounded(entity_index)
            if grounded and row == target_row and abs(current_x - target_x) <= 8.0:
                self._release(input_provider)
                advance(simulation, input_provider, frames=2)
                return True
            input_provider.set_action_held("move_right", target_x - current_x > 5.0)
            input_provider.set_action_held("move_left", target_x - current_x < -5.0)
            # O pulo e por borda: manter a tecla pressionada dispara uma vez
            # so, entao o bot alterna a cada frame em que esta no chao.
            wants_jump = grounded and row > target_row
            input_provider.set_action_held("jump", wants_jump and not pulsing)
            pulsing = wants_jump and not pulsing
            advance(simulation, input_provider, frames=1)

        self._release(input_provider)
        advance(simulation, input_provider, frames=2)
        return False

    def test_a_fase_4_perdoa_descer_antes_de_abrir_a_porta(self, simulation, input_provider):
        """
        O bug que o jogador encontrou, agora como regressao jogada.

        Descer da saliencia pra olhar a porta de perto e o movimento mais
        natural do mundo, e era irreversivel: os degraus estavam empilhados
        na mesma coluna, o de cima era teto do de baixo, e a zona de luz --
        a unica coisa que destranca a porta -- ficava inalcancavel. Sem
        morte, sem mensagem, sem aviso: so uma parede que nunca abria.

        Aqui a Lumen desce PRIMEIRO, de proposito, e tem de conseguir voltar
        pela escada escalonada e terminar a fase.
        """
        simulation.runtime.load(3)
        state = simulation.state
        terrain = simulation.terrain
        light_col = int(np.nonzero(terrain.zone_light)[1][0])
        light_row = int(np.nonzero(terrain.zone_light)[0][0])
        shadow_col = int(np.nonzero(terrain.zone_shadow)[1][0])

        # Facho ligado: ela precisa dele pra sobreviver ao trecho escuro do
        # chao, e a carga se recompoe entre os saltos.
        self._press(simulation, input_provider, "ability")
        assert bool(state.ability_on[LUMEN])

        assert self._climb_to(simulation, input_provider, 18, 17), "nao chegou ao chao junto da porta"
        assert state.outcome == OUTCOME_PLAYING, f"morreu na descida: {state.message!r}"

        # A volta, degrau por degrau.
        for col, row in ((13, 15), (15, 13), (light_col, light_row)):
            assert self._climb_to(simulation, input_provider, col, row), (
                f"nao conseguiu subir de volta ate (col={col}, row={row}) -- a descida voltou "
                f"a ser de mao unica e a fase esta insolvel"
            )

        if not bool(state.ability_on[LUMEN]):
            self._press(simulation, input_provider, "ability")
        self._press(simulation, input_provider, "switch")
        self._walk_to(simulation, input_provider, shadow_col)
        assert state.door_open, "a porta deveria ceder depois da volta a zona de luz"

        self._walk_to(simulation, input_provider, terrain.umbra_goal_cell[0])
        self._press(simulation, input_provider, "switch")
        self._climb_to(simulation, input_provider, 27, 17)
        if not bool(state.ability_on[LUMEN]):
            self._press(simulation, input_provider, "ability")
        self._walk_to(simulation, input_provider, terrain.lumen_goal_cell[0])

        assert state.outcome == OUTCOME_COMPLETE, f"estado: {state.message!r}"

    def test_a_fase_2_e_completavel_levando_a_umbra_primeiro(self, simulation, input_provider):
        """
        'O Mesmo Chao' tem uma ORDEM obrigatoria, e e ela a licao da fase.

        O caminho intuitivo -- levar a Lumen ate o portal dela primeiro --
        nao fecha: para chegar ao portal dela a Umbra tem que absorver a
        lampada que fica a tres celulas do portal da Lumen, e isso deixa a
        Lumen no escuro por mais tempo do que ela aguenta. Levando a Umbra
        primeiro, a Lumen ainda esta la atras, no raio da outra lampada, e
        a absorcao nao a alcanca.

        Este teste percorre a fase inteira por input. Se um ajuste de
        balanceamento fechar tambem esta ordem, a fase deixa de ter solucao
        e o teste falha aqui, nao no jogador.
        """
        simulation.runtime.load(1)
        state = simulation.state
        terrain = simulation.terrain

        self._press(simulation, input_provider, "switch")
        assert state.active == UMBRA
        # A ponte de eter ja esta apagada: ela atravessa sem habilidade.
        self._walk_to(simulation, input_provider, 25)
        # Absorcao ligada so para passar pela lampada.
        self._press(simulation, input_provider, "ability")
        assert bool(state.ability_on[UMBRA])
        self._walk_to(simulation, input_provider, terrain.umbra_goal_cell[0])
        self._press(simulation, input_provider, "ability")
        assert not bool(state.ability_on[UMBRA])
        assert bool(state.reached_goal[UMBRA])

        self._press(simulation, input_provider, "switch")
        assert state.active == LUMEN
        self._walk_to(simulation, input_provider, 14)
        # Facho ligado so para a travessia do eter.
        self._press(simulation, input_provider, "ability")
        assert bool(state.ability_on[LUMEN])
        self._walk_to(simulation, input_provider, 24)
        self._press(simulation, input_provider, "ability")
        self._walk_to(simulation, input_provider, terrain.lumen_goal_cell[0])

        assert state.outcome == OUTCOME_COMPLETE, (
            f"a fase 2 deveria fechar com a Umbra primeiro (estado: {state.message!r})"
        )

    def test_a_fase_3_e_completavel_revezando_os_andares(self, simulation, input_provider):
        """
        'Revezamento': os dois andares de eter ficam a quatro celulas um do
        outro, perto o bastante para o facho da Lumen, no de cima, acender o
        eter do de baixo. Enquanto ela atravessa, a Umbra nao tem chao --
        entao a Umbra atravessa primeiro, com o facho desligado, e so depois
        a Lumen acende o proprio caminho.
        """
        simulation.runtime.load(2)
        state = simulation.state
        terrain = simulation.terrain

        self._press(simulation, input_provider, "switch")
        assert state.active == UMBRA
        self._walk_to(simulation, input_provider, terrain.umbra_goal_cell[0])
        assert bool(state.reached_goal[UMBRA]), "o andar de baixo esta apagado: ela passa sem habilidade"

        self._press(simulation, input_provider, "switch")
        self._walk_to(simulation, input_provider, 8)
        self._press(simulation, input_provider, "ability")
        assert bool(state.ability_on[LUMEN])
        self._walk_to(simulation, input_provider, terrain.lumen_goal_cell[0])

        assert state.outcome == OUTCOME_COMPLETE, f"estado: {state.message!r}"

    def test_a_fase_4_e_completavel_destrancando_a_porta(self, simulation, input_provider):
        """
        'Eclipse': a porta cede com a Lumen numa zona acesa -- que so o facho
        dela acende -- e a Umbra numa apagada, no mesmo instante. A rocha da
        saliencia e o que impede o facho de vazar ate a zona da Umbra e
        cancelar a propria condicao.

        Depois de aberta, a ordem volta a importar: a Umbra atravessa o eter
        escuro primeiro, e so ai a Lumen o acende para si.
        """
        simulation.runtime.load(3)
        state = simulation.state
        terrain = simulation.terrain
        light_col = int(np.nonzero(terrain.zone_light)[1][0])
        shadow_col = int(np.nonzero(terrain.zone_shadow)[1][0])

        # Lumen ate a zona de luz, na saliencia, e acende.
        self._walk_to(simulation, input_provider, light_col)
        self._press(simulation, input_provider, "ability")
        assert bool(state.ability_on[LUMEN])

        # Umbra ate a zona de sombra: as duas condicoes valem juntas.
        self._press(simulation, input_provider, "switch")
        self._walk_to(simulation, input_provider, shadow_col)
        assert state.door_open, "a porta deveria ter cedido com os dois em posicao"

        # Ela segue pelo eter escuro ate o portal antes de a Lumen acende-lo.
        self._walk_to(simulation, input_provider, terrain.umbra_goal_cell[0])
        assert bool(state.reached_goal[UMBRA])

        # Agora a Lumen desce, atravessa e acende o eter atras da Umbra.
        self._press(simulation, input_provider, "switch")
        self._walk_to(simulation, input_provider, 27)
        state_charge = float(state.charge[LUMEN])
        assert state_charge > 0.3, "a carga deveria ter se recomposto na caminhada"
        if not bool(state.ability_on[LUMEN]):
            self._press(simulation, input_provider, "ability")
        self._walk_to(simulation, input_provider, terrain.lumen_goal_cell[0])

        assert state.outcome == OUTCOME_COMPLETE, f"estado: {state.message!r}"

    def test_atravessar_a_ponte_da_polaridade_errada_derruba(self, simulation, input_provider):
        """O contrario da anterior: a Umbra tentando andar pela ponte ACESA
        da fase 1 cai. E o feedback que ensina a mecanica."""
        simulation.runtime.load(0)
        state = simulation.state
        self._press(simulation, input_provider, "switch")
        assert state.active == UMBRA
        # Sobe a Umbra para a pista da Lumen, junto da ponte acesa.
        place(simulation, UMBRA, 12, 9)
        advance(simulation, input_provider, frames=4)

        input_provider.set_action_held("move_right", True)
        advance(simulation, input_provider, frames=60)

        _, umbra_y = position(simulation, UMBRA)
        assert umbra_y > 10 * simulation.terrain.cell_size, (
            "a Umbra deveria ter afundado na ponte acesa em vez de atravessa-la"
        )


class TestLevelFlow:
    def test_completar_a_ultima_fase_volta_a_primeira(self, simulation):
        """O slice nao tem tela de fim de jogo; o ciclo volta ao inicio."""
        last = simulation.catalog.count - 1
        simulation.runtime.load(last)
        simulation.runtime.advance()
        assert simulation.state.level_index == 0

    def test_recomecar_devolve_a_fase_ao_estado_inicial(self, simulation, input_provider):
        simulation.runtime.load(0)
        state = simulation.state
        place(simulation, LUMEN, 30, 5)
        state.ability_on[LUMEN] = True
        state.charge[LUMEN] = 0.1
        state.peril[LUMEN] = 0.5
        advance(simulation, input_provider, frames=2)

        simulation.runtime.reset()

        assert state.outcome == OUTCOME_PLAYING
        assert not bool(state.ability_on[LUMEN])
        assert float(state.charge[LUMEN]) == 1.0
        assert float(state.peril[LUMEN]) == 0.0
        assert state.active == LUMEN
        assert tuple(state.cell[LUMEN]) == simulation.terrain.lumen_spawn_cell

    @pytest.fixture
    def scene(self, simulation, input_provider):
        return PenumbraScene(simulation.runtime, simulation.state, simulation.tuning, input_provider)

    def _drive_scene(self, scene, simulation, input_provider, frames):
        for _ in range(frames):
            input_provider.poll()
            scene.update(simulation.world, FRAME)

    def test_a_cena_congela_o_mundo_enquanto_o_aviso_esta_na_tela(
        self, scene, simulation, input_provider
    ):
        """O congelamento e proposital: o jogador precisa ver a causa da
        morte parada na tela, nao um corte pra um menu."""
        simulation.runtime.load(1)
        state = simulation.state
        state.fail("teste")
        place(simulation, LUMEN, 20, 5)  # no ar: cairia se o mundo andasse
        pool = simulation.world.get_pool("transform")
        dense_row = pool.dense_row_of(int(state.entity_index[LUMEN]))
        frozen_y = float(pool.active_view()["position_y"][dense_row])

        self._drive_scene(scene, simulation, input_provider, frames=6)

        assert float(pool.active_view()["position_y"][dense_row]) == frozen_y

    def test_a_cena_recarrega_a_fase_depois_de_uma_falha(self, scene, simulation, input_provider):
        simulation.runtime.load(1)
        state = simulation.state
        state.fail("teste")

        frames = int(simulation.tuning.flow.overlay_seconds * 60) + 4
        self._drive_scene(scene, simulation, input_provider, frames=frames)

        assert state.outcome == OUTCOME_PLAYING
        assert state.level_index == 1, "falhar recarrega a MESMA fase"

    def test_a_cena_avanca_de_fase_depois_de_uma_vitoria(self, scene, simulation, input_provider):
        simulation.runtime.load(1)
        state = simulation.state
        state.complete("teste")

        frames = int(simulation.tuning.flow.overlay_seconds * 60) + 4
        self._drive_scene(scene, simulation, input_provider, frames=frames)

        assert state.outcome == OUTCOME_PLAYING
        assert state.level_index == 2

    def test_o_aviso_ignora_a_tecla_ainda_pressionada_no_frame_da_morte(
        self, scene, simulation, input_provider
    ):
        """`overlay_min_seconds` existe pra que o pulo que o jogador estava
        segurando quando morreu nao dispense o aviso antes de ele ser
        lido."""
        simulation.runtime.load(1)
        state = simulation.state
        state.fail("teste")
        input_provider.set_action_held("jump", True)

        self._drive_scene(scene, simulation, input_provider, frames=2)

        assert state.outcome == OUTCOME_FAILED, "o aviso nao pode sumir no primeiro frame"
