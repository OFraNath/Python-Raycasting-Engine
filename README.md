# Raycasting FP Engine (Edição GPU)

Engine de renderização pseudo-3D inspirada no estilo clássico de *Wolfenstein 3D*, mas executada **diretamente no Fragment Shader (GPU)** usando Pygame, ModernGL e OpenGL (GLSL 330) — em vez do raycasting tradicional feito coluna por coluna na CPU.

O diferencial é o sistema de iluminação dinâmica: luzes seguem a lei do inverso do quadrado, projetam sombras suavizadas (penumbra) e ainda reemitem luz indiretamente nas paredes vizinhas (GI/Bounce), tudo calculado previamente assim que o .rcfg é carregado.

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

## ✨ Principais recursos

- Renderização por pixel no fragment shader (GPU real, não CPU)
- Iluminação dinâmica com queda de intensidade por inverso do quadrado
- Sombras com penumbra suave (soft shadows)
- Global Illumination simplificada (bounce de luz nas paredes)
- Billboards: sprites 2D sempre de frente pra câmera, com oclusão por profundidade (Fase 5)
- Texturas em sRGB com correção de gamma automática, com fallback para cor sólida
- Formato de mapa próprio (`.rcfg`), simples de editar em qualquer editor de texto
- Drag & drop de arquivos `.rcfg` direto na janela do jogo, para trocar de mapa sem reiniciar

---

## 📁 Estrutura do projeto

```
RAYCASTING-ENGINE/
├── Raycasting.pyw        # arquivo principal — execute este
├── requirements.txt
├── editor.html           # editor de mapas .rcfg
├── mapas/                # mapas de exemplo em formato .rcfg
│   ├── backrooms/
│   │   ├── backrooms.rcfg
│   │   └── sprites/
│   │       └── wall.jpg
│   ├── demo_billboards/
│   │   ├── demo_billboards.rcfg
│   │   └── sprites/
│   ├── demo_waifu_billboard/
│   │   ├── waifu.rcfg
│   │   └── sprites/
│   ├── festa_colorida.rcfg
│   └── teste_iluminação.rcfg
└── LICENSE
```

---

## ⚡ Como executar

### Pré-requisitos
- Python 3.8+
- Placa de vídeo compatível com OpenGL 3.3+

### Instalação

```bash
git clone https://github.com/SEU-USUARIO/RAYCASTING-ENGINE.git
cd RAYCASTING-ENGINE
pip install -r requirements.txt
```

### Executando

Com o mapa padrão interno da engine:

```bash
python Raycasting.pyw
```

Carregando um mapa específico `.rcfg` diretamente:

```bash
python Raycasting.pyw mapas/backrooms/backrooms.rcfg
```

> **Dica:** com o jogo já em execução, arraste e solte qualquer arquivo `.rcfg` dentro da janela para trocar de mapa instantaneamente, sem precisar reiniciar.

---

## ⌨️ Controles

| Tecla | Ação |
| :--- | :--- |
| `W` `A` `S` `D` ou setas | Movimentação |
| `Shift` | Correr |
| `Mouse` | Rotacionar câmera / olhar para cima e para baixo |
| `Esc` | Alternar captura do mouse (travar/destravar cursor) |
| `R` | Resetar posição do jogador para o `SPAWN` original do mapa |

---

## 🛠️ Criando seus próprios mapas (`.rcfg`)

Mapas são arquivos de texto simples. O `.rcfg` deve ficar na mesma pasta das texturas que ele referencia (ou usar caminhos relativos corretos a partir do local do arquivo).

### Exemplo mínimo

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
1 0 0 L1 1
1 0 2 0 1
1 0 0 0 1
1 1 1 1 1
```

### Referência das seções

#### `[CONFIG]` — opções globais

| Chave | Padrão | Descrição |
| :--- | :--- | :--- |
| `window` | `960 560` | Resolução da janela (`largura altura`) |
| `mm` | `140` | Tamanho da janela do minimapa em pixels |
| `fov` | `60` | Campo de visão da câmera, em graus |
| `num_rays` | `180` | Número de raios por coluna da tela |
| `max_depth` | `30` | Alcance máximo dos raios, em blocos |
| `move_speed` | `0.06` | Velocidade de caminhada por frame |
| `run_multiplier` | `1.8` | Multiplicador de velocidade ao correr (`Shift`) |
| `mouse_sens_x` | `0.004` | Sensibilidade horizontal do mouse |
| `mouse_sens_y` | `1.0` | Sensibilidade vertical do mouse |
| `max_look_y` | `240` | Ângulo máximo de olhar para cima/baixo |
| `fog` | `1.4` | Intensidade da névoa por distância |
| `gradient_steps` | `14` | Número de faixas do gradiente de céu |
| `ambient` | `0.07` | Intensidade da luz ambiente global (`0.0` a `1.0`) |
| `floor_bands` | `4` | Número de faixas do gradiente de chão |
| `floor_step` | `2` | Progressão de escurecimento entre as faixas do chão |
| `light_res` | `1` | Subdivisão da grade de luz por bloco (`1, 2, 4, 8, 16, 32`); valores maiores dão gradientes de luz mais precisos, com custo de performance |
| `light_soft_samples` | `6` | Número de amostras usadas na penumbra das sombras |
| `light_soft_radius` | `0.4` | Raio de espalhamento da penumbra |
| `light_bounce` | `0.35` | Intensidade do rebote de luz nas paredes (GI) |
| `light_bounce_radius` | `1.6` | Raio de alcance do rebote de luz |
| `light_bounce_passes` | `2` | Número de passes do rebote de luz |
| `texture_size` | `256` | Tamanho de redimensionamento padrão das texturas importadas |

#### `[SPAWN]` — posição inicial

- `x`, `y`: posição no grid do mapa
- `angle`: ângulo inicial da câmera, em graus (`0` a `360`)

#### `[COLORS]` — paredes sem textura

Sintaxe: `ID COR_FACES_NORTE_SUL COR_FACES_LESTE_OESTE`

```
1 #888888 #555555
```

#### `[TEXTURES]` — paredes texturizadas

Sintaxe: `ID caminho/relativo/imagem.png`

```
1 texturas/tijolo.png
```

A imagem é tratada em espaço de cor sRGB, com correção de gamma 2.2 aplicada automaticamente no shader.

#### `[LIGHTS]` — fontes de luz

Sintaxe: `ID COR_HEX RAIO`

```
1 #ff8800 6.0
```
Tocha com luz alaranjada e alcance de 6 blocos. No formato novo, o `ID` de `1` a `9` corresponde aos tokens `L1`..`L9` usados na grade do `[MAP]`.

#### `[BILLBOARDS]` — sprites sempre de frente pra câmera

Sintaxe: `ID caminho/relativo/imagem.png offset_y`

```
1 sprites/vaso_planta.png 0.0
2 sprites/orbe_flutuante.png 0.9
```
`offset_y` é a elevação em blocos em relação ao chão (`0.0` = encostado no chão, valores maiores = flutuando). Os `ID`s de `1` a `9` correspondem aos tokens `B1`..`B9` usados na grade do `[MAP]`. Cada instância de billboard é atravessável e sempre encara a câmera, recebendo oclusão correta contra as paredes do DDA.

#### `[MAP]` — layout do nível

Matriz de tokens separados por espaço, vírgula ou ponto e vírgula:

- `0`: espaço vazio (área percorrível)
- `1` a `6`: paredes (definidas em `[TEXTURES]` ou `[COLORS]`)
- `L1` a `L9`: fontes de luz (definidas em `[LIGHTS]`)
- `B1` a `B9`: billboards (definidos em `[BILLBOARDS]`)

*(O formato legado ainda é aceito: `7` ou mais = luzes definidas em `[LIGHTS]` com o mesmo número.)*

---

## 🗺️ Mapas de exemplo

A pasta [`mapas/`](./mapas) já vem com alguns exemplos prontos para testar.

- Basta arrastar o .rcfg do mapa que preferir para dentro da janela do Raycasting

---

## 🧭 Roadmap / ideias futuras

- [ ] Billboards com IA e movimento (entidades vivas)
- [ ] Otimização de UX do editor de .rcfg
- [ ] Sistema de som posicional

*(sinta-se livre para abrir uma issue sugerindo algo)*

---

## ⚖️ Licença

Este projeto está licenciado sob a **GNU General Public License v3.0 (GPLv3)**. Veja o arquivo [LICENSE](./LICENSE) para o texto completo.

**Resumo prático:** você é livre para usar, estudar, modificar e distribuir este software. Qualquer versão modificada ou projeto derivado deve permanecer open source sob a mesma licença (GPLv3), com os devidos créditos aos autores originais.
