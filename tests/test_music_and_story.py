"""
A musica de fundo e as falas entre capitulos.

A musica sai de `tools/generate_music.py` e mora em `data/music/` como WAV.
Os testes conferem o que nao se ouve num `pytest`: que os arquivos sao
exatamente o que o gerador produz (um WAV editado a mao, ou um gerador mudado
sem regravar, divergiria em silencio), que o laco fecha sem estalo, e que
nada estoura. As falas: que cabem na tela, que existem para os tres
capitulos, e que o fluxo as mostra na borda certa.
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
import pytest

from penumbra.audio import MUSIC_FILES, PenumbraMusic
from penumbra.story import StoryError, load_interludes
from tools.generate_music import PEAK, SAMPLE_RATE, TRACKS, render

_ROOT = Path(__file__).resolve().parents[1]
_MUSIC = _ROOT / "data" / "music"
_STORY = _ROOT / "data" / "story" / "interludes.json"


def _read_wav(path: Path) -> tuple[np.ndarray, wave._wave_params]:
    with wave.open(str(path), "rb") as handle:
        params = handle.getparams()
        frames = handle.readframes(params.nframes)
    return np.frombuffer(frames, dtype="<i2"), params


class TestMusicFiles:
    @pytest.mark.parametrize("chapter", sorted(TRACKS))
    def test_o_arquivo_e_exatamente_o_que_o_gerador_produz(self, chapter):
        samples, params = _read_wav(_MUSIC / TRACKS[chapter][0])
        assert (params.nchannels, params.sampwidth, params.framerate) == (1, 2, SAMPLE_RATE)
        assert np.array_equal(samples, render(chapter)), (
            "o WAV nao bate com o gerador -- rode `python -m tools.generate_music`"
        )

    @pytest.mark.parametrize("chapter", sorted(TRACKS))
    def test_o_laco_fecha_sem_estalo_e_nada_estoura(self, chapter):
        """O ultimo sample emenda no primeiro como qualquer par vizinho da
        faixa: a emenda nao pode ser o maior salto dela."""
        pcm = render(chapter).astype(np.float64) / 32767.0
        steps = np.abs(np.diff(pcm))
        seam = abs(pcm[0] - pcm[-1])
        assert seam <= float(np.quantile(steps, 0.9999)), f"estalo na emenda: {seam:.4f}"
        assert float(np.max(np.abs(pcm))) <= PEAK + 1e-3
        duration = len(pcm) / SAMPLE_RATE
        assert 15.0 <= duration <= 40.0
        assert float(np.sqrt(np.mean(pcm ** 2))) > 0.05, "silencio nao e musica"

    def test_as_tres_faixas_sao_diferentes(self):
        tracks = [render(chapter) for chapter in sorted(TRACKS)]
        assert len({t.tobytes()[:20000] for t in tracks}) == len(tracks)

    def test_o_jogo_pede_as_faixas_que_o_gerador_escreve(self):
        assert {name for name, _ in TRACKS.values()} == set(MUSIC_FILES.values())


class _Engine:
    def __init__(self) -> None:
        self.loaded = {}
        self.playing = None
        self.plays = 0
        self.volume = None

    def load_track(self, track_id, path):
        self.loaded[track_id] = path

    def play_track(self, track_id, start_offset_seconds=0.0, loop=False):
        assert loop, "musica de fundo toca em laco"
        self.playing = track_id
        self.plays += 1

    def stop_track(self, track_id):
        if self.playing == track_id:
            self.playing = None

    def set_track_volume(self, volume):
        self.volume = volume


class TestMusicPlayer:
    def test_carrega_as_tres_e_troca_por_capitulo(self):
        engine = _Engine()
        music = PenumbraMusic(engine, _MUSIC)
        assert music.available == {1, 2, 3}
        music.play_chapter(2)
        music.play_chapter(2)
        assert engine.plays == 1, "a fase seguinte do mesmo capitulo nao recomeca a faixa"
        music.play_chapter(3)
        assert engine.playing.endswith("3")
        music.stop()
        assert engine.playing is None

    def test_som_desligado_cala_a_musica(self):
        engine = _Engine()
        music = PenumbraMusic(engine, _MUSIC)
        music.apply(False, 0.8)
        assert engine.volume == 0.0
        music.apply(True, 0.3)
        assert engine.volume == pytest.approx(0.3)

    def test_sem_arquivo_fica_mudo_sem_erro(self, tmp_path):
        engine = _Engine()
        music = PenumbraMusic(engine, tmp_path)
        music.play_chapter(1)
        assert engine.playing is None
        PenumbraMusic(None, _MUSIC).play_chapter(1)   # headless


class TestMusicVolumeOption:
    def test_o_volume_da_musica_e_proprio_e_sobrevive(self, simulation, input_provider, tmp_path):
        from penumbra.menu import OPTION_MUSIC
        from penumbra.progress import Progress
        from penumbra.scenes import PenumbraFlow
        from penumbra.terrain import Terrain
        from tests.conftest import CELL_SIZE, GRID_COLS, GRID_ROWS
        from tests.test_shipped_levels import _FakeGameLoop

        engine = _Engine()
        path = tmp_path / "progress.json"
        flow = PenumbraFlow(
            _FakeGameLoop(), simulation.runtime, simulation.state,
            simulation.catalog, simulation.tuning, input_provider,
            preview_terrain=Terrain(GRID_COLS, GRID_ROWS, CELL_SIZE),
            progress=Progress(simulation.catalog.count, path),
            music=PenumbraMusic(engine, _MUSIC),
        )
        flow.show_options()
        flow.options.screen.selected = OPTION_MUSIC
        effects = flow.progress.volume
        input_provider.set_action_held("move_right", True)
        input_provider.poll()
        flow.options.update(simulation.world, 1 / 60)

        assert flow.progress.music_volume == pytest.approx(0.6)
        assert flow.progress.volume == effects, "musica e efeitos tem volumes separados"
        assert engine.volume == pytest.approx(0.6)
        assert engine.playing is not None, "ajustar a musica deixa ouvir a musica"
        assert Progress(simulation.catalog.count, path).load().music_volume == pytest.approx(0.6)


class TestStory:
    def test_uma_fala_por_capitulo(self, simulation):
        interludes = load_interludes(_STORY)
        chapters = {chapter.number for chapter in simulation.catalog.chapters}
        assert set(interludes) == chapters

    def test_cada_linha_cabe_na_tela(self):
        """16 px de fonte monoespacada gastam ~9,6 px por letra; a janela tem
        896. Uma linha que sai da tela e uma frase cortada no meio, e headless
        ninguem ve."""
        for interlude in load_interludes(_STORY).values():
            assert len(interlude.lines) <= 5
            for line in interlude.lines:
                assert len(line) * 16 * 0.6 <= 896 - 2 * 40, line

    def test_arquivo_malformado_falha_alto(self, tmp_path):
        bad = tmp_path / "falas.json"
        bad.write_text('{"interludes": [{"chapter": 1}]}', encoding="utf-8")
        with pytest.raises(StoryError):
            load_interludes(bad)

    def test_sem_arquivo_o_jogo_fica_calado(self, tmp_path):
        assert load_interludes(tmp_path / "nada.json") == {}


class TestStoryInTheFlow:
    @pytest.fixture
    def flow(self, simulation, input_provider, tmp_path):
        from penumbra.progress import Progress
        from penumbra.scenes import PenumbraFlow
        from penumbra.terrain import Terrain
        from tests.conftest import CELL_SIZE, GRID_COLS, GRID_ROWS
        from tests.test_shipped_levels import _FakeGameLoop

        return PenumbraFlow(
            _FakeGameLoop(), simulation.runtime, simulation.state,
            simulation.catalog, simulation.tuning, input_provider,
            preview_terrain=Terrain(GRID_COLS, GRID_ROWS, CELL_SIZE),
            progress=Progress(simulation.catalog.count, tmp_path / "progress.json"),
            interludes=load_interludes(_STORY),
        )

    def test_a_primeira_fase_abre_com_o_prologo(self, flow, simulation, input_provider):
        flow.enter_level(0)
        scene = flow._game_loop.current_scene
        assert scene is flow.interlude
        assert scene.then_level == 0

        # ESPAÇO adianta as linhas; o segundo ESPAÇO entra na fase.
        for _ in range(2):
            input_provider.set_action_held("jump", True)
            input_provider.poll()
            scene.update(simulation.world, 1 / 60)
            input_provider.set_action_held("jump", False)
            input_provider.poll()
        assert flow._game_loop.current_scene is flow.gameplay
        assert simulation.state.level_index == 0

    def test_depois_de_vencida_a_primeira_fase_nao_repete_o_prologo(self, flow):
        flow.progress.completed[0] = True
        flow.enter_level(0)
        assert flow._game_loop.current_scene is flow.gameplay

    def test_a_borda_do_capitulo_traz_a_fala_dele(self, flow, simulation):
        catalog = simulation.catalog
        last_of_first = catalog.chapters[0].last
        flow.start_level(last_of_first)
        flow.finish_level(last_of_first)
        scene = flow._game_loop.current_scene
        assert scene is flow.interlude
        assert scene.interlude.chapter == 2
        assert scene.then_level == last_of_first + 1

    def test_dentro_do_capitulo_nao_ha_fala(self, flow):
        flow.start_level(0)
        flow.finish_level(0)
        assert flow._game_loop.current_scene is flow.gameplay

    def test_a_tela_da_fala_desenha_tudo_dentro_da_janela(self, flow):
        from penumbra.menu import InterludeScreen

        drawn = []

        class _R:
            def get_viewport_size(self):
                return (896, 616)

            def draw_ui_rect(self, *args):
                pass

            def draw_text(self, x, y, text, size, rgba, anchor="topleft"):
                drawn.append((text, x - len(text) * size * 0.3, x + len(text) * size * 0.3, y))

        for interlude in flow.interludes.values():
            InterludeScreen().draw(_R(), interlude, elapsed=60.0)
        assert drawn
        for text, left, right, y in drawn:
            assert 0 <= left and right <= 896 and 0 <= y <= 616, text
