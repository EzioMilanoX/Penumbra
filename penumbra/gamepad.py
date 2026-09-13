"""
O controle -- e o unico adaptador de backend que este repositorio escreve.

Penumbra e um jogo de sofa para dois, e ate aqui os dois dividiam um teclado:
o jogador 1 em WASD+ESPACO, o jogador 2 nas setas. Funciona e e apertado --
dois pares de maos a trinta centimetros um do outro, e ninguem pode se
levantar. Era a ultima lacuna que muda COMO se joga, e nao so o que se ve.

A engine nao resolve isso: `PygameInputProvider._resolve_binding` entende
`KEY_*` e `MOUSE_*` e mais nada, e o unico uso que ela faz de joystick e
`set_rumble`. Entao o adaptador vem pra ca -- nao pra dentro da engine, cujos
arquivos este projeto nunca modificou, e nao pra dentro do nucleo, que nunca
importa um backend concreto. Ele e registrado so em `build_game`, como o audio
e a poeira: removido, o jogo continua identico e so com teclado.

## Onde ele e amostrado, e por que isso e a parte dificil

`GameLoop.run()` chama `input_provider.poll()` uma vez por frame no provider
que o `CompositionRoot` construiu, e `GameLoop.input_provider` e uma
propriedade **somente-leitura** -- documentada como tal. Envolver o provider e
entregar o embrulho pro laco exigiria escrever em `_input_provider`, e
contrariar uma decisao explicita de API da engine pra ganhar um wrapper nao
vale o precedente.

Entao a amostragem se prende ao frame por outro caminho, todo ele publico:
`set_on_draw_ui` roda uma vez por frame, no fim, independente da cena -- ali o
controle so e marcado como **velho**. Quem de fato amostra e a PRIMEIRA
consulta de acao do frame seguinte, que acontece dentro do `update()` da cena,
no mesmo ponto em que o teclado acabou de ser amostrado pelo `poll()` da
engine. As bordas saem exatas e sem um frame de atraso -- amostrar dentro do
proprio `set_on_draw_ui` custaria os ~16 ms entre o fim de um frame e o
comeco do outro, o que num jogo de plataforma e a diferenca entre o coyote
time perdoar e nao perdoar.

## Um controle por jogador

O controle 0 dirige as acoes do jogador 1, o 1 dirige as `p2_*`. Nao ha
mistura: com um controle so no modo duo, o jogador 2 continua nas setas, que e
exatamente o arranjo que um sofa com um controle tem. E nenhum controle mexe
no menu do outro -- ha um cursor so, e dois donos brigando por ele e pior que
um dono.
"""
from __future__ import annotations

import json
from typing import Dict, Optional, Tuple

from ouroboros.interfaces.input_provider import IInputProvider

_BUTTONS: Dict[str, int] = {
    "PAD_A": 0, "PAD_B": 1, "PAD_X": 2, "PAD_Y": 3,
    "PAD_LB": 4, "PAD_RB": 5, "PAD_BACK": 6, "PAD_START": 7,
}
"""Numeracao de fato de todo controle que se apresenta como XInput -- o padrao
de Xbox, que DualShock e os genericos seguem quando o SDL os mapeia."""

_DIRECTIONS: Dict[str, Tuple[int, float]] = {
    "PAD_LEFT": (0, -1.0), "PAD_RIGHT": (0, 1.0),
    "PAD_UP": (1, -1.0), "PAD_DOWN": (1, 1.0),
}
"""Direcao -> (eixo, sinal). O direcional e o analogico esquerdo entram pelo
MESMO codigo: pro jogo sao a mesma intencao, e obrigar o jogador a saber qual
dos dois o menu escuta seria uma pergunta sem resposta boa."""

_ENGAGE = 0.55
_RELEASE = 0.30
"""Duas soleiras, e nao uma. Um analogico em repouso nao para em zero -- fica
tremendo perto dele, e com uma soleira so um polegar parado na fronteira
manda dezenas de bordas por segundo: na fase o ser vibra no lugar, e no menu o
cursor atravessa a lista sozinho. Com histerese a direcao so ENGATA em 0.55 e
so SOLTA abaixo de 0.30, e o tremor acontece inteiro dentro do vao."""


def load_gamepad_bindings(path) -> Dict[str, str]:
    """Le o JSON de bindings de controle. Chaves iniciadas por `_` sao
    descartadas -- o carregador de dificuldade da engine ja faz isso, o de
    teclas nao faz, e uma chave de comentario no JSON de teclas ja derrubou
    este jogo na abertura uma vez."""
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    return {k: v for k, v in data.items() if not k.startswith("_")}


class PygamePads:
    """
    Os controles fisicos, e a unica coisa deste repositorio que importa pygame.

    O import e adiado pro construtor para que o modulo continue importavel num
    processo headless sem video -- e toda chamada ao pygame vive num
    `try/except`, pelo mesmo criterio que a engine usa em `set_rumble`:
    **a ausencia de hardware nunca levanta**. Um controle desconectado no meio
    de uma fase nao pode ser o motivo de o jogo fechar.
    """

    def __init__(self) -> None:
        try:
            import pygame

            self._pygame = pygame
            if not pygame.joystick.get_init():
                pygame.joystick.init()
        except Exception:
            self._pygame = None
        self._pads = []
        self._known = -1
        self.refresh()

    def refresh(self) -> None:
        """Reabre a lista quando o numero de controles muda. `get_count()` e
        barato e reflete o que o `pygame.event.get()` do provider de teclado ja
        bombeou, entao dar as maos a um controle ligado com o jogo aberto nao
        custa nada nem pede um evento proprio."""
        if self._pygame is None:
            return
        try:
            count = self._pygame.joystick.get_count()
        except Exception:
            return
        if count == self._known:
            return
        self._known = count
        pads = []
        for index in range(count):
            try:
                pad = self._pygame.joystick.Joystick(index)
                pad.init()
                pads.append(pad)
            except Exception:
                pass
        self._pads = pads

    def count(self) -> int:
        return len(self._pads)

    def pressed(self, pad: int, button: int) -> bool:
        if pad >= len(self._pads):
            return False
        try:
            return bool(self._pads[pad].get_button(button))
        except Exception:
            return False

    def axis(self, pad: int, axis: int) -> float:
        """O analogico esquerdo e o direcional somados num valor so. O
        direcional manda quando esta sendo usado: ele e digital, entao um 1.0
        exato nunca pode perder pro tremor do analogico parado ao lado."""
        if pad >= len(self._pads):
            return 0.0
        handle = self._pads[pad]
        try:
            if handle.get_numhats() > 0:
                hat_x, hat_y = handle.get_hat(0)
                # O chapeu reporta CIMA como +1 e o analogico como -1. Sem
                # esta inversao o direcional andaria com o menu ao contrario.
                digital = float(hat_x) if axis == 0 else -float(hat_y)
                if digital:
                    return digital
        except Exception:
            pass
        try:
            return float(handle.get_axis(axis))
        except Exception:
            return 0.0


class GamepadInput(IInputProvider):
    """
    O provider do teclado, mais os controles, num `ou` logico.

    Nao substitui nada: toda consulta vai primeiro ao provider de dentro e so
    depois olha o controle. Um jogador de teclado nunca perde nada por haver um
    controle ligado, e no duo os dois arranjos podem se misturar -- controle e
    setas na mesma partida.
    """

    def __init__(self, inner: IInputProvider, bindings: Dict[str, str],
                 pads: Optional[PygamePads] = None,
                 player_two_prefix: str = "p2_") -> None:
        self._inner = inner
        self._pads = pads if pads is not None else PygamePads()
        self._prefix = player_two_prefix

        # Resolve os codigos UMA vez: no laco quente so restam inteiros.
        self._button: Dict[str, Tuple[int, int]] = {}
        self._direction: Dict[str, Tuple[int, int, float]] = {}
        for action, code in bindings.items():
            pad = 1 if action.startswith(player_two_prefix) else 0
            if code in _BUTTONS:
                self._button[action] = (pad, _BUTTONS[code])
            elif code in _DIRECTIONS:
                axis, sign = _DIRECTIONS[code]
                self._direction[action] = (pad, axis, sign)

        self._held: Dict[str, bool] = {}
        self._previous: Dict[str, bool] = {}
        self._stale = True

    # -- o encaixe no frame -------------------------------------------------

    def end_frame(self) -> None:
        """Registrado em `set_on_draw_ui`. So MARCA: quem amostra e a proxima
        consulta, ja dentro do frame seguinte (ver a docstring do modulo)."""
        self._stale = True

    def _sample(self) -> None:
        self._stale = False
        self._pads.refresh()
        if not self._pads.count():
            # Sem o `_previous` ser trocado TODO frame, um controle arrancado
            # com um botao apertado deixava `is_action_released` verdadeiro
            # pra sempre: o frame seguinte via `_held` vazio, nao mexia em
            # nada, e a borda de soltar se repetia ate o fim da partida.
            self._previous, self._held = self._held, {}
            return

        self._previous = self._held
        held: Dict[str, bool] = {}
        for action, (pad, button) in self._button.items():
            held[action] = self._pads.pressed(pad, button)
        for action, (pad, axis, sign) in self._direction.items():
            value = self._pads.axis(pad, axis) * sign
            # A histerese: quem ja estava engatado solta mais tarde do que
            # engatou. Sem o estado anterior aqui, nao ha histerese nenhuma.
            soleira = _RELEASE if self._held.get(action) else _ENGAGE
            held[action] = value >= soleira
        self._held = held

    def _fresh(self) -> None:
        if self._stale:
            self._sample()

    # -- IInputProvider -----------------------------------------------------

    def load_bindings(self, bindings_path: str) -> None:
        self._inner.load_bindings(bindings_path)

    def poll(self) -> None:
        self._inner.poll()

    def is_action_pressed(self, action_name: str) -> bool:
        if self._inner.is_action_pressed(action_name):
            return True
        self._fresh()
        return self._held.get(action_name, False) and not self._previous.get(action_name, False)

    def is_action_held(self, action_name: str) -> bool:
        if self._inner.is_action_held(action_name):
            return True
        self._fresh()
        return self._held.get(action_name, False)

    def is_action_released(self, action_name: str) -> bool:
        if self._inner.is_action_released(action_name):
            return True
        self._fresh()
        return self._previous.get(action_name, False) and not self._held.get(action_name, False)

    def get_axis(self, axis_name: str) -> float:
        return self._inner.get_axis(axis_name)

    def get_cursor_position(self):
        return self._inner.get_cursor_position()

    def wants_quit(self) -> bool:
        return self._inner.wants_quit()

    def set_rumble(self, low_freq: float, high_freq: float, duration_sec: float) -> None:
        self._inner.set_rumble(low_freq, high_freq, duration_sec)

    # -- o que a interface do jogo precisa saber ----------------------------

    @property
    def pad_count(self) -> int:
        """Quantos controles estao ligados. O rodape da fase muda de rotulo com
        isto: uma dica de controle que MENTE e pior que dica nenhuma."""
        self._pads.refresh()
        return self._pads.count()
