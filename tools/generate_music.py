"""
Gera a musica de fundo de Penumbra: uma faixa por capitulo, sintetizada.

    python -m tools.generate_music          # reescreve data/music/*.wav

Nada aqui vem de fora: nem amostra, nem melodia de ninguem. Cada nota e uma
soma de senoides com envelope, escrita por este arquivo -- o mesmo principio
dos efeitos (`IAudioEngine.register_tone`), so que longo o bastante para
virar fundo. E deterministico: rodar de novo produz os mesmos bytes, e um
teste confere que os WAVs do repositorio sao exatamente o que este gerador
produz (`tests/test_music_and_story.py`).

## As tres faixas

Cada capitulo tem a funcao dele, e a musica segue a funcao, nao um tema:

* **I · Aprender** -- la menor pentatonica, 72 bpm. Um arpejo de vidro, ralo,
  sobre quatro acordes que voltam sempre. Nada surpreende: o capitulo inteiro
  e uma coisa nova por vez, e a musica nao pode ser a segunda.
* **II · Misturar** -- re dorico, 84 bpm. Duas vozes que se respondem: uma
  aguda e limpa (a Lumen), outra grave e dedilhada (a Umbra). Nunca tocam a
  mesma nota ao mesmo tempo -- e o jogo, dito em musica.
* **III · Especiais** -- mi frigio, 66 bpm. Um drone que respira (a fonte
  incha e contrai) e o segundo grau menor, o fa, puxando contra o mi. O
  capitulo que quebra a propria regra soa sem chao.

## Por que fecha o laco sem emenda

A faixa toca em `loop`, e uma emenda audivel a cada 25 s seria pior que
silencio. Toda nota que passa do fim da faixa e somada de volta no comeco
(indice modulo o comprimento), e o eco tambem e circular (`np.roll`). O
ultimo sample, portanto, e continuo com o primeiro por construcao.

Mono, 16 bits, 22 050 Hz: os timbres sao senoides suaves, sem nada acima de
~6 kHz, e o dobro da taxa so dobraria o tamanho.
"""
from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SAMPLE_RATE = 22050
PEAK = 0.62
"""Pico depois de normalizar. A musica e FUNDO: os efeitos do jogo tocam por
cima dela, e o aviso de perigo precisa continuar sendo a coisa mais alta."""

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "music"


def midi(note: int) -> float:
    return 440.0 * 2.0 ** ((note - 69) / 12.0)


# ---------------------------------------------------------------------------
# timbres
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Timbre:
    harmonics: tuple[tuple[float, float], ...]
    """(multiplo da fundamental, amplitude relativa)."""
    attack: float
    decay_rate: float
    """Decaimento exponencial por segundo depois do ataque (0 = sustenta)."""
    release: float
    detune: float = 0.0
    """Uma segunda copia desafinada em `detune` Hz: o batimento lento que faz
    um pad parecer ar em vez de apito."""


GLASS = Timbre(((1.0, 1.0), (2.0, 0.18), (3.0, 0.22), (5.04, 0.05)), 0.006, 2.4, 0.25)
"""Sino de vidro: ataque seco, terceiro harmonico, decai sozinho."""
PLUCK = Timbre(((1.0, 1.0), (2.0, 0.45), (3.0, 0.2), (4.0, 0.08)), 0.004, 4.0, 0.12)
"""Corda grave dedilhada: a voz da Umbra no capitulo II."""
PAD = Timbre(((1.0, 1.0), (2.0, 0.32), (3.0, 0.12), (4.0, 0.05)), 0.9, 0.0, 1.4, detune=0.7)
"""O ar entre as notas: ataque lento, sustenta, solta devagar."""
BASS = Timbre(((1.0, 1.0), (2.0, 0.25)), 0.03, 0.9, 0.5)
DRONE = Timbre(((1.0, 1.0), (2.0, 0.5), (3.0, 0.18), (1.5, 0.12)), 2.0, 0.0, 2.0, detune=0.35)


class Track:
    """Um buffer circular de `seconds` segundos onde as notas sao somadas."""

    def __init__(self, bpm: float, bars: int, beats_per_bar: int = 4) -> None:
        self.beat = 60.0 / bpm
        self.length = int(round(bars * beats_per_bar * self.beat * SAMPLE_RATE))
        self.buffer = np.zeros(self.length, dtype=np.float64)

    def note(self, freq: float, start_beat: float, beats: float, amp: float, timbre: Timbre) -> None:
        start = int(round(start_beat * self.beat * SAMPLE_RATE))
        hold = beats * self.beat
        total = hold + timbre.release
        n = min(int(total * SAMPLE_RATE), self.length)
        t = np.arange(n, dtype=np.float64) / SAMPLE_RATE

        env = np.minimum(1.0, t / max(timbre.attack, 1e-4))
        if timbre.decay_rate > 0.0:
            env *= np.exp(-timbre.decay_rate * np.maximum(0.0, t - timbre.attack))
        tail = t > hold
        env[tail] *= np.maximum(0.0, 1.0 - (t[tail] - hold) / timbre.release)

        wave_ = np.zeros(n, dtype=np.float64)
        for multiple, weight in timbre.harmonics:
            wave_ += weight * np.sin(2.0 * np.pi * freq * multiple * t)
            if timbre.detune:
                wave_ += 0.6 * weight * np.sin(2.0 * np.pi * (freq * multiple + timbre.detune) * t)
        norm = sum(w for _, w in timbre.harmonics) * (1.6 if timbre.detune else 1.0)
        idx = (start + np.arange(n)) % self.length
        self.buffer[idx] += amp * env * wave_ / norm

    def chord(self, notes, start_beat, beats, amp, timbre) -> None:
        for note in notes:
            self.note(midi(note), start_beat, beats, amp, timbre)

    def echo(self, delays_beats=(0.75, 1.5), gains=(0.28, 0.12)) -> None:
        """Eco circular: o mesmo `np.roll` que fecha o laco fecha o eco."""
        dry = self.buffer.copy()
        for delay, gain in zip(delays_beats, gains):
            self.buffer += gain * np.roll(dry, int(round(delay * self.beat * SAMPLE_RATE)))

    def breathe(self, period_beats: float, depth: float) -> None:
        """Respiracao: o volume inteiro sobe e desce num periodo que divide a
        faixa, para que o fim encontre o comeco na mesma fase."""
        t = np.arange(self.length) / SAMPLE_RATE
        period = period_beats * self.beat
        self.buffer *= 1.0 - depth * 0.5 * (1.0 + np.cos(2.0 * np.pi * t / period))

    def pcm(self) -> np.ndarray:
        peak = float(np.max(np.abs(self.buffer))) or 1.0
        mixed = np.tanh(1.2 * self.buffer / peak) / np.tanh(1.2)
        return np.round(mixed * PEAK * 32767.0).astype("<i2")


# ---------------------------------------------------------------------------
# capitulos
# ---------------------------------------------------------------------------


def chapter_one() -> Track:
    """Aprender: o arpejo que nunca surpreende."""
    rng = np.random.default_rng(101)
    track = Track(bpm=72, bars=8)
    # Am(add9) - Fmaj7 - C(add9) - G6, dois compassos cada um
    chords = ((57, 60, 64, 71), (53, 57, 60, 64), (48, 55, 62, 64), (55, 59, 62, 64))
    roots = (45, 41, 48, 43)
    pentatonic = (69, 72, 74, 76, 79, 81, 84)
    for bar in range(8):
        chord = chords[(bar // 2) % 4]
        beat0 = bar * 4.0
        if bar % 2 == 0:
            track.chord(chord, beat0, 7.5, 0.16, PAD)
            track.note(midi(roots[(bar // 2) % 4]), beat0, 3.0, 0.42, BASS)
        else:
            track.note(midi(roots[(bar // 2) % 4]), beat0 + 2.0, 1.5, 0.30, BASS)
        # arpejo em colcheias, com pausas: sobe nos compassos pares, desce nos impares
        tones = sorted(n for n in pentatonic if any((n - c) % 12 == 0 for c in chord)) or list(pentatonic)
        order = tones if bar % 2 == 0 else tones[::-1]
        for step in range(8):
            if step in (3, 7) and bar % 4 != 3:
                continue
            note = order[step % len(order)]
            velocity = 0.30 + 0.06 * float(rng.random())
            track.note(midi(note), beat0 + step * 0.5, 0.45, velocity, GLASS)
    track.echo()
    return track


def chapter_two() -> Track:
    """Misturar: a Lumen pergunta, a Umbra responde, e nunca ao mesmo tempo."""
    rng = np.random.default_rng(202)
    track = Track(bpm=84, bars=8)
    # Dm9 - G13 - Em7 - Am7 (re dorico)
    chords = ((50, 57, 60, 64), (55, 59, 64, 65), (52, 55, 59, 62), (57, 60, 64, 67))
    lumen = ((74, 77, 79, 81), (79, 77, 76, 74), (76, 79, 81, 83), (81, 79, 76, 77))
    umbra = ((38, 45, 41, 43), (43, 47, 45, 40), (40, 47, 43, 45), (45, 40, 43, 50))
    for bar in range(8):
        beat0 = bar * 4.0
        chord_index = (bar // 2) % 4
        if bar % 2 == 0:
            track.chord(chords[chord_index], beat0, 7.6, 0.13, PAD)
            phrase = lumen[chord_index]
            for i, note in enumerate(phrase):          # pergunta, em cima
                track.note(midi(note), beat0 + i * 0.75, 0.6, 0.30 + 0.05 * float(rng.random()), GLASS)
        else:
            phrase = umbra[chord_index]
            for i, note in enumerate(phrase):          # resposta, embaixo
                track.note(midi(note), beat0 + 0.5 + i * 0.75, 0.7, 0.40 + 0.05 * float(rng.random()), PLUCK)
            track.note(midi(chords[chord_index][-1] + 12), beat0 + 3.5, 0.5, 0.18, GLASS)
    track.echo(delays_beats=(0.5, 1.0), gains=(0.22, 0.10))
    return track


def chapter_three() -> Track:
    """Especiais: sem chao. Um drone que respira e o fa contra o mi."""
    rng = np.random.default_rng(303)
    track = Track(bpm=66, bars=8)
    for bar in range(0, 8, 4):
        track.chord((28, 35, 40), bar * 4.0, 15.6, 0.30, DRONE)    # mi e si, graves
    motif = ((76, 77, 76), (79, 77, 76), (76, 77, 81), (83, 81, 77))
    for bar in range(8):
        beat0 = bar * 4.0
        # o batimento: dois pulsos graves, como um coracao lento
        track.note(midi(40), beat0, 0.4, 0.34, BASS)
        track.note(midi(40), beat0 + 0.75, 0.4, 0.20, BASS)
        if bar % 2 == 1:
            phrase = motif[(bar // 2) % 4]
            for i, note in enumerate(phrase):
                track.note(midi(note), beat0 + 1.0 + i * 1.0, 0.9, 0.24 + 0.04 * float(rng.random()), GLASS)
        if bar in (3, 7):
            track.chord((53, 57, 64), beat0 + 2.0, 2.0, 0.10, PAD)     # fa contra o mi
    track.breathe(period_beats=8.0, depth=0.35)
    track.echo(delays_beats=(1.0, 2.0), gains=(0.30, 0.15))
    return track


TRACKS = {
    1: ("capitulo_1.wav", chapter_one),
    2: ("capitulo_2.wav", chapter_two),
    3: ("capitulo_3.wav", chapter_three),
}
"""Capitulo -> (arquivo em `data/music/`, gerador)."""


def render(chapter: int) -> np.ndarray:
    """Os samples PCM de um capitulo, prontos para o WAV."""
    return TRACKS[chapter][1]().pcm()


def write_wav(path: Path, pcm: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(pcm.tobytes())


def main() -> int:
    for chapter, (name, _) in TRACKS.items():
        pcm = render(chapter)
        write_wav(OUT_DIR / name, pcm)
        print(f"capitulo {chapter}: {OUT_DIR / name}  ({len(pcm) / SAMPLE_RATE:.1f} s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
