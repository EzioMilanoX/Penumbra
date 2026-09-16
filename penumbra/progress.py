"""
O que sobrevive a fechar o jogo.

Ate aqui, `completed` e `shards` viviam so em memoria: trinta fases vencidas
e trinta fragmentos apanhados evaporavam ao fechar a janela. Num jogo de
trinta fases isso deixa de ser um detalhe e vira uma falha de projeto -- e a
parte mais cara nao e perder o progresso, e descobrir que se perdeu.

O **mecanismo** -- ler sem nunca levantar, escrever de forma atomica, falhar
em silencio -- nao tem nada de Penumbra e vive em
`ouroboros.bootstrap.save_file`: todo produto da engine que guarde qualquer
coisa entre sessoes escreve o mesmo par de funcoes, e erra nos mesmos lugares,
porque os erros so aparecem em maquina de outra pessoa.

O que fica aqui e o **formato**, que e o que muda de jogo para jogo: quais
campos existem, que tipos tem, e o que fazer com um save gravado por uma
versao com outro numero de fases. A resposta de Penumbra a essa ultima e
`_flags`, que AJUSTA em vez de recusar -- acrescentar fases nao pode apagar o
que alguem ja fez.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Set

from ouroboros.bootstrap.save_file import SaveFile, default_save_path

_SCHEMA = 1
_FILE_NAME = "progress.json"


def default_path() -> Path:
    """`%APPDATA%/Penumbra/progress.json`, ou o equivalente XDG fora do
    Windows. Nunca ao lado do codigo: o repositorio e clonavel e
    somente-leitura em muitas maquinas."""
    return default_save_path("Penumbra", _FILE_NAME)


class Progress:
    """
    Progresso da sessao, e o unico objeto que sabe ler e gravar em disco.

    `level_count` fixa o tamanho das listas: um save gravado com um catalogo
    de outro tamanho e aceito e AJUSTADO (truncado ou completado com falso)
    em vez de recusado -- acrescentar fases a um jogo nao pode apagar o que o
    jogador ja fez.
    """

    def __init__(self, level_count: int, path: Optional[Path] = None) -> None:
        self._path = Path(path) if path is not None else default_path()
        self._file = SaveFile(self._path)
        self.level_count = int(level_count)
        self.completed: List[bool] = [False] * self.level_count
        self.shards: List[bool] = [False] * self.level_count
        self.achievements: Set[str] = set()
        self.ending_choice: Optional[str] = None
        self.duo = False
        # Ajustes. Moram no mesmo arquivo do progresso porque sao a mesma
        # pergunta pro jogador -- "como eu deixei isto da ultima vez?" -- e
        # dois arquivos dobrariam as chances de um deles nao abrir.
        self.volume = 0.7
        self.sound_on = True
        self.fullscreen = False

    @property
    def path(self) -> Path:
        return self._path

    # ------------------------------------------------------------------

    def load(self) -> "Progress":
        """Le o save, ou fica no vazio. `SaveFile.read` nunca levanta --
        arquivo ausente, JSON corrompido ou raiz que nao e objeto viram `{}`,
        e cada campo abaixo tem o proprio default."""
        raw = self._file.read()

        self.completed = _flags(raw.get("completed"), self.level_count)
        self.shards = _flags(raw.get("shards"), self.level_count)
        achievements = raw.get("achievements")
        if isinstance(achievements, list):
            self.achievements = {str(item) for item in achievements}
        choice = raw.get("ending_choice")
        self.ending_choice = str(choice) if isinstance(choice, str) else None
        self.duo = bool(raw.get("duo", False))
        self.volume = _ratio(raw.get("volume"), 0.7)
        self.sound_on = bool(raw.get("sound_on", True))
        self.fullscreen = bool(raw.get("fullscreen", False))
        return self

    def save(self) -> bool:
        """Grava de forma atomica. Devolve se conseguiu -- falhar custa o
        progresso da sessao, nunca a sessao."""
        payload = {
            "schema": _SCHEMA,
            "completed": [bool(done) for done in self.completed],
            "shards": [bool(got) for got in self.shards],
            "achievements": sorted(self.achievements),
            "ending_choice": self.ending_choice,
            "duo": bool(self.duo),
            "volume": float(self.volume),
            "sound_on": bool(self.sound_on),
            "fullscreen": bool(self.fullscreen),
        }
        return self._file.write(payload)


def _ratio(value, fallback: float) -> float:
    """Um 0..1 vindo do disco, ou o padrao. Um volume fora de faixa num save
    editado a mao nao pode virar audio estourado nem silencio misterioso."""
    try:
        return min(1.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return fallback


def _flags(value, count: int) -> List[bool]:
    """Lista de booleanos do tamanho do catalogo ATUAL, venha o que vier.

    Um save de uma versao com menos fases e completado com falso; um com
    mais, truncado. Recusar o save inteiro por causa do tamanho apagaria o
    progresso de quem so atualizou o jogo."""
    if not isinstance(value, list):
        return [False] * count
    flags = [bool(item) for item in value[:count]]
    flags.extend([False] * (count - len(flags)))
    return flags
