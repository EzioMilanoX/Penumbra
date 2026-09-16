"""
O fundo, agora que a engine faz o trabalho.

A primeira versao subdividia a grade a mao: 1904 sub-quadros, interpolacao
escrita aqui, 2 ms por frame, e ainda assim degraus de 16 px. Ela existia
porque `draw_batch` cobra por entidade. A resposta certa nao era um sistema
mais esperto do lado do jogo, era a engine ganhar `IRenderer.draw_field` -- e
com ela o fundo virou dois arrays de 28 x 17 e uma chamada.

O que estes testes guardam:

1. **Quais papeis podem ser suavizados.** Ar e rocha sao os dois unicos que
   nao carregam decisao. Todo o resto responde "de quem e este chao, agora?",
   e essa resposta tem de ser lida na celula exata.

2. **A orientacao dos arrays.** `draw_field` recebe (colunas, linhas), que e a
   convencao de superficie; as mascaras do terreno sao (linhas, colunas). Uma
   transposicao esquecida passa em qualquer teste que so olhe totais, e na
   tela vira o nivel inteiro embaralhado.
"""
from __future__ import annotations

import numpy as np
import pytest

from penumbra.backdrop import Backdrop
from penumbra.backdrop import VOID
from penumbra.systems.presentation_system import (
    AIR_GLOW, AIR_GLOW_MAX_ALPHA, ROCK_LIT, ROCK_UNLIT)
from penumbra.terrain import ROLE_EMPTY, ROLE_ROCK

from tests.conftest import advance, load_custom


class _FieldRecorder:
    """Guarda o que foi entregue a `draw_field`, e mais nada."""

    def __init__(self) -> None:
        self.fields = []

    def draw_field(self, rgb, x, y, width, height, alpha=None):
        self.fields.append((rgb.copy(), x, y, width, height,
                            None if alpha is None else alpha.copy()))


class TestTwoFieldsAndWhyTwo:
    """Um campo so nao consegue cobrir a tela E recortar a parede.

    O alpha e um canal. Ou ele vale 255 em tudo -- e a cor da rocha vaza pra
    fora dela, borrando a silhueta -- ou ele recorta a rocha, e entao o brilho
    do ar tem de morar no alpha, que por contrato NAO interpola, e o ar sai
    quadriculado. As duas tentativas foram feitas, e as duas apareceram na
    tela antes de aparecer em qualquer teste."""

    _ROOM = {
        10: "..........#####.............",
        11: "....*.....#####.............",
        12: "..A....B..#####...X......Y..",
        13: "############################",
        14: "#####~~~~~~~~~~~~~~~~~~#####",
    }

    def test_a_luz_do_ar_vai_na_cor_e_o_campo_dele_nao_tem_mascara(
            self, simulation, input_provider):
        """Luz e VALOR, e valor mora na cor. A primeira versao punha o brilho
        do ar no alpha e o ar saiu mais quadriculado do que antes de tudo."""
        load_custom(simulation, self._ROOM)
        advance(simulation, input_provider, frames=2)

        recorder = _FieldRecorder()
        simulation.backdrop.draw(recorder)
        ar = recorder.fields[0]
        assert ar[5] is None, "o campo do ar nao pode ter mascara"

        azul = simulation.backdrop._air[:, :, 2].astype(np.int32)
        assert azul.max() > azul.min(), "a luz tem de variar na cor"
        assert azul.min() == VOID[2], (
            "ar no escuro total tem de sair igual ao vazio atras dele"
        )

    def test_a_rocha_e_recortada_seca_e_so_ela(self, simulation, input_provider):
        """A regra do que pode ser suavizado. Ar e rocha sao os dois unicos
        papeis que nao carregam decisao; todo o resto responde "de quem e este
        chao, agora?", e essa resposta tem de ser lida na celula exata."""
        load_custom(simulation, self._ROOM)
        advance(simulation, input_provider, frames=2)

        role = simulation.terrain.role.T
        alpha = simulation.backdrop._rock_alpha
        assert (alpha[role == ROLE_ROCK] == 255).all(), "a rocha e opaca"
        assert not alpha[role != ROLE_ROCK].any(), "e so a rocha"

    def test_a_cor_da_rocha_e_calculada_fora_dela_tambem(self, simulation, input_provider):
        """Senao a bilinear da borda leria preto do lado de fora e cada
        silhueta ganharia uma orla escura que nada no jogo explica."""
        load_custom(simulation, self._ROOM)
        advance(simulation, input_provider, frames=2)

        role = simulation.terrain.role.T
        fora = simulation.backdrop._rock[:, :, 0][role != ROLE_ROCK]
        assert fora.min() > 0, "a cor da rocha fora dela nao pode ser preta"

    def test_o_ar_vai_primeiro(self, simulation, input_provider):
        """A ordem e a propria definicao de fundo: o ar e o que se ve onde nao
        ha pedra. Invertida, a rocha some sob o ar."""
        load_custom(simulation, self._ROOM)
        advance(simulation, input_provider, frames=2)
        recorder = _FieldRecorder()
        simulation.backdrop.draw(recorder)
        assert len(recorder.fields) == 2
        assert recorder.fields[0][5] is None and recorder.fields[1][5] is not None

    def test_as_celulas_de_ar_e_rocha_nao_sao_desenhadas_duas_vezes(
            self, simulation, input_provider):
        """Elas continuam existindo como entidade (nenhuma entidade deste jogo
        e destruida), so param de ser pintadas."""
        from penumbra.systems.presentation_system import PresentationSystem

        load_custom(simulation, self._ROOM)
        advance(simulation, input_provider, frames=2)
        pres = next(s for s in simulation.world._systems
                    if isinstance(s, PresentationSystem))

        role = simulation.terrain.role.reshape(-1)
        for papel, nome in ((ROLE_EMPTY, "ar"), (ROLE_ROCK, "rocha")):
            assert not pres._alpha[role == papel].any(), f"{nome} nas duas camadas"


class TestTheArraysAreTheShapeTheEngineWants:
    """`draw_field` recebe (colunas, linhas); o terreno e (linhas, colunas).

    Uma transposicao esquecida nao levanta erro nenhum numa grade de 28 x 17 --
    os dois arrays existem, os dois tem o mesmo numero de celulas, e todo teste
    que some ou conte continua verde. Na tela o nivel sai embaralhado."""

    def test_uma_parede_vertical_sai_como_parede_vertical(self, simulation, input_provider):
        """Transposta, ela viraria uma faixa horizontal -- e nada mais no
        codigo diria qual das duas orientacoes esta certa."""
        load_custom(simulation, {
            9:  ".........#..................",
            10: ".........#..................",
            11: ".........#..................",
            12: "..A....B.#........X......Y..",
            13: "############################",
        })
        advance(simulation, input_provider, frames=2)
        alpha = simulation.backdrop._rock_alpha

        assert (alpha[9, 9:13] == 255).all(), "a parede vertical sumiu"
        assert not (alpha[0:9, 9] == 255).any(), (
            "ha uma faixa horizontal onde deveria haver uma parede vertical "
            "-- os arrays estao transpostos"
        )

    def test_os_campos_tem_as_dimensoes_da_grade(self, simulation):
        backdrop = simulation.backdrop
        cols, rows = simulation.terrain.cols, simulation.terrain.rows
        assert backdrop._air.shape == (cols, rows, 3)
        assert backdrop._rock.shape == (cols, rows, 3)
        assert backdrop._rock_alpha.shape == (cols, rows)

    def test_o_retangulo_cobre_o_campo_de_jogo_inteiro(self, simulation):
        """Nem mais nem menos: sobrando, o fundo invade o rodape; faltando,
        aparece uma tira preta onde deveria haver chao."""
        recorder = _FieldRecorder()
        simulation.backdrop.draw(recorder)
        terrain = simulation.terrain
        for _, x, y, width, height, _ in recorder.fields:
            assert (x, y) == (0.0, 0.0)
            assert width == terrain.cols * terrain.cell_size
            assert height == terrain.rows * terrain.cell_size


class TestItCostsNothingPerFrame:
    def test_atualizar_nao_aloca_array_novo(self, simulation, input_provider):
        """O fundo e reescrito todo frame dentro de `World.step()`, onde a
        constituicao da engine pede zero alocacao."""
        load_custom(simulation, {12: "..A....B..........X......Y..",
                                 13: "############################"})
        backdrop = simulation.backdrop
        campos = (backdrop._air, backdrop._rock, backdrop._rock_alpha)
        advance(simulation, input_provider, frames=5)
        assert (backdrop._air, backdrop._rock, backdrop._rock_alpha) == campos

    def test_o_fundo_nao_gasta_entidade_nenhuma(self):
        """A versao anterior gastava 1904, e exigia subir `entity_capacity` de
        640 para 2560. O numero no `config.json` e a prova de que a engine
        passou a fazer o trabalho."""
        import json
        from pathlib import Path

        config = json.loads(
            (Path(__file__).resolve().parents[1] / "penumbra" / "config.json")
            .read_text(encoding="utf-8"))
        assert config["entity_capacity"] <= 640


class TestItReachesTheScreenBehindTheWorld:
    def test_a_cena_desenha_o_fundo_antes_do_mundo(self, simulation, input_provider, tmp_path):
        """Fundo desenhado DEPOIS do mundo apagaria os dois seres. A ordem
        mora em `PenumbraFlow.draw_world` justamente porque duas cenas
        diferentes desenham o mundo."""
        from penumbra.progress import Progress
        from penumbra.scenes import PenumbraFlow
        from penumbra.terrain import Terrain
        from tests.conftest import CELL_SIZE, GRID_COLS, GRID_ROWS
        from tests.test_shipped_levels import _FakeGameLoop

        ordem = []

        class _Ordem:
            def draw_field(self, *a, **k): ordem.append("fundo")

        class _Mundo:
            def render(self, world, renderer): ordem.append("mundo")

        flow = PenumbraFlow(
            _FakeGameLoop(), simulation.runtime, simulation.state,
            simulation.catalog, simulation.tuning, input_provider,
            preview_terrain=Terrain(GRID_COLS, GRID_ROWS, CELL_SIZE),
            progress=Progress(simulation.catalog.count, tmp_path / "p.json"),
            backdrop=simulation.backdrop,
        )
        flow.draw_world(simulation.world, _Ordem(), _Mundo())
        assert ordem[-1] == "mundo", "o mundo tem de vir por ultimo"
        assert set(ordem[:-1]) == {"fundo"}, "e todo o fundo antes dele"

    def test_sem_fundo_o_mundo_ainda_desenha(self, simulation, input_provider, tmp_path):
        """Todo teste headless monta o fluxo sem fundo. Se `draw_world`
        exigisse um, a suite inteira cairia -- e o fundo e apresentacao, que
        por definicao pode faltar."""
        from penumbra.progress import Progress
        from penumbra.scenes import PenumbraFlow
        from penumbra.terrain import Terrain
        from tests.conftest import CELL_SIZE, GRID_COLS, GRID_ROWS
        from tests.test_shipped_levels import _FakeGameLoop

        desenhou = []

        class _Mundo:
            def render(self, world, renderer): desenhou.append(True)

        flow = PenumbraFlow(
            _FakeGameLoop(), simulation.runtime, simulation.state,
            simulation.catalog, simulation.tuning, input_provider,
            preview_terrain=Terrain(GRID_COLS, GRID_ROWS, CELL_SIZE),
            progress=Progress(simulation.catalog.count, tmp_path / "p.json"),
        )
        flow.draw_world(simulation.world, object(), _Mundo())
        assert desenhou == [True]
