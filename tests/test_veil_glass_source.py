"""
O veu, o vidro e a fonte que respira.

Ate o ato III, toda celula solida barrava luz e toda celula vazada a deixava
passar -- "e chao" e "faz sombra" eram a mesma pergunta, e por isso nenhuma
fase tinha mais de um andar. O veu e o vidro separam as duas propriedades,
cada um pra um lado, e os dois podem deixar de fazer isso sem gerar erro:
um veu que so fosse uma parede, um vidro que fizesse sombra como a rocha.

A fonte e o terceiro relogio do mundo. O farol liga e desliga, a lanterna se
desloca, a fonte INCHA -- e uma fonte cuja intensidade nao mudasse seria
apenas uma lampada com outro nome.
"""
from __future__ import annotations

from penumbra.state import LUMEN, UMBRA

from tests.conftest import advance, load_custom, place

# Lampada em (12,10) sobre uma ponte de eter, e um veu em (16,*) que corta a
# luz sem cortar a passagem.
_VEIL = {
    9:  "................:...........",
    10: "............*...:...........",
    11: "................:...........",
    12: "..A.....B.......:......X...Y",
    13: "########~~~~~~~#~~~~~~~#####",
    14: "############################",
}

# Andar de cima de vidro (linha 10), andar de baixo de contra-eter (linha
# 13): a Lumen anda na 9, a Umbra na 12 -- quatro linhas entre a Lumen e o
# chao da parceira, que e a unica distancia em que a conta fecha.
_GLASS = {
    9:  "...A....................X...",
    10: "########---------###########",
    12: "...B....................Y...",
    13: "########;;;;;;;;;###########",
}

_SOURCE = {
    12: "..A.....B.....@........X...Y",
    13: "##########~~~~#~~~~~~~######",
    14: "############################",
}


class TestVeil:
    def test_o_veu_atravessa_se_a_pe(self, simulation, input_provider):
        """Se ele barrasse passagem seria uma parede, e paredes o jogo ja
        tem quatro."""
        load_custom(simulation, _VEIL)
        assert simulation.terrain.veil.any()
        assert not simulation.lumen_grid.cells[12, 16], "o veu nao e chao de ninguem"
        assert not simulation.umbra_grid.cells[12, 16]

        place(simulation, LUMEN, 16, 12)
        advance(simulation, input_provider, frames=8)
        assert not simulation.lumen_grid.cells[12, 16]

    def test_o_veu_faz_sombra_sem_parede(self, simulation, input_provider):
        """A propriedade inteira. Ate aqui toda sombra do jogo vinha de uma
        parede -- a laje da fase 4, o macico das pontes."""
        load_custom(simulation, _VEIL)
        advance(simulation, input_provider, frames=4)
        state = simulation.state

        assert bool(state.lit[13, 12]), "deste lado do veu a lampada acende"
        assert not bool(state.lit[13, 18]), "do outro lado, nao"
        assert simulation.lumen_grid.cells[13, 12], "aceso: chao da Lumen"
        assert simulation.umbra_grid.cells[13, 18], "apagado: chao da Umbra"

    def test_dentro_do_veu_o_facho_nao_existe(self, simulation, input_provider):
        """A unica coisa do jogo que tira o verbo da Lumen sem tirar a
        habilidade dela. A semente e multiplicada pela mascara de propagacao,
        e ali ela e zero."""
        load_custom(simulation, _VEIL)
        state = simulation.state
        place(simulation, LUMEN, 18, 12)
        input_provider.set_action_held("ability", True)
        advance(simulation, input_provider, frames=6)
        assert bool(state.ability_on[LUMEN])
        assert bool(state.lit[13, 18]), "fora do veu o facho acende o chao dela"

        place(simulation, LUMEN, 16, 12)     # dentro da cortina
        advance(simulation, input_provider, frames=6)

        assert bool(state.ability_on[LUMEN]), "a habilidade continua ligada"
        assert float(state.light[12, 16]) == 0.0, "mas ali ela nao produz luz"


class TestGlass:
    def test_o_vidro_e_chao_dos_dois(self, simulation, input_provider):
        load_custom(simulation, _GLASS)
        advance(simulation, input_provider, frames=4)
        assert simulation.terrain.glass.any()
        assert simulation.lumen_grid.cells[10, 12]
        assert simulation.umbra_grid.cells[10, 12]

    def test_a_luz_atravessa_o_vidro(self, simulation, input_provider):
        """E disso que vive o andar duplo: a rocha faria sombra e o piso de
        baixo ficaria escuro pra sempre."""
        load_custom(simulation, _GLASS)
        state = simulation.state
        place(simulation, LUMEN, 12, 9)
        input_provider.set_action_held("ability", True)
        advance(simulation, input_provider, frames=6)

        assert bool(state.ability_on[LUMEN])
        assert float(state.light[13, 12]) > 0.35, "o facho desceu pelo vidro"

    def test_o_facho_de_cima_acende_o_chao_da_umbra_embaixo(self, simulation, input_provider):
        """A unica travessia do jogo em que a luz de um serve ao outro. O
        contra-eter so e chao da Umbra sob luz, e ela nao sabe fazer luz."""
        load_custom(simulation, _GLASS)
        state = simulation.state
        assert not simulation.umbra_grid.cells[13, 12], "no escuro nao e chao dela"

        place(simulation, LUMEN, 12, 9)
        input_provider.set_action_held("ability", True)
        advance(simulation, input_provider, frames=6)

        assert simulation.umbra_grid.cells[13, 12], "com o facho de cima, passa a ser"
        assert float(state.light[12, 12]) <= 0.60, (
            "e a celula onde ela ANDA nao pode passar do limiar de dissolucao -- "
            "quatro linhas entre os dois andares e a unica distancia em que as "
            "duas coisas valem ao mesmo tempo"
        )

    def test_o_vidro_separa_os_dois_seres(self, simulation, input_provider):
        """Solido pros dois, entao a Umbra nao sobe e a Lumen nao desce: os
        dois caminham juntos e nao podem se tocar, que e a imagem do jogo."""
        load_custom(simulation, _GLASS)
        place(simulation, UMBRA, 12, 12)
        advance(simulation, input_provider, frames=20)
        assert simulation.state.outcome == 0, "ninguem atravessou o vidro pra anular o outro"


class TestBreathingSource:
    def test_a_fonte_respira_entre_os_dois_extremos(self, simulation, input_provider):
        load_custom(simulation, _SOURCE)
        state, flow = simulation.state, simulation.tuning.flow
        assert simulation.terrain.has_source

        seen_low = seen_high = False
        for _ in range(int(flow.source_period_seconds * 60) + 20):
            advance(simulation, input_provider, frames=1)
            assert flow.source_min_intensity - 1e-3 <= state.source_intensity <= flow.source_max_intensity + 1e-3
            if state.source_intensity <= flow.source_min_intensity + 0.02:
                seen_low = True
            if state.source_intensity >= flow.source_max_intensity - 0.02:
                seen_high = True
        assert seen_low and seen_high, "um ciclo inteiro passa pelos dois extremos"

    def test_o_chao_aceso_dilata_e_contrai(self, simulation, input_provider):
        """A diferenca inteira entre ela e as outras duas. O farol troca o
        dono sem sair do lugar, a lanterna leva a divisa junto, e a fonte faz
        a divisa CRESCER -- ninguem precisa dar um passo pra perder o chao."""
        load_custom(simulation, _SOURCE)
        bridge = [c for c in range(10, 22) if c != 14]

        widths = []
        for _ in range(12):
            advance(simulation, input_provider, frames=30)
            widths.append(sum(1 for c in bridge if simulation.lumen_grid.cells[13, c]))

        assert min(widths) < max(widths), "o chao da Lumen muda de tamanho sozinho"
        assert min(widths) <= 2, "no vale quase nada e dela"
        assert max(widths) >= 6, "no auge, a maior parte da ponte e"

    def test_no_vale_a_ponte_toda_e_da_umbra(self, simulation, input_provider):
        load_custom(simulation, _SOURCE)
        state = simulation.state
        bridge = [c for c in range(10, 22) if c != 14]

        for _ in range(int(simulation.tuning.flow.source_period_seconds * 60) + 10):
            advance(simulation, input_provider, frames=1)
            if state.source_intensity <= simulation.tuning.flow.source_min_intensity + 0.01:
                break

        assert all(simulation.umbra_grid.cells[13, c] for c in bridge), (
            "expirada, a fonte devolve a ponte inteira a Umbra"
        )
