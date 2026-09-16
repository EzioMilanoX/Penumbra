"""
Os dois corpos, e a unica diferenca entre eles que dava pra ver.

A Lumen e agil e fragil, a Umbra e pesada e resistente -- e ate aqui isso
existia so em NUMERO. Velocidade, altura de salto, tempo de medidor: o jogador
lia a diferenca numa tabela de tuning que ele nunca abre, e via dois blocos
deslizando igual. O unico sinal no corpo era a cor, e ela diz outra coisa (o
medidor de perigo).

Agora os dois esticam no ar e amassam ao pousar, com numeros invertidos de
proposito: a Lumen se estica mais e volta em 0,10 s (um quique); a Umbra quase
nao se estica e leva 0,28 s (um baque). E o mesmo fato -- massa -- dito nos
dois momentos em que ele aparece.

O que estes testes guardam nao e a aparencia, e as tres coisas que podem
quebrar em silencio: que isso e SO visual, que um corpo em repouso tem o
tamanho dele, e que amassar nao solta ninguem no ar.
"""
from __future__ import annotations

import numpy as np
import pytest

from penumbra.composition import SHADOW_HITBOX_POOL
from penumbra.systems.presentation_system import (
    _AIR_STRETCH, _LAND_RECOVER, _LAND_SQUASH, _STRETCH_LIMITS)
from penumbra.state import LUMEN, UMBRA

from tests.conftest import CELL_SIZE, advance, load_custom

_ROOM = {
    12: "..A....B..........X......Y..",
    13: "############################",
    14: "############################",
}


def _scale(simulation, side):
    pool = simulation.world.get_pool("transform")
    row = pool.dense_row_of(int(simulation.state.entity_index[side]))
    view = pool.active_view()
    return float(view["scale_y"][row]), float(view["scale_x"][row])


def _hitbox(simulation, side):
    name = "hitbox" if side == LUMEN else SHADOW_HITBOX_POOL
    pool = simulation.world.get_pool(name)
    row = pool.dense_row_of(int(simulation.state.entity_index[side]))
    view = pool.active_view()
    return float(view["half_width"][row]), float(view["half_height"][row])


def _drop(simulation, input_provider, cells=5.0, frames=80):
    """Levanta os dois e deixa cair, guardando a altura desenhada por frame."""
    pool = simulation.world.get_pool("transform")
    for side in (LUMEN, UMBRA):
        row = pool.dense_row_of(int(simulation.state.entity_index[side]))
        pool.active_view()["position_y"][row] = cells * CELL_SIZE

    history = {LUMEN: [], UMBRA: []}
    for _ in range(frames):
        advance(simulation, input_provider, frames=1)
        for side in (LUMEN, UMBRA):
            history[side].append(_scale(simulation, side)[0])
    return history


class TestItIsOnlyDrawing:
    def test_amassar_nao_muda_o_corpo_que_colide(self, simulation, input_provider):
        """A propriedade que sustenta tudo isto.

        A geometria das trinta fases foi medida com o corpo INTEIRO -- quantas
        celulas cada um sobe, que vao cada um atravessa. Se a amassada
        encolhesse o hitbox, um ser passaria por um vao no frame do pouso e a
        auditoria continuaria verde, porque ela nao simula pouso nenhum."""
        load_custom(simulation, _ROOM)
        antes = {side: _hitbox(simulation, side) for side in (LUMEN, UMBRA)}
        _drop(simulation, input_provider)
        for side, nome in ((LUMEN, "Lumen"), (UMBRA, "Umbra")):
            assert _hitbox(simulation, side) == antes[side], f"{nome} mudou de hitbox"

    def test_a_escala_de_fato_muda(self, simulation, input_provider):
        """O contraponto do teste acima: provar que o hitbox nao mexe nao vale
        nada se o desenho tambem nao mexer."""
        load_custom(simulation, _ROOM)
        history = _drop(simulation, input_provider)
        for side, nome in ((LUMEN, "Lumen"), (UMBRA, "Umbra")):
            alturas = np.array(history[side])
            assert alturas.max() > alturas.min() * 1.2, f"{nome} nao se deforma"


class TestABodyAtRestHasItsOwnSize:
    def test_parado_no_chao_a_escala_e_exatamente_a_base(self, simulation, input_provider):
        """O defeito que a medicao pegou e o olho nao pegaria.

        Parado no chao, a gravidade do frame ainda escreve uns 18 px/s antes
        de a colisao zerar. Medindo o alongamento contra zero, os dois ficavam
        1% esticados e 1% estreitos em TODO frame de todas as trinta fases --
        pequeno demais pra alguem apontar, e sempre errado."""
        load_custom(simulation, _ROOM)
        advance(simulation, input_provider, frames=120)

        for side, nome in ((LUMEN, "Lumen"), (UMBRA, "Umbra")):
            tuning = simulation.tuning.lumen if side == LUMEN else simulation.tuning.umbra
            alto, largo = _scale(simulation, side)
            assert alto == pytest.approx(tuning.half_height * 2.0 / 8.0, abs=1e-4), nome
            assert largo == pytest.approx(tuning.half_width * 2.0 / 8.0, abs=1e-4), nome


class TestTheWeightIsVisible:
    def test_a_umbra_amassa_mais_fundo_e_a_lumen_estica_mais(self, simulation, input_provider):
        """A inversao e o ponto. Peso nao flutua, entao a Umbra mal se estica
        no ar; peso chega com tudo, entao ela amassa mais. Se os dois numeros
        andassem juntos, a diferenca viraria "uma e maior que a outra"."""
        load_custom(simulation, _ROOM)
        history = _drop(simulation, input_provider)
        base = {
            LUMEN: simulation.tuning.lumen.half_height * 2.0 / 8.0,
            UMBRA: simulation.tuning.umbra.half_height * 2.0 / 8.0,
        }
        lumen = np.array(history[LUMEN]) / base[LUMEN]
        umbra = np.array(history[UMBRA]) / base[UMBRA]

        assert lumen.max() > umbra.max(), "a leve tem de esticar mais no ar"
        assert umbra.min() < lumen.min(), "a pesada tem de amassar mais fundo"

    def test_a_umbra_leva_mais_tempo_pra_voltar(self, simulation, input_provider):
        """Profundidade sozinha nao le como peso: uma amassada funda que some
        rapido le como elastico, que e o contrario do que ela e."""
        load_custom(simulation, _ROOM)
        history = _drop(simulation, input_provider)
        base = {
            LUMEN: simulation.tuning.lumen.half_height * 2.0 / 8.0,
            UMBRA: simulation.tuning.umbra.half_height * 2.0 / 8.0,
        }

        def frames_ate_voltar(side):
            alturas = np.array(history[side]) / base[side]
            fundo = int(np.argmin(alturas))
            for i in range(fundo, len(alturas)):
                if alturas[i] > 0.995:
                    return i - fundo
            return len(alturas)

        assert frames_ate_voltar(UMBRA) > 2 * frames_ate_voltar(LUMEN)
        assert _LAND_RECOVER[UMBRA] > _LAND_RECOVER[LUMEN]
        assert _AIR_STRETCH[LUMEN] > _AIR_STRETCH[UMBRA]
        assert _LAND_SQUASH[UMBRA] > _LAND_SQUASH[LUMEN]


class TestNobodyFloats:
    _MAX_LIFT_PX = 4.0
    """Quanto os pes podem sair do chao, no pior pouso do jogo.

    O sprite escala em torno do CENTRO -- a posicao da entidade e o centro
    dela, e posicao e estado de jogo, que a apresentacao nao move. Entao toda
    amassada levanta o pe em `half_height * (1 - escala)`. Acima de uns 4 px o
    ser deixa de parecer amassado contra a rocha e passa a parecer solto no
    ar, que e exatamente o oposto do que um baque diz."""

    def test_nenhum_dos_dois_descola_do_chao_ao_amassar(self, simulation, input_provider):
        for meia_altura, side, nome in (
            (simulation.tuning.lumen.half_height, LUMEN, "Lumen"),
            (simulation.tuning.umbra.half_height, UMBRA, "Umbra"),
        ):
            levanta = meia_altura * (1.0 - _STRETCH_LIMITS[0])
            assert levanta <= self._MAX_LIFT_PX, (
                f"{nome} flutuaria {levanta:.1f} px ao amassar"
            )

    def test_o_piso_do_alongamento_e_o_que_de_fato_limita(self, simulation, input_provider):
        """O teste acima confere a CONSTANTE. Este confere que a constante e
        mesmo o limite -- que nenhum caminho escapa do `clip`."""
        load_custom(simulation, _ROOM)
        history = _drop(simulation, input_provider, cells=2.0)
        base = {
            LUMEN: simulation.tuning.lumen.half_height * 2.0 / 8.0,
            UMBRA: simulation.tuning.umbra.half_height * 2.0 / 8.0,
        }
        for side in (LUMEN, UMBRA):
            alturas = np.array(history[side]) / base[side]
            assert alturas.min() >= _STRETCH_LIMITS[0] - 1e-5
            assert alturas.max() <= _STRETCH_LIMITS[1] + 1e-5


class TestChangingLevelClearsTheImpact:
    def test_a_queda_de_uma_fase_nao_vira_baque_na_seguinte(self, simulation, input_provider):
        """Trocar de fase teleporta os dois. Sem zerar a memoria de impacto, o
        primeiro frame da fase seguinte mostraria um baque que nunca
        aconteceu -- e no comeco de uma fase e quando o jogador esta olhando
        pros dois corpos pra entender onde eles estao."""
        load_custom(simulation, _ROOM)
        _drop(simulation, input_provider, frames=24)      # em pleno impacto

        simulation.state.level_index += 1
        load_custom(simulation, _ROOM)
        advance(simulation, input_provider, frames=1)

        for side, nome in ((LUMEN, "Lumen"), (UMBRA, "Umbra")):
            tuning = simulation.tuning.lumen if side == LUMEN else simulation.tuning.umbra
            alto, _ = _scale(simulation, side)
            assert alto == pytest.approx(tuning.half_height * 2.0 / 8.0, abs=1e-4), (
                f"{nome} chegou amassada na fase nova"
            )
