"""Porta de polaridade: abre quando um esta na luz e o outro na sombra."""
from __future__ import annotations

from ouroboros.core.systems.base_system import ISystem
from ouroboros.core.world import World

from penumbra.state import DualityState, LUMEN, UMBRA
from penumbra.terrain import Terrain


class PolarityDoorSystem(ISystem):
    """
    Destranca as celulas `D` de uma fase no instante em que Lumen esta
    numa zona `L` ACESA e Umbra numa zona `S` APAGADA, ao mesmo tempo.

    A porta fica aberta pro resto da fase, de proposito. A condicao e
    simultanea -- e nisso esta o puzzle, ja que o jogador comanda um ser
    por vez e precisa deixar o primeiro parado numa zona cuja polaridade
    ele mesmo pode destruir ao mover o segundo -- mas se a abertura
    tambem fosse momentanea, ninguem conseguiria atravessar: para passar
    pela porta e preciso sair da zona, o que a fecharia no mesmo frame.

    Roda depois do `LightFieldSystem` (le a luz deste frame) e antes dele
    no frame seguinte, quando as duas grades de colisao passam a nao
    considerar mais as celulas da porta como solidas.

    Uma fase abre a porta de UM dos dois jeitos, nunca dos dois (o `Terrain`
    recusa a combinacao): pelas **zonas de polaridade**, que exigem os dois
    seres em posicao ao mesmo tempo e travam a porta aberta pra sempre, ou
    por uma **placa de pressao**, que a mantem aberta so enquanto alguem
    esta em cima. Os dois gatilhos abrem a mesma coisa com regras opostas, e
    nada na tela diria qual esta valendo.
    """

    def __init__(self, terrain: Terrain, state: DualityState) -> None:
        self._terrain = terrain
        self._state = state

    def _someone_on_plate(self) -> bool:
        state, terrain = self._state, self._terrain
        for side in (LUMEN, UMBRA):
            col, row = int(state.cell[side, 0]), int(state.cell[side, 1])
            if bool(terrain.plate[row, col]):
                return True
        return False

    def update(self, world: World, delta_time: float) -> None:
        del world, delta_time
        state, terrain = self._state, self._terrain

        if terrain.has_plate:
            # Placa: a porta fica aberta SO enquanto alguem esta em cima.
            # Nao trava, e e essa a diferenca -- e o unico lugar do jogo onde
            # o ser parado tem uma funcao em vez de so estar vulneravel.
            state.door_open = self._someone_on_plate()
            return

        if state.door_open:
            return

        lumen_col, lumen_row = int(state.cell[LUMEN, 0]), int(state.cell[LUMEN, 1])
        umbra_col, umbra_row = int(state.cell[UMBRA, 0]), int(state.cell[UMBRA, 1])

        lumen_ready = bool(terrain.zone_light[lumen_row, lumen_col]) and bool(state.lit[lumen_row, lumen_col])
        umbra_ready = bool(terrain.zone_shadow[umbra_row, umbra_col]) and not bool(state.lit[umbra_row, umbra_col])
        if lumen_ready and umbra_ready:
            state.door_open = True
