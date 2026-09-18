"""
O jogo nao pode depender do diretorio atual.

Penumbra so rodava a partir da raiz do projeto. Os caminhos do `config.json`
sao relativos, e Python os resolve contra o DIRETORIO ATUAL -- entao abrir o
jogo de qualquer outro lugar morria no boot, com um erro sobre um arquivo que
esta ali do lado.

Isso nunca incomodou porque o unico jeito de jogar era `python -m
penumbra.main` da raiz. Um executavel nao tem raiz de projeto nenhuma, e o
diretorio atual passa a ser onde quer que a pessoa tenha clicado -- entao a
mesma falha que era um detalhe vira a unica coisa que acontece.

Este arquivo existe pra que a correcao nao se perca: os testes rodam da raiz,
onde o defeito e invisivel.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from ouroboros.bootstrap.engine_config import EngineConfig

from penumbra.composition import ARCHETYPES_DIR, LEVELS_DIR, build_simulation
from penumbra.paths import is_frozen, resolve, resource, resource_root

_CONFIG = resource("penumbra", "config.json")


class TestResourceRoot:
    def test_a_raiz_contem_os_dados(self):
        root = resource_root()
        assert (root / "data" / "levels").is_dir()
        assert (root / "data" / "difficulties").is_dir()
        assert (root / "penumbra" / "config.json").is_file()

    def test_a_raiz_nao_depende_do_diretorio_atual(self, tmp_path, monkeypatch):
        before = resource_root()
        monkeypatch.chdir(tmp_path)
        assert resource_root() == before

    def test_no_repositorio_nao_esta_congelado(self):
        assert not is_frozen()


class TestResolve:
    def test_um_relativo_vira_absoluto_sob_a_raiz(self):
        resolved = Path(resolve("data/levels"))
        assert resolved.is_absolute()
        assert resolved == resource_root() / "data" / "levels"

    def test_um_absoluto_passa_intacto(self, tmp_path):
        """Quem apontou pra fora do bundle sabia o que estava fazendo -- uma
        dificuldade de teste, por exemplo."""
        target = tmp_path / "outro.json"
        assert Path(resolve(str(target))) == target

    def test_resolve_nao_muda_com_o_diretorio_atual(self, tmp_path, monkeypatch):
        before = resolve("data/levels")
        monkeypatch.chdir(tmp_path)
        assert resolve("data/levels") == before


class TestTheGameLoadsFromAnywhere:
    def test_as_pastas_de_dados_sao_absolutas(self):
        """`ARCHETYPES_DIR` e `LEVELS_DIR` sao constantes de modulo: se
        fossem relativas, o import ja nasceria preso ao diretorio de quem
        importou."""
        assert Path(ARCHETYPES_DIR).is_absolute()
        assert Path(LEVELS_DIR).is_absolute()
        assert Path(LEVELS_DIR).is_dir()

    def test_a_simulacao_monta_de_outro_diretorio(self, tmp_path, monkeypatch):
        """A prova de ponta a ponta, e a que teria pego o defeito: montar o
        jogo inteiro com o diretorio atual em outro lugar."""
        monkeypatch.chdir(tmp_path)
        config = EngineConfig.from_json(str(_CONFIG))
        simulation = build_simulation(config)

        # Conta o que esta em disco, e nao um numero cravado: o teste e
        # sobre MONTAR de outro diretorio, e um numero aqui so faz a suite
        # cair toda vez que alguem acrescenta uma fase.
        from penumbra.paths import resource

        esperado = len(list(resource("data", "levels").glob("*.json")))
        assert simulation.catalog.count == esperado
        assert simulation.terrain.cols > 0

    def test_a_dificuldade_do_config_e_relativa_de_proposito(self):
        """O `config.json` continua com caminhos relativos -- eles sao dados,
        e um caminho absoluto ali seria a maquina de quem gravou o arquivo."""
        config = EngineConfig.from_json(str(_CONFIG))
        assert not Path(config.difficulty_path).is_absolute()
        assert not Path(config.input_bindings_path).is_absolute()
        assert Path(resolve(config.difficulty_path)).is_file()
        assert Path(resolve(config.input_bindings_path)).is_file()
