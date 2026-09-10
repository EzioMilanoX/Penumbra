"""
O conteudo data-driven falha alto, cedo e explicando -- ou nao serve.

Um jogo cujas regras vivem em JSON troca "erro de compilacao" por "fase
silenciosamente insolvel". Estes testes existem pra que cada arquivo de
dados malformado produza uma excecao com um motivo legivel na composicao,
antes do primeiro frame, e nunca um jogo que abre e nao pode ser terminado.
"""
from __future__ import annotations

import json

import pytest

from penumbra.levels import LevelCatalog, LevelCatalogError
from penumbra.terrain import Terrain, TerrainDefinitionError
from penumbra.tuning import DualityTuning, TuningDefinitionError

from tests.conftest import DIFFICULTY_PATH, GRID_COLS, GRID_ROWS, make_rows


def _write_difficulty(tmp_path, **overrides):
    raw = json.loads(DIFFICULTY_PATH.read_text(encoding="utf-8"))
    for section, values in overrides.items():
        raw[section] = {**raw[section], **values}
    path = tmp_path / "difficulty.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return str(path)


class TestTuning:
    def test_o_arquivo_do_jogo_carrega(self):
        tuning = DualityTuning.from_json(str(DIFFICULTY_PATH))
        assert tuning.name == "basic"
        assert tuning.world.grid_cols > 0
        assert tuning.light.decay_per_cell == pytest.approx(1.0 / tuning.light.falloff_radius_cells)

    def test_faixas_de_luz_fora_de_ordem_sao_recusadas(self, tmp_path):
        """A unica invariante do jogo que um arquivo de dados pode quebrar
        sem causar nenhuma excecao em runtime: sem penumbra entre os dois
        limiares, toda celula mata um dos dois seres."""
        path = _write_difficulty(tmp_path, light={"extinguish_below": 0.8})
        with pytest.raises(TuningDefinitionError, match="penumbra intermediaria"):
            DualityTuning.from_json(path)

    def test_hitbox_maior_que_meia_celula_e_recusada(self, tmp_path):
        """`TileCollisionSystem` v1 assume que uma AABB nunca cobre mais de
        2 colunas/2 linhas. Violar isso da resultado ERRADO, nao crash."""
        path = _write_difficulty(tmp_path, umbra={"half_width": 999.0})
        with pytest.raises(TuningDefinitionError, match="metade do cell_size"):
            DualityTuning.from_json(path)

    def test_salto_para_baixo_e_recusado(self, tmp_path):
        path = _write_difficulty(tmp_path, lumen={"jump_velocity_y": 400.0})
        with pytest.raises(TuningDefinitionError, match="negativo"):
            DualityTuning.from_json(path)

    def test_secao_ausente_e_recusada(self, tmp_path):
        raw = json.loads(DIFFICULTY_PATH.read_text(encoding="utf-8"))
        del raw["light"]
        path = tmp_path / "difficulty.json"
        path.write_text(json.dumps(raw), encoding="utf-8")
        with pytest.raises(TuningDefinitionError, match="light"):
            DualityTuning.from_json(str(path))


class TestTerrain:
    @pytest.fixture
    def terrain(self):
        return Terrain(cols=GRID_COLS, rows=GRID_ROWS, cell_size=32.0)

    _VALID = {14: "..A.....B.........X....Y..", 15: "#" * GRID_COLS}

    def test_uma_fase_valida_carrega(self, terrain):
        terrain.load_rows(make_rows(self._VALID))
        assert terrain.lumen_spawn_cell == (2, 14)
        assert terrain.umbra_spawn_cell == (8, 14)
        assert terrain.lumen_goal_cell == (18, 14)
        assert terrain.umbra_goal_cell == (23, 14)
        assert not terrain.has_door

    def test_recarregar_no_lugar_nao_deixa_residuo_da_fase_anterior(self, terrain):
        """Trocar de fase reescreve as mascaras em vez de recriar entidades
        -- se uma mascara nao fosse zerada, a fase nova herdaria terreno
        invisivel da anterior."""
        terrain.load_rows(make_rows({**self._VALID, 10: "~~~~~~~~~~"}))
        assert terrain.ether.any()

        terrain.load_rows(make_rows(self._VALID))

        assert not terrain.ether.any()
        assert not terrain.door.any()
        assert terrain.lamp.max() == 0.0

    def test_numero_de_linhas_errado_e_recusado(self, terrain):
        with pytest.raises(TerrainDefinitionError, match="linhas"):
            terrain.load_rows(("." * GRID_COLS,) * (GRID_ROWS - 1))

    def test_numero_de_colunas_errado_e_recusado(self, terrain):
        rows = list(make_rows(self._VALID))
        rows[5] = "." * (GRID_COLS - 1)
        with pytest.raises(TerrainDefinitionError, match="colunas"):
            terrain.load_rows(tuple(rows))

    def test_caractere_desconhecido_e_recusado(self, terrain):
        with pytest.raises(TerrainDefinitionError, match="desconhecido"):
            terrain.load_rows(make_rows({**self._VALID, 5: "...Z..."}))

    def test_marcador_duplicado_e_recusado(self, terrain):
        with pytest.raises(TerrainDefinitionError, match="mais de uma vez"):
            terrain.load_rows(make_rows({**self._VALID, 5: "...A..."}))

    def test_marcador_ausente_e_recusado(self, terrain):
        with pytest.raises(TerrainDefinitionError, match="marcador obrigatorio"):
            terrain.load_rows(make_rows({14: "..A.....B.........X"}))

    def test_ultima_linha_nao_vazia_e_recusada(self, terrain):
        """A ultima linha e o abismo. Sem ela ninguem cai de verdade --
        `Grid2D` trata fora-dos-limites como solido, entao o ser que
        perdesse o chao simplesmente pousaria na borda de baixo."""
        rows = list(make_rows(self._VALID))
        rows[-1] = "#" * GRID_COLS
        with pytest.raises(TerrainDefinitionError, match="abismo"):
            terrain.load_rows(tuple(rows))

    def test_porta_sem_zonas_e_recusada(self, terrain):
        with pytest.raises(TerrainDefinitionError, match="zona de luz"):
            terrain.load_rows(make_rows({**self._VALID, 10: "....DD...."}))

    def test_zonas_sem_porta_sao_recusadas(self, terrain):
        with pytest.raises(TerrainDefinitionError, match="sem nenhuma celula de porta"):
            terrain.load_rows(make_rows({**self._VALID, 10: "....L....S...."}))


class TestLevelCatalog:
    def test_as_quatro_fases_do_jogo_carregam_e_sao_validas(self):
        """`validate_all` parseia TODAS as fases contra o `Terrain` real na
        composicao, nao na transicao: descobrir que a fase 4 esta quebrada
        depois de o jogador resolver as tres primeiras seria a pior hora
        possivel."""
        from penumbra.composition import LEVELS_DIR

        catalog = LevelCatalog.load_from_directory(LEVELS_DIR)
        assert catalog.count == 4
        catalog.validate_all(Terrain(cols=GRID_COLS, rows=GRID_ROWS, cell_size=32.0))
        for index in range(catalog.count):
            level = catalog.at(index)
            assert level.name and level.hint, "toda fase precisa de nome e de uma dica"

    def test_diretorio_vazio_e_recusado(self, tmp_path):
        with pytest.raises(LevelCatalogError, match="nenhum arquivo de fase"):
            LevelCatalog.load_from_directory(tmp_path)

    def test_campo_obrigatorio_ausente_e_recusado(self, tmp_path):
        (tmp_path / "01.json").write_text(json.dumps({"id": "x", "name": "x"}), encoding="utf-8")
        with pytest.raises(LevelCatalogError, match="'hint'"):
            LevelCatalog.load_from_directory(tmp_path)

    def test_fase_invalida_e_apontada_pelo_id(self, tmp_path):
        (tmp_path / "01.json").write_text(
            json.dumps({"id": "quebrada", "name": "q", "hint": "h", "rows": ["."]}),
            encoding="utf-8",
        )
        catalog = LevelCatalog.load_from_directory(tmp_path)
        with pytest.raises(LevelCatalogError, match="quebrada"):
            catalog.validate_all(Terrain(cols=GRID_COLS, rows=GRID_ROWS, cell_size=32.0))
