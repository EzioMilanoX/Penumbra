"""
O que sobrevive a fechar o jogo, o que os fragmentos valem, e a voz.

Tres coisas que nao existiam e nenhuma delas falha com erro:

* **Progresso.** Um save que nao carrega, ou que e recusado por ter sido
  gravado numa versao com outro numero de fases, apaga trinta fases vencidas
  em silencio. O save nunca pode ser o motivo de o jogo nao abrir.
* **Fragmentos.** Eles nao valiam nada -- um contador na tela de titulo. Sao
  fragmentos DA FONTE, e a ultima tela pergunta se os dois querem se fundir
  nela: nao se funde uma fonte que nunca foi remontada.
* **Audio.** A unica coisa aqui que o teste headless consegue medir e que
  todo som que o jogo pede foi REGISTRADO -- um `play_one_shot` com um id que
  ninguem sintetizou nao levanta nada, so nao toca.
"""
from __future__ import annotations

import json

from penumbra import achievements
from penumbra import audio as audio_ids
from penumbra.audio import _TONES, AudioSystem, PenumbraAudio
from penumbra.progress import Progress


class _FakeEngine:
    """Duplo do `IAudioEngine`: guarda o que foi registrado e o que tocou."""

    def __init__(self) -> None:
        self.registered = {}
        self.played = []

    def register_tone(self, sound_id, kind="square", freq=440.0, duration=0.12):
        self.registered[sound_id] = (kind, freq, duration)

    def play_one_shot(self, sound_id, volume=1.0):
        self.played.append((sound_id, volume))


class TestProgressSurvives:
    def test_grava_e_le_de_volta(self, tmp_path):
        path = tmp_path / "progress.json"
        progress = Progress(30, path)
        progress.completed[0] = True
        progress.shards[2] = True
        progress.achievements.add(achievements.FIRST_LIGHT)
        progress.ending_choice = "separados"
        progress.duo = True
        assert progress.save()

        again = Progress(30, path).load()
        assert again.completed[0] and not again.completed[1]
        assert again.shards[2]
        assert achievements.FIRST_LIGHT in again.achievements
        assert again.ending_choice == "separados"
        assert again.duo is True

    def test_arquivo_ausente_da_progresso_vazio(self, tmp_path):
        progress = Progress(30, tmp_path / "nao_existe.json").load()
        assert not any(progress.completed) and not any(progress.shards)

    def test_arquivo_corrompido_nao_derruba_o_jogo(self, tmp_path):
        """A falha mais cara de um save nao e perder o progresso: e o jogo
        nao abrir por causa dele."""
        path = tmp_path / "progress.json"
        path.write_text("{isto nao e json", encoding="utf-8")
        progress = Progress(30, path).load()
        assert not any(progress.completed)

    def test_campo_com_o_tipo_errado_e_ignorado(self, tmp_path):
        path = tmp_path / "progress.json"
        path.write_text(json.dumps({"completed": "sim", "shards": 7}), encoding="utf-8")
        progress = Progress(30, path).load()
        assert progress.completed == [False] * 30
        assert progress.shards == [False] * 30

    def test_save_de_uma_versao_com_menos_fases_e_aproveitado(self, tmp_path):
        """Acrescentar fases a um jogo nao pode apagar o que o jogador ja
        fez -- entao o save curto e COMPLETADO, nao recusado."""
        path = tmp_path / "progress.json"
        Progress(10, path).load()
        short = Progress(10, path)
        short.completed = [True] * 10
        short.save()

        grown = Progress(30, path).load()
        assert grown.completed[:10] == [True] * 10
        assert grown.completed[10:] == [False] * 20

    def test_save_de_uma_versao_com_mais_fases_e_truncado(self, tmp_path):
        path = tmp_path / "progress.json"
        long = Progress(50, path)
        long.completed = [True] * 50
        long.save()

        shrunk = Progress(30, path).load()
        assert len(shrunk.completed) == 30 and all(shrunk.completed)

    def test_gravar_e_atomico(self, tmp_path):
        """Grava num `.tmp` e renomeia por cima: um desligamento no meio da
        escrita deixa o save ANTERIOR intacto, nunca meio arquivo."""
        path = tmp_path / "progress.json"
        first = Progress(30, path)
        first.completed[0] = True
        first.save()

        assert not (tmp_path / "progress.tmp").exists(), "o temporario nao pode sobrar"
        assert json.loads(path.read_text(encoding="utf-8"))["completed"][0] is True

    def test_gravar_num_lugar_impossivel_nao_levanta(self, tmp_path):
        """Disco cheio ou pasta somente-leitura custam o progresso da sessao,
        nao a sessao."""
        blocker = tmp_path / "bloqueio"
        blocker.write_text("sou um arquivo, nao uma pasta", encoding="utf-8")
        progress = Progress(30, blocker / "progress.json")
        assert progress.save() is False


class TestShardsAreWorthSomething:
    def test_a_fonte_so_esta_inteira_com_todos_os_fragmentos(self, tmp_path):
        from penumbra.menu import EndingScreen

        screen = EndingScreen(whole=False)
        screen.move(-1)
        assert not screen.fused, "sem os fragmentos, fundir nao e escolhivel"

        whole = EndingScreen(whole=True)
        whole.move(-1)
        assert whole.fused, "com a fonte inteira, e"

    def test_seguir_dois_continua_sempre_disponivel(self):
        """A consequencia nao pode virar beco: quem nao apanhou nada ainda
        tem um fim."""
        from penumbra.menu import EndingScreen

        screen = EndingScreen(whole=False)
        screen.move(1)
        assert not screen.fused
        assert screen.choice == "separados"


class TestAchievements:
    def test_o_catalogo_nao_tem_chave_repetida(self):
        keys = [a.key for a in achievements.CATALOG]
        assert len(keys) == len(set(keys))

    def test_toda_conquista_tem_titulo_e_descricao(self):
        for achievement in achievements.CATALOG:
            assert achievement.title and achievement.description

    def test_vencer_a_primeira_fase_destrava_a_primeira_luz(self, simulation, tmp_path):
        progress = Progress(simulation.catalog.count, tmp_path / "p.json")
        state = simulation.state
        state.used_ability = True
        progress.completed[0] = True

        fresh = achievements.evaluate(
            simulation.catalog, progress, 0, state, clean_run=False, duo=False
        )
        assert achievements.FIRST_LIGHT in fresh

    def test_uma_conquista_so_e_anunciada_uma_vez(self, simulation, tmp_path):
        progress = Progress(simulation.catalog.count, tmp_path / "p.json")
        state = simulation.state
        state.used_ability = True
        progress.completed[0] = True

        first = achievements.evaluate(
            simulation.catalog, progress, 0, state, clean_run=False, duo=False
        )
        again = achievements.evaluate(
            simulation.catalog, progress, 0, state, clean_run=False, duo=False
        )
        assert achievements.FIRST_LIGHT in first
        assert achievements.FIRST_LIGHT not in again, "ja estava no progresso"

    def test_vencer_sem_ligar_habilidade_e_reconhecido(self, simulation, tmp_path):
        progress = Progress(simulation.catalog.count, tmp_path / "p.json")
        state = simulation.state
        state.used_ability = False
        progress.completed[0] = True

        fresh = achievements.evaluate(
            simulation.catalog, progress, 0, state, clean_run=False, duo=False
        )
        assert achievements.NO_ABILITY in fresh

    def test_a_fonte_inteira_precisa_de_todos_os_fragmentos(self, simulation, tmp_path):
        progress = Progress(simulation.catalog.count, tmp_path / "p.json")
        state = simulation.state
        progress.completed[0] = True
        progress.shards = [True] * (simulation.catalog.count - 1) + [False]

        fresh = achievements.evaluate(
            simulation.catalog, progress, 0, state, clean_run=False, duo=False
        )
        assert achievements.WHOLE_SOURCE not in fresh, "falta um"

        progress.shards[-1] = True
        fresh = achievements.evaluate(
            simulation.catalog, progress, 0, state, clean_run=False, duo=False
        )
        assert achievements.WHOLE_SOURCE in fresh


class TestAudio:
    def test_todo_som_que_o_jogo_pede_foi_registrado(self, simulation):
        """`play_one_shot` com um id que ninguem sintetizou nao levanta nada
        -- so nao toca. Este e o unico jeito headless de pegar um som mudo."""
        engine = _FakeEngine()
        PenumbraAudio(engine)

        asked = {name for name in dir(audio_ids)
                 if name.isupper() and isinstance(getattr(audio_ids, name), str)}
        ids = {getattr(audio_ids, name) for name in asked}
        registered = set(engine.registered)
        assert ids <= registered, f"sem tom registrado: {sorted(ids - registered)}"

    def test_o_aviso_de_perigo_acelera_com_o_medidor(self, simulation):
        """O que o jogador le nao e o tom, e a ACELERACAO: um intervalo
        constante viraria ruido de fundo e ele pararia de ouvir."""
        from penumbra.state import LUMEN

        engine = _FakeEngine()
        system = AudioSystem(PenumbraAudio(engine), simulation.state, simulation.terrain)
        state = simulation.state

        def beeps(peril, seconds=2.0):
            engine.played.clear()
            system._peril_countdown[LUMEN] = 0.0
            state.peril[:] = 0.0
            state.peril[LUMEN] = peril
            for _ in range(int(seconds * 60)):
                system.update(None, 1 / 60)
            return sum(1 for name, _ in engine.played if name == audio_ids.PERIL_LUMEN)

        assert beeps(0.05) == 0, "uma nesga de polaridade errada nao dispara aviso"
        calm, urgent = beeps(0.35), beeps(0.95)
        assert 0 < calm < urgent, f"deveria acelerar: {calm} -> {urgent}"

    def test_a_porta_soa_uma_vez_e_nao_sessenta_por_segundo(self, simulation):
        engine = _FakeEngine()
        system = AudioSystem(PenumbraAudio(engine), simulation.state, simulation.terrain)
        simulation.state.door_open = False
        system.update(None, 1 / 60)

        engine.played.clear()
        simulation.state.door_open = True
        for _ in range(120):
            system.update(None, 1 / 60)

        assert sum(1 for name, _ in engine.played if name == audio_ids.DOOR) == 1

    def test_sem_motor_de_audio_nada_quebra(self, simulation):
        """`build_simulation` monta a mesma simulacao sem renderer, sem input
        concreto e sem audio -- e e o que mantem a suite headless."""
        silent = PenumbraAudio(None)
        assert not silent.enabled
        silent.play(audio_ids.DOOR)   # nao levanta

    def test_os_dois_seres_tem_vozes_distantes(self):
        """No duo os dois podem estar em perigo ao mesmo tempo, e a
        informacao que falta nunca e 'alguem esta morrendo', e sim QUEM."""
        tones = {sound_id: freq for sound_id, _, freq, _ in _TONES}
        lumen, umbra = tones[audio_ids.PERIL_LUMEN], tones[audio_ids.PERIL_UMBRA]
        assert lumen > 2 * umbra, "uma oitava nao basta pra distinguir sob pressao"
