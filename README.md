# Penumbra — Luz e Sombra: Dualidade

Puzzle-platformer sobre dois seres que não podem se tocar e não conseguem
avançar separados. **Trinta fases** em três capítulos, menu com seleção
visual, colecionáveis e **multiplayer local**, construído sobre a
[OuroborosEngine](https://github.com/EzioMilanoX/OuroborosEngine) — a engine
vive no repositório dela, não é vendorizada aqui.

📖 **[Manual de campo](docs/index.html)** — a escala de luz, o alfabeto do
terreno, as doze fases e como dois chãos convivem numa simulação só.

```bash
git clone https://github.com/EzioMilanoX/OuroborosEngine.git
git clone https://github.com/EzioMilanoX/Penumbra.git

pip install -e ./OuroborosEngine        # numpy + pygame-ce vêm com ela
cd Penumbra && python -m penumbra.main  # rodar SEMPRE da raiz, como módulo
```

`python -m` não é preferência de estilo: os imports são absolutos
(`from penumbra...`) e os caminhos de `config.json` são relativos à raiz do
projeto, então rodar `python penumbra/main.py` falha.

O jogo abre numa **tela de título** que pergunta primeiro quantos jogadores —
dois botões grandes, **1 JOGADOR** e **2 JOGADORES**, com os controles de cada
modo escritos embaixo. A/D escolhe, ESPAÇO confirma.

**Título** → **seleção de fase** → **fase**. ESC recua uma tela por vez; só no
título ele encerra.

**Seleção de fase**: W/A/S/D escolher na grade · ESPAÇO jogar · ESC voltar ao
título.

**Um jogador**: A/D mover · ESPAÇO pular · S habilidade · TAB trocar de ser ·
R reiniciar · ESC voltar ao menu.

**Dois jogadores** (mesmo teclado): J1 = A/D, ESPAÇO, S · J2 = setas ←→, ↑, ↓.
Os dois lados têm o mesmo formato: mover nos lados, pular pra cima,
habilidade pra baixo.
Ninguém espera, e o contato entre os dois continua aniquilando os dois — o que
num jogador era uma armadilha ocasional, em dois é a fonte principal de
desastre.

Nenhuma fase é trancada. Com fases curtas, poder repetir a que ensinou uma
mecânica vale mais que a cerimônia de desbloquear — e cada card já diz, com
selos, o que você fez nela.

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
| movimento | 200 px/s, sobe degraus de até **3** células | 142 px/s, sobe degraus de **2** células |
| pisa em | rocha + éter **aceso** | rocha + éter **apagado** |
| morre | onde a luz cai abaixo de `0.12` (**se apaga**) | onde a luz passa de `0.60` (**se dissolve**) |
| habilidade (**S**) | **Facho** — emite luz ao redor de si, solidificando éter escuro | **Absorção** — abre um bolsão de escuridão, apagando lâmpadas dentro dele |
| só ela faz | — | **rompe a crosta**, empurrando com A/D. Irreversível. |

Nenhuma das duas mortes é instantânea: um medidor sobe enquanto o perigo dura
e desce quando passa. Atravessar correndo uma nesga da polaridade errada é uma
decisão possível — e é o que dá às habilidades a função de ferramenta em vez
de interruptor.

Sobre o salto: o que decide se um degrau é subível **não é a altura máxima**,
é quanto tempo o ser fica naquela altura. Subir num degrau exige ao menos 1
célula de deslocamento horizontal — o topo do degrau nunca está na coluna onde
o ser está de pé. A Umbra alcança 2,45 células de altura, mas a duas células
ela desloca só **1,43 coluna** — pouco mais que a única que subir exige — e a
três ela não chega. `penumbra/reachability.py` modela isso, e é o que impede
uma fase de pedir dela o que ela não faz.

## Os quatro terrenos

| | de quem é o chão | notas |
|---|---|---|
| **rocha** `#` | dos dois, sempre | o chão neutro, e é ele que torna as fases solúveis: alguém precisa ter onde esperar |
| **éter** `~` | de exatamente um, decidido pela luz **agora** | o conflito central |
| **crosta** `%` | dos dois — até a Umbra rompê-la | opaca. Romper é irreversível, e abre caminho para a luz que ela barrava |
| **eclipse** `=` | **dos dois ao mesmo tempo** — a única célula assim | mas com prazo: o primeiro passo de qualquer um inicia o colapso da zona inteira |
| **contra-éter** `;` | de exatamente um, **pela regra invertida** | sólido para a Lumen no *escuro* e para a Umbra na *luz* |
| **altar** `^` | não é chão — é onde se **larga a forma** | segure a habilidade em cima e ela fica ali *para sempre*; quem a deixou não a usa mais nesta fase |
| **véu** `:` | de ninguém — **atravessa-se a pé** | mas não se atravessa com luz. Do lado de lá há sombra sem parede, e lá dentro o facho **não existe** |
| **vidro** `-` | dos dois, sempre — e **a luz passa** | é o que torna possível empilhar dois andares: uma luz em cima acende o chão de baixo |
| **alavanca** `!` | de ninguém — pisar nela **troca o mundo** | éter vira contra-éter no mapa inteiro. Nenhuma célula muda de brilho, e cada ponte passa ao outro ser |

E três fontes de luz: a **lâmpada** `*`, fixa; o **farol** `o`, que acende e
apaga sozinho; a **lanterna errante**, uma lâmpada que percorre um trilho `>`
de ponta a ponta e volta; e a **fonte** `@`, que não anda — **incha**. A fonte
tem uma irmã `&` que respira meio período atrás dela: com as duas, a metade
acesa da sala vai e vem sozinha.

Mais dois marcadores: a **placa de pressão** `_`, que mantém uma porta aberta
só enquanto alguém está em cima dela, e o **fragmento da fonte** `+`, o
colecionável opcional de cada fase.

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
- **O farol inverte o conflito sem você pedir.** Aceso, a ponte de éter é chão
  da Lumen; apagado, é da Umbra. Até ele existir, os dois sentidos do conflito
  exigiam duas habilidades e duas decisões — aqui vêm de graça, e contra os
  dois. É a única coisa no jogo em que ninguém escolhe a hora.
- **O eclipse troca a pergunta.** Todo o resto do terreno responde "de quem é
  este chão?". O eclipse responde outra: **"dá tempo pros dois?"** É a única
  mecânica que os obriga a ocupar o *mesmo* espaço, em vez de pistas ou
  momentos separados — e o prazo só começa no primeiro passo, para não punir
  quem está pensando.
- **O contra-éter troca a pergunta "acendo ou apago?" por "acendo *o quê*?"**
  Com éter e contra-éter na mesma fase, uma única mudança de luz ajuda uma
  ponte e destrói a outra no mesmo instante. E ele tem uma consequência que
  nada mais no jogo tem: acender o próprio caminho **derruba a Lumen**, porque
  no contra-éter o chão dela é o escuro.
- **A placa dá função ao ser parado.** É o único lugar do jogo onde ele não
  está apenas vulnerável: alguém tem de ficar em cima para a porta continuar
  aberta. Em um jogador você estaciona e troca; em dois, um segura para o
  outro passar — e é aí que a cooperação aparece de verdade.
- **O altar troca poder por permanência, e cobra o poder.** As duas
  habilidades são fortes pela mesma razão: elas **acompanham** o ser. Todo
  problema do jogo é no fundo esse — a luz de que você precisa *ali* está
  *aqui*. O altar é a única resposta possível, e custa tudo: a pedra fica com
  a luz (ou com a escuridão) para sempre, e quem a deixou **não liga mais a
  habilidade nesta fase**. A barra fica vazia e não enche nunca mais.
  É a única coisa que abre uma ponte de contra-éter para a Umbra: ela precisa
  de luz e não sabe fazer luz.
- **A lanterna se atravessa acompanhando, não esperando.** O farol troca o
  dono do éter sem sair do lugar, e o jogador *espera a virada*. A lanterna
  leva o chão junto: a Lumen anda no passo dela, a Umbra anda sempre fora do
  círculo. Numa ponte longa a Umbra não atravessa de uma vez — a janela acesa
  volta por cima dela no meio do caminho — então toda ponte de lanterna tem
  uma **ilha de rocha** onde se espera a passagem.
- **O véu e o vidro separam duas coisas que eram uma só.** Até o ato III,
  toda célula sólida barrava luz e toda célula vazada a deixava passar: *ser
  chão* e *fazer sombra* eram a mesma pergunta, e por isso nenhuma fase tinha
  mais de um andar. O véu atravessa-se a pé e não com luz; o vidro é chão e
  deixa a luz descer. Cada um quebra a fusão para um lado.
- **O véu é a única coisa que tira o verbo da Lumen.** Dentro dele o facho
  simplesmente não existe — a semente é multiplicada pela máscara de
  propagação, que ali é zero. Ela continua com a habilidade ligada e ela não
  produz nada.
- **Sob o vidro, a luz de um serve ao outro.** É a única travessia do jogo em
  que isso acontece: a Lumen caminha na passarela, o facho desce pelo vidro, e
  o contra-éter quatro linhas abaixo vira chão da Umbra. Quatro linhas não é
  escolha estética — é a **única** distância em que o chão dela fica sólido
  (`>= 0.35`) e a célula onde ela anda não a dissolve (`<= 0.60`).
- **A fonte incha; a lanterna anda; o farol liga e desliga.** As três coisas
  que o mundo faz sozinho pedem três leituras diferentes: do farol se
  **espera**, a lanterna se **acompanha**, e da fonte se **recua** — ela vem
  buscar você onde você estava parado.
- **A alavanca muda a outra metade da pergunta.** Todo o resto do jogo
  responde *onde há luz agora?* — o facho acende, a absorção apaga, o farol
  pulsa, a lanterna anda, a fonte incha. A alavanca muda **de quem é o
  aceso**: a mesma ponte, a mesma luz, e o chão passa pro outro. É o único
  verbo que um ser aciona pensando no **outro** — e quem puxa costuma perder
  o próprio chão no mesmo instante.
- **A crosta não volta.** Todo o resto do terreno é interruptor — acender,
  apagar, acender de novo. A crosta, não: rompida, rompida para a fase
  inteira. É a única decisão do jogo que não dá para desfazer. E como ela é
  **opaca**, o buraco que a Umbra abre para passar deixa entrar a luz que ela
  barrava — e é a Umbra quem se dissolve na luz. Até aqui toda destruição de
  terreno ia da Lumen para a Umbra; esta vai da Umbra para ela mesma.

## A mesma fase, dois problemas

O que exige **parar um ser e comandar o outro** vira trivial quando os dois
andam ao mesmo tempo. E o contrário também: as fases de escolta sob o vidro
nasceram desenhadas para dois jogadores e tiveram de ser **afrouxadas** para
fechar no solo — com as trocas de TAB, a carga do facho não cabia na
travessia, e a fase ficava impossível.

Em vez de escolher um dos dois modos, três fases **mudam** conforme quem está
jogando. Cada uma carrega um *diff* de poucas células sobre o mesmo ASCII, e
não um segundo mapa: a diferença costuma ser de duas ou três células, e
escrever a fase duas vezes faria um conserto numa cópia passar despercebido na
outra.

| Fase | No solo | Em dois |
|---|---|---|
| **13 · Sob o Vidro** | duas lâmpadas acendem quase todo o contra-éter; sobra um vão de três células que só o facho preenche | as lâmpadas **saem**: a escolta é a travessia inteira, e só funciona com os dois andando juntos |
| **27 · Sem Rocha** | a pista de baixo é éter, e a Umbra **foge** do buraco de três células que a lanterna abre | a pista de baixo é contra-éter: ela tem de andar **debaixo** da lanterna. A mesma luz, o mesmo trilho, a relação invertida |
| **30 · A Fonte Aberta** | uma lâmpada encurta a escolta antes do altar final | a lâmpada sai: a escolta vai até a pedra |

O card do menu mostra a versão do modo escolhido e leva uma marca **2P**; na
fase, o rodapé troca a dica pela **nota do duo**. Se a fase muda e nada avisa,
o jogador aprende a fase errada e depois acha que o jogo mentiu.

A auditoria roda as três **duas vezes**, uma por versão — a variante é a
metade que se joga menos, e a que quebraria sem ninguém ver.

## Os três capítulos

As fases não são agrupadas por tema, e sim por **função**. O jogo tem trinta,
e o que muda de um capítulo para o outro é o que ele pede de você.

### Capítulo I — **Aprender** (15 fases)

Uma mecânica por fase, e nenhuma se repete. Cada fase declara no próprio JSON
o que apresenta (`teaches`), e um teste confere que são quinze coisas
distintas — e que **nada estreia depois daqui**. Uma mecânica que aparecesse
primeiro numa fase de mistura chegaria sem nome e sem lugar onde praticar.

| # | Nome | Apresenta |
|---|---|---|
| 1 | **Duas Polaridades** | ler a polaridade: o mesmo éter é chão de um e abismo do outro. Vencível **só andando** |
| 2 | **O Facho** | a habilidade da Lumen, sozinha. A ponte está apagada — dela só existe enquanto o facho estiver ligado |
| 3 | **A Absorção** | a habilidade da Umbra, sozinha. Agora a ponte está acesa, e ela só a toma apagando |
| 4 | **A Crosta** | o segundo verbo da Umbra, e o primeiro passo sem volta do jogo |
| 5 | **A Porta** | a porta de polaridade, e a sombra projetada pela rocha |
| 6 | **A Placa** | o gatilho que só vale com alguém **em cima** — o único lugar onde o ser parado tem função |
| 7 | **O Eclipse** | a única célula que aceita os dois, e a única com prazo |
| 8 | **Farol** | o mundo vira sozinho: aceso, a ponte é da Lumen; apagado, da Umbra |
| 9 | **Contra-Éter** | a regra invertida — sólido para a Lumen no escuro e para a Umbra na luz |
| 10 | **A Renúncia** | o altar: largar a habilidade numa pedra, para sempre |
| 11 | **A Lanterna** | a luz que anda, e leva o chão junto |
| 12 | **A Cortina** | o véu: sombra sem parede, e o único lugar onde o facho **não existe** |
| 13 | **Sob o Vidro** | a luz de um serve ao outro: ela caminha em cima, o facho desce, o chão da Umbra acende · **muda em dois jogadores** |
| 14 | **A Fonte Respira** | a fonte não anda: **incha**. O chão aceso dilata e contrai |
| 15 | **A Alavanca** | trocar éter por contra-éter no mapa inteiro, com um passo |

### Capítulo II — **Misturar** (9 fases)

Duas ou mais ao mesmo tempo. Nada de novo aqui — só combinações, e cada uma
existe porque as duas peças **brigam**.

| # | Nome | A mistura |
|---|---|---|
| 16 | **O Mesmo Chão** | facho × absorção: a lâmpada faz a ponte ser da Lumen, e absorver apaga a lâmpada |
| 17 | **Contratempo** | farol + crosta: uma coisa irreversível e uma periódica |
| 18 | **Fusão** | porta + eclipse: a porta destranca a ponte que tem prazo |
| 19 | **Espelhos** | contra-éter + farol: três pontes, duas invertidas, uma virada troca todas |
| 20 | **A Fonte** | placa + eclipse: segurar a porta custa o tempo que a ponte dourada não tem |
| 21 | **Pedra Fria** | o altar da Umbra: apagar a lâmpada devolve a ponte à Lumen — que agora precisa **correr** no escuro |
| 22 | **Contracorrente** | lanterna + contra-éter: um segue a luz, o outro foge dela |
| 23 | **O Guardião** | lanterna + placa: a lanterna não espera quem está segurando a porta |
| 24 | **Contrapeso** | alavanca + lanterna: a alavanca espelha a fase, e não dá para agradar aos dois |

### Capítulo III — **Especiais** (6 fases)

As que quebram a própria regra.

| # | Nome | O que ela quebra |
|---|---|---|
| 25 | **Maré** | a mesma respiração monta uma metade e desmonta a outra, no mesmo instante |
| 26 | **Abrigos** | no auge a fonte dissolve a Umbra a três células; só dentro do véu a luz não chega |
| 27 | **Sem Rocha** | **nenhum chão neutro entre as margens.** A mesma lanterna: em cima é o chão da Lumen, embaixo é o buraco da Umbra — uma a segue, a outra foge · **muda em dois jogadores** |
| 28 | **A Fonte Desperta** | duas fontes em contratempo: a metade acesa da sala vai e vem sozinha |
| 29 | **A Fonte Partida** | ponte dourada com prazo, lanterna que não para, e um altar no fim |
| 30 | **A Fonte Aberta** | a escolta sob o vidro, e a Lumen **desce** ao chão dela para deixar a última luz numa pedra · **muda em dois jogadores** |

Três princípios de desenho, todos aprendidos errando:

- **Spawn perto do portal.** O obstáculo é a polaridade, não a distância. A
  primeira versão custava ~11 s de caminhada por fase com 1–4 decisões: uma
  decisão a cada 3 segundos, e na fase 1 uma a cada 11. Agora são 4–7 s.
- **Teto sobre todo vão de éter.** A Lumen cobre **5,5 células** num salto
  completo — sem teto ela pula por cima e o puzzle vira opcional.
- **Pistas separadas.** Se os dois percorrem o mesmo corredor em sequência, o
  segundo passa por cima do primeiro parado e os dois se anulam. Foi assim
  que três desenhos meus morreram antes de chegar a este.
- **Teto é rocha maciça até o topo, nunca uma laje de uma linha.** Uma laje é
  uma *plataforma*: a Lumen subia nela e caminhava por cima da ponte, e o
  facho ficava opcional em cinco fases. Onde não cabe teto, o vão tem de ter
  mais de 5,45 células — a distância que ela cobre num salto completo.

### Alfabeto das fases (`data/levels/*.json`)

```
#  rocha (sólida para os dois, bloqueia luz)     A  spawn da Lumen
~  éter (sólido para um por vez)                 B  spawn da Umbra
%  crosta (sólida, opaca, só a Umbra rompe)      X  portal da Lumen
=  eclipse (sólida para os dois, com prazo)      Y  portal da Umbra
;  contra-éter (a regra invertida)               +  fragmento da fonte
^  altar de forma (larga a habilidade ali)       >  trilho da lanterna
:  véu (passa o pé, não passa a luz)            -  vidro (chão, e a luz passa)
@  fonte que respira (o raio dilata e contrai)   &  a irmã dela, em contratempo
!  alavanca (troca éter por contra-éter)
*  lâmpada fixa                                  .  vazio
o  farol pulsante
D  porta         L/S  zonas de polaridade      _  placa de pressão
```

A última linha da grade é sempre vazia: é o abismo. `Grid2D` trata
fora-dos-limites como sólido, então sem essa linha ninguém cairia de verdade.

## Como a luz funciona

Um flood geodésico de 8 vizinhos, relaxado 10 vezes por frame sobre a grade
28×17 — cada passe empurra a luz uma célula, perdendo `1/7` de intensidade
(diagonais custam `√2` a mais). Isso dá três coisas que uma soma de discos não
daria:

1. **A luz contorna paredes em vez de vazar por elas** — a sombra projetada
   pela rocha, de que a fase 4 depende inteiramente, existe de graça.
2. **O alcance de uma fonte sai da intensidade dela**:
   `(I − 0.35) × 7` células até deixar de solidificar éter. Uma lâmpada
   alcança 4,55 células; a Lumen fica segura até 6,16 dela; a Umbra se
   dissolve dentro de 2,8. São esses três números que permitem desenhar uma
   fase sem adivinhar.
3. **A sombra obedece a mesma geometria da luz** — é o mesmo flood com outra
   semente, então o bolsão da Umbra também respeita paredes.

Os vizinhos diagonais não são cosméticos: só com os 4 ortogonais a distância
resultante é a de Manhattan e uma lâmpada acende um **losango**, com alcance
diagonal ~71% do horizontal. `tests/test_light_field.py` guarda isso.

A **crosta** também é opaca, e é disso que o verbo da Umbra vive: sem
oclusão, rompê-la seria apenas abrir passagem.

## Arquitetura

```
penumbra/
  main.py            ponto de entrada
  config.json        EngineConfig (janela, capacidade, caminhos de dados)
  composition.py     monta o World, os dois seres e a ORDEM dos sistemas
  tuning.py          lê data/difficulties/penumbra/basic.json
  terrain.py         máscaras densas de uma fase, recarregáveis no lugar
  levels.py          catálogo de data/levels/*.json
  reachability.py    modelo de salto + grafo de alcance (auditoria de geometria)
  state.py           estado compartilhado + troca de fase
  scenes.py          fluxo título -> fases -> jogo -> pausa -> fim
  audio.py           a voz do jogo, sintetizada (nenhum arquivo de som)
  progress.py        o que sobrevive a fechar o jogo
  achievements.py    dez conquistas, e o motivo dos fragmentos
  menu.py            tela de título, grade de cards, prévia do terreno
  hud.py             HUD e avisos de fim de fase
  systems/
    duality_control_system.py   input -> velocity dos dois seres
    light_field_system.py       a luz, e as duas grades de colisão
    crust_break_system.py       o verbo da Umbra; muta o terreno
    world_clock_system.py       farol e eclipse; o que muda sozinho
    form_altar_system.py        a renúncia: poder trocado por permanência
    polarity_door_system.py     a porta que exige os dois ao mesmo tempo
    outcome_system.py           as quatro mortes e a única vitória
    presentation_system.py      estado -> pixels
    quit_on_action_system.py
data/                dificuldade, bindings, arquétipos, fases
assets/penumbra.ico  ícone do atalho (tools/generate_icon.py o refaz)
tests/              212 testes headless
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
8. WorldClockSystem                  farol e eclipse; o que muda sozinho
9. CrustBreakSystem                  o verbo da Umbra; muta o terreno
10. PolarityDoorSystem               lê a luz deste frame
11. OutcomeSystem                    lê posições já resolvidas
12. PresentationSystem               só pixels
```

Não há sistema de "sair": **ESC é tratado nas cenas** (volta ao menu durante
a fase, encerra no menu), porque um `ISystem` só roda dentro de `world.step()`
— e o menu existe justamente enquanto o mundo está parado.

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
  reescreve as máscaras do `Terrain` no lugar. Custo medido: **1,7 ms/frame**
  (teto de ~600 fps).
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
pytest -q                      # 212 testes, ~9 s, headless
python -m tools.audit_levels   # luz, sobrevivência e alcance geométrico por fase
```

Uma fase tem **duas** maneiras independentes de ser insolúvel, e cada uma tem
seu guardião:

- **polaridade** — o éter não acende onde precisa, ou o facho da Lumen vaza até
  a zona de sombra e a porta nunca abre (`tests/test_shipped_levels.py`);
- **geometria** — o degrau é alto demais, ou há um bloco exatamente sobre a
  cabeça e o salto morre no teto (`tests/test_reachability.py`).

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

## As duas tolerâncias do salto

Existem contra o mesmo erro, e é o único erro de plataforma que o jogador não
consegue **ver**: a diferença entre acertar e errar é de 16 ms.

- **Coyote time** (0,10 s) — sair da beira um frame antes de apertar custava o
  salto, e não havia como saber que se apertou tarde.
- **Buffer de pulo** (0,12 s) — apertar um frame antes de pousar custava o
  mesmo. É o caso de encadear dois saltos.

Nenhuma das duas abre caminho novo, e há um teste que garante isso: as duas
janelas são **menores que o tempo de queda de meia célula** (0,17 s sob a
gravidade do jogo). Maiores, deixariam de perdoar um erro de tempo e passariam
a estender o salto — e o alcance geométrico de trinta fases foi medido sem
elas. Saltar zera as duas janelas, que é o que impede o salto duplo.

## O português tem acento

O jogo inteiro escrevia "A Absorcao", "Nao tem volta", "ESPACO" — por uma
limitação que **não existe**: a fonte do backend renderiza acentuado sem
problema nenhum. Era uma suposição minha, carregada por trinta fases. Os trinta
nomes, as trinta dicas e toda a interface estão acentuados agora.

## Som, progresso e pausa

O jogo foi mudo por trinta fases, e a falta não era estética: o **medidor de
perigo é visual**, e ele sobe justamente quando sua atenção está no outro ser.
Agora cada ser tem uma **voz própria** — a Lumen aguda e limpa, a Umbra grave —
e o aviso **acelera** conforme o medidor sobe. O que se lê não é o tom, é a
aceleração: um intervalo constante viraria ruído de fundo em duas fases.

Tudo é **sintetizado** por `IAudioEngine.register_tone` (`square | noise |
sweep | zap`). Não há um único arquivo de som no repositório, e o jogo continua
rodando headless — o `AudioSystem` só é registrado em `build_game`, como a
apresentação. Removido, o jogo fica idêntico e mudo.

A paleta sonora segue a lei da paleta visual: **o dourado tem voz própria**, um
`sweep` médio reservado ao que exige os dois (porta, eclipse, fragmento,
altar).

**O progresso agora sobrevive** a fechar o jogo (`%APPDATA%/Penumbra/`). Três
regras, todas pela mesma razão — um save nunca pode ser o motivo de o jogo não
abrir: ler nunca levanta (arquivo corrompido vira progresso vazio), escrever é
atômico (`.tmp` + rename, então um desligamento no meio deixa o save anterior
intacto), e um save gravado numa versão com outro número de fases é **ajustado**
em vez de recusado — acrescentar fases não pode apagar o que você já fez.

**E dá para pausar.** Antes, ESC no meio da fase voltava ao menu e custava a
tentativa; não havia como só parar. Agora empilha um painel por cima
(`push_scene`), o mundo congela onde estava, e dá para continuar, reiniciar ou
sair.

## Por que colecionar fragmentos

Eles não valiam nada — um contador na tela de título. Um colecionável sem
consequência é um desvio que custa risco e não paga nada, e o jogador aprende
isso na terceira fase.

A resposta estava no nome deles. São **fragmentos da fonte**, e a última tela
pergunta se os dois querem se fundir *nela*:

> **Não se funde uma fonte que nunca foi remontada.**

Com os trinta, "fundir" é uma escolha de verdade. Sem eles, a tela diz quantos
faltam e a única saída é seguir dois. **Não é tranca**: nenhuma fase fica
bloqueada, o jogo inteiro continua jogável, e dá para voltar, apanhar os que
faltam e refazer a escolha. É uma consequência.

### Conquistas

Dez, e nenhuma premia repetição ou tempo de tela — todas reconhecem ter
**entendido alguma coisa**, o tipo de coisa que se faz de propósito ou não se
faz nunca.

| | |
|---|---|
| **Primeira Luz** | vencer a primeira fase |
| **Aprendiz · Misturador · Especialista** | vencer cada capítulo inteiro |
| **A Fonte Inteira** | apanhar todos os fragmentos |
| **Sem as Mãos** | vencer uma fase sem ligar nenhuma habilidade |
| **De Primeira** | vencer uma fase sem morrer nem reiniciar |
| **A Dois** | vencer uma fase em dois jogadores |
| **Escolta** | vencer uma fase de escolta em dois jogadores |
| **Renúncia Dupla** | deixar as duas formas na mesma fase |

## O fim

Depois da fase 30 o jogo faz a pergunta que passou 24 fases fazendo sem dizer
em voz alta: **fundir os dois, ou segui-los separados.**

Nenhum dos dois é recompensado, e é de propósito. Fundir resolve o problema do
jogo eliminando o jogo — ninguém mais cai porque o outro acendeu, e ninguém
mais atravessa o que sozinho não atravessaria. Seguir dois mantém o problema,
porque o problema é a razão de os dois existirem. A tela só põe os dois lado a
lado, com a consequência escrita embaixo de cada um.

## As telas

O jogo abria direto na escolha de modo, e **ESC ali fechava a janela** — não
havia porta nenhuma para conquistas, opções ou sair, e a única saída era um
atalho que ninguém descobriria. Uma tela que só faz uma pergunta ("um ou
dois?") não é uma raiz: é um passo do caminho, e passou a ser exatamente isso.

```
MENU PRINCIPAL          jogar · conquistas · opções · sair
  └─ JOGAR              um jogador ou dois
       └─ FASES         3 capítulos × grade de cards
            └─ FASE     ESC pausa (continuar · reiniciar · menu)
                 └─ FIM fundir ou seguir dois
```

**Conquistas** mostra as dez com título e descrição **legíveis**, mesmo as que
faltam — elas são a lista do que o jogo considera ter entendido alguma coisa.
Escondidas, deixariam de ser um convite e virariam só um placar.

**Opções** tem som, volume, tela cheia e apagar progresso. Apagar fica no mesmo
lugar que o volume porque é ali que o jogador vai procurar — mas exige um
**segundo ESPAÇO**, com o aviso escrito na própria linha. Um menu que apaga
trinta fases num toque é hostil; um que esconde a opção é um menu que mente.
Tudo grava a cada mudança, e não ao sair: fechar pela janela não passa por ali,
e um ajuste perdido assim é o tipo de coisa que ninguém reporta — só deixa de
mexer.

## O menu

Duas telas. A **de título** existe porque o modo era, antes, um atalho de TAB
no canto da seleção de fase: quem nunca leu o rodapé jamais descobriria que o
jogo tem multiplayer local. Modo é a primeira decisão da sessão — merece uma
tela, não uma legenda. Os dois botões mostram os **dois seres** em ambos os
casos, porque em ambos eles existem; o que muda é quem os comanda, e é isso
que o desenho diz: num jogador, um `TAB` entre eles; em dois, um rótulo J1 e
J2.

A **seleção de fase** é uma grade de 5×3 cards por **capítulo** (são três), cada um com
**numerão**, nome, dois selos (fase vencida, fragmento) e uma **prévia** da
fase.

Trinta fases não cabem numa grade só, e encolher o card até caberem
transformaria a miniatura — a única coisa que faz o card valer mais que uma
lista de nomes — em manchinha. Paginar também diz algo verdadeiro sobre o
jogo — mas a página é o **capítulo**, e não um bloco de N fases, porque os
três não têm o mesmo tamanho nem deveriam ter: aprender uma mecânica de cada
vez custa uma fase por mecânica, misturar custa menos, e as especiais são
poucas de propósito. Um capítulo mais curto deixa a grade pela metade, e isso
é uma informação verdadeira — não um buraco. O capítulo é uma
**página, não uma tranca** — nada fica bloqueado, e a seta anda de ato como
anda de card, virando pela borda da grade. Assim o menu inteiro continua em
quatro teclas.

A prévia é o **terreno real**, parseado pelo mesmo `Terrain` que o jogo usa —
não uma imagem exportada à mão que envelheceria no primeiro ajuste de nível.
Cada célula vira um retângulo de poucos pixels com as cores da paleta, então
um terreno novo aparece no menu de graça. As cores da miniatura são
deliberadamente mais claras que no jogo: a 4 px por célula, o contraste real
(rocha quase preta sobre fundo quase preto) desapareceria, e a silhueta da
fase é a única coisa que o card precisa entregar.

## O que os testes não estavam olhando

- **A faixa de realce do menu ficava abaixo da palavra.** `draw_text` aceita um
  `anchor`, e a diferença não é cosmética: com `topleft` o `y` é o **topo** do
  texto; com `center`, o **centro vertical**. Posicionar a faixa a partir de `y`
  como se fosse topo, com o texto centrado, joga a faixa inteira para baixo.
  Nenhum dos 207 testes viu — nenhum deles olhava um pixel. Agora um renderer
  de mentira grava as chamadas de desenho e três telas verificam a única coisa
  que importa: **o texto realçado cabe dentro do retângulo que o realça** (e um
  quarto teste garante que nada saia da janela). Reintroduzi o defeito de
  propósito para ver o teste falhar antes de confiar nele.


Três falhas chegaram por alguém **jogando**, com a suíte inteira verde. Cada
uma virou um teste, e as três são do mesmo tipo: o jogo abre, a fase carrega,
e nada avisa.

- **Escolta impossível no solo.** A carga do facho drena também com o ser
  parado — e é de propósito, o facho custa mesmo estando parado. No duo a
  travessia sob o vidro cabia numa carga; no solo, com as trocas de TAB,
  nunca cabia (medido: a Umbra chegava à coluna 9 de 16 e caía). A correção
  não foi mexer na regra, foi no **desenho**: lâmpadas fixas acendem quase
  todo o contra-éter e sobra um vão curto, do tamanho exato da mancha que o
  facho projeta. A escolta virou um momento, não a fase inteira.
- **Crosta morta no duo.** `CrustBreakSystem` exigia `state.active == UMBRA` e
  lia as teclas do jogador 1 — e no duo não existe "ativo". As fases 2, 7 e 14
  eram invencíveis a dois. Todo teste de crosta rodava em solo.
- **Um comentário no JSON de bindings derrubou o jogo na abertura.** O
  carregador de dificuldade descarta chaves começadas por `_`; o de bindings,
  não. Os testes usam o provider nulo, que ignora o arquivo — agora um deles
  carrega o arquivo pelo **carregador real**, e outro confere que toda ação
  lida pelo código está lá.

## Escopo

Este é o vertical slice das mecânicas centrais. Ficaram **fora**, do documento
de design original:

- **Sacrifício de forma** (a Umbra cobrindo a Lumen para protegê-la)
- **Controle simultâneo** dos dois seres (um em cada analógico)
- **Boss fight** e a narrativa com a escolha da fusão
- **Áudio** — a engine tem `IAudioEngine` e bancos data-driven, mas o slice
  não tem nenhum asset de som. É a lacuna mais funcional das que restam: o
  medidor de perigo é hoje **só visual**, e você olha o ser que comanda
  enquanto o outro morre fora da sua atenção

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
