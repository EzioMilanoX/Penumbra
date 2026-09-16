"""
O fundo: ar e rocha em resolucao dobrada.

O jogo e sobre luz e desenhava luz como um tabuleiro de xadrez -- uma grade de
28 x 17 quadrados de 32 px, cada um de um cinza chapado. O campo de luz ja era
continuo; o que faltava era resolucao no DESENHO.

Duas decisoes ficam guardadas aqui, e as duas quebram em silencio:

1. **Quais papeis podem ser suavizados.** Ar e rocha sao os dois unicos que
   nao carregam decisao -- o ar nao e chao de ninguem, a rocha e chao dos dois,
   sempre. Todo o resto responde "de quem e este chao, agora?", e essa resposta
   tem de ser lida na celula exata. Suavizar eter seria trocar atmosfera por
   erro, e nada na tela diria que foi isso que aconteceu.

2. **Quanto o fundo pode custar.** `PygameRenderer.draw_batch` e um laco
   Python, medido a 2,8 us por entidade. A resolucao do fundo e um orcamento,
   nao um gosto -- e quem dobrar o fator sem refazer a conta descobre pelo
   jogo travando.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from penumbra.systems.presentation_system import BACKDROP_FACTOR, PresentationSystem
from penumbra.terrain import ROLE_EMPTY, ROLE_ROCK

from tests.conftest import advance, load_custom

_CONFIG = Path(__file__).resolve().parents[1] / "penumbra" / "config.json"

_MICROSECONDS_PER_ENTITY = 2.8
"""Custo medido de UMA entidade em `draw_batch`, neste backend, nesta maquina.

`PygameRenderer.draw_batch` percorre as entidades num laco Python e chama
`_draw_shape` em cada uma -- nao ha instancing, nao ha batch de verdade. Medido
com 476 quads opacos: 1,35 ms. Nao e estimativa."""

_FRAME_BUDGET_MS = 8.0
"""Metade dos 16,7 ms de um frame a 60 fps. O fundo e atmosfera: gastar mais
da metade do frame com o que nao decide nada deixaria o jogo sem folga para a
maquina de quem joga, que nao e esta."""


def _presentation(simulation) -> PresentationSystem:
    for system in simulation.world._systems:
        if isinstance(system, PresentationSystem):
            return system
    raise AssertionError("o PresentationSystem sumiu da composicao")


class TestOnlyTheRolesWithoutADecision:
    _ROOM = {
        10: "..........#####.............",
        11: "....*.....#####.............",
        12: "..A....B..#####...X......Y..",
        13: "############################",
        14: "#####~~~~~~~~~~~~~~~~~~#####",
    }

    def test_o_fundo_desenha_ar_e_rocha_e_mais_nada(self, simulation, input_provider):
        """A regra do arquivo. Se alguem acrescentar um papel aqui, o jogador
        passa a ver um degrau de meia celula onde precisa ler uma celula
        inteira -- e o jogo continua rodando, mais bonito e mentindo."""
        load_custom(simulation, self._ROOM)
        advance(simulation, input_provider, frames=2)
        pres = _presentation(simulation)

        role = pres._fine_role.reshape(-1)
        alpha = pres._bd_alpha
        suavizavel = np.logical_or(role == ROLE_EMPTY, role == ROLE_ROCK)

        assert not alpha[~suavizavel].any(), (
            "o fundo pintou um papel que carrega decisao"
        )
        assert alpha[role == ROLE_ROCK].all(), "a rocha e opaca"

    def test_as_celulas_de_ar_e_rocha_nao_sao_desenhadas_duas_vezes(
            self, simulation, input_provider):
        """Elas continuam existindo como entidade (nenhuma entidade deste jogo
        e destruida), so param de ser pintadas. Desenhar as duas camadas
        somaria alpha e a rocha ficaria mais clara que a propria cor dela."""
        load_custom(simulation, self._ROOM)
        advance(simulation, input_provider, frames=2)
        pres = _presentation(simulation)

        role = simulation.terrain.role.reshape(-1)
        alpha = pres._alpha
        for papel, nome in ((ROLE_EMPTY, "ar"), (ROLE_ROCK, "rocha")):
            assert not alpha[role == papel].any(), f"{nome} pintado nas duas camadas"


class TestTheInterpolationIsHonest:
    def test_a_grade_fina_expressa_niveis_que_a_grade_de_celulas_nao_tem(self):
        """O ponto inteiro do fundo, e a forma certa de afirma-lo.

        Uma celula acesa sozinha tem os quatro sub-quadros IGUAIS -- por
        simetria, e nao por defeito: os vizinhos valem zero dos dois lados.
        O que a interpolacao compra nao esta dentro da celula acesa, esta na
        borda dela: degraus intermediarios que uma grade de celulas nao sabe
        representar. Era isso que fazia a luz ler como tabuleiro."""
        campo = np.zeros((5, 5), dtype=np.float32)
        campo[2, 2] = 1.0
        pres = PresentationSystem.__new__(PresentationSystem)
        pres._make_backdrop_buffers(_FakeTerrain(5, 5))

        fino = pres._refine(campo)
        assert len(np.unique(campo)) == 2, "o campo so tem aceso e apagado"
        assert len(np.unique(fino)) > 3, "e a grade fina tem meios-tons"
        # E a queda e monotonica saindo do centro: luz que sobe ao se afastar
        # da fonte seria um peso trocado.
        linha = fino[5, 4:]
        assert all(a >= b for a, b in zip(linha, linha[1:])), "a luz sobe ao se afastar"

    def test_a_interpolacao_nao_inventa_luz(self):
        """Pesos 0.75/0.25 somam 1: nenhum sub-quadro pode passar do maior
        valor do campo nem cair abaixo do menor. Um peso errado acenderia o
        escuro, e num jogo em que a luz decide de quem e o chao isso seria
        visivel antes de ser explicavel."""
        gerador = np.random.default_rng(20260916)
        campo = gerador.uniform(0.0, 1.0, (17, 28)).astype(np.float32)
        pres = PresentationSystem.__new__(PresentationSystem)
        pres._make_backdrop_buffers(_FakeTerrain(17, 28))

        fino = pres._refine(campo)
        assert fino.min() >= campo.min() - 1e-5
        assert fino.max() <= campo.max() + 1e-5

    def test_um_campo_chapado_continua_chapado(self):
        campo = np.full((17, 28), 0.42, dtype=np.float32)
        pres = PresentationSystem.__new__(PresentationSystem)
        pres._make_backdrop_buffers(_FakeTerrain(17, 28))
        assert np.allclose(pres._refine(campo), 0.42, atol=1e-5)

    def test_refinar_nao_aloca_nada_por_frame(self):
        """O sistema roda dentro de `World.step()`, onde a constituicao da
        engine pede zero alocacao. `_refine` devolve SEMPRE o mesmo buffer --
        se alguem trocar um `out=` por uma expressao, isto pega."""
        pres = PresentationSystem.__new__(PresentationSystem)
        pres._make_backdrop_buffers(_FakeTerrain(17, 28))
        campo = np.zeros((17, 28), dtype=np.float32)
        assert pres._refine(campo) is pres._refine(campo)


class TestTheBudgetIsMeasured:
    def test_o_fundo_cabe_em_metade_de_um_frame(self):
        """A resolucao do fundo e um ORCAMENTO. A 4x a luz fica lisa de
        verdade e custa 21 ms so de desenho, contra os 16,7 ms que um frame
        inteiro tem -- foi por isso que ela e 2x, e nao porque 2x e bonito."""
        cols, rows = 28, 17
        sub_quadros = rows * cols * BACKDROP_FACTOR * BACKDROP_FACTOR
        custo = sub_quadros * _MICROSECONDS_PER_ENTITY / 1000.0
        assert custo <= _FRAME_BUDGET_MS, (
            f"fator {BACKDROP_FACTOR}: {sub_quadros} sub-quadros, {custo:.1f} ms"
        )

    def test_cabe_entidade_pra_todo_mundo(self):
        """Sem isto, subir o fator derruba o jogo na abertura -- e so na
        abertura DO JOGO, porque a suite headless monta a mesma composicao e
        cairia junto, mas quem roda o .exe descobre primeiro."""
        config = json.loads(_CONFIG.read_text(encoding="utf-8"))
        cols, rows = 28, 17
        preciso = rows * cols * (1 + BACKDROP_FACTOR * BACKDROP_FACTOR) + 3 + 2
        assert config["entity_capacity"] >= preciso, (
            f"capacidade {config['entity_capacity']} < {preciso} necessarias"
        )


class _FakeTerrain:
    """Só as três medidas que `_make_backdrop_buffers` lê."""

    def __init__(self, rows: int, cols: int) -> None:
        self.rows = rows
        self.cols = cols
        self.cell_size = 32.0
