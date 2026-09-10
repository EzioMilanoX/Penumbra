"""
A fisica da luz: alcance, oclusao e a sombra que apaga fontes.

O campo de luz nao e enfeite -- ele E o chao dos dois seres. Um erro de
alcance ou uma parede que deixa a luz vazar nao aparece como bug: aparece
como uma fase que nao da pra terminar.
"""
from __future__ import annotations

import pytest

from penumbra.state import LUMEN, UMBRA

from tests.conftest import advance, load_custom, place

# Uma unica lampada no meio do vazio (linha 4, coluna 14), com chao de rocha
# so na ultima linha util -- nada pra ocluir, pra que o alcance medido seja o
# alcance puro. Grade 28x17, ver `tests.conftest`.
_OPEN_ROOM = {
    4: "." * 14 + "*",
    14: ".A......B.......X....Y..",
    15: "#" * 28,
}

# A mesma sala, com uma parede logo abaixo da lampada.
_WALLED_ROOM = {
    4: "." * 14 + "*",
    5: "#" * 28,
    14: ".A......B.......X....Y..",
    15: "#" * 28,
}

_LAMP = (4, 14)
"""`(row, col)` da lampada -- a mesma ordem que `_reach_in_direction` usa."""


def _reach_in_direction(state, threshold, origin, step, limit=20):
    """Quantas celulas, a partir de `origin`, a luz ainda se mantem acima
    de `threshold` andando em `step`. Devolve a distancia EUCLIDIANA
    alcancada, pra que direcoes ortogonais e diagonais sejam comparaveis."""
    origin_row, origin_col = origin
    step_row, step_col = step
    reached = 0
    for k in range(1, limit + 1):
        row, col = origin_row + step_row * k, origin_col + step_col * k
        if not (0 <= row < state.light.shape[0] and 0 <= col < state.light.shape[1]):
            break
        if float(state.light[row, col]) < threshold:
            break
        reached = k
    return reached * ((step_row ** 2 + step_col ** 2) ** 0.5)


class TestLightReach:
    def test_o_alcance_de_uma_lampada_segue_a_formula_documentada(self, simulation, input_provider):
        """`(intensidade - solid_threshold) * falloff_radius_cells`. Este
        numero e a unica coisa que permite desenhar uma fase sem adivinhar
        onde o eter fica solido."""
        load_custom(simulation, _OPEN_ROOM)
        advance(simulation, input_provider, frames=2)

        light = simulation.tuning.light
        expected = (light.lamp_intensity - light.solid_threshold) * light.falloff_radius_cells
        measured = _reach_in_direction(
            simulation.state, light.solid_threshold, origin=_LAMP, step=(0, 1)
        )
        assert measured == pytest.approx(expected, abs=1.0)

    def test_a_luz_e_redonda_nao_um_losango(self, simulation, input_provider):
        """Com apenas os 4 vizinhos ortogonais a distancia resultante seria
        a de Manhattan e uma lampada acenderia um LOSANGO -- alcance na
        diagonal ~71% do alcance na horizontal. Os vizinhos diagonais (com
        custo sqrt(2)) existem exatamente pra isso, e sem eles nenhuma fase
        deste jogo teria sido desenhavel."""
        load_custom(simulation, _OPEN_ROOM)
        advance(simulation, input_provider, frames=2)

        threshold = simulation.tuning.light.solid_threshold
        straight = _reach_in_direction(simulation.state, threshold, _LAMP, (0, -1))
        diagonal = _reach_in_direction(simulation.state, threshold, _LAMP, (1, -1))
        assert straight > 0.0
        assert diagonal >= 0.85 * straight, (
            f"diagonal {diagonal:.2f} vs reta {straight:.2f} -- o campo voltou a ser um losango"
        )

    def test_a_rocha_bloqueia_a_luz(self, simulation, input_provider):
        """Sem oclusao, uma lampada iluminaria o outro lado de uma parede e
        a sombra projetada pela rocha -- de que a fase 'Eclipse' depende
        inteiramente -- deixaria de existir."""
        load_custom(simulation, _WALLED_ROOM)
        advance(simulation, input_provider, frames=2)

        state = simulation.state
        assert float(state.light[4, 14]) > 0.0, "a celula da lampada esta acesa"
        assert float(state.light[5, 14]) == 0.0, "a rocha nao guarda luz"
        assert float(state.light[6, 14]) == 0.0, "e nao deixa a luz passar"

    def test_celulas_bloqueadoras_parecem_iluminadas_sem_conduzir_luz(self, simulation, input_provider):
        """`display_light` e so apresentacao: uma parede com luz de um lado
        precisa PARECER iluminada. Nenhuma regra de jogo pode ler isso --
        se lesse, a rocha conduziria luz."""
        load_custom(simulation, _WALLED_ROOM)
        advance(simulation, input_provider, frames=2)

        state = simulation.state
        assert float(state.display_light[5, 14]) > 0.0
        assert float(state.light[5, 14]) == 0.0


class TestShadow:
    def test_a_absorcao_apaga_a_lampada_dentro_do_bolsao(self, simulation, input_provider):
        load_custom(simulation, _OPEN_ROOM)
        state = simulation.state
        place(simulation, UMBRA, 14, 5)
        state.ability_on[UMBRA] = True
        advance(simulation, input_provider, frames=2)

        assert bool(state.absorbed[4, 14]), "a lampada esta dentro do bolsao"
        assert float(state.light[4, 14]) == 0.0, "e portanto apagada"

    def test_o_bolsao_de_sombra_respeita_a_rocha(self, simulation, input_provider):
        """A sombra usa o MESMO flood da luz, com outra semente -- entao ela
        contorna paredes em vez de vazar por elas. Um disco euclidiano
        simples deixaria a Umbra apagar eter do outro lado de uma parede."""
        load_custom(simulation, _WALLED_ROOM)
        state = simulation.state
        place(simulation, UMBRA, 14, 7)  # logo abaixo da parede
        state.ability_on[UMBRA] = True
        advance(simulation, input_provider, frames=2)

        assert bool(state.absorbed[7, 14]), "a celula da propria Umbra esta no bolsao"
        assert not bool(state.absorbed[4, 14]), "a parede deveria proteger a lampada"

    def test_o_raio_de_absorcao_segue_o_valor_ajustado(self, simulation, input_provider):
        load_custom(simulation, _OPEN_ROOM)
        state = simulation.state
        place(simulation, UMBRA, 14, 9)
        state.ability_on[UMBRA] = True
        advance(simulation, input_provider, frames=2)

        expected = simulation.tuning.light.absorb_radius_cells
        reached = 0
        for k in range(1, 20):
            if not bool(state.absorbed[9, 14 + k]):
                break
            reached = k
        assert reached == pytest.approx(expected, abs=1.0)


class TestBeam:
    def test_o_facho_acompanha_a_lumen(self, simulation, input_provider):
        """O facho e semeado na celula dela a cada frame -- e por isso que a
        ilha de eter solido viaja com ela em vez de ficar onde foi criada."""
        load_custom(
            simulation,
            {
                14: ".A......B.......X....Y..",
                15: "####" + "~" * 24,
            },
        )
        state = simulation.state
        place(simulation, LUMEN, 6, 14)
        state.ability_on[LUMEN] = True
        advance(simulation, input_provider, frames=2)
        assert bool(state.lit[15, 6])

        place(simulation, LUMEN, 22, 14)
        advance(simulation, input_provider, frames=2)

        assert bool(state.lit[15, 22]), "o eter sob a nova posicao acende"
        assert not bool(state.lit[15, 6]), "e o de tras volta a ser chao da Umbra"
