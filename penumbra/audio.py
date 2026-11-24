"""
A voz do jogo -- sintetizada, sem um unico arquivo de som.

Penumbra foi mudo por trinta fases, e a falta nao era estetica: o **medidor
de perigo e visual**, e ele sobe justamente quando a sua atencao esta no
outro ser. Olhar para a Umbra atravessando custava nao ver a Lumen se
apagando. Um aviso sonoro resolve isso sem ocupar um pixel da tela.

Tudo aqui sai de `IAudioEngine.register_tone` (`square | noise | sweep |
zap`), que sintetiza na composicao -- o jogo continua sem pasta de assets, e
continua rodando headless, porque nada disto e construido em
`build_simulation`.

A paleta sonora obedece a mesma lei da paleta visual:

* **Lumen** fala agudo e limpo; **Umbra**, grave e aspero. Saber QUEM esta
  em perigo sem olhar e metade do problema que este modulo existe pra
  resolver.
* **O dourado tem voz propria** -- um `sweep` medio, reservado ao que exige
  os dois (porta, eclipse, fragmento, altar). No jogo, dourado significa
  "isto pede voces dois"; aqui tambem.
"""
from __future__ import annotations

from pathlib import Path

from ouroboros.core.systems.base_system import ISystem
from ouroboros.core.world import World

from penumbra.state import LUMEN, OUTCOME_COMPLETE, OUTCOME_FAILED, UMBRA, DualityState
from penumbra.terrain import Terrain

# --- vozes dos dois seres ---
PERIL_LUMEN = "peril_lumen"
PERIL_UMBRA = "peril_umbra"
ABILITY_ON = "ability_on"
ABILITY_OFF = "ability_off"

# --- dourado: o que exige os dois ---
SHARD = "shard"
DOOR = "door"
ALTAR = "altar"
ECLIPSE = "eclipse"

# --- o mundo mexendo sozinho, ou cedendo ---
CRUST = "crust"
LEVER = "lever"
BEACON = "beacon"

# --- fim de fase ---
COMPLETE = "complete"
FAIL = "fail"

# --- o segredo ---
ECHO = "echo"

# --- menu ---
MENU_MOVE = "menu_move"
MENU_PICK = "menu_pick"

_TONES = (
    # id,          kind,     freq,  duracao
    (PERIL_LUMEN, "square",  1180.0, 0.05),
    (PERIL_UMBRA, "square",   240.0, 0.07),
    (ABILITY_ON,  "sweep",    520.0, 0.10),
    (ABILITY_OFF, "square",   300.0, 0.06),
    (SHARD,       "sweep",    920.0, 0.20),
    (DOOR,        "sweep",    430.0, 0.28),
    (ALTAR,       "sweep",    660.0, 0.34),
    (ECLIPSE,     "noise",    180.0, 0.32),
    (CRUST,       "noise",    140.0, 0.22),
    (LEVER,       "zap",      380.0, 0.14),
    (BEACON,      "square",   560.0, 0.06),
    (COMPLETE,    "sweep",    700.0, 0.42),
    (FAIL,        "sweep",    200.0, 0.38),
    (ECHO,        "sweep",    540.0, 0.60),
    (MENU_MOVE,   "square",   640.0, 0.03),
    (MENU_PICK,   "square",   880.0, 0.07),
)

_PERIL_FLOOR = 0.18
"""Abaixo disto o aviso nao toca. Um bipe que comecasse no primeiro frame de
contato com a polaridade errada soaria o tempo todo -- atravessar uma nesga
correndo e uma decisao valida do jogo, nao um erro."""

_PERIL_SLOW = 0.46
_PERIL_FAST = 0.085
"""Intervalo entre bipes, do primeiro aviso ate a morte iminente. O que o
jogador le nao e o tom, e a ACELERACAO: um intervalo constante viraria ruido
de fundo e ele pararia de ouvir em duas fases."""


class PenumbraAudio:
    """
    Registra os tons e guarda o volume -- nada de estado de jogo.

    Existe separado do sistema pra que o menu (que roda com o mundo parado,
    fora de qualquer `world.step()`) possa tocar os proprios sons pelo mesmo
    caminho.
    """

    def __init__(self, engine, enabled: bool = True) -> None:
        self._engine = engine
        self.has_engine = engine is not None
        """Sem motor nao ha o que ligar. A opcao de som do menu alterna
        `enabled`, e sem isto ela poderia 'ligar' o silencio de um build
        headless e mentir pro jogador."""
        self.enabled = bool(enabled and self.has_engine)
        self.volume = 0.7
        if self._engine is None:
            return
        for sound_id, kind, freq, duration in _TONES:
            self._engine.register_tone(sound_id, kind=kind, freq=freq, duration=duration)

    def play(self, sound_id: str, volume: float = 1.0) -> None:
        if not self.enabled:
            return
        self._engine.play_one_shot(sound_id, volume=max(0.0, min(1.0, volume * self.volume)))


MUSIC_FILES = {1: "capitulo_1.wav", 2: "capitulo_2.wav", 3: "capitulo_3.wav"}
"""Capitulo -> faixa em `data/music/`. Os arquivos saem de
`tools/generate_music.py`; nenhum e de terceiros."""


class PenumbraMusic:
    """
    O fundo: uma faixa por capitulo, em laco.

    O jogo tinha voz e nao tinha fundo -- `load_track`/`play_track` existiam na
    engine e ninguem chamava. A faixa segue o CAPITULO e nao a fase: trocar de
    musica a cada fase de 20 s seria um corte por minuto, e o que muda de um
    capitulo para o outro e justamente o que ele pede de quem joga.

    Como o resto do audio, so existe em `build_game`: removida, o jogo fica
    identico e sem fundo. Faixa ausente no disco vira silencio, nunca erro --
    musica nao pode ser o motivo de o jogo nao abrir.
    """

    def __init__(self, engine, directory) -> None:
        self._engine = engine
        self.current: int | None = None
        self.available: set[int] = set()
        self.enabled = True
        self.volume = 0.5
        if engine is None:
            return
        for chapter, name in MUSIC_FILES.items():
            path = Path(directory) / name
            if path.is_file():
                engine.load_track(self._track_id(chapter), str(path))
                self.available.add(chapter)

    @staticmethod
    def _track_id(chapter: int) -> str:
        return f"penumbra_capitulo_{chapter}"

    def apply(self, enabled: bool, volume: float) -> None:
        """Som desligado cala tambem a musica; o volume dela e proprio."""
        self.enabled = bool(enabled)
        self.volume = max(0.0, min(1.0, float(volume)))
        if self._engine is not None:
            self._engine.set_track_volume(self.volume if self.enabled else 0.0)

    def play_chapter(self, chapter: int) -> None:
        """Toca a faixa do capitulo -- e nao recomeca a que ja esta tocando:
        passar de uma fase para a seguinte do mesmo capitulo nao e um corte."""
        if self._engine is None or chapter == self.current:
            return
        if chapter not in self.available:
            self.stop()
            return
        try:
            self._engine.play_track(self._track_id(chapter), loop=True)
        except Exception:   # mixer sem dispositivo, arquivo ilegivel: fica mudo
            self.current = None
            return
        self._engine.set_track_volume(self.volume if self.enabled else 0.0)
        self.current = chapter

    def stop(self) -> None:
        if self._engine is not None and self.current is not None:
            self._engine.stop_track(self._track_id(self.current))
        self.current = None


class AudioSystem(ISystem):
    """
    Traduz mudancas de estado em som, e roda por ULTIMO.

    Como o `PresentationSystem`, nao decide nada: removido, o jogo continua
    identico e fica mudo. E por isso que ele so e registrado em `build_game`
    -- `build_simulation` monta a mesma simulacao sem renderer, sem input
    concreto e sem audio, e e o que mantem os 174 testes headless.

    Quase tudo aqui dispara em BORDA (o valor mudou desde o frame passado),
    e nao em estado: um som por frame em que a porta esta aberta seria um
    zumbido de 60 Hz. A unica excecao e o aviso de perigo, que e periodico de
    proposito -- e a aceleracao dele que carrega a informacao.
    """

    def __init__(self, audio: PenumbraAudio, state: DualityState, terrain: Terrain) -> None:
        self._audio = audio
        self._state = state
        self._terrain = terrain
        self._peril_countdown = [0.0, 0.0]
        self._was_ability = [False, False]
        self._was_door_open = False
        self._was_beacon_on = True
        self._was_shard = False
        self._was_swapped = False
        self._was_spent = [False, False]
        self._was_outcome = 0
        self._crust_cells = -1
        self._eclipse_cells = -1

    def update(self, world: World, delta_time: float) -> None:
        del world
        self._advance_peril(delta_time)
        self._edges()

    # ------------------------------------------------------------------

    def _advance_peril(self, delta_time: float) -> None:
        """Um bipe periodico por ser, cada vez mais rapido conforme o medidor
        sobe. Os dois tons sao distantes de proposito: no duo os dois podem
        estar em perigo ao mesmo tempo, e a informacao que falta nunca e
        'alguem esta morrendo', e sim QUEM."""
        state = self._state
        for side, sound in ((LUMEN, PERIL_LUMEN), (UMBRA, PERIL_UMBRA)):
            ratio = float(state.peril[side])
            if ratio < _PERIL_FLOOR or state.outcome != 0:
                self._peril_countdown[side] = 0.0
                continue

            self._peril_countdown[side] -= delta_time
            if self._peril_countdown[side] > 0.0:
                continue

            urgency = (ratio - _PERIL_FLOOR) / (1.0 - _PERIL_FLOOR)
            self._peril_countdown[side] = _PERIL_SLOW + (_PERIL_FAST - _PERIL_SLOW) * urgency
            self._audio.play(sound, 0.35 + 0.5 * urgency)

    def _edges(self) -> None:
        state, terrain, audio = self._state, self._terrain, self._audio

        for side in (LUMEN, UMBRA):
            on = bool(state.ability_on[side])
            if on != self._was_ability[side]:
                audio.play(ABILITY_ON if on else ABILITY_OFF, 0.45)
                self._was_ability[side] = on

            spent = bool(state.form_spent[side])
            if spent and not self._was_spent[side]:
                audio.play(ALTAR, 0.9)
            self._was_spent[side] = spent

        if state.door_open != self._was_door_open:
            audio.play(DOOR, 0.8)
            self._was_door_open = state.door_open

        if terrain.has_beacon and state.beacon_on != self._was_beacon_on:
            # A virada do farol troca o dono do chao sem o jogador pedir, e e
            # a unica mudanca do jogo que pode acontecer com ele olhando pro
            # outro lado da tela.
            audio.play(BEACON, 0.55)
            self._was_beacon_on = state.beacon_on

        if state.shard_collected and not self._was_shard:
            audio.play(SHARD, 1.0)
        self._was_shard = state.shard_collected

        if state.polarity_swapped != self._was_swapped:
            audio.play(LEVER, 0.85)
            self._was_swapped = state.polarity_swapped

        # Crosta e eclipse nao tem sinalizador proprio no estado: o que muda
        # e a CONTAGEM de celulas no terreno. Contar e barato (mascaras de
        # 476 posicoes) e evita inventar dois campos que nenhuma regra le.
        crust = int(terrain.crust.sum())
        if self._crust_cells >= 0 and crust < self._crust_cells:
            audio.play(CRUST, 0.9)
        self._crust_cells = crust

        eclipse = int(terrain.eclipse.sum())
        if self._eclipse_cells > 0 and eclipse == 0:
            audio.play(ECLIPSE, 1.0)
        self._eclipse_cells = eclipse

        if state.outcome != self._was_outcome:
            if state.outcome == OUTCOME_COMPLETE:
                audio.play(COMPLETE, 1.0)
            elif state.outcome == OUTCOME_FAILED:
                audio.play(FAIL, 0.9)
            self._was_outcome = state.outcome
