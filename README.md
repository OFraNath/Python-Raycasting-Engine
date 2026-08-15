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
python Raycasting.pyw mapas/garden/garden.rcfg
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

> **Regra de ouro dos caminhos:** a engine resolve os caminhos de imagens **relativos à pasta do próprio `.rcfg`**. Coloque as imagens numa subpasta `sprites/` ao lado do arquivo, como fazem os exemplos em [`demos/`](./demos) e [`mapas/`](./mapas).

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
1 sprites/tijolo.png
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
1 sprites/vaso_planta.png 0
2 sprites/orbe_flutuante.png 0.9 1.5
```

```ini
[MAP]
1 1 1 1 1
1 0 0 0 1
1 0+B2 0 0 1
1 0+B1 0 0 1
1 1 1 1 1
```

Sintaxe: `ID caminho offset_y [escala]`. `offset_y` eleva o sprite em relação ao chão (unidades de mundo; `0` = encostado, valores maiores = flutuando). `escala` (padrão `1.0`) multiplica o tamanho — por padrão o sprite ocupa 1 unidade de altura. Cada célula com `B#` é atravessável.

### 6. Partículas (sprites animados)

Igual a billboard, mas gera várias instâncias flutuantes espalhadas pela célula, cada uma subindo e descendo devagar. Definem-se em `[PARTICLES]` com tokens `P#`:

```ini
[PARTICLES]
1 sprites/orbe_flutuante.png 8 0.6 4
```

```ini
[MAP]
1 1 1 1 1
1 0 0 0 1
1 0+P1 0 0 1
1 0 0 0 1
1 1 1 1 1
```

Sintaxe: `ID caminho quantidade velocidade espalhamento`.

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

**Retrocompatibilidade** (a engine continua aceitando mapas antigos):

- `L1`, `B1`, `P1` **sem base** são interpretados como `0+L1`, `0+B1`, `0+P1`.
- Formatos 100% antigos, só com dígitos: `1` a `6` = parede e `7` ou mais = luz (`L1` equivale ao antigo `7`, `L2` ao `8`...). Nesse caso `7`, `8`, `9` **não** são paredes — por isso os mapas novos devem usar `L#`/`B#`/`P#`.

> **Na prática:** escreva sempre os tokens compostos (`0+L1` em vez de `L1`). É o formato atual e evita ambiguidade entre "parede 7" e "luz 1".

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
1 texturas/tijolo.png
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

Sintaxe: `ID caminho/relativo/imagem.png offset_y [escala]` (índices `1` a `9`, usados como `B1`..`B9`)

```
1 sprites/vaso_planta.png 0.0
2 sprites/orbe_flutuante.png 0.9 1.5
```

`offset_y` é a elevação em blocos em relação ao chão (`0.0` = no chão; valores maiores = flutuando). `escala` (padrão `1.0`) multiplica o sprite, que ocupa 1 unidade de altura. Cada célula com `B#` é atravessável e sempre encara a câmera, com oclusão correta contra as paredes.

### `[PARTICLES]` — sprites animados (flutuando)

Sintaxe: `ID caminho/relativo/imagem.png quantidade velocidade espalhamento` (índices `1` a `9`, usados como `P1`..`P9`)

```
1 sprites/orbe_flutuante.png 8 0.6 4
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
1 texturas/parede_pedra.png

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

## 🗺️ Mapas de exemplo

Todos os exemplos são arquivos `.rcfg` prontos. Rode com `python Raycasting.pyw caminho/do/mapa.rcfg` ou arraste para dentro da janela:

| Mapa | O que demonstra |
| :--- | :--- |
| [`mapas/garden/garden.rcfg`](./mapas/garden/garden.rcfg) | Um jardim com texturas e luz ambiente |
| [`mapas/backrooms/backrooms.rcfg`](./mapas/backrooms/backrooms.rcfg) | Labirinto com `wall_scale` alto (corredores altos) |
| [`demos/showcase/showcase.rcfg`](./demos/showcase/showcase.rcfg) | **Autocontido** — céu dinâmico + partículas + billboards (abre só com a pasta dele) |
| [`demos/festa_colorida.rcfg`](./demos/festa_colorida.rcfg) | Muitas luzes coloridas (stress de GI) |
| [`demos/billboards/demo_billboards.rcfg`](./demos/billboards/demo_billboards.rcfg) | Billboards estáticos com oclusão |
| [`demos/waifu_billboard/waifu_billboard.rcfg`](./demos/waifu_billboard/waifu_billboard.rcfg) | Billboards com imagens do dia a dia |
| [`demos/graphics/Shader.rcfg`](./demos/graphics/Shader.rcfg) | Mapas com muitas paredes/tipos |
| [`demos/graphics/Global Illumination.rcfg`](./demos/graphics/Global%20Illumination.rcfg) | Rebatimento de luz em cadeia (bounce) |

---

## Editor visual de mapas

O repositório inclui [`editor.html`](./editor.html), que roda **direto no navegador** (sem servidor). Abra o arquivo localmente, monte o grid, configure texturas/luzes/céu/billboards/partículas e exporte o `.rcfg`. Ele também **abre** `.rcfg` existentes (arraste o arquivo para a página) e os reescreve na ordem canônica: `CONFIG`, `SPAWN`, `INFO`, `COLORS`, `LIGHTS`, `TEXTURES`, `THEME`, `SKY`, `TITLE`, `BILLBOARDS`, `PARTICLES`, `MAP`.

---

## 📁 Estrutura do projeto

```
RAYCASTING-ENGINE/
├── Raycasting.pyw        # arquivo principal — execute este
├── requirements.txt
├── editor.html           # editor visual de mapas .rcfg (abre no navegador)
├── LICENSE
├── README.md
├── demos/                # mapas de demonstração
│   ├── billboards/       # sprites 2D sempre de frente pra câmera
│   │   ├── demo_billboards.rcfg
│   │   └── sprites/
│   │       ├── orbe_flutuante.png
│   │       └── vaso_planta.png
│   ├── festa_colorida.rcfg
│   ├── graphics/         # stress de iluminação
│   │   ├── Global Illumination.rcfg
│   │   └── Shader.rcfg
│   ├── showcase/         # céu + partículas + billboards (autocontido)
│   │   ├── showcase.rcfg
│   │   └── sprites/
│   │       ├── garden.png
│   │       ├── orbe_flutuante.png
│   │       └── vaso_planta.png
│   └── waifu_billboard/
│       ├── waifu_billboard.rcfg
│       └── sprites/
│           ├── folder.png
│           ├── waifu.jpg
│           └── youtube.webp
└── mapas/                # mapas de exemplo
    ├── backrooms/
    │   ├── backrooms.rcfg
    │   └── sprites/
    │       └── wall.jpg
    └── garden/
        ├── garden.rcfg
        └── sprites/
            ├── garden.png
            └── grass.webp
```

> **Dica de organização:** cada mapa vive em uma pasta própria com seus sprites em `sprites/` ao lado do `.rcfg`, como acima. Assim o mapa é **portátil**: copie a pasta inteira para qualquer lugar e ele continua funcionando.

---

## 🧭 Roadmap / ideias futuras

- [ ] Billboards com IA e movimento (entidades vivas)
- [ ] Otimização de UX do editor de `.rcfg`
- [ ] Sistema de som posicional

*(sinta-se livre para abrir uma issue sugerindo algo)*

---

## ⚖️ Licença

Este projeto está licenciado sob a **GNU General Public License v3.0 (GPLv3)**. Veja o arquivo [LICENSE](./LICENSE) para o texto completo.

**Resumo prático:** você é livre para usar, estudar, modificar e distribuir este software. Qualquer versão modificada ou projeto derivado deve permanecer open source sob a mesma licença (GPLv3), com os devidos créditos aos autores originais.
