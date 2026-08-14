## Raycasting FPS Engine (GPU Edition)

Engine de renderização pseudo-3D inspirada no estilo clássico de *Wolfenstein 3D*, executada diretamente no Fragment Shader (GPU) com Pygame, ModernGL e OpenGL (GLSL 330).

O sistema conta com iluminação dinâmica baseada na lei do inverso do quadrado (Inverse-Square Law), sombras suavemente suavizadas (penumbra), re-emissão indireta de luz (GI/Bounce) e suporte a texturas sRGB com fallback para cores sólidas.

---

## ⚡ Como Executar

### Pré-requisitos
* Python 3.8+
* Placa de vídeo compatível com OpenGL 3.3+

### Instalação das dependências
pip install pygame moderngl numpy pillow

### Rodando o projeto
Para abrir com o mapa padrão interno da engine:
python main.py

Para carregar um mapa específico `.rcfg`:
python main.py mapas/meu_mapa.rcfg

> **Dica de uso:** Arraste e solte (`Drag & Drop`) qualquer arquivo `.rcfg` para dentro da janela do jogo em execução para trocá-lo instantaneamente!

---

## 🛠️ Como criar seu próprio mapa (`.rcfg`)

Os mapas são salvos em arquivos texto no formato `.rcfg`. Veja abaixo como configurar cada seção.

> **Importante:** Para que as texturas sejam carregadas corretamente, o arquivo `.rcfg` deve estar na mesma pasta onde a pasta/arquivos de textura estão localizados (ou com os caminhos relativos devidamente mapeados a partir do local do arquivo).

### Exemplo Rápido de `.rcfg`
[TITLE]
value Mapa de Teste

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
1 parede_pedra.png

[LIGHTS]
7 #ffaa44 5.0

[MAP]
1 1 1 1 1
1 0 0 7 1
1 0 2 0 1
1 0 0 0 1
1 1 1 1 1

---

## 📑 Referência das Seções do `.rcfg`

### 1. `[CONFIG]` *(Opções Globais do Engine)*
Ajusta parâmetros de janela, câmera, neblina e algoritmo de luz.

| Chave | Padrão | Descrição |
| :--- | :--- | :--- |
| `window` | `960 560` | Resolução da janela (`largura altura`). |
| `fov` | `60` | Campo de visão da câmera em graus. |
| `ambient` | `0.07` | Intensidade da iluminação ambiente global (0.0 a 1.0). |
| `fog` | `1.4` | Intensidade do efeito de névoa/distância. |
| `light_res` | `1` | Sub-divisão da grade de luz por bloco (`1, 2, 4, 8, 16, 32`). Valores mais altos aumentam a precisão do gradiente da luz. |
| `light_soft_samples`| `6` | Quantidade de amostras para penumbra macia nas sombras. |
| `light_bounce` | `0.35` | Intensidade do re-batimento da luz nas paredes (*Global Illumination*). |
| `texture_size` | `256` | Tamanho padrão de redimensionamento das texturas importadas. |

### 2. `[SPAWN]` *(Posição Inicial)*
Define onde o jogador nasce e para onde está olhando.
* `x`: Posição X no grid.
* `y`: Posição Y no grid.
* `angle`: Ângulo da câmera em graus (0° a 360°).

### 3. `[COLORS]` *(Paredes de Cor Sólida)*
Define as cores das paredes quando **não** houver textura carregada.
* **Sintaxe:** `ID COR_FACES_NORTE_SUL COR_FACES_LESTE_OESTE`
* **Exemplo:** `1 #888888 #555555`

### 4. `[TEXTURES]` *(Paredes Texturizadas)*
Mapeia uma imagem PNG/JPG para um tipo de parede.
* **Sintaxe:** `ID caminho/relativo/imagem.png`
* **Exemplo:** `1 texturas/tijolo.png`
*(Certifique-se de que a pasta com as imagens esteja no mesmo diretório do arquivo `.rcfg` ou especificada a partir dele. A imagem é tratada no espaço de cor sRGB com correção de Gamma 2.2 automática no shader)*.

### 5. `[LIGHTS]` *(Fontes de Luz / Orbes)*
Define a cor e o raio de alcance de pontos luminosos no mapa.
* **Sintaxe:** `ID COR_HEX RAIO`
* **Exemplo:** `7 #ff8800 6.0` *(Torcha com luz alaranjada e alcance de 6 blocos)*.

### 6. `[MAP]` *(Matriz do Cenário)*
Tabela de inteiros representando o layout do nível (separados por espaço, vírgula ou ponto e vírgula):
* **`0`**: Espaço vazio (área onde o jogador caminha).
* **`1` a `6`**: Paredes (Lidas do `[TEXTURES]` ou `[COLORS]`).
* **`7` ou mais**: Fontes de Luz / Orbes (Lidas da seção `[LIGHTS]`).

---

## ⌨️ Controles
* **`W, A, S, D`** ou **`Setas`**: Movimentação.
* **`SHIFT`**: Correr.
* **`Mouse`**: Rotacionar a câmera e olhar para cima/baixo.
* **`ESC`**: Alternar captura da trava do mouse.
* **`R`**: Resetar posição do jogador para o `SPAWN` original do arquivo.

---

## ⚖️ Licença

Este projeto está licenciado sob a **GNU General Public License v3.0 (GPLv3)**. Para mais detalhes legais, consulte o arquivo [LICENSE](./LICENSE) na raiz do repositório.

> **Resumo prático:** Você é livre para usar, estudar, modificar e distribuir este software. No entanto, qualquer versão modificada ou projeto derivado **deve ser mantido como código aberto** sob esta mesma licença (GPLv3), dando os devidos créditos aos autores originais.