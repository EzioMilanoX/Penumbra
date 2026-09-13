"""
Conquistas -- e a resposta para "por que colecionar fragmentos?".

O jogo tinha trinta fragmentos e nenhum motivo para apanha-los: um contador
na tela de titulo, e so. Um colecionavel sem consequencia e um desvio que
custa risco e nao paga nada, e o jogador aprende isso na terceira fase.

A resposta estava no proprio nome deles. Sao **fragmentos da fonte**, e a
ultima tela do jogo pergunta se os dois querem se fundir NELA. Entao:

    **nao se funde uma fonte que nunca foi remontada.**

Com os trinta, "fundir" e uma escolha de verdade. Sem eles, a tela diz
quantos faltam e a unica saida e seguir dois. Nao e uma tranca -- nenhuma
fase fica bloqueada, o jogo inteiro continua jogavel, e da pra voltar,
apanhar os que faltam e refazer a escolha. E uma consequencia.

As conquistas seguem a mesma regra: nenhuma premia repeticao ou tempo de
tela. Todas premiam ter **entendido alguma coisa** -- vencer sem usar
habilidade nenhuma, deixar as duas formas na mesma fase, atravessar a
escolta em dois. Sao coisas que o jogador faz de proposito ou nao faz nunca.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class Achievement:
    """Uma conquista: identidade estavel, titulo, e o que ela reconhece."""

    key: str
    title: str
    description: str


FIRST_LIGHT = "primeira_luz"
CHAPTER_ONE = "aprendiz"
CHAPTER_TWO = "misturador"
CHAPTER_THREE = "especialista"
WHOLE_SOURCE = "a_fonte_inteira"
NO_ABILITY = "sem_as_maos"
FIRST_TRY = "de_primeira"
IN_TWO = "a_dois"
ESCORT_IN_TWO = "escolta"
BOTH_FORMS = "renuncia_dupla"

CATALOG: Tuple[Achievement, ...] = (
    Achievement(FIRST_LIGHT, "Primeira Luz", "Vencer a primeira fase."),
    Achievement(CHAPTER_ONE, "Aprendiz", "Vencer o capítulo de aprender inteiro."),
    Achievement(CHAPTER_TWO, "Misturador", "Vencer o capítulo de misturar inteiro."),
    Achievement(CHAPTER_THREE, "Especialista", "Vencer o capítulo das especiais inteiro."),
    Achievement(WHOLE_SOURCE, "A Fonte Inteira", "Apanhar todos os fragmentos."),
    Achievement(NO_ABILITY, "Sem as Mãos", "Vencer uma fase sem ligar nenhuma habilidade."),
    Achievement(FIRST_TRY, "De Primeira", "Vencer uma fase sem morrer nem reiniciar."),
    Achievement(IN_TWO, "A Dois", "Vencer uma fase em dois jogadores."),
    Achievement(ESCORT_IN_TWO, "Escolta", "Vencer uma fase de escolta em dois jogadores."),
    Achievement(BOTH_FORMS, "Renúncia Dupla", "Deixar as duas formas na mesma fase."),
)

_BY_KEY = {achievement.key: achievement for achievement in CATALOG}


def title_of(key: str) -> str:
    achievement = _BY_KEY.get(key)
    return achievement.title if achievement else key


def evaluate(catalog, progress, level_index: int, state, clean_run: bool, duo: bool):
    """
    As conquistas que esta vitoria acabou de destravar.

    Devolve so as NOVAS, em ordem de catalogo, pra que o chamador possa
    anuncia-las. Nao escreve nada: quem grava e o fluxo, junto com o resto
    do progresso, numa gravacao so.

    Recebe `state` porque metade das condicoes e sobre COMO a fase foi
    vencida -- sem habilidade, sem morrer, com as duas formas deixadas -- e
    isso nao sobrevive ao fim da tentativa.
    """
    earned = set()
    level = catalog.at(level_index)

    if level_index == 0:
        earned.add(FIRST_LIGHT)
    if not bool(state.used_ability):
        earned.add(NO_ABILITY)
    if clean_run:
        earned.add(FIRST_TRY)
    if duo:
        earned.add(IN_TWO)
        if level.has_duo_variant:
            earned.add(ESCORT_IN_TWO)
    if all(bool(spent) for spent in state.form_spent):
        earned.add(BOTH_FORMS)

    chapter_keys = {1: CHAPTER_ONE, 2: CHAPTER_TWO, 3: CHAPTER_THREE}
    for chapter in catalog.chapters:
        key = chapter_keys.get(chapter.number)
        if key and all(progress.completed[i] for i in range(chapter.first, chapter.last + 1)):
            earned.add(key)

    if all(progress.shards):
        earned.add(WHOLE_SOURCE)

    fresh = [a.key for a in CATALOG if a.key in earned and a.key not in progress.achievements]
    progress.achievements.update(fresh)
    return fresh
