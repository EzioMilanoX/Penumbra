"""
As tres falhas que so apareceram com alguem jogando.

Nenhuma delas produzia erro, aparecia na auditoria ou quebrava um teste. As
duas primeiras sao do tipo mais caro que este jogo tem: a fase carrega, o
jogo abre, e ela simplesmente nao pode ser terminada.

1. **Escolta impossivel no solo.** Nas fases de vidro, a Lumen precisa ficar
   parada com o facho ligado enquanto a Umbra caminha por baixo. A carga
   drena tambem com o ser em espera -- e e de proposito, o facho custa
   mesmo estando parado -- entao no duo a travessia cabia numa carga e no
   solo, com as trocas de TAB, nunca cabia. Medido: a Umbra chegava a coluna
   9 de 16 e caia no abismo com a carga em 0,15.
2. **Crosta morta no duo.** `CrustBreakSystem` exigia `state.active == UMBRA`
   e lia as teclas do jogador 1. No duo nao existe "ativo", entao a crosta
   nunca cedia -- e as fases 2, 7 e 14 eram invenciveis a dois.
3. **A habilidade estava no J.** Agora esta no S, que espelha o BAIXO do
   jogador 2: mover nos lados, pular pra cima, habilidade pra baixo.
"""
from __future__ import annotations

import json
from pathlib import Path

from penumbra.state import LUMEN, OUTCOME_FAILED, UMBRA
from tests.conftest import advance, load_custom, place

_BINDINGS = Path(__file__).resolve().parents[1] / "data" / "input_bindings" / "penumbra_keyboard.json"

# Fases de escolta sob o vidro: id -> (colunas do vao que so o facho
# preenche, coluna onde a Lumen tem de parar pra preenche-lo). Endereca por
# ID e nao por numero: a reorganizacao em capitulos renumerou tudo, e um
# teste preso ao numero passa a medir a fase errada em silencio.
_ESCORT_LEVELS = {"13_sob_o_vidro": ((12, 14), 13), "30_a_fonte_aberta": ((9, 11), 10)}


def _level(simulation, level_id: str) -> int:
    for index in range(simulation.catalog.count):
        if simulation.catalog.at(index).level_id == level_id:
            return index
    raise AssertionError(f"fase {level_id!r} nao esta no catalogo")


def _hold(input_provider, *actions):
    for action in ("move_left", "move_right", "jump", "ability",
                   "p2_move_left", "p2_move_right", "p2_jump", "p2_ability"):
        input_provider.set_action_held(action, action in actions)


class TestAbilityOnTheDownKey:
    def test_a_habilidade_espelha_o_baixo_do_jogador_dois(self):
        """Os dois lados do teclado passam a ter o mesmo formato. Sem isso o
        jogador 1 tinha de aprender um layout e o 2, outro."""
        # Cada acao carrega uma LISTA (tecla e botao) desde que o controle
        # passou a ser resolvido pela propria engine; a tecla e a primeira.
        bindings = json.loads(_BINDINGS.read_text(encoding="utf-8"))
        assert bindings["ability"][0] == "KEY_S"
        assert bindings["p2_ability"][0] == "KEY_DOWN"
        assert bindings["jump"][0] == "KEY_SPACE"
        assert bindings["p2_jump"][0] == "KEY_UP"

    def test_o_s_da_habilidade_e_o_do_menu_nunca_valem_juntos(self):
        """Eles compartilham a tecla de proposito: `menu_down` so e lido no
        menu e `ability` so na fase. Se um dia os dois forem lidos na mesma
        cena, descer um card passaria a acender o facho."""
        bindings = json.loads(_BINDINGS.read_text(encoding="utf-8"))
        assert bindings["menu_down"][0] == bindings["ability"][0] == "KEY_S"

        menu_scene = Path(__file__).resolve().parents[1] / "penumbra" / "scenes.py"
        source = menu_scene.read_text(encoding="utf-8")
        menu_block = source[source.index("class MenuScene"):source.index("class PenumbraScene")]
        assert "menu_down" in menu_block
        assert '"ability"' not in menu_block, "o menu nao pode ler a habilidade"


class TestBindingsFileActuallyLoads:
    """
    O arquivo de bindings passa pelo carregador DE VERDADE.

    Os testes rodam com `NullInputProvider`, que ignora o arquivo -- entao
    nada headless olhava o que o jogo de janela realmente carrega. Uma chave
    de documentacao (`_nota`) adicionada ali derrubou o jogo na abertura com
    a suite inteira verde: o carregador do JSON de dificuldade descarta
    chaves comecadas por `_`, o de bindings nao.
    """

    def test_o_carregador_real_aceita_o_arquivo(self):
        import pygame
        from ouroboros.adapters.pygame_backend.pygame_input_provider import PygameInputProvider

        pygame.init()   # `key_code` avisa sem isto; nao abre janela nenhuma
        provider = PygameInputProvider()
        provider.load_bindings(str(_BINDINGS))   # levanta ValueError se algo nao resolver

    def test_toda_acao_que_o_jogo_le_esta_no_arquivo(self):
        """Um rename de acao no codigo sem o rename no JSON nao gera erro: a
        acao simplesmente nunca fica pressionada, e o controle morre em
        silencio. Foi assim que a crosta ficou morta no duo."""
        import re

        bound = set(json.loads(_BINDINGS.read_text(encoding="utf-8")))
        root = Path(__file__).resolve().parents[1] / "penumbra"
        used = set()
        pattern = re.compile(r'is_action_(?:held|pressed|released)\(\s*f?"([a-z2_]+)"')
        prefixed = re.compile(r'is_action_(?:held|pressed)\(f"\{prefix\}([a-z_]+)"')
        for path in root.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            used.update(pattern.findall(source))
            for action in prefixed.findall(source):
                used.add(action)
                used.add("p2_" + action)

        assert used, "o varredor nao achou nenhuma acao -- o padrao ficou obsoleto"
        missing = sorted(used - bound)
        assert not missing, f"acoes lidas pelo jogo e ausentes do binding: {missing}"


class TestCrustInDuo:
    _CRUST = {
        12: "..A.....B..%........X....Y..",
        13: "############################",
        14: "############################",
    }

    def test_a_umbra_rompe_a_crosta_no_duo(self, simulation, input_provider):
        """A regressao. No duo a Umbra e sempre o jogador 2, entao o verbo
        dela tem de sair das teclas DELE -- e nao pode depender de um 'ativo'
        que o duo nao tem."""
        load_custom(simulation, self._CRUST)
        simulation.state.duo = True
        terrain = simulation.terrain
        assert bool(terrain.crust[12, 11])

        place(simulation, UMBRA, 10, 12)
        advance(simulation, input_provider, frames=2)
        _hold(input_provider, "p2_move_right")
        advance(simulation, input_provider, frames=90)

        assert not bool(terrain.crust[12, 11]), (
            "com as teclas do jogador 2, a crosta tem de ceder no duo"
        )

    def test_no_duo_as_teclas_do_jogador_um_nao_rompem_a_crosta(self, simulation, input_provider):
        """A Lumen encosta na crosta e para, como faria numa rocha -- e essa
        e a assimetria toda."""
        load_custom(simulation, self._CRUST)
        simulation.state.duo = True
        place(simulation, LUMEN, 10, 12)
        advance(simulation, input_provider, frames=2)
        _hold(input_provider, "move_right")
        advance(simulation, input_provider, frames=90)

        assert bool(simulation.terrain.crust[12, 11]), "so a Umbra rompe"

    def test_no_solo_a_crosta_continua_saindo_do_ser_ativo(self, simulation, input_provider):
        load_custom(simulation, self._CRUST)
        state = simulation.state
        state.duo = False
        state.active = UMBRA
        place(simulation, UMBRA, 10, 12)
        advance(simulation, input_provider, frames=2)
        _hold(input_provider, "move_right")
        advance(simulation, input_provider, frames=90)

        assert not bool(simulation.terrain.crust[12, 11])


class TestEscortFitsOneCharge:
    """
    As fases de vidro precisam caber numa carga -- com as trocas do SOLO.

    A correcao nao foi mexer na regra da carga (o facho custa mesmo parado, e
    e disso que o jogo vive), e sim no DESENHO: lampadas fixas acendem quase
    todo o contra-eter e sobra um vao curto, do tamanho exato da mancha que o
    facho projeta atraves do vidro. A escolta virou um momento, nao a fase
    inteira.
    """

    def test_as_lampadas_deixam_um_vao_do_tamanho_da_mancha_do_facho(
        self, simulation, input_provider
    ):
        for level_id, (gap, stand_col) in _ESCORT_LEVELS.items():
            simulation.runtime.load(_level(simulation, level_id))
            simulation.state.ability_on[:] = False
            advance(simulation, input_provider, frames=4)
            name = simulation.runtime.current.name

            first, last = gap
            for col in range(first, last + 1):
                assert not simulation.umbra_grid.cells[13, col], (
                    f"{name}: a coluna {col} deveria depender do facho"
                )

            simulation.state.active = LUMEN
            place(simulation, LUMEN, stand_col, 9)
            simulation.state.ability_on[LUMEN] = True
            simulation.state.charge[LUMEN] = 1.0
            advance(simulation, input_provider, frames=4)

            for col in range(first, last + 1):
                assert simulation.umbra_grid.cells[13, col], (
                    f"{name}: com a Lumen na coluna {stand_col}, a {col} tem de virar chao dela"
                )

    def test_a_travessia_escoltada_cabe_na_carga_no_solo(self, simulation, input_provider):
        """O numero que faltava. A Umbra atravessa o vao inteiro enquanto a
        Lumen fica parada -- e sobra carga. Antes ela chegava a um terco do
        caminho e caia."""
        for level_id, (gap, stand_col) in _ESCORT_LEVELS.items():
            simulation.runtime.load(_level(simulation, level_id))
            state = simulation.state
            name = simulation.runtime.current.name
            first, last = gap

            state.active = LUMEN
            place(simulation, LUMEN, stand_col, 9)
            state.ability_on[LUMEN] = True
            advance(simulation, input_provider, frames=4)

            state.active = UMBRA
            place(simulation, UMBRA, first - 1, 12)
            advance(simulation, input_provider, frames=4)
            _hold(input_provider, "move_right")

            for _ in range(600):
                advance(simulation, input_provider, frames=1)
                assert state.outcome != OUTCOME_FAILED, (
                    f"{name}: {state.message} na coluna {int(state.cell[UMBRA, 0])}"
                )
                if int(state.cell[UMBRA, 0]) > last:
                    break
            _hold(input_provider)

            assert int(state.cell[UMBRA, 0]) > last, f"{name}: a Umbra nao chegou ao outro lado"
            assert bool(state.ability_on[LUMEN]), f"{name}: o facho apagou no meio da escolta"
            assert float(state.charge[LUMEN]) > 0.25, (
                f"{name}: sobrou so {float(state.charge[LUMEN]):.2f} de carga -- "
                f"sem folga pra posicionar a Lumen antes"
            )

    def test_o_ultimo_trecho_da_fonte_aberta_continua_dependendo_do_altar(
        self, simulation, input_provider
    ):
        """As lampadas novas nao podem ter acendido o que a pedra existe pra
        acender -- senao o altar final vira enfeite."""
        simulation.runtime.load(_level(simulation, "30_a_fonte_aberta"))
        simulation.state.ability_on[:] = False
        advance(simulation, input_provider, frames=4)
        for col in range(19, 23):
            assert not simulation.umbra_grid.cells[13, col], (
                f"a coluna {col} deveria continuar escura ate a Lumen deixar a forma"
            )
