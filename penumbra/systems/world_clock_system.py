"""
O relogio do mundo: o que muda sozinho, sem ninguem pedir.

Todo o resto do jogo reage ao jogador -- o facho acende porque ela ligou, a
crosta cede porque ela empurrou. Este sistema e o contrario: o farol pulsa e
o eclipse colapsa porque o tempo passou. E o que faz o mundo ser um agente e
nao so um tabuleiro.

Os dois moram juntos porque sao a mesma ideia contada de dois jeitos:

* **Farol pulsante** -- uma lampada em ciclo. Nao e apenas temporizacao: e a
  unica coisa no jogo que inverte o conflito sem o jogador pedir. Quando
  apaga, o eter sob a Lumen deixa de ser chao; quando acende, o da Umbra
  deixa de ser. Ate aqui os dois sentidos do conflito exigiam duas
  habilidades e duas decisoes; aqui vem de graca, e contra os dois.
* **Lanterna errante** -- uma lampada que percorre um trilho de ponta a ponta
  e volta. E a terceira forma de o mundo mexer no chao sem ser pedido, e a
  unica que se atravessa ACOMPANHANDO em vez de esperando: o farol troca o
  dono do eter sem sair do lugar, a lanterna leva o chao junto com ela. A
  Lumen anda no passo da lanterna; a Umbra anda sempre fora do circulo dela.
* **Fonte que respira** -- uma lampada cuja INTENSIDADE sobe e desce em
  ciclo, entao o raio aceso dilata e contrai sem que nada saia do lugar. As
  tres coisas que o mundo faz sozinho pedem tres leituras diferentes: do
  farol se ESPERA a virada, a lanterna se ACOMPANHA, e da fonte se RECUA --
  ela vem buscar voce onde voce esta parado.
* **Zona de eclipse** -- a unica celula que aceita os DOIS, e a unica com
  prazo. Ao primeiro toque de qualquer um deles a zona inteira comeca a
  colapsar; no fim do prazo, desaparece. E a resposta a pergunta que o resto
  do jogo nunca faz: nao "de quem e este chao?", mas "da tempo pros dois?".
"""
from __future__ import annotations

import math

from ouroboros.core.systems.base_system import ISystem
from ouroboros.core.world import World

from penumbra.state import LUMEN, UMBRA, DualityState
from penumbra.terrain import Terrain
from penumbra.tuning import DualityTuning


class WorldClockSystem(ISystem):
    """
    Avanca o ciclo do farol e o prazo do eclipse.

    Roda DEPOIS do `LightFieldSystem`, e isso importa nos dois sentidos. O
    eclipse precisa das celulas dos seres, que e o `LightFieldSystem` quem
    atualiza (`state.cell`) -- ler antes dele usaria a posicao do frame
    anterior. Em troca, o estado do farol que este sistema escreve so entra
    no campo de luz no frame SEGUINTE: um frame de atraso, invisivel, e o
    mesmo contrato que a porta de polaridade ja tem.
    """

    def __init__(
        self,
        terrain: Terrain,
        state: DualityState,
        tuning: DualityTuning,
    ) -> None:
        self._terrain = terrain
        self._state = state
        self._beacon_on_seconds = tuning.flow.beacon_on_seconds
        self._beacon_off_seconds = tuning.flow.beacon_off_seconds
        self._eclipse_seconds = tuning.flow.eclipse_collapse_seconds
        self._wanderer_speed = tuning.flow.wanderer_speed_cells
        self._source_period = tuning.flow.source_period_seconds
        self._source_min = tuning.flow.source_min_intensity
        self._source_max = tuning.flow.source_max_intensity

    def update(self, world: World, delta_time: float) -> None:
        del world
        self._advance_beacon(delta_time)
        self._advance_wanderer(delta_time)
        self._advance_source(delta_time)
        self._advance_eclipse(delta_time)

    # ------------------------------------------------------------------

    def _advance_beacon(self, delta_time: float) -> None:
        """Ciclo simples de liga/desliga. O periodo inteiro vive numa fase
        acumulada em vez de num contador por estado: assim o farol nunca
        acumula deriva, e `beacon_seconds_left` sai direto da fase -- e o HUD
        pode avisar quanto falta pra virada, que e a informacao com que o
        jogador de fato planeja."""
        state = self._state
        if not self._terrain.has_beacon:
            state.beacon_on = True
            state.beacon_seconds_left = 0.0
            return

        period = self._beacon_on_seconds + self._beacon_off_seconds
        state.beacon_phase = (state.beacon_phase + delta_time) % period
        if state.beacon_phase < self._beacon_on_seconds:
            state.beacon_on = True
            state.beacon_seconds_left = self._beacon_on_seconds - state.beacon_phase
        else:
            state.beacon_on = False
            state.beacon_seconds_left = period - state.beacon_phase

    def _advance_wanderer(self, delta_time: float) -> None:
        """Vai e volta entre as duas pontas do trilho, refletindo nas
        bordas.

        A reflexao espelha a sobra em vez de so grudar no extremo: grudar
        faria a lanterna parar um frame na ponta a cada virada, e com a
        velocidade baixa que o jogo usa essa pausa e visivel -- e uma pausa
        que o jogador leria como 'ela para aqui', planejaria em cima disso,
        e seria mentira."""
        state, terrain = self._state, self._terrain
        if not terrain.has_wanderer:
            return

        low = float(terrain.wander_min_col)
        high = float(terrain.wander_max_col)
        position = state.wander_col + state.wander_dir * self._wanderer_speed * delta_time
        span = high - low
        while position < low or position > high:
            if position < low:
                position = low + (low - position)
                state.wander_dir = 1.0
            if position > high:
                position = high - (position - high)
                state.wander_dir = -1.0
            if span <= 0.0:
                position = low
                break
        state.wander_col = position

    def _advance_source(self, delta_time: float) -> None:
        """Respiracao senoidal entre as duas intensidades.

        Senoide e nao dente-de-serra porque o que o jogador le nao e a
        intensidade, e a BORDA do chao aceso -- e uma borda que para e volta
        suavemente pode ser acompanhada de perto, enquanto uma que salta do
        maximo pro minimo so pode ser evitada de longe. O objetivo e que dar
        um passo atras no instante certo baste."""
        state, terrain = self._state, self._terrain
        if not terrain.has_source:
            state.source_intensity = 0.0
            state.source_alt_intensity = 0.0
            return

        state.source_phase = (state.source_phase + delta_time) % self._source_period
        span = self._source_max - self._source_min
        breath = 0.5 - 0.5 * math.cos(math.tau * state.source_phase / self._source_period)
        state.source_intensity = self._source_min + span * breath
        # A segunda fonte respira meio periodo atras: quando uma incha, a
        # outra esvazia, e a faixa segura entre as duas vai e vem sozinha.
        state.source_alt_intensity = self._source_min + span * (1.0 - breath)

    def _advance_eclipse(self, delta_time: float) -> None:
        """O prazo comeca no primeiro toque de QUALQUER um dos dois -- nao no
        inicio da fase. O jogador pode planejar a travessia com calma; o
        relogio so anda depois que alguem pisou."""
        state, terrain = self._state, self._terrain
        if not terrain.has_eclipse:
            return

        if not state.eclipse_touched and self._someone_is_standing_on_eclipse():
            state.eclipse_touched = True
            state.eclipse_seconds_left = self._eclipse_seconds

        if not state.eclipse_touched:
            return

        state.eclipse_seconds_left -= delta_time
        if state.eclipse_seconds_left <= 0.0:
            state.eclipse_seconds_left = 0.0
            terrain.collapse_eclipse()

    def _someone_is_standing_on_eclipse(self) -> bool:
        """Um ser esta sobre a zona quando a celula IMEDIATAMENTE abaixo dele
        e de eclipse -- e a celula dele proprio nunca e (estar dentro de uma
        celula solida nao acontece). Dois seres, laco de duas iteracoes."""
        state, terrain = self._state, self._terrain
        for side in (LUMEN, UMBRA):
            col = int(state.cell[side, 0])
            row = int(state.cell[side, 1]) + 1
            if row < terrain.rows and bool(terrain.eclipse[row, col]):
                return True
        return False
