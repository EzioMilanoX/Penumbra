"""
O que sobrevive a fechar o jogo.

Ate aqui, `completed` e `shards` viviam so em memoria: trinta fases vencidas
e trinta fragmentos apanhados evaporavam ao fechar a janela. Num jogo de
trinta fases isso deixa de ser um detalhe e vira uma falha de projeto -- e a
parte mais cara nao e perder o progresso, e descobrir que se perdeu.

Tres decisoes, todas pela mesma razao (um arquivo de save nunca pode ser o
motivo de o jogo nao abrir):

* **Ler nunca levanta.** Arquivo ausente, JSON corrompido, campo com o tipo
  errado, save de uma versao com outro numero de fases -- tudo cai no
  progresso vazio, e o jogo comeca do zero em vez de morrer no boot.
* **Escrever e atomico.** Grava num `.tmp` ao lado e renomeia por cima; um
  desligamento no meio da escrita deixa o save ANTERIOR intacto, nunca meio
  arquivo.
* **Escrever falhado e silencioso.** Disco cheio ou pasta somente-leitura
  custam o progresso daquela sessao, e nao a sessao.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Optional, Set

_SCHEMA = 1
_FILE_NAME = "progress.json"


def default_path() -> Path:
    """O lugar do save, por plataforma.

    Nao fica ao lado do codigo de proposito: o repositorio e clonavel e
    somente-leitura em muitas maquinas, e um save dentro dele apareceria no
    `git status` a cada fase vencida.
    """
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "Penumbra" / _FILE_NAME
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "Penumbra" / _FILE_NAME


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
        """Le o save, ou fica no vazio. Nunca levanta."""
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return self
        if not isinstance(raw, dict):
            return self

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
        temporary = self._path.with_suffix(".tmp")
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            os.replace(temporary, self._path)
            return True
        except OSError:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            return False


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
