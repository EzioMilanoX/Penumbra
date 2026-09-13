"""
A mesma fase, dois problemas diferentes.

O que exige parar um ser e comandar o outro vira trivial quando os dois andam
ao mesmo tempo -- e o contrario tambem: as fases de escolta nasceram
desenhadas pro duo e tiveram de ser AFROUXADAS pra fechar no solo, porque com
as trocas de TAB a carga do facho nao cabia na travessia.

A variante de duo e um diff de poucas celulas sobre o mesmo ASCII, e nao um
segundo mapa: a diferenca costuma ser de duas ou tres celulas, e escrever a
fase duas vezes faria um conserto numa das copias passar despercebido na
outra.

Tres coisas podem quebrar aqui sem gerar erro nenhum: a variante deixar de
ser carregada (e o duo joga a fase do solo), a variante ser invalida so no
modo que se testa menos, e a variante existir sem que nada na tela diga que a
fase mudou.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from penumbra.levels import LevelCatalog, LevelCatalogError
from penumbra.state import LUMEN, UMBRA
from penumbra.terrain import Terrain

from tests.conftest import GRID_COLS, GRID_ROWS, advance

_LEVELS_DIR = Path(__file__).resolve().parents[1] / "data" / "levels"


def _level(simulation, level_id: str) -> int:
    for index in range(simulation.catalog.count):
        if simulation.catalog.at(index).level_id == level_id:
            return index
    raise AssertionError(f"fase {level_id!r} nao esta no catalogo")


def _with_variants(simulation):
    return [simulation.catalog.at(i) for i in range(simulation.catalog.count)
            if simulation.catalog.at(i).has_duo_variant]


class TestVariantsAreReal:
    def test_o_jogo_tem_fases_que_mudam_no_duo(self, simulation):
        variants = _with_variants(simulation)
        assert variants, "sem nenhuma variante, a mecanica inteira e codigo morto"

    def test_o_diff_muda_o_ascii_e_so_onde_diz_que_muda(self, simulation):
        """Cada celula declarada tem de mudar de fato, e nenhuma outra pode
        mudar junto. Um diff que nao batesse com o mapa seria uma fase
        diferente da desenhada, e so no modo menos testado."""
        for level in _with_variants(simulation):
            solo = level.rows_for(duo=False)
            duo = level.rows_for(duo=True)
            assert solo == level.rows, "a variante nao pode vazar pro solo"

            changed = {
                (col, row)
                for row in range(len(solo))
                for col in range(len(solo[row]))
                if solo[row][col] != duo[row][col]
            }
            declared = {(col, row) for col, row, _ in level.duo_cells}
            assert changed == declared, (
                f"{level.name}: o diff declara {sorted(declared)} e muda {sorted(changed)}"
            )

    def test_as_duas_versoes_carregam(self, simulation):
        """`validate_all` ja faz isso na composicao, e este teste existe pra
        que a falha aponte a FASE e o MODO -- uma variante invalida so quebra
        quando alguem escolhe dois jogadores."""
        terrain = Terrain(cols=GRID_COLS, rows=GRID_ROWS, cell_size=32.0)
        for level in _with_variants(simulation):
            for duo in (False, True):
                terrain.load_rows(level.rows_for(duo))

    def test_toda_variante_diz_ao_jogador_o_que_mudou(self, simulation):
        """Se a fase muda e nada avisa, o jogador aprende a fase errada e
        depois acha que o jogo mentiu. A nota aparece no rodape no lugar da
        dica quando o duo esta ativo."""
        for level in _with_variants(simulation):
            assert level.duo_note, f"{level.name} muda no duo e nao diz o que mudou"
            assert len(level.duo_note) <= int((896.0 - 2 * 14.0) / (12.0 * 0.6)), (
                f"{level.name}: a nota do duo nao cabe no rodape"
            )


class TestRuntimeLoadsTheRightVariant:
    def test_o_modo_escolhe_a_versao_carregada(self, simulation, input_provider):
        """O `LevelRuntime` le `state.duo` no load. Sem isso o duo jogaria a
        fase do solo -- silenciosamente, e exatamente nas fases em que o modo
        e a diferenca toda."""
        index = _level(simulation, "13_sob_o_vidro")
        state = simulation.state

        state.duo = False
        simulation.runtime.load(index)
        solo_lamps = int(simulation.terrain.lamp.sum())

        state.duo = True
        simulation.runtime.load(index)
        duo_lamps = int(simulation.terrain.lamp.sum())

        assert duo_lamps < solo_lamps, (
            "no duo saem as lampadas que encurtavam a escolta"
        )

    def test_recomecar_mantem_a_variante(self, simulation, input_provider):
        """`R` no meio da fase nao pode devolver o jogador a versao do outro
        modo -- seria a pior hora possivel pra fase mudar debaixo dele."""
        state = simulation.state
        state.duo = True
        simulation.runtime.load(_level(simulation, "13_sob_o_vidro"))
        lamps = int(simulation.terrain.lamp.sum())

        simulation.runtime.reset()

        assert int(simulation.terrain.lamp.sum()) == lamps

    def test_no_duo_a_escolta_e_a_travessia_inteira(self, simulation, input_provider):
        """A promessa da variante da fase 13, medida: no solo as lampadas
        deixam livre quase todo o contra-eter e sobra um vao curto; no duo nao
        sobra nada -- cada passo da Umbra depende do facho de cima."""
        index = _level(simulation, "13_sob_o_vidro")
        state = simulation.state
        bridge = range(8, 17)

        state.duo = False
        simulation.runtime.load(index)
        state.ability_on[:] = False
        advance(simulation, input_provider, frames=4)
        free_solo = sum(1 for c in bridge if simulation.umbra_grid.cells[13, c])

        state.duo = True
        simulation.runtime.load(index)
        state.ability_on[:] = False
        advance(simulation, input_provider, frames=4)
        free_duo = sum(1 for c in bridge if simulation.umbra_grid.cells[13, c])

        assert free_solo >= 5, "no solo a maior parte da ponte e de graca"
        assert free_duo == 0, "no duo, nenhuma celula e de graca"

    def test_no_duo_a_umbra_troca_de_relacao_com_a_lanterna(self, simulation, input_provider):
        """A inversao mais completa do jogo. Em 'Sem Rocha', no solo a pista
        de baixo e eter e ela FOGE do buraco que a lanterna abre; no duo e
        contra-eter e ela tem de andar DEBAIXO dela. A mesma luz, o mesmo
        trilho, a relacao invertida -- e por isso a versao do duo e impossivel
        sozinho: o ser em espera perde o chao no instante da troca."""
        index = _level(simulation, "27_sem_rocha")
        state = simulation.state
        lane = range(6, 22)

        state.duo = False
        simulation.runtime.load(index)
        advance(simulation, input_provider, frames=40)
        solo_floor = sum(1 for c in lane if simulation.umbra_grid.cells[13, c])

        state.duo = True
        simulation.runtime.load(index)
        advance(simulation, input_provider, frames=40)
        duo_floor = sum(1 for c in lane if simulation.umbra_grid.cells[13, c])

        assert solo_floor >= 10, "no solo quase toda a pista e dela, menos o buraco"
        assert duo_floor <= 5, "no duo so a janela sob a lanterna e dela"


class TestVariantFileFormat:
    def test_uma_celula_fora_da_grade_e_recusada(self, tmp_path):
        """Falha alto no carregamento. Uma coordenada errada aqui nao daria
        erro em runtime -- so uma fase diferente da desenhada."""
        (tmp_path / "01.json").write_text(json.dumps({
            "id": "quebrada", "name": "q", "hint": "h", "chapter": 1,
            "duo": {"note": "n", "cells": [[99, 0, "#"]]},
            "rows": ["...", "..."],
        }), encoding="utf-8")
        with pytest.raises(LevelCatalogError, match="fora da grade"):
            LevelCatalog.load_from_directory(tmp_path)

    def test_uma_celula_malformada_e_recusada(self, tmp_path):
        (tmp_path / "01.json").write_text(json.dumps({
            "id": "quebrada", "name": "q", "hint": "h", "chapter": 1,
            "duo": {"cells": [[0, 0, "##"]]},
            "rows": ["...", "..."],
        }), encoding="utf-8")
        with pytest.raises(LevelCatalogError, match="caractere"):
            LevelCatalog.load_from_directory(tmp_path)

    def test_uma_fase_sem_duo_continua_valendo(self, simulation):
        """A grande maioria das fases e a mesma nos dois modos, e tem de
        continuar sendo: um jogo em que toda fase muda de modo obrigaria a
        aprender tudo duas vezes."""
        catalog = simulation.catalog
        without = [catalog.at(i) for i in range(catalog.count)
                   if not catalog.at(i).has_duo_variant]
        assert len(without) > len(_with_variants(simulation)), (
            "a variante e a excecao, nao a regra"
        )
        for level in without:
            assert level.rows_for(duo=True) == level.rows
