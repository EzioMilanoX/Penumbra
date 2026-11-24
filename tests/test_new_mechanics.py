"""
Contra-eter, placa de pressao, fragmento e o modo de dois jogadores.

Cada um destes existe pra resolver um problema declarado do jogo, e cada um
pode voltar a nao resolver nada sem gerar erro: um contra-eter que se comporte
como eter comum, uma placa que trave a porta como as zonas, um fragmento que
esteja na rota em vez de num desvio, um modo duo que ignore o segundo jogador.
"""
from __future__ import annotations

import numpy as np

from penumbra.state import LUMEN, UMBRA
from tests.conftest import advance, load_custom, place, position

# Eter (cols 4-7) e contra-eter (cols 9-12) na MESMA fase, com uma lampada
# sobre o contra-eter. Linha de apoio 12, chao 13.
_MIRROR = {
    12: ".A..........*.B.....X....Y..",
    13: "####~~~~#;;;;###############",
    14: "####....#....###############",
    15: "####....#....###############",
}

# Porta com PLACA (nao com zonas): abre so enquanto alguem esta em cima.
_PLATE = {
    12: "..B_....A...........X....Y..",
    13: "############################",
    14: "############################",
}


def _with_door(spec: dict, col: int = 12) -> dict:
    rows = dict(spec)
    for row in range(6, 13):
        content = rows.get(row, "").ljust(28, ".")
        rows[row] = content[:col] + "D" + content[col + 1:]
    return rows


class TestCounterEther:
    def test_o_contra_eter_e_o_espelho_exato_do_eter(self, simulation, input_provider):
        """A propriedade inteira: na MESMA luz, os dois materiais pertencem a
        seres diferentes. Sem isso o contra-eter e so eter com outra cor."""
        load_custom(simulation, _MIRROR)
        state, terrain = simulation.state, simulation.terrain
        advance(simulation, input_provider, frames=3)

        ether = terrain.ether
        counter = terrain.counter_ether
        assert ether.any() and counter.any()

        lumen_solid = simulation.lumen_grid.cells
        umbra_solid = simulation.umbra_grid.cells
        for mask, name in ((ether, "eter"), (counter, "contra-eter")):
            rows, cols = np.nonzero(mask)
            for row, col in zip(rows, cols):
                lumen = bool(lumen_solid[row, col])
                umbra = bool(umbra_solid[row, col])
                assert lumen != umbra, f"{name} em ({col},{row}) nao pertence a exatamente um"

        # e o dono e trocado entre os dois materiais na mesma luz
        lit_ether = [bool(state.lit[r, c]) for r, c in zip(*np.nonzero(ether))]
        lumen_owns_ether = [bool(lumen_solid[r, c]) for r, c in zip(*np.nonzero(ether))]
        assert lumen_owns_ether == lit_ether, "eter aceso e da Lumen"
        lit_counter = [bool(state.lit[r, c]) for r, c in zip(*np.nonzero(counter))]
        lumen_owns_counter = [bool(lumen_solid[r, c]) for r, c in zip(*np.nonzero(counter))]
        assert lumen_owns_counter == [not lit for lit in lit_counter], (
            "contra-eter ACESO tem de ser da Umbra -- e o ponto dele"
        )

    def test_o_facho_da_lumen_derruba_ela_mesma_no_contra_eter(self, simulation, input_provider):
        """A consequencia mais estranha, e a boa: acender o proprio caminho
        DESTROI o chao dela quando o chao e contra-eter."""
        load_custom(simulation, _MIRROR)
        state = simulation.state
        place(simulation, LUMEN, 10, 12)   # em cima do contra-eter, no escuro
        advance(simulation, input_provider, frames=6)
        _, resting_y = position(simulation, LUMEN)
        bridge_top = 13 * simulation.terrain.cell_size
        assert resting_y < bridge_top, "no escuro o contra-eter e chao dela"

        input_provider.set_action_held("ability", True)
        advance(simulation, input_provider, frames=18)

        _, falling_y = position(simulation, LUMEN)
        assert bool(state.ability_on[LUMEN])
        assert falling_y > bridge_top, "acendendo, ela tira o proprio chao"


class TestPressurePlate:
    def test_a_placa_abre_a_porta_so_enquanto_alguem_esta_em_cima(self, simulation, input_provider):
        """Ao contrario das zonas de polaridade, que travam a porta aberta pra
        sempre. E essa diferenca que da funcao ao ser parado -- e que faz o
        modo de dois jogadores ter cooperacao de verdade."""
        load_custom(simulation, _with_door(_PLATE))
        state, terrain = simulation.state, simulation.terrain
        assert terrain.has_plate and terrain.has_door
        advance(simulation, input_provider, frames=3)
        assert not state.door_open, "sem ninguem em cima, a porta esta fechada"

        place(simulation, UMBRA, 3, 12)   # a placa
        advance(simulation, input_provider, frames=3)
        assert state.door_open
        assert simulation.lumen_grid.cells[10, 12] == 0, "e a porta deixa de ser solida"

        place(simulation, UMBRA, 8, 12)   # sai de cima
        advance(simulation, input_provider, frames=3)
        assert not state.door_open, "a placa NAO trava -- sair fecha de novo"
        assert simulation.lumen_grid.cells[10, 12] != 0

    def test_qualquer_um_dos_dois_serve_de_peso(self, simulation, input_provider):
        load_custom(simulation, _with_door(_PLATE))
        state = simulation.state
        place(simulation, LUMEN, 3, 12)
        advance(simulation, input_provider, frames=3)
        assert state.door_open, "a placa nao tem polaridade"


class TestShard:
    _SHARD = {
        12: ".A......B...+.......X....Y..",
        13: "############################",
        14: "############################",
    }

    def test_qualquer_um_apanha_o_fragmento(self, simulation, input_provider):
        load_custom(simulation, self._SHARD)
        state = simulation.state
        assert simulation.terrain.shard_cell == (12, 12)
        assert not state.shard_collected

        place(simulation, UMBRA, 12, 12)
        advance(simulation, input_provider, frames=3)

        assert state.shard_collected

    def test_o_fragmento_nao_entra_na_condicao_de_vitoria(self, simulation, input_provider):
        """Ele e um desvio opcional. Se entrasse na vitoria deixaria de ser
        escolha e viraria mais um item obrigatorio no caminho."""
        load_custom(simulation, self._SHARD)
        state = simulation.state
        place(simulation, LUMEN, 20, 12)
        place(simulation, UMBRA, 25, 12)
        advance(simulation, input_provider, frames=3)

        assert state.outcome != 0, "os dois portais completam a fase"
        assert not state.shard_collected, "e sem o fragmento"

    def test_recomecar_devolve_o_fragmento(self, simulation, input_provider):
        load_custom(simulation, self._SHARD)
        state = simulation.state
        place(simulation, UMBRA, 12, 12)
        advance(simulation, input_provider, frames=3)
        assert state.shard_collected

        simulation.runtime.reset()

        assert not state.shard_collected


class TestDuoMode:
    _FLAT = {
        12: ".A......B...........X....Y..",
        13: "############################",
        14: "############################",
    }

    def test_no_duo_os_dois_se_movem_ao_mesmo_tempo(self, simulation, input_provider):
        """No solo o ser parado e a tensao; no duo ele e um parceiro. Se o
        segundo conjunto de acoes nao chegasse ao segundo ser, o modo seria
        so um rotulo."""
        load_custom(simulation, self._FLAT)
        simulation.state.duo = True
        place(simulation, LUMEN, 2, 12)
        place(simulation, UMBRA, 8, 12)
        advance(simulation, input_provider, frames=2)
        lumen_start, _ = position(simulation, LUMEN)
        umbra_start, _ = position(simulation, UMBRA)

        input_provider.set_action_held("move_left", True)     # jogador 1
        input_provider.set_action_held("p2_move_right", True)  # jogador 2
        advance(simulation, input_provider, frames=20)

        lumen_x, _ = position(simulation, LUMEN)
        umbra_x, _ = position(simulation, UMBRA)
        assert lumen_x < lumen_start - 10.0, "o jogador 1 move a Lumen"
        assert umbra_x > umbra_start + 10.0, "e o jogador 2 move a Umbra, no mesmo frame"

    def test_no_duo_o_tab_nao_troca_de_ser(self, simulation, input_provider):
        """Nao existe "ativo" pra alternar quando os dois estao sob comando."""
        load_custom(simulation, self._FLAT)
        simulation.state.duo = True
        input_provider.set_action_held("switch", True)
        advance(simulation, input_provider, frames=2)
        assert simulation.state.active == LUMEN

    def test_no_solo_o_segundo_conjunto_de_acoes_e_ignorado(self, simulation, input_provider):
        load_custom(simulation, self._FLAT)
        simulation.state.duo = False
        place(simulation, UMBRA, 8, 12)
        advance(simulation, input_provider, frames=2)
        umbra_start, _ = position(simulation, UMBRA)

        input_provider.set_action_held("p2_move_right", True)
        advance(simulation, input_provider, frames=20)

        umbra_x, _ = position(simulation, UMBRA)
        assert abs(umbra_x - umbra_start) < 1.0

    def test_o_contato_continua_aniquilando_no_duo(self, simulation, input_provider):
        """A cooperacao tem de poder dar errado -- e no duo, com os dois em
        movimento, isso deixa de ser armadilha ocasional e passa a ser a
        fonte principal de desastre."""
        load_custom(simulation, self._FLAT)
        simulation.state.duo = True
        place(simulation, LUMEN, 10, 12)
        place(simulation, UMBRA, 10, 12)
        advance(simulation, input_provider, frames=3)

        assert simulation.state.outcome == 2
        assert "tocaram" in simulation.state.message
