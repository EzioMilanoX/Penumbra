"""
O altar de forma: trocar poder por permanencia, e nao poder voltar atras.

As duas habilidades do jogo sao fortes pela mesma razao -- elas ACOMPANHAM o
ser. O facho acende onde a Lumen esta, o bolsao escurece onde a Umbra esta, e
por isso nenhum dos dois consegue estar em dois lugares ao mesmo tempo. Todo
problema do jogo, no fundo, e esse: a luz que voce precisa ali esta aqui.

O altar e a unica resposta possivel a esse problema, e ela custa caro. Um ser
em cima de um altar, com a habilidade ligada, derrama a forma na pedra: ao fim
de `form_sacrifice_seconds` o altar fica com uma luz fixa (Lumen) ou uma
escuridao fixa (Umbra) PRA SEMPRE -- e quem a deixou nunca mais liga a
habilidade nesta fase. A carga para de recompor; a barra fica vazia.

Tres consequencias que fazem o verbo valer a pena:

* **E a segunda coisa irreversivel do jogo**, depois da crosta. Mas a crosta e
  irreversivel no TERRENO e a decisao e "quebro ou nao?"; o altar e
  irreversivel no SER, e a decisao e "onde?". Um altar mal escolhido nao
  tranca a fase -- deixa voce com metade do personagem e a luz no lugar
  errado, que e uma derrota mais interessante de ler.
* **A luz deixada nao tem carga.** O facho dura 3,2 s e obriga cada fase a ser
  um problema de sequencia; a luz do altar nao acaba nunca. Uma ponte que
  antes so podia ser atravessada as pressas passa a estar simplesmente la.
* **Os dois tem uma forma pra deixar, e as fases oferecem altares demais.**
  Escolher um e recusar os outros e o unico momento do jogo em que o jogador
  gasta algo que nao volta no proximo `R`.
"""
from __future__ import annotations

from ouroboros.core.systems.base_system import ISystem
from ouroboros.core.world import World

from penumbra.state import DualityState, LUMEN, UMBRA
from penumbra.terrain import Terrain
from penumbra.tuning import DualityTuning


class FormAltarSystem(ISystem):
    """
    Acumula o deposito da forma e, ao completar, marca o altar e o ser.

    Roda DEPOIS do `LightFieldSystem` porque le `state.cell`, que e ele quem
    atualiza -- mesmo contrato do `WorldClockSystem`. A luz que o altar passa
    a emitir entra no campo no frame SEGUINTE; um frame de atraso, invisivel,
    e o mesmo que a porta de polaridade e o farol ja tem.

    Nao ha tecla nova. O gesto e "segurar a habilidade em cima do altar", que
    e literalmente o que o verbo significa -- e e por isso que ele nao disputa
    nada com o `DualityControlSystem`: aquele sistema liga e desliga a
    habilidade, este so observa que ela esta ligada aqui.
    """

    def __init__(
        self,
        terrain: Terrain,
        state: DualityState,
        tuning: DualityTuning,
    ) -> None:
        self._terrain = terrain
        self._state = state
        self._seconds = max(1e-6, float(tuning.flow.form_sacrifice_seconds))
        self._beam_intensity = float(tuning.light.beam_intensity)
        # Mesma conta do `LightFieldSystem`: a semente que faz o flood da
        # sombra alcancar exatamente `absorb_radius_cells` antes de cair
        # abaixo do limiar. A escuridao deixada na pedra tem o mesmo raio que
        # a que a Umbra carrega -- o altar muda a duracao, nunca a forca.
        light = tuning.light
        self._absorb_seed = float(
            light.solid_threshold + light.absorb_radius_cells * light.decay_per_cell
        )

    def update(self, world: World, delta_time: float) -> None:
        del world
        if not self._terrain.has_altar:
            return

        state, terrain = self._state, self._terrain
        for side in (LUMEN, UMBRA):
            if bool(state.form_spent[side]):
                state.altar_progress[side] = 0.0
                continue

            col = int(state.cell[side, 0])
            row = int(state.cell[side, 1])
            if not (bool(terrain.altar[row, col]) and bool(state.ability_on[side])):
                state.altar_progress[side] = 0.0
                continue

            progress = float(state.altar_progress[side]) + delta_time / self._seconds
            if progress < 1.0:
                state.altar_progress[side] = progress
                continue

            self._leave_form(side, col, row)

    # ------------------------------------------------------------------

    def _leave_form(self, side: int, col: int, row: int) -> None:
        """Sela a troca: a pedra fica com a forma, o ser fica sem ela.

        A carga vai a zero e nao volta -- `DualityControlSystem` para de
        recompor quem gastou. Ela nao e escondida do HUD de proposito: uma
        barra vazia que nunca mais enche e a lembranca permanente de uma
        decisao que o jogador tomou, e e exatamente isso que a mecanica
        quer dizer.
        """
        state = self._state
        state.altar_progress[side] = 0.0
        state.form_spent[side] = True
        state.ability_on[side] = False
        state.charge[side] = 0.0
        if side == LUMEN:
            state.altar_light[row, col] = self._beam_intensity
        else:
            state.altar_shadow[row, col] = self._absorb_seed
