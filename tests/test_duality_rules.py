"""
As regras da dualidade: quem tem chao onde, e o que mata cada um.

Este e o arquivo que importa. Toda fase de Penumbra depende de UMA
propriedade -- nenhuma celula de eter e chao dos dois ao mesmo tempo -- e de
quatro condicoes de morte. Se qualquer uma delas silenciosamente parar de
valer, as quatro fases continuam carregando sem erro e o jogo fica
insolvel ou trivial sem nenhum sintoma visivel.
"""
from __future__ import annotations

import numpy as np

from penumbra.state import LUMEN, OUTCOME_COMPLETE, OUTCOME_FAILED, OUTCOME_PLAYING, UMBRA

from tests.conftest import advance, load_custom, place, position

# Chao de rocha nas colunas 0-4 e 15-39, com uma ponte de eter em 5-14 e o
# vazio embaixo dela. Sem lampada: o eter comeca apagado.
_DARK_BRIDGE = {
    17: "..A..............B",
    18: "#####~~~~~~~~~~#########################",
    19: "#####..........#########################",
    20: "#####..........#########################",
}

# A mesma ponte, com uma lampada no meio dela: o eter comeca aceso.
_LIT_BRIDGE = {
    17: "..A......*.......B",
    18: "#####~~~~~~~~~~#########################",
    19: "#####..........#########################",
    20: "#####..........#########################",
}


_BRIDGE_ROW = 18
"""Linha de rocha/eter das fases de teste -- a superficie de apoio fica no
topo dela."""


def _bridge_top(simulation) -> float:
    """Coordenada Y do topo da ponte. Quem esta de pe fica ACIMA dela; quem
    perdeu o chao acaba abaixo. Comparar contra esta linha e mais honesto
    que uma tolerancia em pixels: `place` deixa o ser no centro da celula,
    e ele desce alguns pixels so pra assentar no chao."""
    return _BRIDGE_ROW * simulation.terrain.cell_size


def _add_goals(spec: dict, lumen_col: int = 30, umbra_col: int = 35) -> dict:
    """Toda fase precisa dos quatro marcadores; os portais dos testes ficam
    longe da area testada, sobre rocha."""
    row = spec[17].ljust(40, ".")
    row = row[:lumen_col] + "X" + row[lumen_col + 1:]
    row = row[:umbra_col] + "Y" + row[umbra_col + 1:]
    return {**spec, 17: row}


class TestEtherPolarity:
    """O eter pertence a exatamente um ser por vez -- nunca aos dois, nunca
    a nenhum."""

    def test_eter_apagado_e_chao_da_umbra_e_abismo_da_lumen(self, simulation, input_provider):
        load_custom(simulation, _add_goals(_DARK_BRIDGE))
        place(simulation, LUMEN, 8, 17)
        place(simulation, UMBRA, 12, 17)

        advance(simulation, input_provider, frames=18)

        bridge_top = _bridge_top(simulation)
        _, lumen_y = position(simulation, LUMEN)
        _, umbra_y = position(simulation, UMBRA)
        assert lumen_y > bridge_top, "Lumen deveria afundar no eter apagado"
        assert umbra_y < bridge_top, "Umbra deveria ficar de pe no eter apagado"

    def test_eter_aceso_e_chao_da_lumen_e_abismo_da_umbra(self, simulation, input_provider):
        load_custom(simulation, _add_goals(_LIT_BRIDGE))
        place(simulation, LUMEN, 6, 17)
        place(simulation, UMBRA, 13, 17)

        advance(simulation, input_provider, frames=18)

        bridge_top = _bridge_top(simulation)
        _, lumen_y = position(simulation, LUMEN)
        _, umbra_y = position(simulation, UMBRA)
        assert lumen_y < bridge_top, "Lumen deveria ficar de pe no eter aceso"
        assert umbra_y > bridge_top, "Umbra deveria afundar no eter aceso"

    def test_as_duas_grades_de_colisao_sao_complementares_no_eter(self, simulation, input_provider):
        """A invariante estrutural do jogo: em toda celula de eter, uma das
        duas grades e solida e a outra nao. Um XOR que der zero em qualquer
        celula significa eter que ninguem pisa (fase insolvel) ou que os
        dois pisam (a dualidade deixou de existir)."""
        load_custom(simulation, _add_goals(_LIT_BRIDGE))
        advance(simulation, input_provider, frames=3)

        ether = simulation.terrain.ether
        lumen_solid = simulation.lumen_grid.cells[ether].astype(bool)
        umbra_solid = simulation.umbra_grid.cells[ether].astype(bool)
        assert ether.any(), "a fase de teste precisa ter eter"
        assert np.all(lumen_solid ^ umbra_solid)

    def test_rocha_e_solida_para_os_dois(self, simulation, input_provider):
        """A rocha e o chao neutro. Sem ela nenhuma fase seria solvel: os
        dois seres precisam de algum lugar onde esperar em seguranca
        enquanto o jogador comanda o outro."""
        load_custom(simulation, _add_goals(_LIT_BRIDGE))
        advance(simulation, input_provider, frames=3)

        rock = simulation.terrain.rock
        assert np.all(simulation.lumen_grid.cells[rock] != 0)
        assert np.all(simulation.umbra_grid.cells[rock] != 0)


class TestAbilities:
    """As duas habilidades trocam o dono do terreno -- e uma a outra."""

    def test_facho_da_lumen_solidifica_eter_apagado(self, simulation, input_provider):
        load_custom(simulation, _add_goals(_DARK_BRIDGE))
        place(simulation, LUMEN, 8, 17)
        advance(simulation, input_provider, frames=2)
        assert not bool(simulation.state.lit[18, 8]), "sem lampada, o eter comeca apagado"

        input_provider.set_action_held("ability", True)
        advance(simulation, input_provider, frames=2)

        assert bool(simulation.state.ability_on[LUMEN])
        assert bool(simulation.state.lit[18, 8]), "o facho deveria acender o eter sob a Lumen"
        assert simulation.umbra_grid.cells[18, 8] == 0, "e retira-lo da Umbra no mesmo instante"

    def test_absorcao_da_umbra_apaga_a_lampada(self, simulation, input_provider):
        load_custom(simulation, _add_goals(_LIT_BRIDGE))
        simulation.state.active = UMBRA
        place(simulation, UMBRA, 9, 16)
        advance(simulation, input_provider, frames=2)
        assert bool(simulation.state.lit[18, 9]), "com a lampada, o eter comeca aceso"

        input_provider.set_action_held("ability", True)
        advance(simulation, input_provider, frames=2)

        assert bool(simulation.state.ability_on[UMBRA])
        assert bool(simulation.state.absorbed[17, 9]), "a lampada deveria estar dentro do bolsao"
        assert not bool(simulation.state.lit[18, 9]), "o eter deveria voltar a ser chao da Umbra"

    def test_a_carga_drena_e_desliga_a_habilidade_sozinha(self, simulation, input_provider):
        """A carga e o que torna a solidificacao TEMPORARIA -- sem ela cada
        fase se resolveria ligando a habilidade uma vez e esquecendo."""
        load_custom(simulation, _add_goals(_DARK_BRIDGE))
        state = simulation.state
        place(simulation, LUMEN, 2, 17)

        input_provider.set_action_held("ability", True)
        advance(simulation, input_provider, frames=2)
        assert bool(state.ability_on[LUMEN])
        input_provider.set_action_held("ability", False)

        charge_seconds = simulation.tuning.lumen.ability_charge_seconds
        advance(simulation, input_provider, frames=int(charge_seconds * 60) + 6)

        assert not bool(state.ability_on[LUMEN]), "a habilidade deveria se desligar ao esgotar a carga"
        # A carga ja voltou a subir nos frames seguintes ao desligamento
        # automatico -- o que se afirma aqui e que ela ESGOTOU, nao que
        # continue em zero.
        assert float(state.charge[LUMEN]) < 0.1

    def test_a_carga_recompoe_com_a_habilidade_desligada(self, simulation, input_provider):
        load_custom(simulation, _add_goals(_DARK_BRIDGE))
        state = simulation.state
        state.charge[LUMEN] = 0.2
        advance(simulation, input_provider, frames=30)
        assert float(state.charge[LUMEN]) > 0.2


class TestOutcomes:
    """As quatro mortes e a unica vitoria."""

    def test_lumen_se_apaga_no_escuro(self, simulation, input_provider):
        load_custom(simulation, _add_goals(_DARK_BRIDGE))
        place(simulation, LUMEN, 2, 17)
        frames = int(simulation.tuning.lumen.peril_seconds * 60) + 10

        advance(simulation, input_provider, frames=frames)

        assert simulation.state.outcome == OUTCOME_FAILED
        assert "apagou" in simulation.state.message

    def test_umbra_se_dissolve_na_luz(self, simulation, input_provider):
        load_custom(simulation, _add_goals(_LIT_BRIDGE))
        # Sobre rocha, ao lado da lampada: ela nao cai, ela se dissolve.
        place(simulation, UMBRA, 16, 17)
        place(simulation, LUMEN, 2, 17)
        simulation.terrain.lamp[17, 16] = 1.0
        frames = int(simulation.tuning.umbra.peril_seconds * 60) + 10

        advance(simulation, input_provider, frames=frames)

        assert simulation.state.outcome == OUTCOME_FAILED
        assert "dissolveu" in simulation.state.message

    def test_o_perigo_recua_quando_a_polaridade_volta_ao_normal(self, simulation, input_provider):
        """O medidor sobe e DESCE. Sem a recuperacao, atravessar uma nesga
        da polaridade errada seria sempre fatal e as habilidades perderiam
        o sentido."""
        load_custom(simulation, _add_goals(_LIT_BRIDGE))
        state = simulation.state
        # Longe da lampada (col 9), sobre a rocha: escuro o bastante pra
        # comecar a apagar, sem risco de cair.
        place(simulation, LUMEN, 25, 17)
        advance(simulation, input_provider, frames=30)
        peril_no_escuro = float(state.peril[LUMEN])
        assert peril_no_escuro > 0.0

        place(simulation, LUMEN, 9, 17)  # em cima da lampada
        advance(simulation, input_provider, frames=20)

        assert float(state.peril[LUMEN]) < peril_no_escuro
        assert state.outcome == OUTCOME_PLAYING

    def test_contato_entre_os_dois_anula_os_dois(self, simulation, input_provider):
        load_custom(simulation, _add_goals(_LIT_BRIDGE))
        place(simulation, LUMEN, 16, 17)
        place(simulation, UMBRA, 16, 17)

        advance(simulation, input_provider, frames=2)

        assert simulation.state.outcome == OUTCOME_FAILED
        assert "tocaram" in simulation.state.message

    def test_cair_no_abismo_mata(self, simulation, input_provider):
        load_custom(simulation, _add_goals(_DARK_BRIDGE))
        place(simulation, UMBRA, 8, simulation.terrain.rows - 1)

        advance(simulation, input_provider, frames=2)

        assert simulation.state.outcome == OUTCOME_FAILED
        assert "abismo" in simulation.state.message

    def test_os_dois_portais_ao_mesmo_tempo_completam_a_fase(self, simulation, input_provider):
        load_custom(simulation, _add_goals(_LIT_BRIDGE))
        place(simulation, LUMEN, 30, 17)
        advance(simulation, input_provider, frames=2)
        assert simulation.state.outcome == OUTCOME_PLAYING, "um portal so nao completa nada"

        place(simulation, UMBRA, 35, 17)
        advance(simulation, input_provider, frames=2)

        assert simulation.state.outcome == OUTCOME_COMPLETE


class TestSwitching:
    """Um ser por vez sob comando; o outro espera, mas nao esta imune."""

    def test_tab_alterna_o_ser_comandado(self, simulation, input_provider):
        load_custom(simulation, _add_goals(_LIT_BRIDGE))
        assert simulation.state.active == LUMEN

        input_provider.set_action_held("switch", True)
        advance(simulation, input_provider, frames=1)
        assert simulation.state.active == UMBRA

        input_provider.set_action_held("switch", False)
        advance(simulation, input_provider, frames=1)
        input_provider.set_action_held("switch", True)
        advance(simulation, input_provider, frames=1)
        assert simulation.state.active == LUMEN, "TAB e por borda, nao continuo"

    def test_apenas_o_ser_ativo_se_move(self, simulation, input_provider):
        load_custom(simulation, _add_goals(_LIT_BRIDGE))
        place(simulation, LUMEN, 2, 17)
        place(simulation, UMBRA, 16, 17)
        advance(simulation, input_provider, frames=2)
        lumen_start_x, _ = position(simulation, LUMEN)
        umbra_start_x, _ = position(simulation, UMBRA)

        input_provider.set_action_held("move_right", True)
        advance(simulation, input_provider, frames=20)

        lumen_x, _ = position(simulation, LUMEN)
        umbra_x, _ = position(simulation, UMBRA)
        assert lumen_x > lumen_start_x + 10.0
        assert abs(umbra_x - umbra_start_x) < 1.0

    def test_o_ser_inativo_cai_se_perder_o_chao(self, simulation, input_provider):
        """A tensao central: o ser que espera nao esta protegido. Se o
        jogador acender o eter sob a Umbra enquanto comanda a Lumen, ela
        cai -- e e por isso que cada fase e um problema de sequencia."""
        load_custom(simulation, _add_goals(_DARK_BRIDGE))
        place(simulation, LUMEN, 10, 17)
        place(simulation, UMBRA, 8, 17)
        advance(simulation, input_provider, frames=2)
        _, umbra_start_y = position(simulation, UMBRA)

        input_provider.set_action_held("ability", True)  # facho da Lumen, que esta ativa
        advance(simulation, input_provider, frames=18)

        _, umbra_y = position(simulation, UMBRA)
        assert bool(simulation.state.ability_on[LUMEN])
        assert umbra_y > umbra_start_y + 20.0, "o facho deveria ter tirado o chao da Umbra"


class TestPolarityDoor:
    """A porta que exige os dois ao mesmo tempo."""

    _DOOR_LEVEL = {
        12: "....*A.....L......*.DD..*............*..",
        13: "...#########........DD..................",
        14: ".............#......DD..................",
        16: ".............#......DD..................",
        17: "...B.....S..........DD.............X..Y.",
        18: "############################~~~~~~######",
        19: "############################......######",
        20: "############################......######",
    }

    def _with_door_column(self, spec: dict) -> dict:
        rows = dict(spec)
        for row in range(6, 18):
            content = rows.get(row, "").ljust(40, ".")
            rows[row] = content[:20] + "DD" + content[22:]
        return rows

    def test_a_porta_cede_com_lumen_na_luz_e_umbra_na_sombra(self, simulation, input_provider):
        load_custom(simulation, self._with_door_column(self._DOOR_LEVEL))
        state = simulation.state
        assert not state.door_open, "a porta comeca trancada"

        place(simulation, LUMEN, 11, 12)
        place(simulation, UMBRA, 9, 17)
        state.ability_on[LUMEN] = True  # so o facho acende a zona dela
        advance(simulation, input_provider, frames=3)

        assert state.door_open

    def test_a_porta_nao_cede_sem_o_facho(self, simulation, input_provider):
        load_custom(simulation, self._with_door_column(self._DOOR_LEVEL))
        place(simulation, LUMEN, 11, 12)
        place(simulation, UMBRA, 9, 17)
        advance(simulation, input_provider, frames=3)
        assert not simulation.state.door_open

    def test_a_porta_fica_aberta_depois_de_ceder(self, simulation, input_provider):
        """Deliberado: a condicao e simultanea, a abertura e permanente. Se
        a porta fechasse ao sair da zona, ninguem conseguiria atravessa-la
        -- sair da zona e exatamente o que atravessar exige."""
        load_custom(simulation, self._with_door_column(self._DOOR_LEVEL))
        state = simulation.state
        place(simulation, LUMEN, 11, 12)
        place(simulation, UMBRA, 9, 17)
        state.ability_on[LUMEN] = True
        advance(simulation, input_provider, frames=3)
        assert state.door_open

        state.ability_on[LUMEN] = False
        place(simulation, LUMEN, 5, 12)
        place(simulation, UMBRA, 3, 17)
        advance(simulation, input_provider, frames=5)

        assert state.door_open
        assert simulation.lumen_grid.cells[10, 20] == 0, "a porta aberta deixa de ser solida"
        assert simulation.umbra_grid.cells[10, 20] == 0
