"""
O Instante -- o segredo, e a unica coisa que o jogo nunca pede.

Penumbra tem uma regra inviolavel: os dois nao podem se tocar. Trinta fases
foram desenhadas em volta dela. O segredo e o contrario: parar os dois o mais
perto que da SEM se tocarem, lado a lado, no chao, e ficar quieto.

Tres coisas podem quebra-lo sem produzir erro nenhum: a janela de distancia
encostar na regra de contato (e o segredo vira a morte de sempre), acontecer
por acaso com os dois parados a esmo, ou nunca acontecer porque a janela nao
cabe em fase nenhuma.
"""
from __future__ import annotations

from penumbra import achievements
from penumbra.state import LUMEN, OUTCOME_FAILED, OUTCOME_PLAYING, UMBRA
from tests.conftest import advance, load_custom, place

# A lampada nao e enfeite: o Instante leva 2,2 s e a Lumen se apaga no
# escuro em 1,3 s. O segredo so acontece onde ela sobrevive parada -- o que
# e verdade em qualquer lugar do jogo onde faca sentido parar.
_ROOM = {
    9:  ".........*..................",
    12: "..A.....B..........X......Y.",
    13: "############################",
    14: "############################",
}


def _stand(simulation, input_provider, lumen_col, umbra_col):
    """Poe os dois no chao, parados, nas colunas pedidas."""
    place(simulation, LUMEN, lumen_col, 12)
    place(simulation, UMBRA, umbra_col, 12)
    advance(simulation, input_provider, frames=10)   # o tempo de assentar


class TestTheSecretHappens:
    def test_parados_lado_a_lado_o_instante_acontece(self, simulation, input_provider):
        """O segredo inteiro. Uma celula de distancia -- 32 px, contra os 23
        que aniquilam -- e nada mais acontecendo."""
        load_custom(simulation, _ROOM)
        state = simulation.state
        _stand(simulation, input_provider, 9, 10)
        assert not state.echo_found

        advance(simulation, input_provider, frames=int(2.4 * 60))

        assert state.echo_found, "parados a uma celula, o Instante tem de acontecer"
        assert state.outcome == OUTCOME_PLAYING, "e nao pode custar a fase"

    def test_o_medidor_sobe_antes_de_completar(self, simulation, input_provider):
        """A apresentacao le isto pra desenhar o anel entre os dois: o
        segredo precisa ser VISTO antes de ser entendido, senao e
        indistinguivel de nao existir."""
        load_custom(simulation, _ROOM)
        state = simulation.state
        _stand(simulation, input_provider, 9, 10)

        advance(simulation, input_provider, frames=30)
        half = state.echo_seconds
        assert 0.0 < half < 2.2

        advance(simulation, input_provider, frames=30)
        assert state.echo_seconds > half, "o medidor avanca enquanto eles ficam"

    def test_acontece_ja_na_primeira_fase(self, simulation, input_provider):
        """De proposito. Um segredo que so existisse no fim seria um premio;
        este e um convite, e esta la desde o comeco -- a fase 1 tem chao
        compartilhado e uma lampada em cima dele."""
        simulation.runtime.load(0)
        state = simulation.state
        # Longe o bastante da lampada da fase: a Umbra se dissolve a menos de
        # tres celulas dela, e o Instante leva 2,2 s. O gesto tem um lugar
        # certo, e achar o lugar e parte dele.
        place(simulation, LUMEN, 4, 7)
        place(simulation, UMBRA, 5, 7)
        advance(simulation, input_provider, frames=int(2.6 * 60))

        assert state.echo_found
        assert state.outcome == OUTCOME_PLAYING


class TestTheSecretDoesNotHappenByAccident:
    def test_longe_demais_nao_conta(self, simulation, input_provider):
        """De longe, ficar parado lado a lado e o que dois seres fazem o tempo
        todo -- o que se reconhece aqui e a intencao de chegar PERTO."""
        load_custom(simulation, _ROOM)
        _stand(simulation, input_provider, 9, 12)     # duas celulas
        advance(simulation, input_provider, frames=int(3.0 * 60))

        assert not simulation.state.echo_found

    def test_perto_demais_continua_matando(self, simulation, input_provider):
        """O piso da janela e a propria regra de contato. Se ela encostasse
        nele, o segredo seria a morte de sempre com outro nome."""
        load_custom(simulation, _ROOM)
        state = simulation.state
        place(simulation, LUMEN, 9, 12)
        place(simulation, UMBRA, 9.6, 12)             # menos de 23 px
        advance(simulation, input_provider, frames=6)

        assert state.outcome == OUTCOME_FAILED
        assert "tocaram" in state.message
        assert not state.echo_found

    def test_em_movimento_nao_conta(self, simulation, input_provider):
        """"Ficar quieto" e a metade do gesto. Passar um pelo outro na
        distancia certa acontece em qualquer fase, o tempo todo."""
        load_custom(simulation, _ROOM)
        _stand(simulation, input_provider, 9, 10)
        simulation.state.active = LUMEN
        input_provider.set_action_held("move_left", True)
        advance(simulation, input_provider, frames=int(3.0 * 60))

        assert not simulation.state.echo_found

    def test_no_ar_nao_conta(self, simulation, input_provider):
        load_custom(simulation, {
            12: "..A.....B..........X......Y.",
            13: "##.......................###",
            14: "##.......................###",
        })
        place(simulation, LUMEN, 9, 6)
        place(simulation, UMBRA, 10, 6)
        advance(simulation, input_provider, frames=8)

        assert not simulation.state.echo_found, "caindo lado a lado nao e ficar parado"


class TestTheSecretIsRemembered:
    def test_e_uma_conquista_escondida(self):
        """Aparece como "???" ate ser achada: uma lista que a mostrasse
        deixaria de haver segredo, e uma que nunca a mostrasse tiraria do
        jogador a chance de saber que achou algo que o jogo guardava."""
        catalog = {a.key: a for a in achievements.CATALOG}
        assert achievements.ECHO in catalog
        assert catalog[achievements.ECHO].hidden
        assert sum(1 for a in achievements.CATALOG if a.hidden) == 1, (
            "so o Instante e escondido -- as outras nove sao um convite, nao um enigma"
        )

    def test_recomecar_a_fase_zera_o_medidor(self, simulation, input_provider):
        load_custom(simulation, _ROOM)
        state = simulation.state
        _stand(simulation, input_provider, 9, 10)
        advance(simulation, input_provider, frames=30)
        assert state.echo_seconds > 0.0

        simulation.runtime.reset()

        assert state.echo_seconds == 0.0 and not state.echo_found


class TestTheWindowIsReachable:
    def test_a_janela_cabe_entre_o_contato_e_uma_celula(self, simulation):
        """A garantia de que o gesto e possivel: a distancia de uma celula --
        que e como os dois ficam lado a lado num chao de grade -- tem de
        estar DENTRO da janela, e acima da regra de contato."""
        tuning = simulation.tuning
        contact = tuning.lumen.half_width + tuning.umbra.half_width
        cell = tuning.world.cell_size

        assert contact < cell, (
            "se o contato fosse mais largo que uma celula, os dois nunca "
            "poderiam ficar em celulas vizinhas e o segredo seria impossivel"
        )
        assert contact + 1.0 <= cell <= contact + cell * 0.7
