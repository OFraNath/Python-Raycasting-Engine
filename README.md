# Raycasting FP Engine (Edição GPU)

Uma engine de renderização pseudo-3D no estilo *Wolfenstein 3D*, mas que faz o raycasting inteiro **no fragment shader (GPU)**, usando Pygame, ModernGL e OpenGL 3.3. Em vez de calcular cada coluna da tela na CPU, cada pixel é decidido na placa de vídeo.

A iluminação é dinâmica: as luzes seguem a lei do inverso do quadrado, projetam sombras com penumbra suave e reemitem luz nas paredes vizinhas (GI/bounce), tudo pré-calculado no momento em que o mapa `.rcfg` é carregado.

Este README é um **guia de uso**: como rodar, como montar seu primeiro mapa do zero e a referência completa do formato `.rcfg`.

![status](https://img.shields.io/badge/status-em%20desenvolvimento-yellow)
![python](https://img.shields.io/badge/python-3.8%2B-blue)
![license](https://img.shields.io/badge/license-GPLv3-lightgrey)

---

## 📸 Screenshots

<p align="center">
  <img src="https://github.com/user-attachments/assets/e51838fc-f34e-46a2-ab9b-2edbbdc29427" width="32%" />
  <img src="https://github.com/user-attachments/assets/a6ac940d-5160-4813-a369-a2e82ee8fe7b" width="32%" />
  <img src="https://github.com/user-attachments/assets/cbd49320-b23f-4157-9c81-798e501583c1" width="32%" />
</p>

---

## ⚡ Como executar

### Pré-requisitos
- Python 3.8+
- Placa de vídeo com OpenGL 3.3+

### Instalação

Na pasta do projeto:

```bash
pip install -r requirements.txt
```

### Executando

Sem argumentos, a engine abre com um mapa de demonstração embutido:

```bash
python Raycasting.pyw
```

Passando o caminho de um `.rcfg`, esse mapa é carregado na inicialização:

```bash
python Raycasting.pyw showcase.rcfg
```

**Durante a execução:**

- **Arraste e solte** qualquer arquivo `.rcfg` dentro da janela para trocar de mapa na hora, sem reiniciar.
- O mapa **atualmente carregado** tem hot-reload: edite e salve o `.rcfg` no disco e o jogo recarrega sozinho, mantendo a posição da câmera.

### Controles

| Tecla | Ação |
| :--- | :--- |
| `W` `A` `S` `D` ou setas | Movimentação |
| `Shift` | Correr |
| `Mouse` | Rotacionar câmera / olhar para cima e para baixo |
| `Esc` | Travar/destravar o cursor do mouse |
| `R` | Voltar para o `SPAWN` original do mapa |
| `,` / `.` | Recuar / avançar o horário do céu (30 min por toque) |
| `P` | Pausar / retomar o ciclo de dia e noite |

---

## 🧱 Construindo seu primeiro mapa

Um mapa é um arquivo de texto com extensão `.rcfg`. Ele tem seções (entre `[COLCHETES]`) e uma grade de células em `[MAP]`. Siga o passo a passo abaixo — cada bloco é uma seção real que a engine entende.

> **Regra de ouro dos caminhos:** a engine resolve os caminhos de imagens **relativos à pasta do próprio `.rcfg`**. Siga o padrão do mapa de exemplo [`showcase.rcfg`](./showcase.rcfg) e coloque suas imagens na pasta [`assets/`](./assets) na raiz do projeto (referenciada como `assets/imagem.png` no `.rcfg`).

### 1. Esqueleto do arquivo

```ini
[TITLE]
Meu Primeiro Corredor

[CONFIG]
window 960 560
fov 60
ambient 0.08

[SPAWN]
x 2.5
y 2.5
angle 0
```

- `[TITLE]`: texto da janela do jogo.
- `[CONFIG]`: opções de qualidade/controle (veja a [tabela completa](#config--opções-globais)). Tudo aqui é opcional — o que você não escrever usa o padrão.
- `[SPAWN]`: onde o jogador nasce (`x`, `y` no grid; `angle` em graus). Se o ponto cair dentro de uma parede, a engine move o jogador sozinha para a primeira célula vazia.

### 2. O layout com `[MAP]`

A grade é uma matriz de tokens separados por espaço, vírgula ou ponto e vírgula. As paredes do contorno fecham o mapa:

```ini
[MAP]
1 1 1 1 1
1 0 0 0 1
1 0 0 0 1
1 0 0 0 1
1 1 1 1 1
```

### 3. Cores ou texturas das paredes

As paredes `1` a `9` são definidas em `[TEXTURES]` (imagens) ou, na ausência delas, em `[COLORS]`:

```ini
[COLORS]
1 #8a7a63 #5c5041
```

Cada linha é `ID cor_ns cor_ew` — a cor é escolhida por **face atingida**: `cor_ns` pinta as faces de paredes que correm de norte a sul, `cor_ew` as de paredes que correm de leste a oeste (estas saem ~20% mais escuras). Truque clássico de raycaster para dar sensação de volume.

Para textura em vez de cor, use `[TEXTURES]` (a imagem entra em espaço sRGB, com correção de gamma no shader):

```ini
[TEXTURES]
1 assets/tijolo.png
```

Um tipo de parede pode estar só em `[TEXTURES]`, só em `[COLORS]`, ou nos dois (textura com cor de reserva).

### 4. Luzes

Primeiro define-se a luz em `[LIGHTS]`, depois espalha-se `L#` pelas células do mapa:

```ini
[LIGHTS]
1 #ffb36b 5.5
```

```ini
[MAP]
1 1 1 1 1
1 0+L1 0 0 1
1 0 0 0+L1 1
1 0 0 0 1
1 1 1 1 1
```

Cada linha de `[LIGHTS]` é `ID cor_hex raio`. O token `0+L1` significa: **célula vazia (`0`) mais (`+`) a luz `L1` sobre ela**. Tochas, velas e lustres são feitos assim.

### 5. Billboards (sprites sempre de frente)

Sprites 2D que sempre encaram a câmera e recebem oclusão correta das paredes. Definem-se em `[BILLBOARDS]` e usam tokens `B#`:

```ini
[BILLBOARDS]
1 assets/vaso_planta.png 0
2 assets/orbe_flutuante.png 0.9 1.5
```

```ini
[MAP]
1 1 1 1 1
1 0 0 0 1
1 0+B2 0 0 1
1 0+B1 0 0 1
1 1 1 1 1
```

Sintaxe: `ID caminho offset_y [escala] [ai_type] [speed]`. `offset_y` eleva o sprite em relação ao chão (unidades de mundo; `0` = encostado, valores maiores = flutuando). `escala` (padrão `1.0`) multiplica o tamanho — por padrão o sprite ocupa 1 unidade de altura. Cada célula com `B#` é atravessável.

Os tokens opcionais `ai_type` e `speed` transformam o billboard num agente que se move pelo mapa (veja **§5.1**) e, se quiser, numa fonte de áudio espacial (veja **§5.2**):

- `ai_type` (padrão `none`): `none` = estático; `friendly` = seguidor; `enemy` = perseguidor.
- `speed` (unidades de mundo por frame): padrão `0.035` (amigável) e `0.05` (inimigo) quando omitido.

### 5.1 IA dos Billboards (FSM + Pathfinding)

Um billboard com `ai_type` diferente de `none` vira um agente que navega o labirinto usando uma **máquina de estados (FSM)** acoplada a um **pathfinding por onda (BFS / wavefront)**:

- **Amigável (`friendly`)** — FSM `FOLLOW → STAY_CLOSE`: segue o jogador e para a ~1,2 de distância, orbitando suavemente. Não causa dano.
- **Inimigo (`enemy`)** — FSM `CHASE → GAME_OVER_TRIGGER`: persegue o jogador pelo labirinto. A engine calcula uma grade de distâncias a partir da posição do jogador (BFS) e o inimigo desce o gradiente, contornando paredes; quando está na mesma célula, faz *homing* direto para não travar.

**Game Over:** se o inimigo encosta no jogador (`dist < 0,5`), surge uma tela **"GAME OVER"** por 2 segundos e o mapa é restaurado (jogador e billboards com IA voltam ao seu spawn original).

**Minimapa:** billboards com IA aparecem como um ponto **móvel** (âmbar = amigável, vermelho = inimigo). O ponto estático de spawn é suprimido para essas células, para não confundir com o jogador.

### 5.2 Som posicional estéreo (opcional)

Cada tipo de billboard pode ter um áudio de loop associado numa nova seção `[BILLBOARD_SOUNDS]`, indexada pelo **mesmo índice** do billboard (`1` a `9`), usada como `B1`..`B9`:

```ini
[BILLBOARDS]
1 assets/waifu.png 0.0 1.0 friendly 0.04
2 assets/monstro.png 0.0 1.0 enemy

[BILLBOARD_SOUNDS]
1 assets/ambiente.mp3 10.0 1.0
2 assets/rugido.mp3 14.0 4.0
```

Sintaxe: `ID caminho_do_audio raio volume`.

- **Loop infinito:** o som toca continuamente enquanto o mapa estiver carregado.
- **Estéreo posicional:** o volume é dividido entre os canais esquerdo/direito conforme o ângulo do emissor em relação à sua mira (pan), e atenua com a distância até `raio` (silêncio total fora do raio).
- **Oclusão por parede:** cada parede entre o emissor e o jogador reduz o volume em `~0.45^paredes`, simulando som abafado atrás de muros.
- **Volume 0–10:** `1` = volume original (1×); valores maiores amplificam até 10×. Funciona tanto para billboards parados quanto para os que se movem (IA).

> O mixer é iniciado automaticamente na primeira carga de um mapa que tenha `[BILLBOARD_SOUNDS]`; mapas sem som não inicializam áudio.

### 6. Partículas (sprites animados)

Igual a billboard, mas gera várias instâncias flutuantes espalhadas pela célula, cada uma subindo e descendo devagar. Definem-se em `[PARTICLES]` com tokens `P#`:

```ini
[PARTICLES]
1 assets/orbe_flutuante.png 8 0.6 4
```

```ini
[MAP]
1 1 1 1 1
1 0 0 0 1
1 0+P1 0 0 1
1 0 0 0 1
1 1 1 1 1
```

Sintaxe: `ID caminho quantidade velocidade espalhamento offset_y escala`.

### 7. Céu dinâmico (opcional)

Sem `[SKY]`, o céu é o gradiente estático do `[THEME]`. Com ele, a engine desenha sol, lua e estrelas e pode animar a passagem do tempo:

```ini
[SKY]
cycle true
day_length 120
start_time 8
sun_color #fff2c0
moon_color #b9c6e0
stars 140
```

Veja a [tabela completa](#sky--ciclo-de-dia-e-noite-opcional).

### 8. Teste e itere

```bash
python Raycasting.pyw caminho/do/meu_mapa.rcfg
```

Troque valores, salve e observe o hot-reload. Quando quiser editar visualmente (grid, cores, céu), abra o [`editor.html`](#editor-visual-de-mapas).

---

## 📖 Referência do formato `.rcfg`

### Regras gerais

- Comentários: linhas que **começam com `#`**, ou `#` no fim da linha (`1 #ff0000 #880000  # parede vermelha`).
- Chaves e valores não diferenciam maiúsculas/minúsculas.
- A ordem das seções não importa para a engine (o editor as reordena ao salvar).
- Toda célula fora do alcance do `SPAWN`/das paredes é tratada como bloqueada pela engine.

### `[MAP]` — a grade do nível

Cada token de uma célula é `base+extra`. A **base** é o que ocupa a célula (parede ou vazio); os **extras** (uma ou mais camadas `L#`, `B#`, `P#`) ficam **sobre** ela, separados por `+`. Vale no máximo um `L`, um `B` e um `P` por célula.

| Token | O que faz |
| :--- | :--- |
| `0` | Chão vazio, percorrível |
| `1` a `9` | Parede dos tipos `1`..`9` (definidos em `[TEXTURES]`/`[COLORS]`) |
| `N` | **Parede invisível**: bloqueia o jogador mas não é desenhada nem aparece no minimapa (sem cor/textura) — útil para confinar sem fechar a visão |
| `0+L1` | Célula vazia com a luz `1` no centro |
| `1+B2` | Parede do tipo `1` com um billboard `2` na célula |
| `0+P3` | Célula vazia com as partículas `3` |
| `0+L1+B2+P3` | As três camadas juntas na mesma célula |

> **Sem retrocompatibilidade:** versões antigas da engine aceitavam `L1`/`B1`/`P1` sozinhos (sem base) e um formato legado só com dígitos (`7` a `9` = luz). Isso **foi removido** — hoje todo token precisa de uma base numérica válida (`0`–`9` ou `N`), e camadas exigem sempre a forma composta `base+L#`/`base+B#`/`base+P#` (ex.: `0+L1`). Mapas escritos no formato antigo precisam ser convertidos.

### `[CONFIG]` — opções globais

| Chave | Padrão | Descrição |
| :--- | :--- | :--- |
| `window` | `960 560` | Resolução da janela (`largura altura`) |
| `mm` | `140` | Tamanho da janela do minimapa em pixels |
| `fov` | `60` | Campo de visão da câmera, em graus |
| `num_rays` | `200` | Raios por coluna da tela (detalhe vertical) |
| `max_depth` | `30` | Alcance máximo dos raios, em blocos |
| `move_speed` | `0.06` | Velocidade de caminhada por frame |
| `run_multiplier` | `1.8` | Multiplicador ao correr (`Shift`) |
| `mouse_sens_x` | `0.004` | Sensibilidade horizontal do mouse |
| `mouse_sens_y` | `1.0` | Sensibilidade vertical do mouse |
| `max_look_y` | `240` | Ângulo máximo de olhar para cima/baixo |
| `fog` | `1.4` | Intensidade da névoa por distância (maior = mais densa) |
| `gradient_steps` | `14` | Faixas do gradiente do céu |
| `ambient` | `0.07` | Luz ambiente global (`0.0` a `1.0`) |
| `floor_bands` | `3` | Faixas do gradiente do chão |
| `floor_step` | `2` | Escurecimento entre as faixas do chão |
| `light_res` | `1` | Subdivisão da grade de luz por bloco (`1, 2, 4, 8, 16, 32`). Maior = gradientes mais precisos, mais custo. Valores fora da lista são ajustados para o mais próximo |
| `light_soft_samples` | `6` | Amostras da penumbra das sombras |
| `light_soft_radius` | `0.4` | Raio de espalhamento da penumbra |
| `light_bounce` | `0.35` | Intensidade do rebote de luz nas paredes (GI) |
| `light_bounce_radius` | `1.6` | Raio de alcance do rebote |
| `light_bounce_passes` | `2` | Passes do rebote de luz |
| `texture_size` | `256` | Tamanho de redimensionamento das texturas importadas |
| `wall_scale` | `1.0` | Altura das paredes: `1.0` = proporcionais, `> 1` = mais finas e altas, `< 1` = mais grossas e baixas |

### `[SPAWN]` — posição inicial

- `x`, `y`: posição no grid (centro da célula = `n.5`)
- `angle`: direção inicial da câmera em graus (`0` a `360`)

Se o ponto cair em parede, a engine realoca o jogador para a primeira célula vazia do mapa.

### `[INFO]` — metadados

Chaves livres, exibidas no HUD:

```
NAME Meu Mapa
AUTHOR Fulano
```

### `[THEME]` — cores da interface e do ambiente

Todas aceitam um hex (`#rrggbb`):

```
SKY_BASE #1a1a3a       # topo do céu (mais escuro)
SKY_TOP #4a3b6e        # base do céu (horizonte)
FLOOR_BASE #1e1e24     # chão perto do horizonte
FLOOR_TOP #3a3a4d      # chão perto da câmera
CROSSHAIR #00ffff      # retículo central
HUD_LIGHT #00ffcc      # cor de luz no HUD
HUD_ALERT #ffcc00      # alertas no HUD
MINIMAP_PLAYER #00ffff # jogador no minimapa
```

### `[COLORS]` — paredes sem textura

Sintaxe: `ID COR_FACES_NORTE_SUL COR_FACES_LESTE_OESTE`

```
1 #888888 #555555
```

### `[TEXTURES]` — paredes texturizadas

Sintaxe: `ID caminho/relativo/imagem.png` (relativo à pasta do `.rcfg`)

```
1 assets/tijolo.png
```

Se a imagem não existir, a engine usa um **xadrez magenta/preto** (textura de erro) em vez de travar — você vê na hora qual caminho está errado.

### `[LIGHTS]` — fontes de luz

Sintaxe: `ID COR_HEX RAIO` (índices `1` a `9`, usados como `L1`..`L9` no `[MAP]`)

```
1 #ff8800 6.0
```

### `[SKY]` — ciclo de dia e noite (opcional)

| Chave | Padrão | Descrição |
| :--- | :--- | :--- |
| `cycle` | `false` | Se `true`, o horário avança sozinho durante o jogo |
| `day_length` | `120` | Duração de um dia completo, em segundos reais |
| `start_time` | `8` | Horário inicial do "dia de jogo" (`0` a `24`) |
| `sun_peak` | `45` | Elevação máxima do sol ao meio-dia (`10` a `90`; `45` mantém o arco visível na tela, `90` = zênite) |
| `sun_color` | `#fff2c0` | Cor do sol |
| `moon_color` | `#b9c6e0` | Cor da lua |
| `stars` | `0` | Quantidade de estrelas à noite |

O horário também se controla em tempo real com `,` `.` e `P`.

### `[BILLBOARDS]` — sprites sempre de frente pra câmera

Sintaxe: `ID caminho/relativo/imagem.png offset_y [escala] [ai_type] [speed]` (índices `1` a `9`, usados como `B1`..`B9`)

```
1 assets/vaso_planta.png 0.0
2 assets/orbe_flutuante.png 0.9 1.5
3 assets/monstro.png 0.0 1.0 enemy 0.05
```

`offset_y` é a elevação em blocos em relação ao chão (`0.0` = no chão; valores maiores = flutuando). `escala` (padrão `1.0`) multiplica o sprite, que ocupa 1 unidade de altura. Cada célula com `B#` é atravessável e sempre encara a câmera, com oclusão correta contra as paredes.

Token opcionais (deixe de fora para billboards estáticos):

| Token | Valores | Padrão | Descrição |
| :--- | :--- | :--- | :--- |
| `ai_type` | `none` / `friendly` / `enemy` | `none` | Comportamento de IA (ver tutorial **§5.1**) |
| `speed` | número | `0.035` (friendly) / `0.05` (enemy) | Velocidade de deslocamento em unidades de mundo por frame |

### `[BILLBOARD_SOUNDS]` — áudio espacial por tipo de billboard (opcional)

Sintaxe: `ID caminho/relativo/audio.ext raio volume` (índices `1` a `9`, casam com os `B#` de `[BILLBOARDS]`)

```
1 assets/ambiente.mp3 10.0 1.0
2 assets/rugido.mp3 14.0 4.0
```

Cada entrada vincula um áudio de **loop infinito** a um tipo de billboard. O som é **estéreo posicional** (pan pelo ângulo relativo à mira, atenuação até `raio`) e sofre **oclusão** (`~0.45^paredes` entre emissor e jogador). `volume` vai de `0` a `10` (`1` = original, até `10×` amplificado). O mixer é iniciado só quando o mapa tem esta seção (ver tutorial **§5.2**).

### `[PARTICLES]` — sprites animados (flutuando)

Sintaxe: `ID caminho/relativo/imagem.png quantidade velocidade espalhamento` (índices `1` a `9`, usados como `P1`..`P9`)

```
1 assets/orbe_flutuante.png 8 0.6 4
```

`quantidade` (padrão `8`) = instâncias por célula, `velocidade` (padrão `0.5`) = rapidez do movimento, `espalhamento` (padrão `0.4`) = raio de dispersão ao redor do ponto central. O flutuar vertical é animado automaticamente.

### Exemplo mínimo completo

```ini
[TITLE]
Mapa de Teste

[CONFIG]
window 960 560
fov 60
ambient 0.08
fog 1.2
light_res 2
light_bounce 0.35

[SPAWN]
x 2.5
y 2.5
angle 0

[COLORS]
1 #444444 #222222
2 #882222 #661111

[TEXTURES]
1 assets/parede_pedra.png

[LIGHTS]
1 #ffaa44 5.0

[MAP]
1 1 1 1 1
1 0 0 0+L1 1
1 0 2 0 1
1 0 0 0 1
1 1 1 1 1
```

---

## 🗺️ Mapa de exemplo

As antigas demonstrações separadas (`demos/`, `mapas/`) foram **unificadas em uma única vitrine**, [`showcase.rcfg`](./showcase.rcfg), na raiz do projeto — reúne texturas, luzes, céu dinâmico, billboards e partículas num só lugar. Rode com:

```bash
python Raycasting.pyw showcase.rcfg
```

ou arraste o arquivo para dentro da janela.

---

## Editor visual de mapas

O repositório inclui [`editor.html`](./editor.html), que roda **direto no navegador** (sem servidor). Abra o arquivo localmente, monte o grid, configure texturas/luzes/céu/billboards/partículas e exporte o `.rcfg`. No painel **Billboards** você também define o **Tipo de IA** (Nenhum/Amigável/Inimigo), a **Velocidade da IA** e, no fieldset **Som posicional**, o caminho do áudio, o raio e o volume (0–10) por tipo. Ele também **abre** `.rcfg` existentes (arraste o arquivo para a página) e os reescreve na ordem canônica: `CONFIG`, `SPAWN`, `INFO`, `COLORS`, `LIGHTS`, `TEXTURES`, `THEME`, `SKY`, `TITLE`, `BILLBOARDS`, `BILLBOARD_SOUNDS`, `PARTICLES`, `MAP`.

---

## 📁 Estrutura do projeto

```
RAYCASTING-ENGINE/
├── Raycasting.pyw        # arquivo principal — execute este
├── requirements.txt
├── editor.html           # editor visual de mapas .rcfg (abre no navegador)
├── showcase.rcfg         # mapa de exemplo (texturas, luzes, céu, billboards e partículas)
├── LICENSE
├── README.md
└── assets/               # imagens usadas pelo showcase.rcfg
    ├── floating_orb.png
    ├── folder.png
    ├── garden_bush.png
    ├── garden_wall.png
    ├── grass.webp
    ├── metal.jpg
    ├── plant_pot.png
    ├── sparkle.png
    ├── waifu.png
    ├── wall.jpg
    └── youtube.webp
```

> **Dica de organização:** o projeto usa uma pasta [`assets/`](./assets) central na raiz, compartilhada por todos os mapas — é o padrão usado pelo `showcase.rcfg` e o recomendado para novos mapas. Como os caminhos no `.rcfg` são relativos ao próprio arquivo, isso significa que mapas na raiz do projeto referenciam as imagens como `assets/imagem.png`.

---

## 🧭 Roadmap / ideias futuras

- [ ] Otimização de desempenho da engine
- [ ] Melhoria gráfica da engine
- [x] Sistema de som posicional (estéreo + oclusão por parede)
- [ ] Muffle / low-pass real por parede (fase 2 do som)

*(sinta-se livre para abrir uma issue sugerindo algo)*

---

## ⚖️ Licença

Este projeto está licenciado sob a **GNU General Public License v3.0 (GPLv3)**. Veja o arquivo [LICENSE](./LICENSE) para o texto completo.

**Resumo prático:** você é livre para usar, estudar, modificar e distribuir este software. Qualquer versão modificada ou projeto derivado deve permanecer open source sob a mesma licença (GPLv3), com os devidos créditos aos autores originais.
