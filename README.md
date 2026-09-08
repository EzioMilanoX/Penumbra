# Penumbra — Luz e Sombra: Dualidade

Puzzle-platformer de um jogador só sobre dois seres que não podem se tocar e
não conseguem avançar separados. Vertical slice de 4 fases construído sobre a
[OuroborosEngine](https://github.com/EzioMilanoX/OuroborosEngine) — a engine
vive no repositório dela, não é vendorizada aqui.

```bash
git clone https://github.com/EzioMilanoX/OuroborosEngine.git
git clone https://github.com/EzioMilanoX/Penumbra.git

pip install -e ./OuroborosEngine        # numpy + pygame-ce vêm com ela
cd Penumbra && python -m penumbra.main  # rodar SEMPRE da raiz, como módulo
```

`python -m` não é preferência de estilo: os imports são absolutos
(`from penumbra...`) e os caminhos de `config.json` são relativos à raiz do
projeto, então rodar `python penumbra/main.py` falha.

Controles: **A/D** mover · **ESPAÇO** pular · **J** habilidade · **TAB** trocar
de ser · **R** reiniciar a fase · **ESC** sair.

---

## A ideia em uma frase

O mundo não tem um chão: tem dois, e eles se excluem. Cada célula de **éter**
é piso sólido para exatamente um dos dois seres, dependendo de haver luz ali
*naquele instante* — então tudo que um faz para abrir caminho fecha o do
outro.

## Os dois seres

|  | **Lumen** (luz) | **Umbra** (sombra) |
|---|---|---|
| corpo | círculo branco, pequeno | bloco escuro com orla, largo |
| movimento | 200 px/s, salto de 3,5 células | 108 px/s, salto de 2 células |
| pisa em | rocha + éter **aceso** | rocha + éter **apagado** |
| morre | onde a luz cai abaixo de `0.12` (**se apaga**) | onde a luz passa de `0.60` (**se dissolve**) |
| habilidade (**J**) | **Facho** — emite luz ao redor de si, solidificando éter escuro | **Absorção** — abre um bolsão de escuridão, apagando lâmpadas dentro dele |

Nenhuma das duas mortes é instantânea: um medidor sobe enquanto o perigo dura
e desce quando passa. Atravessar correndo uma nesga da polaridade errada é uma
decisão possível — e é o que dá às habilidades a função de ferramenta em vez
de interruptor.

## O conflito, concretamente

Entre os dois limiares de morte existe uma **penumbra** onde os dois
sobrevivem, e é só nela que uma fase pode ser resolvida. O limiar de solidez
do éter (`0.35`) fica no meio dessa faixa:

```
0.0        0.12                0.35                0.60          1.0
 |───────────|───────────────────|──────────────────|─────────────|
   Lumen se     éter apagado         éter aceso        Umbra se
   apaga        (chão da Umbra)      (chão da Lumen)   dissolve
             └──────── os dois sobrevivem aqui ───────┘
```

Disso saem as situações que as fases exploram:

- **O facho da Lumen tira o chão da Umbra.** Acender éter para si mesma
  significa despolarizar o piso onde o outro está parado esperando.
- **A absorção da Umbra apaga a Lumen.** Engolir uma lâmpada para criar chão
  próprio deixa a Lumen no escuro — e ela tem cerca de um segundo.
- **A carga esgota.** Cada habilidade tem ~3,2 s ligada e se desliga sozinha
  ao zerar, recompondo devagar enquanto desligada. É isso que faz a
  solidificação ser *temporária*, e é isso que transforma cada fase num
  problema de sequência em vez de um botão ligado para sempre.
- **O ser inativo não está protegido.** Ele fica parado, mas continua sujeito
  à gravidade e ao próprio chão. Se você mudar a polaridade sob ele enquanto
  comanda o outro, ele cai.

## As quatro fases

| # | Nome | O que ela ensina |
|---|---|---|
| 1 | **Duas Polaridades** | Alternância (TAB) e leitura do terreno. Duas pistas, o mesmo material de éter: acesa em cima, apagada embaixo. Vencível **só andando** — nenhuma habilidade. |
| 2 | **O Mesmo Chão** | As duas habilidades. Uma ponte só, escura por padrão: a Umbra atravessa de graça, a Lumen precisa do facho. Depois a Umbra tem que passar por uma lâmpada absorvendo — o que apaga o abrigo da Lumen do outro lado. |
| 3 | **Revezamento** | Timing e carga. Dois andares de éter, quatro células um do outro: o facho da Lumen no andar de cima acende o éter do de baixo e derruba a Umbra. Um atravessa, depois o outro. |
| 4 | **Eclipse** | A porta de polaridade, e a **sombra projetada pela rocha** — a saliência de pedra é o que impede o facho da Lumen de vazar até a zona de sombra da Umbra. |

### Alfabeto das fases (`data/levels/*.json`)

```
#  rocha (sólida para os dois, bloqueia luz)     A  spawn da Lumen
~  éter (sólido para um por vez)                 B  spawn da Umbra
*  lâmpada                                       X  portal da Lumen
D  porta de polaridade                           Y  portal da Umbra
L  zona de luz (gatilho da Lumen)                .  vazio
S  zona de sombra (gatilho da Umbra)
```

A última linha da grade é sempre vazia: é o abismo. `Grid2D` trata
fora-dos-limites como sólido, então sem essa linha ninguém cairia de verdade.

## Como a luz funciona

Um flood geodésico de 8 vizinhos, relaxado 14 vezes por frame sobre a grade
40×22 — cada passe empurra a luz uma célula, perdendo `1/9` de intensidade
(diagonais custam `√2` a mais). Isso dá três coisas que uma soma de discos não
daria:

1. **A luz contorna paredes em vez de vazar por elas** — a sombra projetada
   pela rocha, de que a fase 4 depende inteiramente, existe de graça.
2. **O alcance de uma fonte sai da intensidade dela**:
   `(I − 0.35) × 9` células até deixar de solidificar éter. Uma lâmpada
   alcança 5,85 células; a Lumen fica segura até 7,92 dela; a Umbra se
   dissolve dentro de 3,6. São esses três números que permitem desenhar uma
   fase sem adivinhar.
3. **A sombra obedece a mesma geometria da luz** — é o mesmo flood com outra
   semente, então o bolsão da Umbra também respeita paredes.

Os vizinhos diagonais não são cosméticos: só com os 4 ortogonais a distância
resultante é a de Manhattan e uma lâmpada acende um **losango**, com alcance
diagonal ~71% do horizontal. `tests/test_light_field.py` guarda isso.

## Arquitetura

```
penumbra/
  main.py            ponto de entrada
  config.json        EngineConfig (janela, capacidade, caminhos de dados)
  composition.py     monta o World, os dois seres e a ORDEM dos sistemas
  tuning.py          lê data/difficulties/penumbra/basic.json
  terrain.py         máscaras densas de uma fase, recarregáveis no lugar
  levels.py          catálogo de data/levels/*.json
  state.py           estado compartilhado + troca de fase
  scenes.py          quando o mundo anda e quando congela
  hud.py             HUD e avisos de fim de fase
  systems/
    duality_control_system.py   input -> velocity dos dois seres
    light_field_system.py       a luz, e as duas grades de colisão
    polarity_door_system.py     a porta que exige os dois ao mesmo tempo
    outcome_system.py           as quatro mortes e a única vitória
    presentation_system.py      estado -> pixels
    quit_on_action_system.py
data/                dificuldade, bindings, arquétipos, fases
assets/penumbra.ico  ícone do atalho (tools/generate_icon.py o refaz)
tests/               63 testes headless
tools/               audit_levels.py (balanceamento de luz), generate_icon.py
```

### Dois chãos na mesma simulação

É o ponto não-óbvio do projeto. `TileCollisionSystem` resolve toda entidade
com Transform+Velocity+Hitbox contra **uma** grade — mas os nomes das três
pools são parâmetros do construtor. Então Penumbra cria uma segunda pool de
hitbox (`hitbox_shadow`) e registra **dois** `TileCollisionSystem`:

- um contra a grade da luz, olhando só quem tem `hitbox` → **Lumen**;
- outro contra a grade da sombra, olhando só quem tem `hitbox_shadow` → **Umbra**.

Nenhum dos dois sabe que o outro existe, e nenhum sistema genérico da engine
ganhou um ramo condicional. É o mesmo idioma que a própria engine documenta
para "algumas entidades precisam de física diferente" (ver a docstring do
`GravitySystem` sobre entidades imunes à gravidade precisarem de uma pool
`velocity` separada).

O `LightFieldSystem` reescreve as duas grades a cada frame, e é só isso que
faz a ação de um ser desfazer o terreno do outro.

### Ordem dos sistemas

```
1. PhysicsSystem          (engine)   integra posição
2. CollisionSystem        (engine)   ocioso aqui — só Lumen tem `hitbox`
3. TileCollisionSystem    (engine)   Lumen contra a grade da luz
4. TileCollisionSystem    (Penumbra) Umbra contra a grade da sombra
5. GravitySystem          (Penumbra) fecha o contrato Physics -> Tile* -> Gravity
6. DualityControlSystem              escreve `velocity` depois de tudo acima
7. LightFieldSystem                  recalcula a luz e as duas grades
8. PolarityDoorSystem                lê a luz deste frame
9. OutcomeSystem                     lê posições já resolvidas
10. PresentationSystem               só pixels
11. QuitOnActionSystem
```

`CompositionRoot.build()` registra 1–3 e sempre nessa ordem; `gravity_y` é
deliberadamente **omitido** na chamada para que o `GravitySystem` possa entrar
depois do segundo `TileCollisionSystem`, respeitando o contrato
`PhysicsSystem → TileCollisionSystem → GravitySystem` que as docstrings da
engine exigem.

### A Constituição da engine, honrada

- **Zero-GC no gameplay.** Todo buffer do campo de luz e da apresentação é
  alocado na composição; `update()` só faz ufuncs NumPy com `out=`. As 880
  entidades de célula e os dois seres existem do primeiro ao último frame do
  processo — **trocar de fase não cria nem destrói nenhuma entidade**, só
  reescreve as máscaras do `Terrain` no lugar. Custo medido: **2,8 ms/frame**
  (teto de ~354 fps).
- **Logic vs Presentation.** Nenhum módulo de `penumbra` importa `pygame`. O
  HUD usa `draw_text`/`draw_ui_rect`, que alocam, e por isso vive no callback
  de `GameLoop.set_on_draw_ui` — nunca dentro de um `ISystem`.
- **Data-Driven.** Todo número de balanceamento está em
  `data/difficulties/penumbra/basic.json` e é lido de verdade via
  `EngineConfig.difficulty_path` (o slice do Platformer deixava esse campo
  como débito declarado); as fases são JSON; os arquétipos são JSON, e é um
  deles que declara a pool `hitbox_shadow` da Umbra.

## Testes e auditoria

```
pytest -q                      # 63 testes, ~8 s, headless
python -m tools.audit_levels   # relatório de balanceamento de luz por fase
```

Os testes rodam a **simulação real**: `build_simulation` monta o mesmo `World`
com os mesmos sistemas na mesma ordem que o jogo com janela, só sem
renderer/input/áudio concretos (via `CompositionRoot.build_world`). Nenhum
teste reimplementa uma regra para depois conferi-la contra si mesma.

Os mais fortes terminam **as quatro fases jogando** — um controlador
rudimentar que segura as teclas e aperta TAB e J na ordem certa. É essa a
prova de que o slice tem solução, e é ela que quebra se um ajuste de
balanceamento fechar o único caminho de alguma fase. Eles também documentam a
ordem obrigatória de cada fase: nas fases 2, 3 e 4 a Umbra precisa atravessar
antes, porque o facho da Lumen despolariza o chão dela.

`tools/audit_levels.py` não afirma nada e não falha: é o instrumento que
respondeu às perguntas de projeto das quatro fases (onde o éter fica sólido,
onde cada ser sobrevive, se o facho vaza até a zona de sombra). Ele achou um
soft-lock real na fase 4 — a Lumen descia da saliência para atravessar a porta
e não tinha como voltar à zona de luz —, corrigido com dois degraus de rocha.

## Escopo

Este é o vertical slice das mecânicas centrais. Ficaram **fora**, do documento
de design original:

- **Zona de eclipse** (área que os dois pisam por tempo limitado)
- **Sacrifício de forma** (a Umbra cobrindo a Lumen para protegê-la)
- **Controle simultâneo** dos dois seres (um em cada analógico)
- **Boss fight** e a narrativa com a escolha da fusão
- **Áudio** — a engine tem `IAudioEngine` e bancos data-driven, mas o slice
  não tem nenhum asset de som

## Paleta

Preto, branco e um terceiro tom dourado. O dourado não decora: aparece **só**
no que exige os dois seres ao mesmo tempo — as zonas de polaridade, a porta
que elas destrancam, os dois portais, e o anel que marca quem está sob
comando. Quando a tela mostra dourado, o jogador está olhando para o único
tipo de problema que nenhum dos dois resolve sozinho.

A única exceção é o medidor de perigo, num carmim dessaturado: ele precisa ser
lido antes de ser pensado, e o dourado não podia servir — significa
cooperação, o oposto do que aquele medidor avisa.

## Licença

Código próprio, importando `ouroboros` como biblioteca. A OuroborosEngine é
MPL-2.0 com copyleft por arquivo: nenhum arquivo dela foi modificado por este
projeto.
