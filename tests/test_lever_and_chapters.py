"""
A alavanca, a segunda fonte, e a divisao do jogo em capitulos.

A alavanca e o unico verbo que muda a outra metade da pergunta. Todo o resto
do jogo responde "onde ha luz agora?" -- o facho acende, a absorcao apaga, o
farol pulsa, a lanterna anda, a fonte incha. A alavanca muda "**de quem** e o
aceso", e uma alavanca que nao trocasse o dono seria so um botao decorativo
no chao.

Os capitulos sao dados (`chapter` no JSON de cada fase), nao posicoes: o menu
pagina por eles, e as tres funcoes -- aprender uma mecanica de cada vez,
misturar, e as especiais -- so valem se cada fase estiver no bloco certo. A
verificacao mais util aqui nao e de codigo, e de CONTEUDO: o capitulo 1
promete uma mecanica nova por fase, e e facil quebrar essa promessa sem
quebrar nada.
"""
from __future__ import annotations

from penumbra.state import LUMEN, UMBRA
from tests.conftest import advance, load_custom, place

# Ponte de eter acesa por duas lampadas -- da Lumen -- com a alavanca na
# rocha da esquerda, longe dela.
_LEVER = {
    11: "...........*.....*..........",
    12: ".!..B...A..................Y",
    13: "########~~~~~~~~~~~~########",
    14: "########............########",
    15: "########............#######X",
}

# Duas fontes em contratempo sobre duas metades de eter.
_TWIN = {
    11: "..........@......&..........",
    12: "..A..B.....................X",
    13: "#######~~~~~~##~~~~~~~######",
    14: "#######..............#####Y#",
    15: "############################",
}


class TestPolarityLever:
    def test_pisar_na_alavanca_troca_eter_por_contra_eter(self, simulation, input_provider):
        """O verbo inteiro. Sem isto ela e um azulejo diferente no chao."""
        load_custom(simulation, _LEVER)
        terrain = simulation.terrain
        assert terrain.has_lever
        ether_before = terrain.ether.copy()
        counter_before = terrain.counter_ether.copy()
        assert ether_before.any() and not counter_before.any()

        place(simulation, UMBRA, 1, 12)
        advance(simulation, input_provider, frames=4)

        assert simulation.state.polarity_swapped
        assert (terrain.counter_ether == ether_before).all(), "o eter virou contra-eter"
        assert not terrain.ether.any()

    def test_a_ponte_muda_de_dono_sem_uma_celula_mudar_de_brilho(
        self, simulation, input_provider
    ):
        """O que a torna diferente de tudo o que veio antes: a luz fica
        exatamente onde estava, e o chao passa pro outro."""
        load_custom(simulation, _LEVER)
        state = simulation.state
        advance(simulation, input_provider, frames=4)
        light_before = state.light.copy()
        assert simulation.lumen_grid.cells[13, 12], "acesa, a ponte e da Lumen"
        assert not simulation.umbra_grid.cells[13, 12]

        place(simulation, UMBRA, 1, 12)
        advance(simulation, input_provider, frames=4)

        assert simulation.umbra_grid.cells[13, 12], "depois da alavanca, e dela"
        assert not simulation.lumen_grid.cells[13, 12]
        assert float(abs(state.light - light_before).max()) < 1e-5, (
            "nenhuma celula podia ter mudado de brilho"
        )

    def test_a_alavanca_volta_atras(self, simulation, input_provider):
        """Um interruptor global irreversivel trancaria a fase na primeira
        curiosidade do jogador -- e uma alavanca convida exatamente isso."""
        load_custom(simulation, _LEVER)
        state = simulation.state
        place(simulation, UMBRA, 1, 12)
        advance(simulation, input_provider, frames=4)
        assert state.polarity_swapped

        place(simulation, UMBRA, 5, 12)          # sai de cima
        advance(simulation, input_provider, frames=4)
        place(simulation, UMBRA, 1, 12)          # e volta
        advance(simulation, input_provider, frames=4)

        assert not state.polarity_swapped
        assert simulation.terrain.ether.any() and not simulation.terrain.counter_ether.any()

    def test_ficar_parado_em_cima_nao_troca_sessenta_vezes_por_segundo(
        self, simulation, input_provider
    ):
        """A troca dispara na BORDA de entrada. Sem isso o terreno piscaria a
        60 Hz e nenhuma polaridade duraria tempo suficiente pra alguem pisar."""
        load_custom(simulation, _LEVER)
        state = simulation.state
        place(simulation, UMBRA, 1, 12)
        advance(simulation, input_provider, frames=120)

        assert state.polarity_swapped, "trocou uma vez e ficou"

    def test_qualquer_um_dos_dois_puxa(self, simulation, input_provider):
        load_custom(simulation, _LEVER)
        place(simulation, LUMEN, 1, 12)
        advance(simulation, input_provider, frames=4)
        assert simulation.state.polarity_swapped, "a alavanca nao tem polaridade"

    def test_recomecar_desfaz_a_troca(self, simulation, input_provider):
        load_custom(simulation, _LEVER)
        place(simulation, UMBRA, 1, 12)
        advance(simulation, input_provider, frames=4)
        assert simulation.state.polarity_swapped

        simulation.runtime.reset()

        assert not simulation.state.polarity_swapped
        assert simulation.terrain.ether.any()


class TestTwinSources:
    def test_a_segunda_fonte_respira_em_contratempo(self, simulation, input_provider):
        """Meio periodo atras: quando uma incha a outra esvazia. Em fase, as
        duas seriam uma lampada grande."""
        load_custom(simulation, _TWIN)
        state, flow = simulation.state, simulation.tuning.flow
        total = flow.source_min_intensity + flow.source_max_intensity

        for _ in range(int(flow.source_period_seconds * 60)):
            advance(simulation, input_provider, frames=1)
            assert abs((state.source_intensity + state.source_alt_intensity) - total) < 1e-4, (
                "as duas somadas tem de ser constantes -- e o que 'contratempo' quer dizer"
            )

    def test_a_metade_acesa_da_sala_vai_e_vem(self, simulation, input_provider):
        """O chao dos DOIS oscila no mesmo relogio, em sentidos opostos. E a
        unica fase em que isso acontece sem ninguem fazer nada."""
        load_custom(simulation, _TWIN)
        left = list(range(8, 13))
        right = list(range(15, 21))

        saw_left = saw_right = False
        for _ in range(int(simulation.tuning.flow.source_period_seconds * 60) + 30):
            advance(simulation, input_provider, frames=1)
            lumen_left = sum(1 for c in left if simulation.lumen_grid.cells[13, c])
            lumen_right = sum(1 for c in right if simulation.lumen_grid.cells[13, c])
            if lumen_left >= 4 and lumen_right == 0:
                saw_left = True
            if lumen_right >= 4 and lumen_left == 0:
                saw_right = True

        assert saw_left and saw_right, (
            "num ciclo, a metade acesa tem de estar inteiramente de um lado e "
            "depois inteiramente do outro"
        )


class TestChapters:
    def test_os_capitulos_sao_blocos_contiguos(self, simulation):
        catalog = simulation.catalog
        chapters = catalog.chapters
        assert len(chapters) == 3, "aprender, misturar, especiais"
        assert chapters[0].first == 0
        assert chapters[-1].last == catalog.count - 1
        for previous, current in zip(chapters, chapters[1:]):
            assert current.first == previous.last + 1, "sem buracos entre capitulos"

    def test_cada_fase_declara_o_capitulo_dela(self, simulation):
        catalog = simulation.catalog
        for index in range(catalog.count):
            level = catalog.at(index)
            assert level.chapter in (1, 2, 3), f"{level.level_id}: capitulo {level.chapter}"
            assert catalog.chapter_of(index).number == level.chapter

    def test_o_primeiro_capitulo_ensina_uma_mecanica_nova_por_fase(self, simulation):
        """A promessa do capitulo 1, e ela e de CONTEUDO: cada fase dele
        apresenta uma mecanica, e nenhuma repete.

        `teaches` e dado e nao deducao do ASCII porque duas destas fases
        ensinam habilidades -- o facho e a absorcao -- e nenhuma das duas traz
        um caractere de terreno que a fase anterior ja nao tivesse."""
        catalog = simulation.catalog
        learning = [catalog.at(i) for i in range(catalog.count) if catalog.at(i).chapter == 1]
        assert len(learning) >= 10, "o capitulo de aprender e o maior do jogo"

        taught = []
        for level in learning:
            assert level.teaches, f"{level.name} esta no capitulo 1 e nao declara o que ensina"
            assert level.teaches not in taught, (
                f"{level.name} repete {level.teaches!r} -- duas fases do tutorial pro "
                f"mesmo assunto e uma fase de mistura no lugar errado"
            )
            taught.append(level.teaches)

    def test_fora_do_tutorial_ninguem_declara_que_ensina(self, simulation):
        """Mistura e especial nao apresentam: combinam. Uma fase de mistura
        com `teaches` e uma fase de tutorial no capitulo errado."""
        catalog = simulation.catalog
        for index in range(catalog.count):
            level = catalog.at(index)
            if level.chapter != 1:
                assert not level.teaches, (
                    f"{level.name} (cap {level.chapter}) declara ensinar {level.teaches!r}"
                )

    def test_todo_terreno_do_jogo_e_apresentado_no_tutorial(self, simulation):
        """O espelho: nada pode estrear depois do capitulo 1. Uma mecanica que
        aparece primeiro numa fase de mistura chega sem nome e sem lugar onde
        praticar -- que e exatamente o que este teste pegou quando a segunda
        fonte so existia na fase do chefe."""
        catalog = simulation.catalog

        # Esqueleto de toda fase, mais os marcadores e o colecionavel.
        skeleton = set("#.ABXY+")
        # `&` e a MESMA fonte de `@`, meio periodo atras. A fase do chefe
        # pode estrea-la: e a reviravolta dela sobre algo ja ensinado.
        family = {"&": "@"}

        # A mancha (`x`) e uma excecao PROVISORIA, e o motivo dela e um achado
        # de projeto, nao uma conveniencia.
        #
        # Ela so significa alguma coisa num mundo de luz ambiente: no escuro
        # dos capitulos 1 e 2, uma fonte fixa de sombra e redundante -- ja esta
        # tudo escuro. Entao ela NAO PODE ser apresentada no tutorial sem que o
        # tutorial tenha uma fase acesa, e uma fase acesa no capitulo 1 seria
        # ensinar duas coisas de uma vez (o ambiente e a mancha), que e
        # exatamente o que o capitulo 1 promete nao fazer.
        #
        # Ou seja: **o mundo do avesso nao se parafusa no fim**. Ou o ambiente
        # entra no tutorial como mecanica propria, com a mancha logo depois, ou
        # ele vira um segundo eixo (mundo x capitulo) que este jogo ainda nao
        # tem. As duas fases que usam `x` hoje sao SONDAS do conceito.
        provisional = {"x"}

        taught = set()
        for index in range(catalog.count):
            level = catalog.at(index)
            if level.chapter != 1:
                continue
            taught |= {ch for row in level.rows for ch in row} - skeleton

        for index in range(catalog.count):
            level = catalog.at(index)
            glyphs = {family.get(ch, ch) for row in level.rows for ch in row} - skeleton
            unexplained = glyphs - taught - provisional
            assert not unexplained, (
                f"{level.name} (cap {level.chapter}) usa {sorted(unexplained)}, "
                f"que nenhuma fase do capitulo 1 apresenta"
            )
