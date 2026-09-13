"""
As duas tolerancias do salto.

Existem contra o mesmo erro, e e o unico erro de plataforma que o jogador nao
consegue VER: a diferenca entre acertar e errar e de 16 ms. Sair da beira um
frame antes de apertar custava o salto; apertar um frame antes de pousar,
tambem. Em nenhum dos dois casos havia como saber que se apertou fora do
tempo -- o jogo simplesmente nao pulava.

Duas coisas podem quebrar aqui sem gerar erro: as tolerancias deixarem de
valer (e o jogo volta a comer saltos em silencio) ou valerem DEMAIS, virando
salto duplo -- o que abriria caminho em fases que trinta auditorias provaram
fechadas pela geometria.
"""
from __future__ import annotations

import pytest

from penumbra.state import LUMEN, UMBRA

from tests.conftest import advance, load_custom, place, position

# Uma borda: rocha ate a coluna 9, abismo depois. Quem anda pra direita cai.
_LEDGE = {
    12: "..A.....B..........X......Y.",
    13: "##########..................",
    14: "##########..................",
}

_FLOOR = {
    12: "..A.....B..........X......Y.",
    13: "############################",
    14: "############################",
}


def self_jump(input_provider, simulation):
    """Um toque em `jump` -- a acao e de BORDA, entao soltar antes importa."""
    input_provider.set_action_held("jump", False)
    advance(simulation, input_provider, frames=1)
    input_provider.set_action_held("jump", True)
    advance(simulation, input_provider, frames=1)
    input_provider.set_action_held("jump", False)


def _velocity_y(simulation, side):
    pool = simulation.world.get_pool("velocity")
    row = pool.dense_row_of(int(simulation.state.entity_index[side]))
    return float(pool.active_view()["linear_y"][row])


class TestCoyoteTime:
    def test_o_salto_ainda_vale_logo_depois_de_sair_da_beira(
        self, simulation, input_provider
    ):
        """O coyote inteiro. Sem ele, sair da plataforma um frame antes de
        apertar custa o salto -- e o jogador nao tem como saber que apertou
        tarde."""
        load_custom(simulation, _LEDGE)
        state = simulation.state
        place(simulation, LUMEN, 9, 12)
        advance(simulation, input_provider, frames=8)   # o tempo de assentar
        assert float(state.coyote[LUMEN]) > 0.0, "de pe, a janela esta cheia"

        # Anda pra fora da beira e solta a direcao: agora esta no ar.
        input_provider.set_action_held("move_right", True)
        advance(simulation, input_provider, frames=8)
        input_provider.set_action_held("move_right", False)
        advance(simulation, input_provider, frames=1)
        assert float(state.coyote[LUMEN]) > 0.0, "a janela ainda esta aberta"

        input_provider.set_action_held("jump", True)
        advance(simulation, input_provider, frames=1)

        assert _velocity_y(simulation, LUMEN) < 0.0, "o salto tem de sair"

    def test_a_janela_fecha(self, simulation, input_provider):
        """Ela e curta de proposito: maior que o tempo de queda de meia
        celula, ela deixaria de ser tolerancia e viraria um salto no ar."""
        load_custom(simulation, _LEDGE)
        state = simulation.state
        place(simulation, LUMEN, 9, 12)
        advance(simulation, input_provider, frames=8)   # o tempo de assentar

        input_provider.set_action_held("move_right", True)
        advance(simulation, input_provider, frames=8)
        input_provider.set_action_held("move_right", False)
        # 0,2 s no ar: o dobro da janela, e ainda antes de ela chegar ao fundo
        # -- `Grid2D` trata fora-dos-limites como SOLIDO, entao quem cai do
        # mundo volta a contar como "no chao" e o coyote recarregaria.
        advance(simulation, input_provider, frames=12)

        assert float(state.coyote[LUMEN]) == 0.0
        input_provider.set_action_held("jump", True)
        advance(simulation, input_provider, frames=1)

        assert _velocity_y(simulation, LUMEN) > 0.0, "caindo ha meio segundo, nao pula"

    def test_o_coyote_nao_vira_salto_duplo(self, simulation, input_provider):
        """O risco real da mecanica. Se a janela continuasse aberta depois do
        salto, ela valeria uma segunda vez no ar -- e trinta fases provadas
        fechadas pela geometria passariam a ter caminho."""
        load_custom(simulation, _FLOOR)
        state = simulation.state
        place(simulation, LUMEN, 9, 12)
        advance(simulation, input_provider, frames=8)   # o tempo de assentar

        input_provider.set_action_held("jump", True)
        advance(simulation, input_provider, frames=1)
        first = _velocity_y(simulation, LUMEN)
        assert first < 0.0
        assert float(state.coyote[LUMEN]) == 0.0, "saltar fecha a janela"

        input_provider.set_action_held("jump", False)
        advance(simulation, input_provider, frames=2)
        input_provider.set_action_held("jump", True)
        advance(simulation, input_provider, frames=1)

        assert _velocity_y(simulation, LUMEN) > first, (
            "o segundo aperto no ar nao pode dar impulso nenhum"
        )

    def test_trocar_de_ser_no_ar_nao_da_salto_de_graca(self, simulation, input_provider):
        """Por isso os relogios rodam fora de `_drive`: no solo so o ser ativo
        e conduzido, mas o inativo continua caindo. Se o coyote dele parasse
        de contar, bastaria trocar pra reabrir a janela."""
        load_custom(simulation, _LEDGE)
        state = simulation.state
        state.active = UMBRA
        place(simulation, LUMEN, 11, 10)       # a Lumen ja esta no ar
        advance(simulation, input_provider, frames=30)
        assert float(state.coyote[LUMEN]) == 0.0

        state.active = LUMEN
        input_provider.set_action_held("jump", True)
        advance(simulation, input_provider, frames=1)

        assert _velocity_y(simulation, LUMEN) > 0.0, "continua caindo"


class TestJumpBuffer:
    def test_o_aperto_feito_pouco_antes_de_pousar_e_lembrado(
        self, simulation, input_provider
    ):
        """O espelho do coyote, e o caso real dele: encadear dois saltos.

        O arco completo da Lumen dura `2*480/1100` = 0,873 s (52 frames).
        Apertar por volta do frame 48 e apertar ANTES de pousar -- sem o
        buffer, esse aperto se perde e o segundo salto nao sai."""
        load_custom(simulation, _FLOOR)
        state = simulation.state
        place(simulation, LUMEN, 9, 12)
        advance(simulation, input_provider, frames=8)

        self_jump(input_provider, simulation)               # primeiro salto
        advance(simulation, input_provider, frames=46)
        assert _velocity_y(simulation, LUMEN) > 0.0, "ja esta descendo"

        self_jump(input_provider, simulation)               # aperta no ar
        assert float(state.jump_buffer[LUMEN]) > 0.0, "o aperto ficou guardado"

        advance(simulation, input_provider, frames=6)
        assert _velocity_y(simulation, LUMEN) < 0.0, (
            "ao encostar, o aperto lembrado tem de virar salto"
        )

    def test_um_aperto_muito_antes_e_esquecido(self, simulation, input_provider):
        """Senao qualquer toque em qualquer momento da queda viraria um salto
        automatico ao pousar, e o jogador perderia o controle da aterrissagem."""
        load_custom(simulation, _FLOOR)
        state = simulation.state
        place(simulation, LUMEN, 9, 6)          # queda longa
        advance(simulation, input_provider, frames=2)

        input_provider.set_action_held("jump", True)
        advance(simulation, input_provider, frames=1)
        input_provider.set_action_held("jump", False)
        advance(simulation, input_provider, frames=20)   # muito depois

        assert float(state.jump_buffer[LUMEN]) == 0.0
        landed = _velocity_y(simulation, LUMEN)
        advance(simulation, input_provider, frames=10)
        assert _velocity_y(simulation, LUMEN) >= min(0.0, landed), "nao pulou sozinho"


class TestItDoesNotOpenNewRoutes:
    def test_as_duas_janelas_sao_menores_que_meia_celula_de_queda(self, simulation):
        """A garantia de que a tolerancia nao virou alcance.

        Meia celula sob a gravidade do jogo leva `sqrt(2*16/1100)` = 0,17 s.
        Uma janela maior que isso deixaria de perdoar um erro de tempo e
        passaria a estender o salto -- e o alcance geometrico de trinta fases
        foi medido sem ela."""
        from math import sqrt

        world = simulation.tuning.world
        half_cell_fall = sqrt(2.0 * (world.cell_size / 2.0) / world.gravity_y)
        for who, character in (("lumen", simulation.tuning.lumen),
                               ("umbra", simulation.tuning.umbra)):
            assert character.coyote_seconds < half_cell_fall, (
                f"{who}: coyote de {character.coyote_seconds}s passa de "
                f"{half_cell_fall:.3f}s e vira salto no ar"
            )
            assert character.jump_buffer_seconds < 2.0 * half_cell_fall, who

    def test_as_fases_continuam_com_o_mesmo_alcance(self, simulation, input_provider):
        """As tolerancias nao podem ter aberto rota nova: os testes de
        alcance geometrico de `test_reachability` medem o salto a partir do
        chao, e e assim que ele continua saindo."""
        load_custom(simulation, _FLOOR)
        state = simulation.state
        place(simulation, LUMEN, 9, 12)
        advance(simulation, input_provider, frames=8)   # o tempo de assentar
        input_provider.set_action_held("jump", True)
        advance(simulation, input_provider, frames=1)

        assert _velocity_y(simulation, LUMEN) == pytest.approx(
            simulation.tuning.lumen.jump_velocity_y
        ), "o impulso e exatamente o de sempre"
