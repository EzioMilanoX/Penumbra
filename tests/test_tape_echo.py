"""
Solo com eco (GAM-20): gravar a Lumen, rebobinar, jogar a Umbra ao lado dela.

Tres promessas, cada uma com o seu guardiao:

1. **A fita e deterministica.** Os mesmos inputs, no mesmo tick fixo, geram a
   mesma trajetoria -- bit a bit, enquanto o presente nao mexe em nada. Sem
   isso o eco sairia de sincronia sozinho, e todo paradoxo seria mentira.
2. **O paradoxo e real e visivel.** Quando o presente quebra o passado (a
   Umbra apaga a luz de que o eco precisava), o eco morre ou sai do caminho,
   o mundo congela e o ponto fica marcado. E da para regravar dali.
3. **As fases de dupla fecham em laco, SEM afrouxar.** O eco carrega a versao
   do duo; cada fase marcada com eco e resolvida aqui, jogando, e a que nao
   tiver solucao conferida nao pode ter a marca no card.
"""
from __future__ import annotations

import numpy as np
import pytest

from penumbra.state import (
    LUMEN,
    OUTCOME_COMPLETE,
    OUTCOME_FAILED,
    OUTCOME_PLAYING,
    TAPE_OFF,
    TAPE_RECORD,
    TAPE_REPLAY,
    UMBRA,
)
from penumbra.tape import TAPE_ACTIONS, TICK, TapeInput, TapeSession
from tests.conftest import advance, load_custom, position

LEFT, RIGHT, JUMP, ABILITY = 1, 2, 4, 8
"""Os bits da fita, na ordem de `TAPE_ACTIONS`."""


def _level(simulation, level_id: str) -> int:
    for index in range(simulation.catalog.count):
        if simulation.catalog.at(index).level_id == level_id:
            return index
    raise AssertionError(f"fase {level_id!r} nao esta no catalogo")


def _x(simulation, side: int) -> float:
    return position(simulation, side)[0]


def _cell_x(simulation, col: float) -> float:
    return col * simulation.terrain.cell_size


# ---------------------------------------------------------------------------
# Os jogadores de teste. Gravando, so os bits da Lumen viram fita; jogando a
# Umbra, o "jogador" pode olhar o eco -- e o que uma pessoa faz.
# ---------------------------------------------------------------------------


def _escort_lumen(simulation, beam_col: float, stop_col: float):
    """A Lumen caminha no passo que a Umbra vai ter, e liga o facho ao chegar
    a `beam_col`. E a escolta de 'Sob o Vidro', gravada sozinha."""
    umbra_x0 = _x(simulation, UMBRA)
    speed = simulation.tuning.umbra.move_speed
    beam = {"on": False}

    def player(tick: int) -> int:
        x = _x(simulation, LUMEN)
        planned = min(umbra_x0 + speed * tick * TICK, _cell_x(simulation, stop_col))
        bits = RIGHT if x < planned - 2 else 0
        if not beam["on"] and x >= _cell_x(simulation, beam_col):
            beam["on"] = True
            bits |= ABILITY
        return bits

    return player


def _record(simulation, player, done, limit: int = 3000) -> None:
    tape = simulation.tape
    for tick in range(limit):
        tape.tick(player(tick))
        assert simulation.state.outcome == OUTCOME_PLAYING, (
            f"a gravacao falhou: {simulation.state.message}"
        )
        if done():
            return
    raise AssertionError("a gravacao nao terminou")


def _play(simulation, player, limit: int = 3000) -> None:
    tape = simulation.tape
    for tick in range(limit):
        tape.tick(player(tick))
        if simulation.state.outcome != OUTCOME_PLAYING:
            return


def _solve_13(simulation) -> None:
    """Sob o Vidro, no duo: a escolta e a travessia inteira."""
    goal_x = _cell_x(simulation, simulation.terrain.lumen_goal_cell[0] + 0.5)
    _record(simulation, _escort_lumen(simulation, beam_col=6.0, stop_col=21.5),
            lambda: abs(_x(simulation, LUMEN) - goal_x) < 4)
    simulation.tape.rewind()
    umbra_goal = _cell_x(simulation, simulation.terrain.umbra_goal_cell[0] + 0.5)
    _play(simulation, lambda tick: RIGHT if _x(simulation, UMBRA) < umbra_goal - 2 else 0)


def _lantern_follower(simulation, side: int, goal_cell):
    """Espera na margem a lanterna voltar ao comeco da pista e anda debaixo
    dela. Em 'Sem Rocha', no duo, e o que os DOIS precisam fazer."""
    state = simulation.state
    engaged = {"on": False}

    def player(tick: int) -> int:
        del tick
        x = _x(simulation, side)
        lantern_x = _cell_x(simulation, state.wander_col + 0.5)
        if not engaged["on"]:
            target = _cell_x(simulation, 5.0)
            if (state.wander_dir > 0 and abs(lantern_x - _cell_x(simulation, 6.5)) < _cell_x(simulation, 0.4)
                    and x >= _cell_x(simulation, 4.6)):
                engaged["on"] = True
        else:
            target = lantern_x
            if state.wander_col >= 20.4 or x >= _cell_x(simulation, 21.6):
                target = _cell_x(simulation, goal_cell[0] + 0.5)
        if x < target - 2:
            return RIGHT
        if x > target + 2:
            return LEFT
        return 0

    return player


def _solve_27(simulation) -> None:
    terrain = simulation.terrain
    goal_x = _cell_x(simulation, terrain.lumen_goal_cell[0] + 0.5)
    _record(simulation, _lantern_follower(simulation, LUMEN, terrain.lumen_goal_cell),
            lambda: abs(_x(simulation, LUMEN) - goal_x) < 3)
    simulation.tape.rewind()
    _play(simulation, _lantern_follower(simulation, UMBRA, terrain.umbra_goal_cell))


def _solve_30(simulation) -> None:
    """A Fonte Aberta, no duo: escolta inteira, a descida a pedra, a subida.
    A Umbra espera no escuro enquanto a Lumen recarrega, recua para longe do
    facho enquanto ela deixa a forma, e so cruza depois que ela subiu."""
    state, terrain = simulation.state, simulation.terrain
    lumen_collision = simulation.tile_collision_systems[LUMEN]
    escort = _escort_lumen(simulation, beam_col=7.0, stop_col=17.6)
    goal_x = _cell_x(simulation, terrain.lumen_goal_cell[0] + 0.5)
    step = {"phase": 0, "pressed": False}

    def lumen(tick: int) -> int:
        x, y = position(simulation, LUMEN)
        phase = step["phase"]
        if phase == 0:
            if x >= _cell_x(simulation, 17.4):
                step["phase"] = 1
            return escort(tick)
        if phase == 1:   # desliga o facho e cai pelo buraco ate a pedra
            bits = ABILITY if state.ability_on[LUMEN] else 0
            if x < _cell_x(simulation, 18.5) - 2:
                bits |= RIGHT
            if (tuple(state.cell[LUMEN]) == (18, 12)
                    and lumen_collision.is_grounded(int(state.entity_index[LUMEN]))):
                step["phase"] = 2
            return bits
        if phase == 2:   # recarrega, e deixa a ultima luz na pedra
            bits = 0
            if not step["pressed"] and state.charge[LUMEN] >= 0.5 and not state.ability_on[LUMEN]:
                step["pressed"] = True
                bits |= ABILITY
            if state.form_spent[LUMEN]:
                step["phase"] = 3
            return bits
        if phase == 3:   # sobe reto, e so no alto vai pra direita
            if y <= _cell_x(simulation, 9.45):
                step["phase"] = 4
            return JUMP
        return RIGHT if x < goal_x - 2 else 0

    _record(simulation, lumen, lambda: step["phase"] == 4 and abs(_x(simulation, LUMEN) - goal_x) <= 2)
    simulation.tape.rewind()

    umbra_goal = _cell_x(simulation, terrain.umbra_goal_cell[0] + 0.5)
    present = {"phase": 0}

    def umbra(tick: int) -> int:
        del tick
        x = _x(simulation, UMBRA)
        lumen_y = position(simulation, LUMEN)[1]
        if present["phase"] == 0:   # sob a escolta, ate a rocha escura
            if state.ability_on[LUMEN] and tuple(state.cell[LUMEN]) == (18, 12):
                present["phase"] = 1
            return RIGHT if x < _cell_x(simulation, 17.5) - 2 else 0
        if present["phase"] == 1:   # recua da luz da pedra
            if state.form_spent[LUMEN] and lumen_y < _cell_x(simulation, 10.5):
                present["phase"] = 2
            return LEFT if x > _cell_x(simulation, 15.5) + 2 else 0
        return RIGHT if x < umbra_goal - 2 else 0

    _play(simulation, umbra)


_SOLVERS = {
    "13_sob_o_vidro": _solve_13,
    "27_sem_rocha": _solve_27,
    "30_a_fonte_aberta": _solve_30,
}


def _start(simulation, level_id: str) -> TapeSession:
    simulation.tape.start(_level(simulation, level_id))
    return simulation.tape


# ---------------------------------------------------------------------------


class TestTapeInput:
    def test_desligado_e_transparente(self, input_provider):
        """O jogo de sempre passa pelo `TapeInput` sem saber dele."""
        tape_input = TapeInput(input_provider)
        input_provider.set_action_held("p2_move_left", True)
        input_provider.poll()
        assert tape_input.is_action_held("p2_move_left")
        assert tape_input.is_action_pressed("p2_move_left")
        assert not tape_input.is_action_held("move_left")

    def test_ligado_cada_metade_le_a_sua_fonte(self, simulation):
        """No eco a Lumen sao as acoes sem prefixo e a Umbra as `p2_*` -- e as
        duas fontes sao as MESMAS teclas do jogador, em tempos diferentes."""
        tape = _start(simulation, "13_sob_o_vidro")
        tape_input = tape.input
        tape.tick(RIGHT)
        assert tape_input.is_action_held("move_right")
        assert not tape_input.is_action_held("p2_move_right"), "gravando, a Umbra nao recebe nada"
        assert not tape_input.is_action_pressed("restart"), "no eco quem reinicia e a cena"


class TestDeterminism:
    def test_gravar_e_reproduzir_da_a_mesma_trajetoria_bit_a_bit(self, simulation, input_provider):
        """Com a Umbra parada nas duas passadas, o mundo inteiro tem de se
        repetir: a trajetoria da Lumen igual em todo tick, e o hash das pools
        de movimento (`world_state_hash` da engine) igual em todo ponto
        conferido."""
        index = _level(simulation, "13_sob_o_vidro")
        # Vem de outra fase, jogada: as grades de colisao do ultimo frame sao
        # as DELA. Foi assim, entrando pelo menu, que o primeiro eco do jogo
        # acusou um paradoxo no tick zero sem ninguem mexer em nada.
        simulation.runtime.load(0)
        advance(simulation, input_provider, frames=10)
        tape = TapeSession(simulation.world, simulation.state, simulation.runtime,
                           simulation.tape.input, hash_pools=("velocity",), hash_every=10,
                           grids=(simulation.lumen_grid, simulation.umbra_grid))
        tape.start(index)
        player = _escort_lumen(simulation, beam_col=6.0, stop_col=21.5)
        for tick in range(240):
            tape.tick(player(tick))
        recorded = tape.trail[:tape.recorded_ticks].copy()
        tape.rewind()

        replayed = np.zeros_like(recorded)
        for tick in range(len(recorded)):
            tape.tick(0)                       # a Umbra parada, como na gravacao
            replayed[tick] = position(simulation, LUMEN)
            assert simulation.state.outcome == OUTCOME_PLAYING, simulation.state.message

        assert np.array_equal(recorded, replayed), "o eco saiu do caminho sem ninguem mexer nele"
        assert tape.desync_frame is None, f"o mundo divergiu no tick {tape.desync_frame}"
        assert not simulation.state.tape_paradox

    def test_o_tick_e_fixo_seja_qual_for_o_quadro(self, simulation, input_provider):
        """O mundo anda em passos de 1/60 s: um quadro de 1/30 s roda dois, dois
        quadros de 1/120 s rodam um. E um aperto vale UMA vez, mesmo que o
        quadro rode dois ticks -- a borda e de tick para tick."""
        tape = _start(simulation, "13_sob_o_vidro")
        assert tape.advance(input_provider, 1.0 / 30.0) == 2
        assert tape.advance(input_provider, 1.0 / 120.0) == 0
        assert tape.advance(input_provider, 1.0 / 120.0) == 1

        input_provider.set_action_held("ability", True)
        input_provider.poll()
        tape.advance(input_provider, 1.0 / 30.0)
        assert bool(simulation.state.ability_on[LUMEN]), "dois ticks com S segurado ligam o facho uma vez"

    def test_um_quadro_lento_nao_vira_rajada(self, simulation, input_provider):
        tape = _start(simulation, "13_sob_o_vidro")
        assert tape.advance(input_provider, 2.0) <= 4


class TestRecordingPhase:
    def test_gravando_a_umbra_ainda_nao_chegou(self, simulation):
        """Ela fica no spawn e nada a mata nem a encosta na Lumen. Aqui a
        Lumen atravessa o lugar da Umbra -- no jogo normal, os dois se
        anulariam."""
        load_custom(simulation, {
            9: "...*........*.......*.......",
            10: "..A..B..............X....Y..",
            11: "############################",
        })
        tape = simulation.tape
        tape.start()
        for _ in range(90):
            tape.tick(RIGHT)
        assert simulation.state.outcome == OUTCOME_PLAYING, simulation.state.message
        assert _x(simulation, LUMEN) > _cell_x(simulation, 6.0), "a Lumen passou pelo lugar dela"

    def test_a_lumen_sozinha_no_portal_nao_vence(self, simulation):
        load_custom(simulation, {
            9: "...*........................",
            10: "..A.X.......................",
            11: "############################",
            12: "..B......................Y..",
            13: "############################",
        })
        tape = simulation.tape
        tape.start()
        for _ in range(120):
            tape.tick(RIGHT if _x(simulation, LUMEN) < _cell_x(simulation, 4.5) else 0)
        assert bool(simulation.state.reached_goal[LUMEN])
        assert simulation.state.outcome == OUTCOME_PLAYING

    def test_a_fita_tem_teto_e_rebobina_sozinha(self, simulation):
        """Um minuto e o maximo; passou disso, a fase rebobina sem pedir."""
        tape = TapeSession(simulation.world, simulation.state, simulation.runtime,
                           simulation.tape.input, capacity=30)
        tape.start(_level(simulation, "13_sob_o_vidro"))
        for _ in range(30):
            tape.tick(0)
        assert simulation.state.tape_phase == TAPE_REPLAY
        assert tape.trail_count == 30

    def test_desligar_devolve_o_teclado(self, simulation):
        tape = _start(simulation, "13_sob_o_vidro")
        tape.stop()
        assert simulation.state.tape_phase == TAPE_OFF
        assert not tape.input.engaged


_BRIDGE = {
    9: "........*.........*.........",
    10: "....A...............X.......",
    11: "######~~~~~#################",
    12: ".....B..............Y.......",
    13: "############################",
}
"""Uma ponte de eter acesa por uma lampada, e a Umbra logo abaixo dela, perto
o bastante para que a absorcao apague a lampada."""


class TestParadox:
    def _record_crossing(self, simulation, wait_ticks: int = 0) -> None:
        tape = simulation.tape
        tape.start()
        goal_x = _cell_x(simulation, 20.5)
        for tick in range(400):
            tape.tick(RIGHT if tick >= wait_ticks and _x(simulation, LUMEN) < goal_x - 2 else 0)
            assert simulation.state.outcome == OUTCOME_PLAYING, simulation.state.message
            if abs(_x(simulation, LUMEN) - goal_x) <= 2:
                break
        tape.rewind()

    def test_apagar_a_ponte_do_eco_e_paradoxo_no_ponto_da_queda(self, simulation):
        """O presente quebrou o passado: a Umbra engole a lampada, a ponte da
        Lumen gravada apaga, e ela sai do caminho. O mundo congela e o ponto
        marcado fica sobre a ponte -- onde a falha aconteceu, e nao no
        abismo, um segundo depois."""
        load_custom(simulation, _BRIDGE)
        self._record_crossing(simulation)
        state = simulation.state
        _play(simulation, lambda tick: ABILITY if tick == 0 else 0)

        assert state.tape_paradox, f"devia ser paradoxo, foi: {state.message!r}"
        assert state.outcome == OUTCOME_FAILED
        assert state.message.startswith("Paradoxo")
        assert _cell_x(simulation, 5.0) <= state.tape_paradox_x <= _cell_x(simulation, 12.0)
        assert state.tape_paradox_y < _cell_x(simulation, 13.0), "marcado antes de chegar ao abismo"

    def test_sem_mexer_no_passado_nao_ha_paradoxo(self, simulation):
        """O mesmo cenario, com a Umbra so andando: o eco atravessa a ponte e
        ninguem e acusado de nada."""
        load_custom(simulation, _BRIDGE)
        self._record_crossing(simulation)
        _play(simulation, lambda tick: RIGHT if _x(simulation, UMBRA) < _cell_x(simulation, 20.5) - 2 else 0)
        assert not simulation.state.tape_paradox, simulation.state.message
        assert simulation.state.outcome == OUTCOME_COMPLETE, simulation.state.message

    def test_apagar_a_luz_da_lumen_parada_tambem_e_paradoxo(self, simulation):
        """O eco nao precisa cair: se morre no escuro que a Umbra fez, o
        passado foi desfeito do mesmo jeito."""
        load_custom(simulation, {
            9: "........*...................",
            10: "....A...B...........X....Y..",
            11: "############################",
        })
        tape = simulation.tape
        tape.start()
        for _ in range(200):                 # parada, mas DENTRO da fita
            tape.tick(0)
        tape.rewind()
        _play(simulation, lambda tick: ABILITY if tick == 0 else 0, limit=400)
        state = simulation.state
        assert state.tape_paradox, state.message
        assert "apagou" in state.message
        assert tape.paradox_tick < tape.trail_count

    def test_morrer_esperando_depois_da_fita_tambem_para_o_laco(self, simulation):
        """A fita acabou e o eco ficou parado onde a Umbra apaga tudo. Nao da
        para saber se a culpa e do presente -- mas recomecar o presente daria
        no mesmo, entao isso tambem congela e oferece regravar dali."""
        load_custom(simulation, {
            9: "........*...................",
            10: "....A...B...........X....Y..",
            11: "############################",
        })
        tape = simulation.tape
        tape.start()
        for _ in range(10):
            tape.tick(0)
        tape.rewind()
        _play(simulation, lambda tick: ABILITY if tick == 0 else 0, limit=400)
        state = simulation.state
        assert state.tape_paradox, state.message
        assert "fita acabou" in state.message
        tape.rerecord_from_paradox()
        assert tape.prefix_ticks <= 10

    def test_regravar_desde_o_paradoxo_repete_o_passado_ate_ali(self, simulation):
        """A fita antiga se repete ate um segundo antes do ponto marcado --
        com as teclas do jogador ignoradas -- e so entao a Lumen volta para
        ele. O trecho repetido cai exatamente onde caiu da primeira vez."""
        load_custom(simulation, _BRIDGE)
        self._record_crossing(simulation, wait_ticks=120)
        tape, state = simulation.tape, simulation.state
        original = tape.trail[:tape.trail_count].copy()
        _play(simulation, lambda tick: ABILITY if tick == 0 else 0)
        assert state.tape_paradox
        paradox_tick = tape.paradox_tick

        tape.rerecord_from_paradox()
        assert state.tape_phase == TAPE_RECORD
        assert not state.tape_paradox
        assert tape.prefix_ticks == paradox_tick - 60
        for _ in range(tape.prefix_ticks):
            assert tape.replaying_prefix
            tape.tick(LEFT | JUMP)          # o jogador aperta, e o passado nao obedece
        assert not tape.replaying_prefix
        assert np.array_equal(tape.trail[:tape.prefix_ticks], original[:tape.prefix_ticks])

    def test_tentar_o_presente_de_novo_mantem_a_fita(self, simulation):
        load_custom(simulation, _BRIDGE)
        self._record_crossing(simulation)
        tape = simulation.tape
        length = tape.trail_count
        _play(simulation, lambda tick: ABILITY if tick == 0 else 0)
        tape.retry_present()
        assert simulation.state.tape_phase == TAPE_REPLAY
        assert simulation.state.outcome == OUTCOME_PLAYING
        assert tape.trail_count == length


class TestDuoLevelsInLoop:
    def test_toda_fase_com_eco_e_de_dupla_e_tem_solucao_conferida(self, simulation):
        """A marca ECO no card e uma promessa: esta fase de dupla fecha
        sozinho, em laco, sem afrouxar. Toda fase marcada tem de estar aqui,
        jogada -- e toda fase daqui tem de ser de dupla."""
        catalog = simulation.catalog
        marked = {catalog.at(i).level_id for i in range(catalog.count) if catalog.at(i).has_echo}
        assert marked, "sem nenhuma fase com eco, o modo e codigo morto"
        assert marked == set(_SOLVERS), f"marcadas {sorted(marked)}, conferidas {sorted(_SOLVERS)}"
        for level_id in marked:
            assert catalog.at(_level(simulation, level_id)).has_duo_variant, level_id

    @pytest.mark.parametrize("level_id", sorted(_SOLVERS))
    def test_a_fase_fecha_em_laco_na_versao_do_duo(self, simulation, level_id):
        _start(simulation, level_id)
        level = simulation.runtime.current
        assert simulation.terrain.lamp.sum() == sum(
            row.count("*") for row in level.rows_for(duo=True)
        ), "o eco tem de carregar a versao do duo, sem as lampadas do solo"
        _SOLVERS[level_id](simulation)
        state = simulation.state
        assert not state.tape_paradox, state.message
        assert state.outcome == OUTCOME_COMPLETE, f"{level.name}: {state.message}"

    def test_sem_o_eco_a_umbra_nao_atravessa_sob_o_vidro(self, simulation):
        """O contraprova: com a fita vazia, a mesma Umbra cai. E a luz do
        passado que a sustenta, e nao a fase que ficou facil."""
        tape = _start(simulation, "13_sob_o_vidro")
        tape.tick(0)
        tape.rewind()
        _play(simulation, lambda tick: RIGHT)
        assert simulation.state.outcome == OUTCOME_FAILED
        assert not simulation.state.tape_paradox
        assert "Umbra" in simulation.state.message


class _Renderer:
    """Grava os textos com a largura estimada do glifo monoespacado (~0,6 em),
    como `tests/test_menu_layout.py`, e aceita as primitivas do paradoxo."""

    def __init__(self) -> None:
        self.texts = []
        self.circles = []

    def get_viewport_size(self):
        return (896, 616)

    def draw_ui_rect(self, *args):
        pass

    def draw_ui_line(self, *args):
        pass

    def draw_ui_circle(self, x, y, radius, rgba, width=0):
        self.circles.append((x, y, radius))

    def draw_text(self, x, y, text, size, rgba, anchor="topleft"):
        width = len(text) * size * 0.6
        left = x - width / 2.0 if anchor == "center" else (x - width if anchor == "topright" else x)
        self.texts.append((text, left, left + width))

    def wrote(self, needle: str) -> bool:
        return any(needle in text for text, _, _ in self.texts)


def _press(input_provider, action: str) -> None:
    input_provider.set_action_held(action, True)
    input_provider.poll()
    input_provider.set_action_held(action, False)


class TestEchoScene:
    @pytest.fixture
    def flow(self, simulation, input_provider, tmp_path):
        from penumbra.progress import Progress
        from penumbra.scenes import PenumbraFlow
        from penumbra.terrain import Terrain
        from tests.conftest import CELL_SIZE, GRID_COLS, GRID_ROWS
        from tests.test_shipped_levels import _FakeGameLoop

        return PenumbraFlow(
            _FakeGameLoop(), simulation.runtime, simulation.state,
            simulation.catalog, simulation.tuning, input_provider,
            preview_terrain=Terrain(GRID_COLS, GRID_ROWS, CELL_SIZE),
            progress=Progress(simulation.catalog.count, tmp_path / "progress.json"),
            tape=simulation.tape,
        )

    def _enter(self, flow, simulation, input_provider, level_id="13_sob_o_vidro"):
        flow.show_menu()
        flow.menu._grid.selected = _level(simulation, level_id)
        _press(input_provider, "echo")
        flow._game_loop.current_scene.update(simulation.world, TICK)
        return flow._game_loop.current_scene

    def test_e_no_card_de_dupla_abre_o_laco(self, flow, simulation, input_provider):
        scene = self._enter(flow, simulation, input_provider)
        assert scene is flow.echo
        assert simulation.state.tape_phase == TAPE_RECORD
        assert simulation.state.duo, "o eco joga a versao do duo"
        assert flow.hud_visible

    def test_e_num_card_sem_eco_nao_faz_nada(self, flow, simulation, input_provider):
        scene = self._enter(flow, simulation, input_provider, "01_duas_polaridades")
        assert scene is flow.menu
        assert simulation.state.tape_phase == TAPE_OFF

    def test_em_dois_jogadores_nao_ha_eco(self, flow, simulation):
        flow.toggle_duo()
        assert not flow.can_echo(_level(simulation, "13_sob_o_vidro"))

    def test_tab_rebobina_e_tab_de_novo_volta_a_gravar(self, flow, simulation, input_provider):
        scene = self._enter(flow, simulation, input_provider)
        for _ in range(10):
            input_provider.poll()
            scene.update(simulation.world, TICK)
        _press(input_provider, "switch")
        scene.update(simulation.world, TICK)
        assert simulation.state.tape_phase == TAPE_REPLAY
        input_provider.poll()                  # soltou o TAB
        _press(input_provider, "switch")
        scene.update(simulation.world, TICK)
        assert simulation.state.tape_phase == TAPE_RECORD

    def test_voltar_ao_menu_desliga_o_eco(self, flow, simulation, input_provider):
        self._enter(flow, simulation, input_provider)
        flow.show_menu()
        assert simulation.state.tape_phase == TAPE_OFF
        assert not simulation.state.duo
        assert not simulation.tape.input.engaged

    def test_jogar_normal_depois_do_eco_e_o_jogo_de_sempre(self, flow, simulation, input_provider):
        self._enter(flow, simulation, input_provider)
        flow.start_level(_level(simulation, "13_sob_o_vidro"))
        assert simulation.state.tape_phase == TAPE_OFF
        assert not simulation.state.duo

    def test_o_rodape_e_o_paradoxo_cabem_na_janela(self, flow, simulation, input_provider):
        """Tres momentos, tres rodapes, e o painel do paradoxo com o ponto
        marcado. Nenhuma linha pode sair da janela -- headless ninguem ve."""
        from penumbra.hud import PenumbraHud

        hud = PenumbraHud(simulation.state, simulation.runtime, simulation.tuning,
                          simulation.world.get_pool("transform"), (896, 616),
                          tape=simulation.tape)
        load_custom(simulation, _BRIDGE)
        tape = simulation.tape
        tape.start()
        for tick in range(150):
            tape.tick(RIGHT if tick > 30 else 0)
        renderer = _Renderer()
        hud(renderer)
        assert renderer.wrote("GRAVANDO A LUMEN")

        tape.rewind()
        tape.tick(ABILITY)
        renderer = _Renderer()
        hud(renderer)
        assert renderer.wrote("UMBRA + ECO")
        _play(simulation, lambda tick: 0)
        assert simulation.state.tape_paradox
        renderer = _Renderer()
        hud(renderer)
        assert renderer.wrote("PARADOXO")
        assert renderer.circles, "o ponto do paradoxo tem de aparecer"
        for text, left, right in renderer.texts:
            assert 0.0 <= left and right <= 896.0, f"{text!r} sai da janela"


def test_a_fita_grava_so_as_quatro_acoes_do_corpo():
    """Pausar, reiniciar e trocar sao da cena, nao do passado."""
    assert TAPE_ACTIONS == ("move_left", "move_right", "jump", "ability")
