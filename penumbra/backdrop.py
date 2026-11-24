"""
O fundo: ar e rocha, num campo continuo.

O jogo e sobre luz e desenhava luz como um tabuleiro de xadrez -- uma grade de
28 x 17 quadrados de 32 px, cada um de um cinza chapado. O campo de luz sempre
foi continuo; faltava resolucao no DESENHO.

A primeira resposta foi subdividir: 1904 sub-quadros interpolados a mao, 2 ms
por frame, e ainda assim degraus de 16 px. Ela existia porque `draw_batch`
cobra por entidade -- e a resposta certa era a engine ganhar
`IRenderer.draw_field`, que desenha um campo inteiro em UMA chamada, com
filtragem bilinear de verdade, em resolucao de tela. Este arquivo e o que
sobrou daquele sistema depois que a engine passou a fazer o trabalho: dois
arrays de 28 x 17 e uma chamada.

## O que pode ser suavizado, e por que so isto

Ar e rocha sao os dois unicos papeis da grade que **nao carregam decisao**: o
ar nao e chao de ninguem, a rocha e chao dos dois, sempre. Todo o resto --
eter, contra-eter, crosta, placa, portal -- responde *"de quem e este chao,
agora?"*, e essa resposta tem de ser lida na celula exata. Suavizar eter seria
trocar atmosfera por erro, e nada na tela diria que foi isso que aconteceu.

E dentro do proprio fundo a divisao continua, que e exatamente o contrato de
`draw_field`: a **cor** interpola (quanta luz banha esta pedra e uma pergunta
com resposta no meio do caminho) e a **forma** nao (a silhueta da rocha e uma
parede, e meia parede nao existe).
"""
from __future__ import annotations

import numpy as np

from penumbra.systems.presentation_system import AIR_GLOW, AIR_GLOW_MAX_ALPHA, ROCK_LIT, ROCK_UNLIT
from penumbra.terrain import ROLE_ROCK

VOID = (8, 8, 14)
"""A cor com que `IRenderer.begin_frame` limpa a tela.

Precisa estar aqui porque o fundo entrega cor OPACA: o ar no escuro total tem
de sair exatamente igual ao vazio atras dele, senao a metade apagada de cada
fase ganha uma mancha com a forma da grade."""


class Backdrop:
    """
    Os dois arrays que `IRenderer.draw_field` pede, mantidos prontos.

    Vive fora do `World` pelo mesmo motivo que `SparkField`: nao e entidade
    de nada, e desenhar e responsabilidade explicita de quem chama --
    tipicamente a cena, ANTES do mundo, porque fundo e o que fica atras.

    Zero-GC: os dois arrays nascem aqui e sao reescritos no lugar.
    """

    def __init__(self, state, terrain, tuning) -> None:
        self._state = state
        self._terrain = terrain
        rows, cols = terrain.rows, terrain.cols

        # `IRenderer.draw_field` recebe (colunas, linhas), que e a convencao
        # de superficie; as mascaras do terreno sao (linhas, colunas). A
        # transposicao e feita na escrita, por view, sem copia.
        self._air = np.zeros((cols, rows, 3), dtype=np.uint8)
        self._rock = np.zeros((cols, rows, 3), dtype=np.uint8)
        self._rock_alpha = np.zeros((cols, rows), dtype=np.uint8)

        self._red = np.zeros((rows, cols), dtype=np.float32)
        self._green = np.zeros((rows, cols), dtype=np.float32)
        self._blue = np.zeros((rows, cols), dtype=np.float32)
        self._ramp = np.zeros((rows, cols), dtype=np.float32)
        self._channel = np.zeros((rows, cols), dtype=np.float32)
        self._mask = np.zeros((rows, cols), dtype=bool)

        self._width = float(cols * terrain.cell_size)
        self._height = float(rows * terrain.cell_size)

    def update(self) -> None:
        """Dois campos, e sao dois por uma razao exata.

        Um campo so nao consegue ao mesmo tempo **cobrir a tela inteira** e
        **recortar a parede**: o alpha e um canal, e ou ele vale 255 em tudo
        (e a cor da rocha vaza pra fora dela, borrando a silhueta) ou ele
        recorta a rocha (e entao o brilho do ar tem de morar no alpha, que
        por contrato NAO interpola -- e o ar sai quadriculado).

        As duas tentativas foram feitas e as duas apareceram na tela. Entao:

        - **o ar** e um campo opaco de tela cheia, sem mascara, com toda a luz
          na cor. Ele passa por baixo da rocha, e nao faz mal: a rocha e
          desenhada por cima.
        - **a rocha** e um campo com mascara recortada seca. A cor dela e
          calculada em TODA celula, inclusive fora da rocha, pra que a
          bilinear das bordas leia pedra iluminada e nao preto.
        """
        light = self._state.display_light
        role = self._terrain.role
        np.clip(light, 0.0, 1.0, out=self._ramp)

        # --- o ar, composto a mao contra o vazio ---
        np.multiply(self._ramp, AIR_GLOW_MAX_ALPHA / 255.0, out=self._channel)
        for index, (void, glow) in enumerate(zip(VOID, AIR_GLOW)):
            np.multiply(self._channel, float(glow - void), out=self._red)
            np.add(self._red, float(void), out=self._red)
            self._air[:, :, index] = self._red.T

        # --- a rocha, em toda parte, recortada pelo alpha ---
        for index, (unlit, lit) in enumerate(zip(ROCK_UNLIT, ROCK_LIT)):
            np.multiply(self._ramp, float(lit - unlit), out=self._red)
            np.add(self._red, float(unlit), out=self._red)
            self._rock[:, :, index] = self._red.T

        np.equal(role, ROLE_ROCK, out=self._mask)
        self._rock_alpha[:] = 0
        self._rock_alpha.T[self._mask] = 255

    def draw(self, renderer) -> None:
        """Ar primeiro, rocha por cima. A ordem e a propria definicao de
        fundo: o ar e o que se ve onde nao ha pedra."""
        renderer.draw_field(self._air, 0.0, 0.0, self._width, self._height)
        renderer.draw_field(self._rock, 0.0, 0.0, self._width, self._height,
                            alpha=self._rock_alpha)
