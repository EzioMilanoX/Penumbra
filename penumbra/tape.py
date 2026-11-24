"""
Solo com eco (GAM-20, E.C.L.I.P.S.E.): voce e os dois, em tempos diferentes.

As fases de dupla nasceram para duas pessoas andando AO MESMO TEMPO, e o solo
so as fechava afrouxado (lampadas a mais, escolta encurtada). O eco resolve
sem afrouxar nada: primeiro voce joga a Lumen e o jogo grava os inputs dela em
tick fixo; depois rebobina, e voce joga a Umbra ao lado da gravacao -- o eco
-- que repete exatamente o que voce fez. A fase carregada e a do DUO.

Como a luz decide de quem e cada celula, o presente pode quebrar o passado: a
Umbra apaga a luz de que o eco precisava, rompe uma crosta, pisa numa
alavanca. Quando o eco morre ou sai do caminho gravado, isso e um
**paradoxo**: o mundo congela, o ponto da falha fica marcado, e da para
tentar o presente de novo ou regravar a Lumen a partir de pouco antes dali.

## Como, sem que o `World` saiba

O mesmo idioma do replay da engine (`ouroboros.bootstrap.replay`): nenhum
sistema ganhou um ramo de "eco". O modo liga `state.duo` -- os dois seres
andam juntos, a Lumen nas acoes sem prefixo e a Umbra nas `p2_*` -- e entrega
aos sistemas um `TapeInput` no lugar do teclado. E ele que decide de onde vem
cada metade:

* **gravando**: a Lumen le as teclas do jogador, tick a tick; a Umbra, nada
  (ela ainda nao chegou -- fica no spawn, intocavel pelo `OutcomeSystem`);
* **reproduzindo**: a Lumen le a fita (`ReplayInputProvider`); a Umbra le as
  teclas do jogador, as MESMAS A/D/ESPACO/S de sempre.

## Tick fixo

`GameLoop.run` passa o tempo real de cada quadro, e tempo real nao se repete:
com ele a mesma fita gerava outra trajetoria. Aqui o mundo anda em passos de
`TICK` (1/60 s) acumulados (`TapeSession.advance`), e as bordas de "apertou"
sao calculadas de um tick para o outro -- nunca do quadro -- para que gravar
e reproduzir vejam exatamente os mesmos apertos.

O paradoxo e detectado comparando a Lumen do presente com a trajetoria
gravada, tick a tick (`trail`). Sem interferencia as duas sao identicas bit a
bit; qualquer diferenca acima de `DIVERGENCE_PX` e o presente mexendo no
passado.
"""
from __future__ import annotations

import math

import numpy as np
from ouroboros.bootstrap.replay import (
    ActionMask,
    Replay,
    ReplayInputProvider,
    ReplayRecorder,
    world_state_hash,
)
from ouroboros.core.world import World
from ouroboros.interfaces.input_provider import IInputProvider

from penumbra.state import (
    LUMEN,
    OUTCOME_FAILED,
    OUTCOME_PLAYING,
    TAPE_OFF,
    TAPE_RECORD,
    TAPE_REPLAY,
    UMBRA,
    DualityState,
    LevelRuntime,
)

__all__ = [
    "DIVERGENCE_PX", "TAPE_ACTIONS", "TAPE_OFF", "TAPE_RECORD", "TAPE_REPLAY", "TAPE_SECONDS",
    "TAPE_TICKS", "TICK", "TapeInput", "TapeSession",
]

TAPE_ACTIONS = ("move_left", "move_right", "jump", "ability")
"""O que entra na fita. A ordem e o formato (um bit por acao): mudou a lista,
fitas antigas leem as teclas erradas -- e por isso a versao vai junto."""

TICK = 1.0 / 60.0
TAPE_SECONDS = 60.0
TAPE_TICKS = int(round(TAPE_SECONDS / TICK))
"""Ate um minuto de Lumen. Uma fase de dupla se atravessa em 10-20 s; o teto
e folga, e e tambem o que impede uma gravacao esquecida de crescer sem fim."""

MAX_TICKS_PER_FRAME = 4
"""Um quadro lento (janela arrastada, disco) nao vira uma rajada de cem ticks:
o acumulador descarta o excesso, como `MAX_DELTA_TIME_SECONDS` da engine."""

DIVERGENCE_PX = 12.0
"""Quanto o eco pode se afastar do caminho gravado antes de virar paradoxo.
Sem interferencia a distancia e ZERO (a simulacao e deterministica); 12 px e
pouco mais de um terco de celula -- longe o bastante para nao ser ruido e
perto o bastante para marcar a falha onde ela aconteceu, nao um segundo
depois, quando o eco ja caiu."""

REWIND_MARGIN_TICKS = 60
"""Regravar "a partir do paradoxo" volta um segundo antes dele: a causa quase
sempre vem pouco antes do efeito (a luz some e so depois o eco se apaga)."""

TAPE_VERSION = "penumbra-eco-1"


class _BitsInput(IInputProvider):
    """Um jogador feito de bits: segura o que `push` mandou, e "apertou" e a
    diferenca para o tick anterior. E o lado vivo do eco -- as teclas reais,
    amostradas uma vez por tick."""

    def __init__(self, mask: ActionMask) -> None:
        self._mask = mask
        self._current = 0
        self._previous = 0

    def push(self, bits: int) -> None:
        self._previous = self._current
        self._current = int(bits)

    def clear(self) -> None:
        self._current = self._previous = 0

    def load_bindings(self, bindings_path: str) -> None:
        pass

    def poll(self) -> None:
        pass

    def is_action_pressed(self, action_name: str) -> bool:
        b = self._mask.bit(action_name)
        return bool(self._current & b) and not bool(self._previous & b)

    def is_action_held(self, action_name: str) -> bool:
        return bool(self._current & self._mask.bit(action_name))

    def is_action_released(self, action_name: str) -> bool:
        b = self._mask.bit(action_name)
        return bool(self._previous & b) and not bool(self._current & b)

    def get_axis(self, axis_name: str) -> float:
        return 0.0

    def get_cursor_position(self):
        return (0.0, 0.0)

    def wants_quit(self) -> bool:
        return False

    def set_rumble(self, low_freq: float, high_freq: float, duration_sec: float) -> None:
        pass


class TapeInput(IInputProvider):
    """
    O `IInputProvider` que os sistemas de jogo recebem.

    Desligado, e transparente: tudo vai ao provider real, e o jogo e o de
    sempre. Ligado, as acoes sem prefixo (Lumen, no duo) vem de `lumen` e as
    `p2_*` (Umbra) vem de `umbra`, sem o prefixo -- os sistemas continuam
    lendo `move_left` e `p2_move_left` e nao sabem que uma das metades e uma
    fita. `restart`, `switch` e o resto ficam mudos: no eco, quem reinicia e
    a cena.
    """

    _P2 = "p2_"

    def __init__(self, real: IInputProvider) -> None:
        self.real = real
        self.engaged = False
        self.lumen: IInputProvider = real
        self.umbra: IInputProvider = real

    def engage(self, lumen: IInputProvider, umbra: IInputProvider) -> None:
        self.engaged = True
        self.lumen, self.umbra = lumen, umbra

    def release(self) -> None:
        self.engaged = False
        self.lumen = self.umbra = self.real

    def _route(self, action_name: str):
        if action_name.startswith(self._P2):
            return self.umbra, action_name[len(self._P2):]
        return self.lumen, action_name

    # -- IInputProvider -----------------------------------------------------
    def load_bindings(self, bindings_path: str) -> None:
        self.real.load_bindings(bindings_path)

    def poll(self) -> None:
        # Quem faz o poll do teclado e o `GameLoop`, no provider real. O eco
        # avanca por tick, em `TapeSession`, e nunca por aqui.
        if not self.engaged:
            self.real.poll()

    def is_action_pressed(self, action_name: str) -> bool:
        if not self.engaged:
            return self.real.is_action_pressed(action_name)
        source, name = self._route(action_name)
        return source.is_action_pressed(name)

    def is_action_held(self, action_name: str) -> bool:
        if not self.engaged:
            return self.real.is_action_held(action_name)
        source, name = self._route(action_name)
        return source.is_action_held(name)

    def is_action_released(self, action_name: str) -> bool:
        if not self.engaged:
            return self.real.is_action_released(action_name)
        source, name = self._route(action_name)
        return source.is_action_released(name)

    def get_axis(self, axis_name: str) -> float:
        return self.real.get_axis(axis_name) if not self.engaged else 0.0

    def get_cursor_position(self):
        return self.real.get_cursor_position()

    def wants_quit(self) -> bool:
        return self.real.wants_quit()

    def connected_pads(self) -> int:
        return self.real.connected_pads()

    def set_rumble(self, low_freq: float, high_freq: float, duration_sec: float) -> None:
        self.real.set_rumble(low_freq, high_freq, duration_sec)


class TapeSession:
    """
    O laco gravar -> rebobinar -> jogar ao lado do eco, numa fase.

    Nao e um `ISystem`: como trocar de fase, rebobinar e coisa de ENTRE dois
    `world.step()` (reposiciona os seres pelo `LevelRuntime`). A cena chama
    `advance(real_input, dt)` a cada quadro, e o resto acontece aqui.

    Estado que a tela precisa ler mora no `DualityState` (`tape_phase`,
    `tape_paradox`, `tape_paradox_x/y`), porque a apresentacao e o HUD ja
    leem o estado e nao deveriam conhecer a sessao.
    """

    def __init__(
        self,
        world: World,
        state: DualityState,
        runtime: LevelRuntime,
        tape_input: TapeInput,
        *,
        capacity: int = TAPE_TICKS,
        hash_pools: tuple[str, ...] = (),
        hash_every: int = 30,
        grids=(),
    ) -> None:
        self._grids = tuple(grids)
        """As duas grades de colisao. Sao reescritas pelo `LightFieldSystem` a
        cada frame -- mas o PRIMEIRO tick depois de um reset colide contra a
        grade do frame anterior, que pode ser de outra fase. Gravar vindo do
        menu e reproduzir vindo da gravacao partiriam de chaos diferentes, e o
        eco acusaria um paradoxo no tick zero. Zeradas nos dois comecos, os
        dois partem do mesmo lugar."""
        self._world = world
        self._state = state
        self._runtime = runtime
        self.input = tape_input
        self.mask = ActionMask(TAPE_ACTIONS)
        self.capacity = int(capacity)
        self._hash_pools = tuple(hash_pools)
        self._recorder = ReplayRecorder(
            TAPE_ACTIONS, capacity=self.capacity,
            hash_every=hash_every if self._hash_pools else 0,
            game_version=TAPE_VERSION,
        )
        self._lumen_live = _BitsInput(self.mask)
        self._umbra_live = _BitsInput(self.mask)
        self._umbra_idle = _BitsInput(self.mask)
        self._transform_pool = world.get_pool("transform")
        self.trail = np.zeros((self.capacity, 2), dtype=np.float32)
        """Onde a Lumen estava depois de cada tick gravado. E contra isto que
        o eco e conferido -- e o que o HUD desenha como o caminho do passado."""
        self.trail_count = 0
        self.tape: Replay | None = None
        self._playback: ReplayInputProvider | None = None
        self._prefix: Replay | None = None
        self._accumulator = 0.0
        self.paradox_tick = -1
        self.desync_frame: int | None = None
        """Primeiro tick em que o hash do mundo (quando pedido em
        `hash_pools`) difere do gravado. So os testes ligam isto: no jogo a
        Umbra anda, e o mundo inteiro PRECISA diferir."""

    # ------------------------------------------------------------------
    # estado
    # ------------------------------------------------------------------

    @property
    def phase(self) -> int:
        return int(self._state.tape_phase)

    @property
    def active(self) -> bool:
        return self.phase != TAPE_OFF

    @property
    def recorded_ticks(self) -> int:
        return self._recorder.frame_count

    @property
    def recorded_seconds(self) -> float:
        return self._recorder.frame_count * TICK

    @property
    def replay_tick(self) -> int:
        """O tick do eco que acabou de rodar (-1 antes do primeiro)."""
        return self._playback.frame if self._playback is not None else -1

    @property
    def prefix_ticks(self) -> int:
        """Ticks de um passado ja gravado que a regravacao repete antes de
        devolver a Lumen ao jogador."""
        return self._prefix.frame_count if self._prefix is not None else 0

    @property
    def replaying_prefix(self) -> bool:
        return self.phase == TAPE_RECORD and self.recorded_ticks < self.prefix_ticks

    # ------------------------------------------------------------------
    # transicoes
    # ------------------------------------------------------------------

    def start(self, level_index: int | None = None) -> None:
        """Liga o modo e comeca a gravar a Lumen do zero.

        Com `level_index`, carrega essa fase na versao do DUO -- a que foi
        desenhada para dois andando juntos, sem as lampadas que afrouxam o
        solo. Sem ele, fica com o ASCII ja carregado (testes e sondas)."""
        self._state.duo = True
        if level_index is not None:
            self._runtime.load(level_index)
        self._prefix = None
        self.tape = None
        self.trail_count = 0
        self._begin_record()

    def stop(self) -> None:
        """Desliga o modo. O teclado volta inteiro para os sistemas."""
        self.input.release()
        self._state.tape_phase = TAPE_OFF
        self._clear_paradox()
        self._playback = None
        self._prefix = None

    def rewind(self) -> None:
        """Fim da gravacao: a fita fica pronta e a fase volta ao comeco, agora
        com a Umbra nas maos do jogador."""
        if self.phase != TAPE_RECORD or self.replaying_prefix:
            return
        self.tape = self._recorder.replay()
        self.trail_count = self.tape.frame_count
        self._begin_replay()

    def retry_present(self) -> None:
        """Mesma fita, presente do zero."""
        if self.tape is not None:
            self._begin_replay()

    def rerecord(self) -> None:
        """Joga a fita fora e grava a Lumen de novo, do comeco."""
        self._prefix = None
        self.trail_count = 0
        self._begin_record()

    def rerecord_from_paradox(self) -> None:
        """Regrava so o trecho do passado a partir de pouco antes do
        paradoxo: a fita antiga se repete ate ali (com a Umbra parada, como
        foi gravada) e entao a Lumen volta para o jogador."""
        if self.tape is None:
            self.rerecord()
            return
        cut = max(0, min(self.tape.frame_count, self.paradox_tick - REWIND_MARGIN_TICKS))
        self._prefix = Replay(TAPE_ACTIONS, self.tape.bits[:cut], self.tape.dts[:cut],
                              game_version=TAPE_VERSION) if cut > 0 else None
        self._begin_record()

    def restart(self) -> None:
        """`R`: recomeca o passo corrente. Gravando, a gravacao (mantendo o
        trecho repetido, se houver); reproduzindo, o presente."""
        if self.phase == TAPE_RECORD:
            self._begin_record()
        elif self.phase == TAPE_REPLAY:
            self._begin_replay()

    def _begin_record(self) -> None:
        self._reset_world()
        self._clear_paradox()
        self._state.tape_phase = TAPE_RECORD
        self._recorder.start(seed=0, meta={"level": self._state.level_index})
        self._lumen_live.clear()
        self._umbra_idle.clear()
        self.input.engage(self._lumen_live, self._umbra_idle)
        self._playback = None
        self._accumulator = 0.0
        self.desync_frame = None

    def _begin_replay(self) -> None:
        self._reset_world()
        self._clear_paradox()
        self._state.tape_phase = TAPE_REPLAY
        # O anel dourado de "quem voce comanda" passa para a Umbra: a Lumen
        # agora e o eco, e ninguem a comanda.
        self._state.active = UMBRA
        self._playback = ReplayInputProvider(self.tape)
        self._umbra_live.clear()
        self.input.engage(self._playback, self._umbra_live)
        self._accumulator = 0.0
        self.desync_frame = None

    def _reset_world(self) -> None:
        """O comeco comum de gravar e de reproduzir: a fase do zero, e as
        grades de colisao sem memoria do frame anterior."""
        self._runtime.reset()
        for grid in self._grids:
            grid.cells[...] = 0

    def _clear_paradox(self) -> None:
        state = self._state
        state.tape_paradox = False
        state.tape_paradox_x = state.tape_paradox_y = 0.0
        self.paradox_tick = -1

    # ------------------------------------------------------------------
    # simulacao
    # ------------------------------------------------------------------

    def advance(self, real_input: IInputProvider, delta_time: float) -> int:
        """Um quadro de tempo real -> zero ou mais ticks fixos. O jogador e
        amostrado uma vez por tick (o mesmo estado de teclas para todos os
        ticks do quadro: as bordas saem de tick para tick). Devolve quantos
        ticks rodaram."""
        self._accumulator += delta_time
        ticks = 0
        while self._accumulator >= TICK - 1e-9 and ticks < MAX_TICKS_PER_FRAME:
            self._accumulator -= TICK
            if self._state.outcome != OUTCOME_PLAYING:
                break
            self.tick(self.mask.encode(real_input))
            ticks += 1
            if not self.active:
                break
        if ticks >= MAX_TICKS_PER_FRAME:
            self._accumulator = 0.0
        return ticks

    def tick(self, player_bits: int) -> None:
        """Um passo fixo do mundo, com o jogador segurando `player_bits`."""
        if self._state.outcome != OUTCOME_PLAYING:
            return
        if self.phase == TAPE_RECORD:
            self._tick_record(player_bits)
        elif self.phase == TAPE_REPLAY:
            self._tick_replay(player_bits)

    def _tick_record(self, player_bits: int) -> None:
        index = self._recorder.frame_count
        if self._prefix is not None and index < self._prefix.frame_count:
            bits = int(self._prefix.bits[index])     # o passado se repete
        else:
            bits = int(player_bits)
        self._lumen_live.push(bits)
        self._umbra_idle.push(0)
        self._recorder.record_bits(bits, TICK)
        self._world.step(TICK)
        self.trail[index] = self._lumen_position()
        if self._recorder.wants_hash():
            self._recorder.record_hash(world_state_hash(self._world, self._hash_pools))
        if self._recorder.frame_count >= self.capacity and self._state.outcome == OUTCOME_PLAYING:
            self.rewind()

    def _tick_replay(self, player_bits: int) -> None:
        playback = self._playback
        playback.poll()
        self._umbra_live.push(int(player_bits))
        self._world.step(TICK)
        index = playback.frame
        if playback.wants_hash() and not playback.verify(world_state_hash(self._world, self._hash_pools)):
            if self.desync_frame is None:
                self.desync_frame = playback.desync_frame
        self._check_paradox(index)

    def _check_paradox(self, index: int) -> None:
        state = self._state
        x, y = self._lumen_position()
        terrain = self._runtime.terrain
        void_top = (terrain.rows - 1) * terrain.cell_size
        died = float(state.peril[LUMEN]) >= 1.0 or y >= void_top
        diverged = False
        if index < self.trail_count:
            gx, gy = float(self.trail[index, 0]), float(self.trail[index, 1])
            diverged = math.hypot(x - gx, y - gy) > DIVERGENCE_PX
        if not (died or diverged):
            return
        if state.outcome == OUTCOME_FAILED and not died:
            return   # a Umbra morreu antes; e o presente que falhou, nao o passado
        state.tape_paradox = True
        state.tape_paradox_x, state.tape_paradox_y = x, y
        self.paradox_tick = index
        state.outcome = OUTCOME_FAILED
        if died and index >= self.trail_count:
            # Depois do fim da fita a Lumen so espera, e pode morrer esperando
            # (no escuro, por exemplo). Nao da pra saber se foi o presente; o
            # remedio e o mesmo -- regravar desde pouco antes dali.
            state.message = "Paradoxo: a fita acabou e a Lumen não resistiu à espera."
        elif died:
            state.message = "Paradoxo: o presente apagou a Lumen do passado."
        else:
            state.message = "Paradoxo: o eco da Lumen saiu do caminho gravado."

    def _lumen_position(self) -> tuple[float, float]:
        pool = self._transform_pool
        row = pool.dense_row_of(int(self._state.entity_index[LUMEN]))
        view = pool.active_view()
        return float(view["position_x"][row]), float(view["position_y"][row])
