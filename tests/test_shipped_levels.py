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

from penumbra.scenes import MenuScene, PenumbraFlow, TitleScene
from penumbra.state import (
    LUMEN,
    OUTCOME_COMPLETE,
    OUTCOME_FAILED,
    OUTCOME_PLAYING,
    UMBRA,
)

from penumbra.terrain import Terrain

from tests.conftest import CELL_SIZE, FRAME, GRID_COLS, GRID_ROWS, advance, place, position


def _level_indices(simulation):
    return list(range(simulation.catalog.count))


class TestEveryLevelIsPlayable:
    def test_a_dica_de_cada_fase_cabe_no_rodape(self, simulation):
        """O rodape desenha a dica numa linha so, sem quebra: uma dica mais
        larga que a janela nao estoura nada -- ela simplesmente some pela
        direita, e a frase que explica a fase termina no meio.

        O limite sai da propria janela (896 px), do recuo do HUD (14 de cada
        lado) e da largura do glifo da fonte monoespacada de 12 px do
        backend (~0,6 em). Nenhum numero aqui e chutado."""
        max_chars = int((896.0 - 2 * 14.0) / (12.0 * 0.6))
        for level_index in _level_indices(simulation):
            level = simulation.catalog.at(level_index)
            assert len(level.hint) <= max_chars, (
                f"fase {level_index + 1} ({level.name}): dica de {len(level.hint)} "
                f"caracteres, e so cabem {max_chars}"
            )

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
            if not terrain.has_door or terrain.has_plate:
                continue  # fase de placa tem porta sem zonas; ver test_reachability
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
    """
    A prova final: as quatro fases terminam JOGANDO, so com input.

    Um controlador rudimentar segura as teclas e aperta TAB/J na ordem certa.
    E o unico teste que responde "o slice tem solucao?" -- os invariantes
    acima medem propriedades, este percorre o caminho. Cada rota tambem
    DOCUMENTA a ordem obrigatoria da fase: quando um ajuste de balanceamento
    fecha o unico caminho, e aqui que aparece.
    """

    # ------------------------------------------------------------------
    # o controlador
    # ------------------------------------------------------------------

    def _press(self, simulation, input_provider, action: str) -> None:
        """Um toque -- as acoes de borda (`switch`, `ability`) so disparam na
        transicao de solto pra pressionado."""
        input_provider.set_action_held(action, True)
        advance(simulation, input_provider, frames=1)
        input_provider.set_action_held(action, False)
        advance(simulation, input_provider, frames=1)

    def _release(self, input_provider) -> None:
        for action in ("move_right", "move_left", "jump"):
            input_provider.set_action_held(action, False)

    def _walk_to(self, simulation, input_provider, target_col: int, max_frames: int = 600) -> None:
        """Conduz o ser ATIVO ate uma coluna, soltando as teclas ao chegar."""
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
        self._release(input_provider)
        advance(simulation, input_provider, frames=1)

    def _climb_to(
        self, simulation, input_provider, target_col: int, target_row: int, max_frames: int = 600
    ) -> bool:
        """Como `_walk_to`, mas podendo SALTAR -- e so considera que chegou
        estando de pe (`is_grounded`) na linha certa. Checar so a linha
        aceitaria um apice de salto de passagem, e o teste passaria com o ser
        caindo de volta no frame seguinte."""
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
            if grounded and row == target_row and abs(current_x - target_x) <= 9.0:
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

    def _push_until_broken(
        self, simulation, input_provider, col: int, row: int, max_frames: int = 300
    ) -> bool:
        """Segura a direcao contra a crosta em `(col, row)` ate ela ceder.
        Romper exige `crust_break_seconds` de empurrao continuo -- deliberado,
        porque nao tem volta."""
        terrain = simulation.terrain
        target_x = (col + 0.5) * terrain.cell_size
        for _ in range(max_frames):
            if not bool(terrain.crust[row, col]):
                self._release(input_provider)
                advance(simulation, input_provider, frames=2)
                return True
            current_x, _ = position(simulation, simulation.state.active)
            input_provider.set_action_held("move_right", target_x > current_x)
            input_provider.set_action_held("move_left", target_x < current_x)
            advance(simulation, input_provider, frames=1)
        self._release(input_provider)
        return False

    # ------------------------------------------------------------------
    # as quatro fases
    # ------------------------------------------------------------------

    def test_a_fase_1_e_completavel_so_andando(self, simulation, input_provider):
        """'Duas Polaridades' e a fase de leitura: ensina que o mesmo
        material e chao de um e abismo do outro, e precisa ser vencivel sem
        nenhuma habilidade -- so TAB e as setas. Se algum dia ela exigir o
        facho, o jogo perdeu sua porta de entrada."""
        simulation.runtime.load(0)
        terrain = simulation.terrain
        assert simulation.state.active == LUMEN

        self._walk_to(simulation, input_provider, terrain.lumen_goal_cell[0])
        assert bool(simulation.state.reached_goal[LUMEN])
        assert simulation.state.outcome == OUTCOME_PLAYING, "um portal so nao termina a fase"

        self._press(simulation, input_provider, "switch")
        assert simulation.state.active == UMBRA
        self._walk_to(simulation, input_provider, terrain.umbra_goal_cell[0])

        assert simulation.state.outcome == OUTCOME_COMPLETE, (
            f"a fase 1 deveria terminar so andando (estado: {simulation.state.message!r})"
        )

    def test_a_fase_2_e_completavel_rompendo_a_crosta(self, simulation, input_provider):
        """
        'A Crosta' usa os DOIS verbos da Umbra, com um passo sem volta no meio.

        Ela rompe a crosta pra passar -- e o buraco deixa a lampada acender o
        eter do outro lado, que era o chao DELA. Rompeu e se trancou fora da
        propria ponte. Precisa entao absorver pra devolve-la ao escuro,
        atravessar, e desligar depois, pra que a Lumen encontre a ponte acesa.
        """
        simulation.runtime.load(1)
        state, terrain = simulation.state, simulation.terrain
        assert terrain.crust.any(), "a fase 2 precisa ter crosta"

        self._press(simulation, input_provider, "switch")
        assert state.active == UMBRA
        assert self._push_until_broken(simulation, input_provider, 15, 12), (
            "a Umbra deveria romper a crosta na altura dela"
        )
        assert bool(state.lit[13, 17]), (
            "romper deixou a lampada acender o eter -- e ele era o chao DELA"
        )

        self._walk_to(simulation, input_provider, 16)
        self._press(simulation, input_provider, "ability")
        assert bool(state.ability_on[UMBRA]), "sem absorver, a ponte nao volta a ser dela"
        self._walk_to(simulation, input_provider, 21)
        self._press(simulation, input_provider, "ability")
        self._walk_to(simulation, input_provider, terrain.umbra_goal_cell[0])
        assert bool(state.reached_goal[UMBRA])

        self._press(simulation, input_provider, "switch")
        self._walk_to(simulation, input_provider, terrain.lumen_goal_cell[0])

        assert state.outcome == OUTCOME_COMPLETE, f"estado: {state.message!r}"

    def test_a_fase_3_e_completavel_disputando_a_ponte(self, simulation, input_provider):
        """'O Mesmo Chao': a lampada sobre a ponte faz dela chao da Lumen. A
        Umbra so a toma absorvendo -- e absorver apaga a lampada, entao os
        dois nunca podem estar na ponte ao mesmo tempo."""
        simulation.runtime.load(2)
        state, terrain = simulation.state, simulation.terrain

        self._press(simulation, input_provider, "switch")
        assert state.active == UMBRA
        self._press(simulation, input_provider, "ability")
        assert bool(state.ability_on[UMBRA])
        self._walk_to(simulation, input_provider, 17)
        self._press(simulation, input_provider, "ability")
        self._walk_to(simulation, input_provider, terrain.umbra_goal_cell[0])
        assert bool(state.reached_goal[UMBRA])

        self._press(simulation, input_provider, "switch")
        self._walk_to(simulation, input_provider, 17)
        assert self._climb_to(simulation, input_provider, *terrain.lumen_goal_cell)

        assert state.outcome == OUTCOME_COMPLETE, f"estado: {state.message!r}"

    def test_a_fase_4_e_completavel_destrancando_a_porta(self, simulation, input_provider):
        """
        'Eclipse': a porta cede com a Lumen numa zona acesa -- que so o facho
        dela acende -- e a Umbra numa apagada, no mesmo instante. A LAJE de
        rocha e o que impede o facho de vazar ate a zona da Umbra, logo
        abaixo, e cancelar a propria condicao.

        Os dois seguem em pistas separadas de ponta a ponta, e a rota
        aproveita isso: o facho e desligado enquanto a Umbra caminha (parada
        na zona, a Lumen sobrevive sem ele) pra que a carga se recomponha
        antes da travessia do eter.
        """
        simulation.runtime.load(3)
        state, terrain = simulation.state, simulation.terrain
        light_col = int(np.nonzero(terrain.zone_light)[1][0])
        shadow_col = int(np.nonzero(terrain.zone_shadow)[1][0])

        self._walk_to(simulation, input_provider, light_col)
        self._press(simulation, input_provider, "ability")
        assert bool(state.ability_on[LUMEN])

        self._press(simulation, input_provider, "switch")
        self._walk_to(simulation, input_provider, shadow_col)
        assert state.door_open, "a porta deveria ter cedido com os dois em posicao"

        self._press(simulation, input_provider, "switch")
        self._press(simulation, input_provider, "ability")
        assert not bool(state.ability_on[LUMEN])
        self._press(simulation, input_provider, "switch")

        self._walk_to(simulation, input_provider, terrain.umbra_goal_cell[0])
        assert bool(state.reached_goal[UMBRA])
        assert float(state.charge[LUMEN]) > 0.9, "a carga do facho deveria ter se recomposto"

        self._press(simulation, input_provider, "switch")
        self._press(simulation, input_provider, "ability")
        self._walk_to(simulation, input_provider, terrain.lumen_goal_cell[0])

        assert state.outcome == OUTCOME_COMPLETE, f"estado: {state.message!r}"

    def test_atravessar_a_ponte_da_polaridade_errada_derruba(self, simulation, input_provider):
        """A Umbra tentando andar pela ponte ACESA da fase 1 cai. E o
        feedback que ensina a mecanica."""
        simulation.runtime.load(0)
        state = simulation.state
        self._press(simulation, input_provider, "switch")
        assert state.active == UMBRA
        place(simulation, UMBRA, 11, 7)   # pista da Lumen, sobre a ponte acesa
        advance(simulation, input_provider, frames=4)

        input_provider.set_action_held("move_right", True)
        advance(simulation, input_provider, frames=60)

        _, umbra_y = position(simulation, UMBRA)
        assert umbra_y > 8 * simulation.terrain.cell_size, (
            "a Umbra deveria ter afundado na ponte acesa em vez de atravessa-la"
        )


class _FakeGameLoop:
    """Duplo minimo do `GameLoop` para testar o fluxo de cenas.

    O `PenumbraFlow` usa exatamente tres coisas do `GameLoop` --
    `reset_scenes`, `stop` e `current_scene` -- e nenhuma delas precisa de
    janela. Um duplo aqui deixa o fluxo (menu -> fase -> menu) ser testado
    headless, que e o unico jeito de testa-lo: `CompositionRoot.build_world`
    nao constroi `GameLoop` nenhum."""

    def __init__(self) -> None:
        self.current_scene = None
        self.stopped = False

    def reset_scenes(self, scene) -> None:
        self.current_scene = scene

    def stop(self) -> None:
        self.stopped = True


class TestLevelFlow:
    """Menu -> fase -> menu, e o congelamento entre elas."""

    @pytest.fixture
    def flow(self, simulation, input_provider):
        loop = _FakeGameLoop()
        flow = PenumbraFlow(
            loop, simulation.runtime, simulation.state,
            simulation.catalog, simulation.tuning, input_provider,
            preview_terrain=Terrain(GRID_COLS, GRID_ROWS, CELL_SIZE),
        )
        flow.show_title()
        return flow

    def _drive(self, flow, simulation, input_provider, frames):
        for _ in range(frames):
            input_provider.poll()
            flow._game_loop.current_scene.update(simulation.world, FRAME)

    # ---------------- menu ----------------

    def test_o_jogo_abre_na_tela_de_titulo(self, flow):
        """A primeira pergunta do jogo e quantos jogadores -- nao qual fase.
        Antes o modo era um atalho de TAB no canto do menu de fases: quem
        nunca leu o rodape nunca descobriria que ha multiplayer local."""
        assert isinstance(flow._game_loop.current_scene, TitleScene)

    def test_o_titulo_escolhe_o_modo_com_as_setas(self, flow, simulation, input_provider):
        assert not flow.duo
        input_provider.set_action_held("move_right", True)
        self._drive(flow, simulation, input_provider, frames=1)
        assert flow.duo, "D seleciona DOIS JOGADORES"

        input_provider.set_action_held("move_right", False)
        input_provider.set_action_held("move_left", True)
        self._drive(flow, simulation, input_provider, frames=1)
        assert not flow.duo, "A volta para UM JOGADOR"

    def test_confirmar_no_titulo_leva_a_selecao_de_fase(self, flow, simulation, input_provider):
        input_provider.set_action_held("jump", True)
        self._drive(flow, simulation, input_provider, frames=1)
        assert isinstance(flow._game_loop.current_scene, MenuScene)

    def test_o_modo_escolhido_no_titulo_chega_na_fase(self, flow, simulation):
        """A escolha da tela de abertura tem de atravessar duas cenas ate o
        `DualityState` -- se parar no caminho, o botao e decorativo."""
        flow.title.duo = True
        flow.show_menu()
        flow.start_level(0)
        assert simulation.state.duo, "o modo do titulo governa a partida"

    def test_esc_na_selecao_de_fase_volta_ao_titulo(self, flow, simulation, input_provider):
        flow.show_menu()
        input_provider.set_action_held("quit", True)
        self._drive(flow, simulation, input_provider, frames=1)
        assert isinstance(flow._game_loop.current_scene, TitleScene)
        assert not flow._game_loop.stopped, "ESC recua uma tela; so o titulo encerra"

    def test_esc_no_titulo_encerra_o_jogo(self, flow, simulation, input_provider):
        input_provider.set_action_held("quit", True)
        self._drive(flow, simulation, input_provider, frames=1)
        assert flow._game_loop.stopped

    def test_o_menu_lista_todas_as_fases_e_nenhuma_esta_trancada(self, flow, simulation):
        flow.show_menu()
        """Com oito fases curtas, poder repetir a que ensinou uma mecanica
        vale mais que a cerimonia de desbloquear."""
        assert len(flow.completed) == simulation.catalog.count
        assert not any(flow.completed)
        for index in range(simulation.catalog.count):
            flow.start_level(index)
            assert simulation.state.level_index == index

    def test_escolher_no_menu_e_confirmar_comeca_a_fase(self, flow, simulation, input_provider):
        flow.show_menu()
        input_provider.set_action_held("move_right", True)
        self._drive(flow, simulation, input_provider, frames=1)
        input_provider.set_action_held("move_right", False)
        input_provider.set_action_held("jump", True)
        self._drive(flow, simulation, input_provider, frames=1)

        assert flow._game_loop.current_scene is flow.gameplay
        assert simulation.state.level_index == 1, "A/D anda na grade, ESPACO entra"

    def test_a_grade_do_menu_anda_em_duas_dimensoes(self, flow, simulation, input_provider):
        """Tres colunas: W/S pulam uma linha inteira (tres fases), A/D andam
        de uma em uma. Sem isso, chegar a fase 6 custaria cinco toques."""
        flow.show_menu()
        input_provider.set_action_held("menu_down", True)
        self._drive(flow, simulation, input_provider, frames=1)
        assert flow.menu.selected == 3, "S desce uma linha da grade"
        input_provider.set_action_held("menu_down", False)
        input_provider.set_action_held("move_right", True)
        self._drive(flow, simulation, input_provider, frames=1)
        assert flow.menu.selected == 4

    def test_a_borda_da_grade_vira_de_ato(self, flow, simulation, input_provider):
        """Dezoito fases nao cabem numa grade so, entao o menu pagina em atos
        de seis -- e virar pela BORDA mantem o menu inteiro em quatro teclas.
        Sem isso a metade do jogo ficaria atras de uma tecla nao documentada."""
        flow.show_menu()
        grid = flow.menu._grid
        assert grid.act_count == 3
        grid.selected = 2               # ultima coluna do ato I
        grid.move(1, 0)
        assert grid.selected == 6, "a direita na ultima coluna abre o ato seguinte"
        assert grid.act == 1
        grid.move(-1, 0)
        assert grid.selected == 2, "e a esquerda na primeira volta pro anterior"
        assert grid.act == 0

    def test_a_grade_nao_passa_do_primeiro_nem_do_ultimo_ato(self, flow):
        flow.show_menu()
        grid = flow.menu._grid
        grid.selected = 0
        grid.move(-1, 0)
        assert grid.selected == 0, "nao existe ato antes do primeiro"
        grid.selected = grid.count - 1
        grid.move(1, 0)
        assert grid.selected == grid.count - 1, "nem depois do ultimo"

    def test_o_hud_cala_a_boca_fora_da_fase(self, flow):
        """O HUD e um callback GLOBAL de `set_on_draw_ui` -- roda independente
        da cena no topo. Sem consultar o fluxo ele desenharia a faixa de
        rodape e os medidores dos seres por cima do menu."""
        assert not flow.hud_visible
        flow.start_level(0)
        assert flow.hud_visible

    # ---------------- fase ----------------

    def test_esc_na_fase_volta_ao_menu_em_vez_de_sair(self, flow, simulation, input_provider):
        flow.start_level(2)
        input_provider.set_action_held("quit", True)
        self._drive(flow, simulation, input_provider, frames=1)

        assert isinstance(flow._game_loop.current_scene, MenuScene)
        assert not flow._game_loop.stopped

    def test_a_cena_congela_o_mundo_enquanto_o_aviso_esta_na_tela(
        self, flow, simulation, input_provider
    ):
        """O congelamento e proposital: o jogador precisa ver a causa da
        morte parada na tela, nao um corte pra um menu."""
        flow.start_level(1)
        state = simulation.state
        state.fail("teste")
        place(simulation, LUMEN, 20, 5)  # no ar: cairia se o mundo andasse
        pool = simulation.world.get_pool("transform")
        dense_row = pool.dense_row_of(int(state.entity_index[LUMEN]))
        frozen_y = float(pool.active_view()["position_y"][dense_row])

        self._drive(flow, simulation, input_provider, frames=6)

        assert float(pool.active_view()["position_y"][dense_row]) == frozen_y

    def test_falhar_recarrega_a_mesma_fase(self, flow, simulation, input_provider):
        flow.start_level(1)
        state = simulation.state
        state.fail("teste")

        frames = int(simulation.tuning.flow.overlay_seconds * 60) + 4
        self._drive(flow, simulation, input_provider, frames=frames)

        assert state.outcome == OUTCOME_PLAYING
        assert state.level_index == 1
        assert flow._game_loop.current_scene is flow.gameplay

    def test_vencer_avanca_e_marca_a_fase(self, flow, simulation, input_provider):
        flow.start_level(1)
        state = simulation.state
        state.complete("teste")

        frames = int(simulation.tuning.flow.overlay_seconds * 60) + 4
        self._drive(flow, simulation, input_provider, frames=frames)

        assert flow.completed[1], "a fase vencida fica marcada no menu"
        assert state.level_index == 2

    def test_vencer_a_ultima_fase_volta_ao_menu(self, flow, simulation, input_provider):
        """Antes o ciclo reiniciava da fase 1 em silencio, o que parecia um
        bug. Agora o jogo diz que acabou."""
        last = simulation.catalog.count - 1
        flow.start_level(last)
        simulation.state.complete("teste")

        frames = int(simulation.tuning.flow.overlay_seconds * 60) + 4
        self._drive(flow, simulation, input_provider, frames=frames)

        assert isinstance(flow._game_loop.current_scene, MenuScene)
        assert flow.completed[last]
        assert flow.menu.message, "o menu deveria dizer que o jogo acabou"

    def test_o_aviso_ignora_a_tecla_ainda_pressionada_no_frame_da_morte(
        self, flow, simulation, input_provider
    ):
        """`overlay_min_seconds` existe pra que o pulo que o jogador estava
        segurando quando morreu nao dispense o aviso antes de ele ser lido."""
        flow.start_level(1)
        state = simulation.state
        state.fail("teste")
        input_provider.set_action_held("jump", True)

        self._drive(flow, simulation, input_provider, frames=2)

        assert state.outcome == OUTCOME_FAILED, "o aviso nao pode sumir no primeiro frame"

    def test_recomecar_devolve_a_fase_ao_estado_inicial(self, simulation, input_provider):
        simulation.runtime.load(0)
        state = simulation.state
        place(simulation, LUMEN, 20, 5)
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
