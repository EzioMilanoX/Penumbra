"""
O altar de forma e a lanterna errante.

As duas mecanicas do ato III, e as duas podem deixar de significar qualquer
coisa sem produzir erro nenhum: um altar que devolvesse a habilidade
transformaria a renuncia em recarga; uma luz deixada que sumisse junto com
quem a deixou seria so um facho com passos a mais; uma lanterna que nao
levasse o CHAO junto seria decoracao andando por cima de uma ponte parada.

Aqui tambem mora a regressao do colapso do eclipse: `collapse_eclipse`
apagava, alem do eclipse, a placa de pressao e o contra-eter -- duas linhas
do reset de `load_rows` que vazaram pro metodo errado. A fase 12 tem placa E
eclipse: quando a ponte dourada caia, a porta trancava pra sempre e a placa
continuava DESENHADA no chao, o que faz a fase parecer quebrada em vez de
perdida.
"""
from __future__ import annotations

import pytest

from penumbra.state import LUMEN, UMBRA
from penumbra.terrain import TerrainDefinitionError
from tests.conftest import advance, load_custom, make_rows, place

# Um altar em (10,12), chao de rocha, e contra-eter logo a direita: o
# contra-eter so e solido pra Umbra sob LUZ, entao ele e a prova viva de que
# a luz deixada na pedra continua la.
_ALTAR = {
    12: ".A......B.^........X.....Y..",
    13: "###########;;;;#############",
    14: "############################",
}

# Trilho de sete celulas sobre uma ponte de eter.
_RAIL = {
    11: ".........>>>>>>>............",
    12: "..A...B....................X",
    13: "#########~~~~~~~############",
    14: "########################...Y",
    15: "############################",
}


def _hold_ability(simulation, input_provider, side, frames):
    """Liga a habilidade do ser ATIVO e segura por `frames`."""
    simulation.state.active = side
    input_provider.set_action_held("ability", True)
    advance(simulation, input_provider, frames=frames)


class TestFormAltar:
    def test_segurar_a_habilidade_no_altar_deixa_a_forma_la(self, simulation, input_provider):
        """O verbo inteiro. Sem ele o altar e um enfeite no chao."""
        load_custom(simulation, _ALTAR)
        state = simulation.state
        assert simulation.terrain.has_altar

        place(simulation, LUMEN, 10, 12)
        advance(simulation, input_provider, frames=2)
        assert not bool(state.form_spent[LUMEN])

        _hold_ability(simulation, input_provider, LUMEN, frames=90)

        assert bool(state.form_spent[LUMEN]), "1,1 s em cima do altar bastam"
        assert float(state.altar_light[12, 10]) > 0.0, "a pedra ficou com a luz"

    def test_quem_deixou_a_forma_nao_liga_mais_a_habilidade(self, simulation, input_provider):
        """A troca e poder por permanencia. Se a habilidade voltasse, o altar
        seria um bonus e a decisao deixaria de existir."""
        load_custom(simulation, _ALTAR)
        state = simulation.state
        place(simulation, LUMEN, 10, 12)
        _hold_ability(simulation, input_provider, LUMEN, frames=90)
        assert bool(state.form_spent[LUMEN])

        input_provider.set_action_held("ability", False)
        advance(simulation, input_provider, frames=60)
        input_provider.set_action_held("ability", True)
        advance(simulation, input_provider, frames=4)

        assert not bool(state.ability_on[LUMEN]), "o facho nao acende mais"
        assert float(state.charge[LUMEN]) == 0.0, "e a carga nao recompoe"

    def test_a_luz_deixada_fica_depois_de_ela_sair(self, simulation, input_provider):
        """O ponto todo: o facho acompanha a Lumen, a luz do altar NAO. E e
        isso que permite acender um lugar onde ela nao pode estar."""
        load_custom(simulation, _ALTAR)
        state = simulation.state
        place(simulation, LUMEN, 10, 12)
        _hold_ability(simulation, input_provider, LUMEN, frames=90)
        input_provider.set_action_held("ability", False)

        place(simulation, LUMEN, 2, 12)          # bem longe do altar
        advance(simulation, input_provider, frames=6)

        assert float(state.light[12, 10]) > 0.5, "a pedra continua acesa"
        assert bool(state.lit[13, 11]), "e o contra-eter ao lado continua aceso"

    def test_o_contra_eter_aceso_pelo_altar_vira_chao_da_umbra(self, simulation, input_provider):
        """O contra-eter e solido pra Umbra sob LUZ -- e ela nao sabe fazer
        luz. Sem o altar, essa ponte nunca seria dela."""
        load_custom(simulation, _ALTAR)
        assert not simulation.umbra_grid.cells[13, 12], "no escuro a ponte nao e dela"

        place(simulation, LUMEN, 10, 12)
        _hold_ability(simulation, input_provider, LUMEN, frames=90)
        input_provider.set_action_held("ability", False)
        advance(simulation, input_provider, frames=4)

        assert simulation.umbra_grid.cells[13, 12], "com a luz deixada, passa a ser"
        assert not simulation.lumen_grid.cells[13, 12], "e deixa de ser da Lumen"

    def test_o_altar_da_umbra_guarda_escuridao_e_apaga_a_lampada(self, simulation, input_provider):
        """O espelho exato. A absorcao dela tambem apaga fontes, e deixada na
        pedra ela apaga pra sempre."""
        load_custom(simulation, {
            12: ".A......B.^.*......X.....Y..",
            13: "###########;;;;#############",
            14: "############################",
        })
        state = simulation.state
        advance(simulation, input_provider, frames=3)
        assert float(state.light[12, 12]) > 0.5, "a lampada esta acesa"

        place(simulation, UMBRA, 10, 12)
        _hold_ability(simulation, input_provider, UMBRA, frames=90)
        input_provider.set_action_held("ability", False)
        place(simulation, UMBRA, 2, 12)
        advance(simulation, input_provider, frames=6)

        assert bool(state.form_spent[UMBRA])
        assert bool(state.absorbed[12, 12]), "a lampada continua engolida sem ela por perto"
        assert float(state.light[12, 12]) == 0.0

    def test_sair_do_altar_zera_o_deposito(self, simulation, input_provider):
        """Mesma exigencia da crosta: nada irreversivel pode acontecer de
        raspao, entao o medidor tem de zerar ao primeiro passo pra fora."""
        load_custom(simulation, _ALTAR)
        state = simulation.state
        place(simulation, LUMEN, 10, 12)
        _hold_ability(simulation, input_provider, LUMEN, frames=30)
        assert float(state.altar_progress[LUMEN]) > 0.0

        place(simulation, LUMEN, 6, 12)
        advance(simulation, input_provider, frames=3)

        assert float(state.altar_progress[LUMEN]) == 0.0
        assert not bool(state.form_spent[LUMEN])

    def test_o_altar_nao_recebe_nada_com_a_habilidade_desligada(self, simulation, input_provider):
        load_custom(simulation, _ALTAR)
        state = simulation.state
        place(simulation, LUMEN, 10, 12)
        advance(simulation, input_provider, frames=120)

        assert float(state.altar_progress[LUMEN]) == 0.0
        assert not bool(state.form_spent[LUMEN])

    def test_recomecar_devolve_a_forma(self, simulation, input_provider):
        """Como a crosta: irreversivel DENTRO da tentativa. Um altar mal
        escolhido custa a tentativa, nunca a fase."""
        load_custom(simulation, _ALTAR)
        state = simulation.state
        place(simulation, LUMEN, 10, 12)
        _hold_ability(simulation, input_provider, LUMEN, frames=90)
        assert bool(state.form_spent[LUMEN])

        simulation.runtime.reset()

        assert not bool(state.form_spent[LUMEN])
        assert float(state.charge[LUMEN]) == 1.0
        assert float(state.altar_light[12, 10]) == 0.0


class TestWanderingLantern:
    def test_a_lanterna_anda_e_volta_nas_pontas_do_trilho(self, simulation, input_provider):
        load_custom(simulation, _RAIL)
        terrain, state = simulation.terrain, simulation.state
        assert terrain.has_wanderer
        assert (terrain.wander_row, terrain.wander_min_col, terrain.wander_max_col) == (11, 9, 15)

        assert state.wander_col == pytest.approx(9.0)
        advance(simulation, input_provider, frames=120)
        first = state.wander_col
        assert 9.0 <= first <= 15.0, "nunca sai do trilho"

        seen = set()
        for _ in range(60):
            advance(simulation, input_provider, frames=10)
            assert 9.0 <= state.wander_col <= 15.0
            seen.add(round(float(state.wander_col)))
        assert {9, 15} <= seen, "ela percorre o trilho inteiro, de ponta a ponta"

    def test_a_lanterna_leva_o_chao_junto(self, simulation, input_provider):
        """A diferenca inteira entre ela e o farol pulsante. O farol troca o
        dono do eter sem sair do lugar; a lanterna faz a divisa ANDAR -- e e
        por isso que ela se atravessa acompanhando, nao esperando."""
        load_custom(simulation, _RAIL)
        advance(simulation, input_provider, frames=3)

        near = [col for col in range(9, 16) if simulation.lumen_grid.cells[13, col]]
        assert near, "onde a lanterna esta, a ponte e da Lumen"
        assert 9 in near and 15 not in near, "e a outra ponta e da Umbra"

        advance(simulation, input_provider, frames=150)   # ~2,5 s de viagem

        later = [col for col in range(9, 16) if simulation.lumen_grid.cells[13, col]]
        assert later != near, "a janela acesa se moveu"
        assert 15 in later, "ate a ponta oposta"
        assert not simulation.umbra_grid.cells[13, 15], "que deixou de ser da Umbra"

    def test_um_trilho_partido_e_recusado_no_carregamento(self, simulation):
        """Um buraco no meio faria a lanterna atravessar o vao como se nada
        houvesse -- e o jogador planejaria em cima de uma luz que aparece do
        outro lado sem razao."""
        with pytest.raises(TerrainDefinitionError, match="contiguo"):
            simulation.terrain.load_rows(make_rows({
                11: ".........>>>..>>>...........",
                12: "..A...B....................X",
                13: "############################",
                14: "########################...Y",
            }))

    def test_um_trilho_em_duas_linhas_e_recusado(self, simulation):
        with pytest.raises(TerrainDefinitionError, match="unica linha"):
            simulation.terrain.load_rows(make_rows({
                10: ".........>>>................",
                11: ".........>>>................",
                12: "..A...B....................X",
                13: "############################",
                14: "########################...Y",
            }))

    def test_um_trilho_de_uma_celula_so_e_recusado(self, simulation):
        with pytest.raises(TerrainDefinitionError, match="duas celulas"):
            simulation.terrain.load_rows(make_rows({
                11: ".........>..................",
                12: "..A...B....................X",
                13: "############################",
                14: "########################...Y",
            }))


class TestEclipseCollapseKeepsTheRest:
    def test_o_colapso_do_eclipse_nao_leva_a_placa_junto(self, simulation, input_provider):
        """Regressao. Duas linhas do reset de `load_rows` tinham vazado pro
        `collapse_eclipse`: quando a ponte dourada caia, a placa de pressao
        sumia das mascaras mas continuava DESENHADA -- e a porta que ela
        segurava trancava pra sempre. A fase 12 tem os dois."""
        load_custom(simulation, {
            8:  "............D...............",
            9:  "............D...............",
            10: "............D...............",
            11: "............D...............",
            12: "..B_..A.....D....=====.X.Y..",
            13: "############################",
        })
        terrain = simulation.terrain
        assert terrain.has_plate and terrain.has_eclipse
        plate_before = terrain.plate.copy()

        assert terrain.collapse_eclipse() > 0

        assert not terrain.eclipse.any(), "o eclipse some, que e o trabalho dele"
        assert (terrain.plate == plate_before).all(), "a placa, nao"

    def test_o_colapso_do_eclipse_nao_leva_o_contra_eter_junto(self, simulation):
        load_custom(simulation, {
            12: "..B...A......+.......X....Y.",
            13: "#####;;;;####=====##########",
            14: "############################",
        })
        terrain = simulation.terrain
        counter_before = terrain.counter_ether.copy()

        terrain.collapse_eclipse()

        assert (terrain.counter_ether == counter_before).all()
