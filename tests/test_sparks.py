"""
A poeira, e os instantes que a merecem.

Ate aqui tudo acontecia trocando de cor: a crosta rompia, o eclipse
colapsava, um ser morria, e a unica diferenca na tela era uma celula
desenhada de outro jeito. O jogador via o RESULTADO e nunca o evento.

A regra que estes testes guardam nao e "tem faisca", e sim **som e luz
concordam**: as particulas marcam exatamente os mesmos instantes que
`penumbra.audio` marca. Se um evento nao mereceu um tom, tambem nao merece
faisca -- e o contrario faria um dos dois virar ruido.
"""
from __future__ import annotations

from penumbra.sparks import SparkField
from penumbra.systems.spark_system import SparkSystem
from tests.conftest import load_custom


class _FakeRenderer:
    def __init__(self) -> None:
        self.calls = []

    def draw_particles(self, positions, sizes, tint, count):
        self.calls.append((positions.copy(), sizes.copy(), tint.copy(), count))


class TestSparkField:
    def test_uma_rajada_nasce_e_morre(self):
        field = SparkField()
        assert field.count == 0

        field.crust_broke(100.0, 200.0)
        assert field.count > 0

        for _ in range(120):
            field.update(1 / 60)
        assert field.count == 0, "toda faisca tem prazo"

    def test_a_faisca_cai(self):
        """`ParticleStorage.update` so integra posicao por velocidade -- a
        gravidade e nossa, e e o que faz o estilhaco cair como pedra em vez
        de flutuar como fumaca."""
        field = SparkField()
        field.crust_broke(100.0, 100.0)
        before = field._storage.active_view()["velocity_y"].copy()

        for _ in range(12):
            field.update(1 / 60)

        after = field._storage.active_view()["velocity_y"]
        assert after.shape[0] and float(after.mean()) > float(before.mean())

    def test_estourar_a_capacidade_nao_levanta(self):
        """Uma tela cheia de faisca e cosmetica: travar o jogo por causa dela
        seria pior que perder faisca. A engine trunca em silencio e este
        teste existe pra que a gente nao tente ser mais esperto que isso."""
        field = SparkField(capacity=20)
        for _ in range(30):
            field.eclipse_collapsed(50.0, 50.0)
        assert field.count <= 20

    def test_limpar_apaga_tudo(self):
        field = SparkField()
        field.eclipse_collapsed(50.0, 50.0)
        assert field.count > 0
        field.clear()
        assert field.count == 0

    def test_desenhar_sem_faisca_nao_chama_o_renderer(self):
        """Um `draw_particles` com `count=0` a cada frame e trabalho que nao
        produz pixel nenhum."""
        renderer = _FakeRenderer()
        SparkField().draw(renderer)
        assert not renderer.calls

    def test_o_desenho_desvanece_por_idade(self):
        """`update()` so decrementa o ttl; sem o fade a faisca sumiria de uma
        vez em vez de apagar."""
        field = SparkField()
        field.crust_broke(100.0, 100.0)

        renderer = _FakeRenderer()
        field.draw(renderer)
        fresh = float(renderer.calls[-1][2][:, 3].mean())

        for _ in range(20):
            field.update(1 / 60)
        field.draw(renderer)
        old = float(renderer.calls[-1][2][:, 3].mean())

        assert old < fresh, "o alfa tem de cair com a idade"

    def test_a_faisca_e_grande_o_bastante_pra_ser_vista(self):
        """O defeito que quase passou. O backend desenha
        `radius = max(1, int(size) // 2)`, entao um tamanho 3 vira um circulo
        de UM pixel -- a primeira versao emitia 44 particulas que acendiam
        doze pixels no total. Existiam, custavam frame, e eram invisiveis.

        Medir o tamanho aqui e mais honesto que olhar uma captura: uma faisca
        pequena demais nao some, so fica indistinguivel do ruido de fundo."""
        from penumbra.sparks import _MIN_READABLE_SIZE

        field = SparkField()
        for emit in (field.crust_broke, field.eclipse_collapsed, field.shard_taken,
                     field.form_left, field.echo):
            field.clear()
            emit(100.0, 100.0)
            sizes = field._storage.active_view()["size"]
            assert float(sizes.min()) >= _MIN_READABLE_SIZE, emit.__name__
            assert int(sizes.min()) // 2 >= 2, (
                f"{emit.__name__}: raio de {int(sizes.min()) // 2} px nao se ve"
            )

    def test_cada_ser_se_desfaz_na_propria_cor(self):
        from penumbra.sparks import LUMEN as LUMEN_TINT
        from penumbra.sparks import UMBRA as UMBRA_TINT

        field = SparkField()
        field.died(10.0, 10.0, lumen=True)
        assert int(field._storage.active_view()["tint_r"][0]) == LUMEN_TINT[0]

        field.clear()
        field.died(10.0, 10.0, lumen=False)
        assert int(field._storage.active_view()["tint_r"][0]) == UMBRA_TINT[0]


class TestSparkSystemWatchesTheSameEdges:
    _ROOM = {
        12: "..A.....B..%.......X......Y.",
        13: "############################",
        14: "############################",
    }

    def _system(self, simulation):
        field = SparkField()
        system = SparkSystem(field, simulation.state, simulation.terrain)
        return field, system

    def test_a_crosta_cedendo_solta_estilhaco(self, simulation, input_provider):
        """O unico evento do jogo em que alguem QUEBRA alguma coisa."""
        load_custom(simulation, self._ROOM)
        field, system = self._system(simulation)
        system.update(simulation.world, 1 / 60)
        assert field.count == 0

        simulation.state.crust_target_col = 11
        simulation.state.crust_target_row = 12
        simulation.terrain.break_crust(11, 12)
        system.update(simulation.world, 1 / 60)

        assert field.count > 0

    def test_o_fragmento_apanhado_solta_faisca(self, simulation, input_provider):
        load_custom(simulation, {
            12: "..A.....B...+......X......Y.",
            13: "############################",
        })
        field, system = self._system(simulation)
        system.update(simulation.world, 1 / 60)

        simulation.state.shard_collected = True
        system.update(simulation.world, 1 / 60)

        assert field.count > 0

    def test_trocar_de_fase_apaga_a_poeira(self, simulation, input_provider):
        """O estilhaco de uma crosta rompida chegando no primeiro frame da
        fase seguinte seria um evento que nunca aconteceu ali."""
        load_custom(simulation, self._ROOM)
        field, system = self._system(simulation)
        system.update(simulation.world, 1 / 60)
        field.eclipse_collapsed(100.0, 100.0)
        assert field.count > 0

        simulation.state.level_index = 5
        system.update(simulation.world, 1 / 60)

        assert field.count == 0

    def test_nada_acontecendo_nao_emite_nada(self, simulation, input_provider):
        load_custom(simulation, self._ROOM)
        field, system = self._system(simulation)
        for _ in range(60):
            system.update(simulation.world, 1 / 60)
        assert field.count == 0


class TestSoundAndLightAgree:
    def test_os_eventos_com_faisca_sao_os_eventos_com_som(self):
        """A regra do arquivo. Nao da pra comparar as duas listas
        automaticamente sem inventar um registro que nenhum dos dois usa --
        entao ela fica escrita aqui, ao lado das duas, e quem acrescentar um
        evento num lado ve o outro.

        Com som e com faisca: crosta, eclipse, fragmento, altar, Instante,
        morte. Com som e SEM faisca: habilidade ligada/desligada, porta,
        farol, alavanca, vitoria -- todos sao mudancas de ESTADO do mundo,
        nao coisas que se despedacam."""
        from penumbra import audio

        with_sparks = {"crust_broke", "eclipse_collapsed", "shard_taken",
                       "form_left", "echo", "died"}
        assert with_sparks <= set(dir(SparkField))

        for name in ("CRUST", "ECLIPSE", "SHARD", "ALTAR", "ECHO", "FAIL"):
            assert hasattr(audio, name), f"{name} tem faisca e precisa de som"
