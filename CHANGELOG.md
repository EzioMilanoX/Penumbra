# Changelog

As notas de cada versão, escritas para quem joga.

## Ainda sem versão

**Solo com eco** — as fases de dupla, sozinho, sem afrouxar nada
- Nas fases marcadas com **ECO** no card (13 · Sob o Vidro, 27 · Sem Rocha e 30 · A Fonte Aberta), aperte **E** em vez de ESPAÇO.
- Primeiro você joga a Lumen, e o jogo grava (até 60 s). **TAB** rebobina: agora você joga a Umbra, e a Lumen do passado — o eco — repete exatamente o que você fez. A fase é a versão de dois jogadores, sem as lâmpadas que facilitam o solo.
- Na tela, os pontinhos mostram o caminho que o eco ainda vai fazer.
- Se o que a Umbra faz agora desfaz o passado (apagar a luz de que o eco precisava, por exemplo), é um **paradoxo**: o mundo para, o ponto da falha fica marcado, e você escolhe entre tentar o presente de novo (ESPAÇO) ou regravar a Lumen a partir de um segundo antes dali (TAB).

**Música e falas**
- Cada capítulo tem a sua música de fundo, composta e sintetizada para o jogo. O volume dela fica em Opções → MÚSICA, separado do volume dos efeitos.
- O jogo agora fala: uma fala curta na entrada de cada capítulo (a primeira, antes da fase 1).

**Por dentro**
- Lint (ruff) configurado e limpo; nada muda para quem joga.

## v0.1.0 — Luz e Sombra (2026-11-19)

A primeira versão para jogar sem instalar nada: baixe o `Penumbra-windows.zip`, extraia e abra `Penumbra.exe`.

**O jogo**
- Dois seres que não podem se tocar e não avançam separados: a Lumen, que precisa de luz, e a Umbra, que precisa de sombra.
- **Trinta fases** em três capítulos (Aprender, Misturar e Especiais), todas abertas desde o início. Cada card mostra, com selos, o que você já fez nela.
- **Um ou dois jogadores** no mesmo teclado. No duo ninguém espera, e o contato entre os dois continua aniquilando os dois. Algumas fases mudam de forma quando há dois jogadores.
- Fragmentos para colecionar e conquistas.
- O fim faz uma pergunta, e o menu lembra o que você respondeu.
- Há algo que o jogo não conta.

**Como se joga**
- Menu: A/D escolhe, ESPAÇO confirma, ESC volta.
- Um jogador: A/D mover · ESPAÇO pular · S habilidade · TAB trocar de ser · R reiniciar · ESC menu.
- Dois jogadores: J1 = A/D, ESPAÇO, S, R · J2 = setas ←→, ↑, ↓, END.

**Sobre o executável**
- É uma pasta, não um arquivo só: mantenha o `Penumbra.exe` junto da pasta `_internal`.
- Ele não é assinado. Se o Windows avisar ("O Windows protegeu o computador"), clique em "Mais informações" → "Executar assim mesmo".
