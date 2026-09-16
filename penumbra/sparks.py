"""
O que o jogo faz quando alguma coisa cede.

Ate aqui, tudo acontecia trocando de cor. A crosta rompia, o eclipse
colapsava, um ser morria -- e a unica diferenca na tela era uma celula que
passava a ser desenhada de outro jeito. O jogador via o RESULTADO e nunca o
evento, o que faz uma fase inteira parecer que nada de fisico acontece nela.

As particulas marcam exatamente os mesmos instantes que o audio ja marca, e
isso e deliberado: som e luz tem de concordar, senao um deles vira ruido. Se
um evento nao mereceu um tom em `penumbra.audio`, tambem nao merece faisca.

Blend ADITIVO (`IRenderer.draw_particles`), que e o que separa faisca de
sprite: num jogo cujo assunto e luz, uma particula que SOMA luz onde cai diz
a coisa certa sozinha.

Zero-GC: um `ParticleStorage` pre-alocado e buffers de emissao alocados uma
vez no `__init__`. `emit_burst` recebe arrays prontos e `update` e vetorizado
-- nenhum laco Python por particula, em lugar nenhum.
"""
from __future__ import annotations

import numpy as np

from ouroboros.core.particle_storage import ParticleStorage

_CAPACITY = 360
"""Teto de particulas vivas. `emit_burst` trunca em silencio quando estoura
-- divergencia deliberada da engine, e a certa: uma tela cheia de faisca e
cosmetica, e travar o jogo por causa dela seria pior que perder faisca."""

_MAX_BURST = 48
"""Maior rajada que qualquer evento pede. Os buffers de emissao sao
alocados uma vez com este tamanho e reaproveitados."""

_MIN_READABLE_SIZE = 5.0
"""Menor diametro que ainda vira faisca na tela.

O backend desenha `radius = max(1, int(size) // 2)`, entao um tamanho de 3
vira um circulo de UM pixel. A primeira versao emitia 44 particulas que
acendiam doze pixels no total -- existiam, custavam frame, e eram invisiveis.
Medido, nao estimado."""

_GRAVITY = 520.0
"""Queda das faiscas, em px/s^2 -- o que faz o estilhaco da crosta cair como
pedra em vez de flutuar como fumaca.

O NUMERO e nosso (e uma decisao de peso, como a gravidade dos dois seres); a
conta e da engine, desde que `ParticleStorage.update` passou a aceitar
`gravity_y`. Era o unico produto escrevendo a aceleracao por fora, no buffer
certo e na ordem certa."""

# --- as cores sao as do jogo, nao novas ---
CRUST = (198, 172, 146)
GOLD = (247, 214, 138)
LUMEN = (250, 250, 255)
UMBRA = (164, 154, 196)


class SparkField:
    """
    Um punhado de faiscas, e os eventos que as merecem.

    Vive fora do `World` de proposito: nao existe pool de particulas
    registrada (diferente de `fx`), e desenhar e responsabilidade explicita
    de quem chama -- tipicamente de dentro do callback de `set_on_draw_ui`,
    que e onde o HUD ja mora.
    """

    def __init__(self, capacity: int = _CAPACITY) -> None:
        self._storage = ParticleStorage(capacity)
        size = _MAX_BURST
        self._x = np.zeros(size, dtype=np.float32)
        self._y = np.zeros(size, dtype=np.float32)
        self._vx = np.zeros(size, dtype=np.float32)
        self._vy = np.zeros(size, dtype=np.float32)
        self._ttl = np.zeros(size, dtype=np.float32)
        self._size = np.zeros(size, dtype=np.float32)
        self._tint = np.zeros((size, 4), dtype=np.uint8)
        # Gerador proprio, semeado: duas partidas iguais produzem a mesma
        # faisca. Nao importa pro jogo e importa muito pra um teste poder
        # afirmar alguma coisa sobre o que foi emitido.
        self._random = np.random.default_rng(20260913)

    @property
    def count(self) -> int:
        return self._storage.count

    def clear(self) -> None:
        """Apaga tudo -- usado ao trocar de fase, pra que a poeira de uma
        crosta rompida nao apareca no primeiro frame da fase seguinte."""
        self._storage.update(1e9)

    def update(self, delta_time: float) -> None:
        """Integra e mata as velhas."""
        self._storage.update(delta_time, gravity_y=_GRAVITY)

    def draw(self, renderer) -> None:
        view = self._storage.active_view()
        count = view.shape[0]
        if not count:
            return
        # Desvanece por idade: `update()` so decrementa o ttl, e sem isto a
        # faisca sumiria de uma vez em vez de apagar.
        fade = np.clip(view["ttl_seconds"] / np.maximum(view["ttl0_seconds"], 1e-6), 0.0, 1.0)
        positions = np.empty((count, 2), dtype=np.float32)
        positions[:, 0] = view["position_x"]
        positions[:, 1] = view["position_y"]
        tint = np.empty((count, 4), dtype=np.uint8)
        tint[:, 0] = view["tint_r"]
        tint[:, 1] = view["tint_g"]
        tint[:, 2] = view["tint_b"]
        tint[:, 3] = (view["tint_a"] * fade).astype(np.uint8)
        renderer.draw_particles(positions, view["size"].copy(), tint, count)

    # ------------------------------------------------------------------
    # os eventos
    # ------------------------------------------------------------------

    def burst(self, x: float, y: float, color, amount: int, speed: float,
              ttl: float = 0.55, spread: float = 1.0, size: float = 8.0) -> int:
        """Uma rajada radial. Todo evento passa por aqui -- o que muda entre
        eles e quantas, com que forca e de que cor, e nao a forma."""
        amount = int(min(amount, _MAX_BURST))
        if amount <= 0:
            return 0
        angle = self._random.uniform(0.0, 2.0 * np.pi, amount).astype(np.float32)
        power = self._random.uniform(0.35, 1.0, amount).astype(np.float32) * speed
        self._x[:amount] = x
        self._y[:amount] = y
        self._vx[:amount] = np.cos(angle) * power
        self._vy[:amount] = np.sin(angle) * power * spread
        self._ttl[:amount] = ttl * self._random.uniform(0.6, 1.0, amount)
        self._size[:amount] = np.maximum(
            _MIN_READABLE_SIZE, size * self._random.uniform(0.6, 1.2, amount)
        )
        self._tint[:amount, 0] = color[0]
        self._tint[:amount, 1] = color[1]
        self._tint[:amount, 2] = color[2]
        self._tint[:amount, 3] = 255
        return self._storage.emit_burst(
            self._x[:amount], self._y[:amount], self._vx[:amount], self._vy[:amount],
            self._ttl[:amount], self._size[:amount], self._tint[:amount],
        )

    def crust_broke(self, x: float, y: float) -> int:
        """Estilhaco pesado e quente. E o unico evento do jogo em que alguem
        QUEBRA alguma coisa, e ele merece parecer isso."""
        return self.burst(x, y, CRUST, amount=18, speed=150.0, ttl=0.7, size=9.0)

    def eclipse_collapsed(self, x: float, y: float) -> int:
        """A ponte dourada cedendo. Larga e lenta: a zona inteira some de uma
        vez, e a faisca tem de cobrir a mesma largura."""
        return self.burst(x, y, GOLD, amount=44, speed=210.0, ttl=1.0, size=10.0)

    def shard_taken(self, x: float, y: float) -> int:
        return self.burst(x, y, GOLD, amount=16, speed=120.0, ttl=0.6, size=8.0)

    def form_left(self, x: float, y: float) -> int:
        """A renuncia. Sobe mais do que espalha -- o gesto e de entregar."""
        return self.burst(x, y, GOLD, amount=24, speed=95.0, ttl=1.1, spread=1.6, size=9.0)

    def echo(self, x: float, y: float) -> int:
        return self.burst(x, y, GOLD, amount=30, speed=70.0, ttl=1.3, size=7.0)

    def died(self, x: float, y: float, lumen: bool) -> int:
        """Cada um se desfaz do proprio jeito, na propria cor."""
        return self.burst(x, y, LUMEN if lumen else UMBRA,
                          amount=26, speed=130.0, ttl=0.9, size=8.0)
