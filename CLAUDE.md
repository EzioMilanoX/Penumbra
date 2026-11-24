# CLAUDE.md — Penumbra

Guia para o Claude Code neste projeto. Idioma: PT-BR (texto do jogo **com acento**; comentários
e docstrings do código sem acento, como o resto do repo).

## O que é
Puzzle-platformer de luz e sombra sobre a **OuroborosEngine** (repo irmão `../OuroborosEngine`,
não vendorizada): a Lumen pisa no éter aceso, a Umbra no apagado, e os dois não podem se tocar.
30 fases (+2) em 3 capítulos, solo (TAB troca de ser), duo local e **solo com eco** (GAM-20).
Blueprint GAM-15. O README é o documento de design — leia a seção do que for mexer.

## Rodar / testar
```bash
python -m penumbra.main            # SEMPRE da raiz, como módulo
pytest                             # headless (~45 s); roda a simulação real
ruff check .                       # config em pyproject.toml (E, F, I, UP, B; sem B905)
python -m tools.audit_levels       # luz/alcance por fase (instrumento, não falha)
python -m tools.generate_music     # regrava data/music/*.wav — rode se mexer no gerador
python -m tools.build_exe          # dist/Penumbra/ (onedir)
```
Rodar sem janela (fumaça, capturas): `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy`, `build_game`
e `game_loop.tick_once(dt)`; `pygame.display.get_surface()` dá o quadro.

## Engine
Usa a engine local (editável). **O eco depende de `ouroboros.bootstrap.replay`, que ainda não
tem release** (local, não commitado na engine em 2026-11-24): antes de um build/release do
Penumbra, a engine precisa commitar e versionar esse módulo, e o `pyproject.toml` daqui subir
o `ouroboros-engine>=`. Não modifique a engine a partir daqui; lacunas contornadas ficam
anotadas no README ("O que foi parar na engine").

## Mapa
- `penumbra/composition.py` — monta o World e a **ordem dos sistemas**; `build_game` (janela,
  áudio, música, falas) e `build_simulation` (headless, o que os testes usam).
- `penumbra/state.py` — `DualityState` (todo estado por frame) e `LevelRuntime` (troca de fase).
- `penumbra/systems/` — um `ISystem` por regra. Nenhum importa pygame.
- `penumbra/scenes.py` — fluxo de telas (`PenumbraFlow`) e cenas: fase, eco, fala, pausa, menu.
- `penumbra/tape.py` — **solo com eco**: `TapeInput` (roteia Lumen←fita, Umbra←teclado),
  `TapeSession` (gravar/rebobinar/paradoxo, tick fixo).
- `penumbra/audio.py` — efeitos sintetizados (`PenumbraAudio`) e música (`PenumbraMusic`).
- `penumbra/story.py` + `data/story/interludes.json` — as falas na porta de cada capítulo.
- `penumbra/hud.py`, `penumbra/menu.py` — desenho (fora do `World`: alocam).
- `data/levels/*.json` — fases; `duo` (diff do modo dois jogadores), `echo` (nota do eco).
- `tools/generate_music.py` — a música, determinística; os WAVs ficam em `data/music/`.

## Regras que já custaram caro
- **Fase nova ou mudada precisa passar pelos dois guardiões**: polaridade
  (`tests/test_shipped_levels.py`) e geometria (`tests/test_reachability.py`).
- **Marca `echo` numa fase exige solução jogada** em `tests/test_tape_echo.py` (`_SOLVERS`);
  o teste falha se houver fase marcada sem solução. Só fases com variante de duo.
- **Eco é determinístico só se nada vazar entre passadas**: nada de relógio real nem RNG nos
  sistemas, e todo começo de gravação/reprodução passa por `TapeSession._reset_world` (reset +
  grades de colisão zeradas). Sem isso o eco acusa paradoxo no tick zero.
- `TAPE_ACTIONS`: a ordem é o formato da fita.
- Toda ação lida no código precisa estar em `data/input_bindings/penumbra_keyboard.json`
  (há teste); o carregador de bindings não aceita chaves de comentário.
- Música: um teste compara os WAVs com o gerador — mudou o gerador, rode `tools.generate_music`.
- Texto na tela: testes medem que cabe (largura ~0,6 em por glifo). Rode `pytest` depois de
  mudar qualquer frase.
- Progresso em `%APPDATA%/Penumbra/progress.json`; testes usam `tmp_path`, nunca o save real.

## Fazer depois (anotado)
- Eco: regravar em ramos (guardar a fita anterior), e mais fases de dupla com eco.
- Música: faixa própria para o menu e para o fim.
