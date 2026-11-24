"""
A alavanca: trocar o mundo inteiro de dono, com um passo.

Todas as outras reviravoltas do jogo mudam **quem esta aceso**. O facho
acende, a absorcao apaga, o farol pulsa, a lanterna anda, a fonte incha --
sempre a mesma pergunta, "onde ha luz agora?", com respostas diferentes.

A alavanca muda a outra metade da pergunta: **de quem e o aceso**. Pisar
nela troca eter por contra-eter no mapa inteiro, e cada ponte passa ao outro
ser sem que uma unica celula mude de brilho.

Duas consequencias fazem dela o verbo mais estranho do jogo:

* **Quem puxa costuma perder o proprio chao.** E a unica acao que um ser faz
  pensando no OUTRO, e a unica em que o preco e imediato e recai sobre quem
  pagou -- a Umbra puxa de pe numa rocha porque, se puxasse de pe numa
  ponte, cairia dela no mesmo frame.
* **E reversivel.** Puxar de novo desfaz. Um interruptor global que nao
  voltasse trancaria a fase na primeira curiosidade do jogador, e a
  curiosidade e exatamente o que uma alavanca convida.
"""
from __future__ import annotations

from ouroboros.core.systems.base_system import ISystem
from ouroboros.core.world import World

from penumbra.state import LUMEN, UMBRA, DualityState
from penumbra.terrain import Terrain


class PolarityLeverSystem(ISystem):
    """
    Dispara a troca na BORDA de entrada na celula da alavanca.

    Sem a borda, ficar parado em cima inverteria o mundo a cada frame -- o
    terreno piscaria a 60 Hz e nenhuma das duas polaridades duraria tempo
    suficiente pra alguem pisar. `state.on_lever` guarda, por ser, se ele ja
    estava la no frame anterior.

    Roda DEPOIS do `LightFieldSystem` porque le `state.cell`, que e ele quem
    atualiza -- mesmo contrato do relogio e do altar. A troca so aparece nas
    duas grades no frame seguinte: um frame de atraso, invisivel, e o mesmo
    que a porta de polaridade ja tem.
    """

    def __init__(self, terrain: Terrain, state: DualityState) -> None:
        self._terrain = terrain
        self._state = state

    def update(self, world: World, delta_time: float) -> None:
        del world, delta_time
        terrain = self._terrain
        if not terrain.has_lever:
            return

        state = self._state
        for side in (LUMEN, UMBRA):
            col = int(state.cell[side, 0])
            row = int(state.cell[side, 1])
            standing_on = bool(terrain.lever[row, col])
            if standing_on and not bool(state.on_lever[side]):
                terrain.swap_polarity()
                state.polarity_swapped = not state.polarity_swapped
            state.on_lever[side] = standing_on
