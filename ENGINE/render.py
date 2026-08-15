# Núcleo gráfico — dono dos recursos GPU.
#
# Possui os shaders GLSL, o contexto moderngl, a criação/upload de texturas
# e o carregador de assets de imagem (que alimenta as texturas). Não possui
# estado de jogo: lê o que precisa do núcleo lógico (`logic`) e recebe a
# cena do loop por parâmetro quando aplicável.
import os

import moderngl
import numpy as np
import pygame
from PIL import Image

from . import logic
from .logic import _rgb


# ══ CARREGADOR DE ASSETS (Fase 1) ════════════════════════════════
# Cache em memória: (caminho_absoluto, tamanho) -> pygame.Surface já pronta
# (RGBA, redimensionada). Evita recarregar/redimensionar a mesma imagem
# várias vezes (ex: dois tipos de parede usando a mesma textura).
_ASSET_CACHE = {}


def _fallback_array(tamanho):
    # Xadrez magenta/preto — "textura de erro" clássica, bem visível, pra
    # avisar que um asset referenciado no .rcfg não foi encontrado sem
    # travar o carregamento do mapa inteiro.
    w, h = tamanho
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    cel = max(1, min(w, h) // 8)
    magenta = (255, 0, 255, 255)
    preto = (0, 0, 0, 255)
    for j in range(0, h, cel):
        for i in range(0, w, cel):
            cor = magenta if ((i // cel) + (j // cel)) % 2 == 0 else preto
            arr[j:j + cel, i:i + cel] = cor
    return arr


def load_asset_image(caminho_abs, tamanho, contain=False):
    # Todo caminho de asset já deve chegar aqui RESOLVIDO (absoluto),
    # relativo à pasta do .rcfg — ver load_rcfg(). tamanho é obrigatório
    # aqui pq o texture array da GPU exige que todas as camadas tenham o
    # mesmo tamanho (ver upload_wall_textures / upload_textures).
    #
    # Usa Pillow em vez de pygame.image.load: suporte a WEBP mais confiável
    # e detecção de canal alpha mais previsível, independente de como o
    # pygame/SDL_image local foi compilado (Problema 3 do PLANO.md).
    #
    # Retorna (array_rgba_uint8 do tamanho pedido, aspect_ratio_original).
    # Com contain=True (billboards), a imagem é redimensionada preservando
    # a proporção original e centralizada num quadro `tamanho`, com a
    # sobra preenchida em alpha 0 — sem contain (paredes), a imagem é
    # esticada direto pro tamanho pedido, como antes (Problema 4).
    key = (caminho_abs, tamanho, contain)
    cached = _ASSET_CACHE.get(key)
    if cached is not None:
        return cached

    try:
        raw = Image.open(caminho_abs)
        # Detecta se a imagem de origem tem canal alpha ANTES do convert()
        # forçado abaixo, já que convert("RGBA") sempre adiciona um canal A
        # (opaco) mesmo pra formatos sem transparência (ex. JPG).
        has_alpha = ("A" in raw.getbands()) or ("transparency" in raw.info)
        img = raw.convert("RGBA")
    except Exception as e:
        print(f"[assets] falha ao carregar {caminho_abs!r}: {e}", flush=True)
        arr = _fallback_array(tamanho)
        result = (arr, 1.0)
        _ASSET_CACHE[key] = result
        return result

    if not has_alpha:
        print(
            f"[assets] {caminho_abs!r} não tem canal alpha — vai aparecer "
            f"com fundo sólido",
            flush=True,
        )

    w, h = img.size
    aspect = (w / h) if h else 1.0

    # "Unmatte": zera o RGB de pixels quase totalmente transparentes antes
    # do resize. Neutraliza matte branco/lixo assado na borda de PNGs
    # "transparentes" mal exportados, sem precisar reexportar a arte —
    # e de quebra evita que esse lixo vaze pra dentro da borda durante o
    # resize suave / mipmaps (Problema 2 do PLANO.md).
    arr = np.array(img, dtype=np.uint8)
    alpha_f = arr[:, :, 3].astype(np.float32) / 255.0
    quase_transparente = alpha_f < 0.02
    if np.any(quase_transparente):
        arr[quase_transparente] = 0
        img = Image.fromarray(arr, "RGBA")

    tw, th = tamanho
    if contain and w > 0 and h > 0:
        scale = min(tw / w, th / h)
        new_w = max(1, round(w * scale))
        new_h = max(1, round(h * scale))
        resized = img.resize((new_w, new_h), Image.LANCZOS)
        canvas = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        canvas.paste(resized, ((tw - new_w) // 2, (th - new_h) // 2), resized)
        img = canvas
    elif (w, h) != (tw, th):
        img = img.resize((tw, th), Image.LANCZOS)

    final_arr = np.ascontiguousarray(np.array(img, dtype=np.uint8))
    result = (final_arr, aspect)
    _ASSET_CACHE[key] = result
    return result


# ══ SHADERS (GLSL 330) ═════════════════════════════════════════
VERT = """
#version 330 core
in vec2 in_pos;
in vec2 in_uv;
out vec2 uv;
void main() {
    uv = in_uv;
    gl_Position = vec4(in_pos, 0.0, 1.0);
}
"""

FRAG = """
#version 330 core
in vec2 uv;
out vec4 outColor;

uniform vec2 u_res;
uniform vec2 u_pos;
uniform vec2 u_dir;
uniform vec2 u_plane;
uniform vec2 u_mapSize;
uniform float u_horizon;
uniform float u_scale;
uniform float u_ambient;
uniform float u_fog;
uniform float u_depth;

// Fase 4: em vez de constantes fixas (#define ORB_MIN 7, "t<=6"), agora
// são uniforms — o intervalo de ids de parede e o id mínimo de luz mudam
// conforme o mapa é legado (paredes 1-6, luz é dígito >=7) ou novo
// (paredes 1-9, luz é a letra "L1".."L9", offset interno alto).
uniform float u_wallMax;
uniform float u_orbMin;

uniform sampler2D u_map;    // tipo de celula (R32F)
uniform sampler2D u_light;  // grade de luz (R32F)
uniform sampler2D u_palA;   // cor A por tipo (RGBA32F)
uniform sampler2D u_palB;   // cor B por tipo
uniform sampler2DArray u_wallTex;  // texturas por tipo (Fase 2), 1 camada por tipo
uniform sampler2D u_hasTex;        // 1.0 = tipo tem textura própria, 0.0 = usa cor sólida

// Fase 5: billboards (sprites sempre de frente pra câmera)
uniform int u_bbCount;
uniform vec2 u_bbPos[128];
uniform float u_bbLayer[128];
uniform float u_bbYOff[128];
uniform float u_bbAspect[128];  // largura/altura original de cada sprite (Problema 4 do PLANO.md)
uniform float u_bbScale[128];   // multiplicador de tamanho por instância (escala do .rcfg)
uniform float u_bbAmp[128];     // amplitude do flutuar vertical (0 = billboard estático)
uniform float u_bbVel[128];     // velocidade do flutuar (item 3 do PLANO.md)
uniform float u_bbPhase[128];   // fase inicial (determinística por instância)
uniform float u_time;           // segundos desde o início, pro flutuar das partículas
uniform sampler2DArray u_bbTex;
uniform sampler2D u_mmFlags;       // flags por célula só pro minimapa (Problema 7)

uniform vec3 u_skyB, u_skyT, u_floorB, u_floorT;
uniform float u_sunAngle, u_sunElev, u_nightFactor, u_starsCount, u_skyBodies;
uniform vec3 u_sunColor, u_moonColor;
uniform vec3 u_cross;
uniform vec3 u_mmPlayer;

uniform vec2 u_mmPos;    // pixel do canto sup-esq do minimapa
uniform vec2 u_mmSize;   // pixel
uniform float u_mmCell;  // pixels por celula
uniform vec2 u_playerPix;// pixel do jogador no minimapa
uniform vec2 u_dirPix;   // ponta da linha de direcao

vec2 mapTex(vec2 cell) { return vec2((cell.x + 0.5) / u_mapSize.x, (cell.y + 0.5) / u_mapSize.y); }
int cellType(vec2 cell) { return int(round(texture(u_map, mapTex(cell)).r)); }
// worldPos é uma posição contínua no mundo (não uma célula inteira).
// A textura de luz tem resolução mais fina que o mapa (LIGHT_RES subcelulas
// por bloco) e usa filtro LINEAR, então isso dá um gradiente suave em vez
// de luz "em blocos".
vec3 softClip(vec3 x, float knee, float maxv) {
    // Identidade até 'knee' (a esmagadora maioria da cena passa reta,
    // sem escurecer nada). Só o que passa de 'knee' é comprimido de forma
    // suave em direção a 'maxv' — o cotovelo vira uma curva em vez de um
    // corte seco, sem afetar o brilho geral do resto da imagem.
    vec3 over = max(x - vec3(knee), vec3(0.0));
    vec3 compressed = (maxv - knee) * (vec3(1.0) - exp(-over / (maxv - knee)));
    return min(x, vec3(knee)) + compressed;
}
vec3 lightAt(vec2 worldPos) {
    vec2 uvL = worldPos / u_mapSize;
    vec3 l = texture(u_light, uvL).rgb;
    vec3 hdr = vec3(u_ambient) + l;
    return softClip(hdr, 3.0, 7.0);
}
vec3 palColor(float t, int useA) {
    vec2 c = vec2((t + 0.5) / 256.0, 0.5);
    return useA == 1 ? texture(u_palA, c).rgb : texture(u_palB, c).rgb;
}
float hasWallTex(float t) {
    return texture(u_hasTex, vec2((t + 0.5) / 256.0, 0.5)).r;
}
vec3 wallTexColor(float t, vec2 uvFace) {
    // camada = tipo - 1 (tipos vão de 1 a TEXTURE_LAYERS)
    return texture(u_wallTex, vec3(uvFace, t - 1.0)).rgb;
}

// ── céu: sol/lua/estrelas (PLANO.md item 2) ──
// u_skyBodies é 0.0 quando o .rcfg não tem seção [SKY]: nesse caso as
// contribuições abaixo somam zero e o gradiente fica idêntico ao atual.
float starHash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}

vec3 celestialContrib(vec2 dirWorld, float elevSin, vec3 col, float pixX, float row) {
    // Mesma técnica de projeção câmera-espaço usada nos billboards, só que
    // "dirWorld" é uma direção (astro no infinito) em vez de uma posição.
    float invDet = 1.0 / (u_plane.x * u_dir.y - u_dir.x * u_plane.y);
    float tx = invDet * (u_dir.y * dirWorld.x - u_dir.x * dirWorld.y);
    float ty = invDet * (-u_plane.y * dirWorld.x + u_plane.x * dirWorld.y);
    if (ty <= 0.02) return vec3(0.0);
    float screenX = (u_res.x * 0.5) * (1.0 + tx / ty);
    // Projeção de cúpula: mesma fórmula das estrelas (elevSin = ry/sqrt(rx²+ry²+rz²)).
    // A antiga projeção linear (u_horizon - elevSin*u_scale*0.5) esmagava o astro
    // na direção do horizonte: o zênite (elevSin=1) aparecia a só ~45° de altura.
    // rx usa length(u_plane) igual ao domo das estrelas. Sem clamp no topo: quando
    // a elevação passa do limite do viewport o astro sai da tela como as estrelas
    // (olhar para cima para vê-lo) — nunca fica preso/escorregando na borda.
    float rx = length(u_plane) * (tx / ty);
    float tanE = elevSin / sqrt(max(1.0 - elevSin * elevSin, 1e-4));
    float ry = tanE * sqrt(rx * rx + 1.0);
    float screenY = u_horizon - ry * (u_scale * 0.5);
    float d = length(vec2(pixX - screenX, row - screenY));
    float mask = 1.0 - smoothstep(10.0, 16.0, d);
    float fade = clamp(elevSin * 6.0 + 0.3, 0.0, 1.0);
    return col * mask * fade;
}

vec3 skyColor(float row, vec2 rayDir, float pixX) {
    vec3 base = mix(u_skyB, u_skyT, clamp(row / max(u_horizon, 1.0), 0.0, 1.0));
    if (u_skyBodies < 0.5) return base;
    vec2 sunDir = vec2(cos(u_sunAngle), sin(u_sunAngle));
    base += celestialContrib(sunDir, u_sunElev, u_sunColor, pixX, row);
    base += celestialContrib(-sunDir, -u_sunElev, u_moonColor, pixX, row);
    if (u_starsCount > 0.5 && u_nightFactor > 0.02) {
        float az = atan(rayDir.y, rayDir.x);
        // Cúpula celeste: a elevação usa as 3 componentes do raio (right =
        // u_plane·ndcX, up = (horizon-row)/focal, forward = 1) em vez de só
        // a linha da tela. Isso ancora o grid no MUNDO e restaura a curvatura
        // de domo: as estrelas não achatam nas bordas nem parecem girar com a
        // câmera (antes a elevação "1.0 - row/u_horizon" mudava junto com
        // u_horizon ao olhar pra cima/baixo).
        float focal = max(u_scale * 0.5, 1.0);
        float ndcX = pixX / max(u_res.x * 0.5, 1.0) - 1.0;
        float rx = length(u_plane) * ndcX;
        float ry = (u_horizon - row) / focal;
        float elevSin = ry / sqrt(rx * rx + ry * ry + 1.0);

        // Estrelas como PONTOS (não a célula cheia): a célula de azimute
        // (1.43°) × sin-elevação (1/260) projeta como listra 12×1px perto do
        // horizonte e quadrado 12×12 no alto. Aqui cada estrela é um disco de
        // ~2-3px, redondo em qualquer direção (peso por eixo = px/célula).
        // Verifica a vizinhança 3×3 para a estrela não sumir quando o
        // fragmento está na borda da célula dela; o eixo do azimute usa mod
        // canônico para a costura em ±180° não "comer" estrelas.
        float azCells = 2.0 * 3.14159265 * 40.0;
        float fragX = mod(az * 40.0, azCells);
        vec2 fragCell = vec2(fragX, elevSin * u_starsCount);
        vec2 cellSz = floor(fragCell);
        float pxPerAzCell = (u_res.x * 0.5) * dot(rayDir, rayDir) / max(length(u_plane) * 40.0, 1e-4);
        float pxPerElCell = focal * sqrt(rx * rx + ry * ry + 1.0) / max((1.0 - elevSin * elevSin) * u_starsCount, 1e-4);
        float starMask = 0.0;
        for (int dy = -1; dy <= 1; dy++) {
            for (int dx = -1; dx <= 1; dx++) {
                vec2 c = cellSz + vec2(float(dx), float(dy));
                c.x = mod(c.x, azCells);
                float hasStar = step(0.995, starHash(c));
                vec2 sub = vec2(starHash(c + vec2(0.0, 1.0)), starHash(c + vec2(1.0, 0.0)));
                vec2 off = c + sub - fragCell;
                if (off.x > azCells * 0.5) off.x -= azCells;
                if (off.x < -azCells * 0.5) off.x += azCells;
                float dp = length(vec2(off.x * pxPerAzCell, off.y * pxPerElCell));
                starMask += hasStar * (1.0 - smoothstep(1.3, 3.0, dp));
            }
        }
        base += vec3(1.0) * clamp(starMask, 0.0, 1.0) * u_nightFactor * 0.9;
    }
    return base;
}

void main() {
    vec2 ndc = uv * 2.0 - 1.0;
    vec2 rayDir = u_dir + u_plane * ndc.x;
    if (dot(rayDir, rayDir) < 1e-6) rayDir = u_dir;

    float row = (1.0 - uv.y) * u_res.y;   // 0 no topo da tela
    float horizon = u_horizon;

    vec2 mapPos = floor(u_pos);
    vec2 delta = abs(vec2(1.0, 1.0) / rayDir);
    vec2 sideDist;
    ivec2 step;
    if (rayDir.x < 0.0) { step.x = -1; sideDist.x = (u_pos.x - mapPos.x) * delta.x; }
    else                { step.x =  1; sideDist.x = (mapPos.x + 1.0 - u_pos.x) * delta.x; }
    if (rayDir.y < 0.0) { step.y = -1; sideDist.y = (u_pos.y - mapPos.y) * delta.y; }
    else                { step.y =  1; sideDist.y = (mapPos.y + 1.0 - u_pos.y) * delta.y; }

    int wtype = 0;
    int side = 0;
    bool hit = false;
    int it = 0;
    int maxIt = int(u_depth) + 4;
    while (!hit && it < maxIt) {
        if (sideDist.x < sideDist.y) { sideDist.x += delta.x; mapPos.x += float(step.x); side = 0; }
        else                          { sideDist.y += delta.y; mapPos.y += float(step.y); side = 1; }
        if (mapPos.x < 0.0 || mapPos.x >= u_mapSize.x || mapPos.y < 0.0 || mapPos.y >= u_mapSize.y) break;
        int t = cellType(mapPos);
        if (t >= 1 && t <= int(u_wallMax)) { hit = true; wtype = t; }
        it++;
    }

    vec3 color;
    if (hit) {
        float perpDist = (side == 0) ? (sideDist.x - delta.x) : (sideDist.y - delta.y);
        vec3 wcol = (side == 1) ? palColor(float(wtype), 1) : palColor(float(wtype), 0);
        // amostra a luz na célula ABERTA vizinha (do lado de onde o raio
        // veio), não dentro da própria célula da parede. A coordenada
        // tangencial (ao longo da face) continua vindo do ponto exato de
        // impacto, o que preserva o gradiente de luz ao longo da parede.
        // Já a coordenada perpendicular à face é fixada no centro do texel
        // da célula aberta — assim a amostra nunca mistura (via filtro
        // LINEAR) com o valor "morto"/ambiente da própria parede, que era
        // o que fazia as quinas parecerem mais brilhantes que o centro da
        // face.
        vec2 hitWorld = u_pos + perpDist * rayDir;
        vec2 faceNormal = (side == 0) ? vec2(-float(step.x), 0.0) : vec2(0.0, -float(step.y));
        vec2 wallSample = hitWorld + faceNormal * 0.5;
        wallSample = clamp(wallSample, vec2(0.02), u_mapSize - vec2(0.02));
        vec3 lightv = lightAt(wallSample);
        float fogv = clamp((u_fog * perpDist) / u_depth, 0.0, 1.0);
        // coordenada U ao longo da face (tangencial), repete a cada 1 unidade
        // de mapa — o clássico "fract" de raycaster pra texturizar paredes.
        float texU = fract((side == 0) ? hitWorld.y : hitWorld.x);
        float hasTexFlag = hasWallTex(float(wtype));

        float lineH = u_scale / perpDist;
        float wallTop = horizon - lineH * 0.5;
        float wallBottom = horizon + lineH * 0.5;

        if (row >= wallTop && row <= wallBottom) {
            float texV = clamp((row - wallTop) / max(1.0, wallBottom - wallTop), 0.0, 1.0);

            vec3 wcolFinal;
            if (hasTexFlag > 0.5) {
                // PAREDE COM TEXTURA:
                // 1. Pega a textura e converte de sRGB para espaço linear
                vec3 texColor = wallTexColor(float(wtype), vec2(texU, texV));
                texColor = pow(texColor, vec3(2.2));

                // 2. Comprime a iluminação na textura (Tonemapping suave)
                vec3 dynamicLight = lightv / (lightv + vec3(1.0));
                vec3 litTex = texColor * dynamicLight * 2.2;

                // 3. Aplica o Gamma de volta para os olhos
                wcolFinal = pow(litTex, vec3(1.0 / 2.2));
            } else {
                // PAREDE DE COR SÓLIDA ([COLORS]):
                // Usa a iluminação direta normal, sem distorcer o tom da cor HEX
                vec3 dynamicLight = lightv / (lightv + vec3(1.0));
                wcolFinal = wcol * dynamicLight * 1.5;
            }

            // Sombreamento 3D das quinas (N/S vs L/O)
            float sideShade = (side == 1) ? 0.8 : 1.0;

            color = wcolFinal * sideShade * (1.0 - fogv);
        } else if (row > wallBottom) {
            float rowDist = (u_scale * 0.5) / (row - horizon);
            vec2 fc = u_pos + rowDist * rayDir;
            float depthT = (row - horizon) / (u_scale * 0.5);
            vec3 fcol = mix(u_floorB, u_floorT, clamp(depthT, 0.0, 1.0));
            vec3 lv = lightAt(fc);
            float fv = clamp((u_fog * rowDist) / u_depth, 0.0, 1.0);
            color = fcol * lv * (1.0 - fv);
        } else {
            color = skyColor(row, rayDir, uv.x * u_res.x);
        }
    } else {
        if (row > horizon) {
            float rowDist = (u_scale * 0.5) / (row - horizon);
            vec2 fc = u_pos + rowDist * rayDir;
            float depthT = (row - horizon) / (u_scale * 0.5);
            vec3 fcol = mix(u_floorB, u_floorT, clamp(depthT, 0.0, 1.0));
            vec3 lv = lightAt(fc);
            float fv = clamp((u_fog * rowDist) / u_depth, 0.0, 1.0);
            color = fcol * lv * (1.0 - fv);
        } else {
            color = skyColor(row, rayDir, uv.x * u_res.x);
        }
    }

    vec2 pix = vec2(uv.x, 1.0 - uv.y) * u_res;

    // ── billboards (Fase 5): sprites que sempre encaram a câmera ──
    // Técnica clássica de sprite-casting: transforma a posição do
    // billboard pro espaço da câmera usando a inversa da matriz
    // [plane, dir] (mesma convenção 2D usada nos raycasters tipo
    // Wolfenstein/Lodev). "ty" é a profundidade ao longo do raio da
    // câmera — já corrigida contra o efeito "olho de peixe", assim como
    // perpDist é pras paredes — e "tx" é o deslocamento lateral.
    {
        float wallDepth = hit ? ((side == 0) ? (sideDist.x - delta.x) : (sideDist.y - delta.y)) : 1e9;
        float invDet = 1.0 / (u_plane.x * u_dir.y - u_dir.x * u_plane.y);
        float bestDepth = 1e9;
        vec4 bestSample = vec4(0.0);
        for (int b = 0; b < u_bbCount && b < 128; b++) {
            vec2 sp = u_bbPos[b] - u_pos;
            float tx = invDet * (u_dir.y * sp.x - u_dir.x * sp.y);
            float ty = invDet * (-u_plane.y * sp.x + u_plane.x * sp.y);
            if (ty <= 0.05 || ty >= wallDepth || ty >= bestDepth) continue;

            float screenX = (u_res.x * 0.5) * (1.0 + tx / ty);
            float size = (u_scale / ty) * u_bbScale[b];   // sprite de 1 unidade de mundo (altura) × escala do .rcfg
            float aspect = u_bbAspect[b];
            float sizeX = size * aspect; // largura na tela segue a proporção original da imagem
            float sizeY = size;
            float left = screenX - sizeX * 0.5;
            if (pix.x < left || pix.x > left + sizeX) continue;

            // offset_y fixo + flutuar animado (amplitude/velocidade/fase) — item 3
            // do PLANO.md; pra billboard estático (amplitude 0) fica igual a antes.
            float dynOff = u_bbYOff[b] + u_bbAmp[b] * sin(u_time * u_bbVel[b] + u_bbPhase[b]);
            float shift = dynOff * (u_scale / ty);
            float bottom = horizon + sizeY * 0.5 - shift;
            float top = bottom - sizeY;
            if (row < top || row > bottom) continue;

            // A textura guarda a imagem com "contain" (proporção preservada,
            // centralizada num quadro quadrado com padding transparente) —
            // como o quad na tela já usa a proporção certa (sizeX/sizeY),
            // a amostragem precisa focar só na região não-padding do
            // quadro, senão o sprite fica menor dentro do próprio quad
            // (Problema 4 do PLANO.md).
            float fx = min(1.0, aspect);
            float fy = min(1.0, 1.0 / aspect);
            float ux = (pix.x - left) / sizeX;
            float uy = (row - top) / sizeY;
            vec2 uvBB = vec2(ux * fx + (1.0 - fx) * 0.5, uy * fy + (1.0 - fy) * 0.5);
            vec4 s = texture(u_bbTex, vec3(uvBB, u_bbLayer[b]));
            if (s.a < 0.05) continue;

            bestDepth = ty;
            bestSample = s;
        }
        if (bestSample.a > 0.0) {
            vec2 bWorld = clamp(u_pos + bestDepth * rayDir, vec2(0.02), u_mapSize - vec2(0.02));
            vec3 lv = lightAt(bWorld);
            vec3 dyn = lv / (lv + vec3(1.0));
            vec3 lit = bestSample.rgb * dyn * 2.0;
            float fogv2 = clamp((u_fog * bestDepth) / u_depth, 0.0, 1.0);
            color = mix(color, lit * (1.0 - fogv2), bestSample.a);
        }
    }

    // crosshair (braços curtos, com vão no centro)
    vec2 ctr = u_res * 0.5;
    float ax = abs(pix.x - ctr.x);
    float ay = abs(pix.y - ctr.y);
    bool onH = (ay < 2.0) && (ax < 12.0) && (ax > 4.0);
    bool onV = (ax < 2.0) && (ay < 12.0) && (ay > 4.0);
    if (onH || onV) {
        color = mix(color, u_cross, 0.8);
    }

    // minimapa (canto sup-direito)
    vec2 mmPix = pix - u_mmPos;
    if (mmPix.x >= 0.0 && mmPix.x < u_mmSize.x && mmPix.y >= 0.0 && mmPix.y < u_mmSize.y) {
        vec2 cell = floor(mmPix / u_mmCell);
        if (cell.x >= 0.0 && cell.x < u_mapSize.x && cell.y >= 0.0 && cell.y < u_mapSize.y) {
            int t = cellType(cell);
            int flags = int(round(texture(u_mmFlags, mapTex(cell)).r * 255.0));
            bool fInvis = (flags & 1) != 0;
            bool fBB = (flags & 2) != 0;
            bool fLight = (flags & 4) != 0;
            vec2 cellFrac = fract(mmPix / u_mmCell);
            vec2 cellCenter = cellFrac - vec2(0.5);
            if (t >= 1 && t <= int(u_wallMax)) {
                color = palColor(float(t), 1);
            } else if (fInvis) {
                // faixas diagonais translúcidas — sinaliza sem parecer parede sólida
                float stripe = fract((cellFrac.x + cellFrac.y) * 4.0);
                color = mix(vec3(0.06), vec3(0.498, 0.690, 1.0), stripe < 0.5 ? 0.5 : 0.15);
            } else if (fLight) {
                // círculo centralizado em vez de preenchimento sólido igual parede.
                // bits 4-7 dos flags carregam o índice da luz (1-9) quando ela vem
                // de LIGHT_CELLS (formato novo); 0 = formato legado, cai no `t`.
                int lightIdx = (flags >> 4) & 15;
                float tLight = (lightIdx > 0) ? (u_orbMin + float(lightIdx - 1)) : float(max(t, int(u_orbMin)));
                vec3 lc = palColor(tLight, 1);
                color = (length(cellCenter) < 0.32) ? lc * 1.4 : vec3(0.06);
            } else {
                color = vec3(0.06);
            }
            if (fBB) {
                // losango laranja centralizado sinalizando billboard/partícula na célula
                vec2 ac = abs(cellCenter);
                if (ac.x + ac.y < 0.30) color = vec3(0.878, 0.643, 0.345);
            }
        } else {
            color = vec3(0.02);
        }
        float d = length(pix - u_playerPix);
        if (d < 3.5) color = u_mmPlayer;
        float dd = length(pix - u_dirPix);
        if (dd < 2.5) color = u_mmPlayer;
    }

    outColor = vec4(color, 1.0);
}
"""


# Limites fixos de instâncias/camadas compartilhados com o loop principal:
# o shader usa arrays com esses tamanhos fixos (u_bbPos[128], etc.).
MAX_BILLBOARD_INSTANCES = 128  # limite de sprites simultâneos no mapa (Fase 5 + partículas, item 3)
BILLBOARD_LAYERS = 9           # nº de "slots" de textura únicos suportados
_BB_LAYER_BY_PATH = {}         # caminho_abs -> índice de camada no array da GPU
_BB_ASPECT_BY_PATH = {}        # caminho_abs -> aspect ratio (largura/altura) original
tex_bbTex = None
tex_mmFlags = None             # flags por célula só pro minimapa (Problema 7)


# ══ INICIALIZAÇÃO pygame + moderngl ═════════════════════════════
def resize_window(width, height):
    # Cria/recria a janela pygame no tamanho pedido E sincroniza o viewport
    # do OpenGL/moderngl com esse mesmo tamanho.
    #
    # Bug corrigido aqui (Fase 1): antes, ao trocar de mapa pra um .rcfg com
    # resolução diferente da janela original, o código só chamava
    # pygame.display.set_mode(...) de novo — a janela do SO mudava de
    # tamanho, mas o moderngl continuava desenhando no viewport antigo
    # (o tamanho que existia quando o contexto foi criado, em init_display).
    # O resultado eram bordas pretas: a GPU só pintava um retângulo do
    # tamanho antigo dentro da janela nova, maior.
    pygame.display.set_mode((width, height), pygame.OPENGL | pygame.DOUBLEBUF)
    if ctx is not None:
        ctx.viewport = (0, 0, width, height)


def init_display():
    global ctx, prog, vao, tex_map, tex_light, tex_palA, tex_palB, tex_wallArr, tex_hasTex
    global tex_bbTex
    ctx = None
    pygame.init()
    resize_window(logic.WIDTH, logic.HEIGHT)
    pygame.display.set_caption("Raycasting FPS GPU")
    ctx = moderngl.create_context()
    ctx.viewport = (0, 0, logic.WIDTH, logic.HEIGHT)
    ctx.enable(moderngl.BLEND)

    prog = ctx.program(vertex_shader=VERT, fragment_shader=FRAG)

    verts = np.array([
        -1, -1, 0, 0,
         1, -1, 1, 0,
         1,  1, 1, 1,
        -1, -1, 0, 0,
         1,  1, 1, 1,
        -1,  1, 0, 1,
    ], dtype="f4")
    vbo = ctx.buffer(verts.tobytes())
    vao = ctx.vertex_array(prog, vbo, "in_pos", "in_uv")

    tex_map = tex_light = tex_palA = tex_palB = tex_wallArr = tex_hasTex = None
    tex_bbTex = None
    upload_textures()


# Fixo em WALL_MAX_NOVO (9): o array de texturas sempre reserva o máximo
# de camadas possível, já que o formato de mapa (legado x novo, Fase 4)
# pode mudar de mapa pra mapa, mas o array da GPU precisa de um tamanho
# fixo definido na inicialização.
TEXTURE_LAYERS = logic.WALL_MAX_NOVO  # 1 camada do array por tipo de parede (1..9)


def upload_textures():
    global tex_map, tex_light, tex_palA, tex_palB, tex_wallArr, tex_hasTex, tex_bbTex, tex_mmFlags
    if tex_map is not None:
        tex_map.release()
    if tex_light is not None:
        tex_light.release()
    if tex_palA is not None:
        tex_palA.release()
    if tex_palB is not None:
        tex_palB.release()
    if tex_wallArr is not None:
        tex_wallArr.release()
    if tex_bbTex is not None:
        tex_bbTex.release()
    if tex_hasTex is not None:
        tex_hasTex.release()
    if tex_mmFlags is not None:
        tex_mmFlags.release()

    map_data = np.array(logic.MAP, dtype=np.float32)
    tex_map = ctx.texture((logic.MAP_W, logic.MAP_H), 1, map_data.tobytes(), dtype="f4")
    tex_map.filter = (moderngl.NEAREST, moderngl.NEAREST)

    # ── flags por célula pro minimapa (Problema 7 do PLANO.md) ──
    # bit 1 = barreira invisível, bit 2 = tem billboard, bit 4 = tem luz.
    # Bits 4-7 = índice da luz (1-9), só preenchido quando ela vem de
    # LIGHT_CELLS (formato novo, item 4) — como nesse formato a luz não
    # mora mais no valor de grid, o shader não tem mais como descobrir a
    # COR certa só olhando `t`; por isso o índice viaja embutido aqui.
    # Formato legado (luz ainda codificada direto na grade) não precisa
    # disso: bits 4-7 ficam em 0 e o shader cai no fallback `t >= ORB_MIN`.
    mm_flags = np.zeros((logic.MAP_H, logic.MAP_W), dtype=np.uint8)
    for y in range(logic.MAP_H):
        for x in range(logic.MAP_W):
            t = logic.MAP[y][x]
            f = 0
            if t == logic.INVISIBLE_WALL:
                f |= 1
            light_t = logic.LIGHT_CELLS.get((x, y))
            if light_t is not None:
                f |= 4
                n = max(1, min(9, light_t - logic.ORB_MIN + 1))
                f |= (n << 4)
            elif logic.is_orb(t):
                f |= 4
            mm_flags[y, x] = f
    for (bx, by, _caminho, _yoff, _escala, _amp, _vel, _fase) in logic.BILLBOARDS:
        ix, iy = int(bx), int(by)
        if 0 <= ix < logic.MAP_W and 0 <= iy < logic.MAP_H:
            mm_flags[iy, ix] |= 2
    tex_mmFlags = ctx.texture((logic.MAP_W, logic.MAP_H), 1, mm_flags.tobytes(), dtype="f1")
    tex_mmFlags.filter = (moderngl.NEAREST, moderngl.NEAREST)

    if logic.light_grid_np is not None:
        tex_light = ctx.texture((logic.LIGHT_W, logic.LIGHT_H), 3, logic.light_grid_np.tobytes(), dtype="f4")
        tex_light.filter = (moderngl.LINEAR, moderngl.LINEAR)
        tex_light.repeat_x = False
        tex_light.repeat_y = False

    palA = np.zeros((256, 4), dtype=np.float32)
    palB = np.zeros((256, 4), dtype=np.float32)
    for t, (ns, ew) in logic.WALL_COLORS.items():
        if 1 <= t <= 255:
            palA[t] = [*[c / 255.0 for c in _rgb(ns)], 1.0]
            palB[t] = [*[c / 255.0 for c in _rgb(ew)], 1.0]
    for t, (cor, raio) in logic.LIGHT_ORBS.items():
        if 1 <= t <= 255:
            c = [*[c / 255.0 for c in _rgb(cor)], 1.0]
            palA[t] = c
            palB[t] = c
    tex_palA = ctx.texture((256, 1), 4, palA.tobytes(), dtype="f4")
    tex_palA.filter = (moderngl.NEAREST, moderngl.NEAREST)
    tex_palB = ctx.texture((256, 1), 4, palB.tobytes(), dtype="f4")
    tex_palB.filter = (moderngl.NEAREST, moderngl.NEAREST)

    # ── texture array das paredes (Fase 2) ──
    # Uma camada por tipo (1..TEXTURE_LAYERS). Tipos sem entrada em
    # WALL_TEXTURES ficam com a camada vazia (preta/transparente) e o
    # shader nem chega a usá-la: a máscara has_tex diz pra ele cair no
    # fallback de cor sólida (palA/palB) pra esses tipos.
    tam = (logic.TEXTURE_SIZE, logic.TEXTURE_SIZE)
    camadas = np.zeros((TEXTURE_LAYERS, tam[1], tam[0], 4), dtype=np.uint8)
    has_tex = np.zeros((256, 1), dtype=np.float32)
    for t, caminho_abs in logic.WALL_TEXTURES.items():
        if not (1 <= t <= TEXTURE_LAYERS):
            continue
        arr, _aspect = load_asset_image(caminho_abs, tam)
        camadas[t - 1] = arr
        has_tex[t, 0] = 1.0

    tex_wallArr = ctx.texture_array((tam[0], tam[1], TEXTURE_LAYERS), 4, camadas.tobytes())
    tex_wallArr.filter = (moderngl.LINEAR, moderngl.LINEAR)
    tex_wallArr.repeat_x = True
    tex_wallArr.repeat_y = True
    tex_wallArr.build_mipmaps()

    tex_hasTex = ctx.texture((256, 1), 1, has_tex.tobytes(), dtype="f4")
    tex_hasTex.filter = (moderngl.NEAREST, moderngl.NEAREST)

    # ── texture array dos billboards (Fase 5) ──
    # Cada instância de billboard no [MAP] (B1, B2, ...) referencia uma
    # camada desse array pelo índice que já vem calculado em BILLBOARDS
    # (ver upload de uniforms no loop principal). Sprites sem imagem
    # (caminho inválido) caem no fallback xadrez magenta, igual às paredes.
    bb_camadas = np.zeros((BILLBOARD_LAYERS, tam[1], tam[0], 4), dtype=np.uint8)
    caminhos_billboards = sorted({caminho for (_, _, caminho, _, _, _, _, _) in logic.BILLBOARDS})[:BILLBOARD_LAYERS]
    aspects_billboards = [1.0] * BILLBOARD_LAYERS
    for idx, caminho_abs in enumerate(caminhos_billboards):
        arr, aspect = load_asset_image(caminho_abs, tam, contain=True)
        bb_camadas[idx] = arr
        aspects_billboards[idx] = aspect
    tex_bbTex = ctx.texture_array((tam[0], tam[1], BILLBOARD_LAYERS), 4, bb_camadas.tobytes())
    tex_bbTex.filter = (moderngl.LINEAR, moderngl.LINEAR)
    tex_bbTex.repeat_x = False
    tex_bbTex.repeat_y = False
    # Sem build_mipmaps() aqui de propósito (Problema 2 do PLANO.md):
    # billboards não tileiam feito paredes, então minificação suave não
    # compensa o risco de a GPU misturar RGB de texels opacos da borda com
    # texels vizinhos totalmente transparentes ao gerar os mip levels —
    # isso é o que causava a linha clara/escura contornando o sprite.
    # guarda o mapeamento caminho -> índice de camada/aspect pra montar os
    # uniforms de instância (posição/camada/offset/aspect) no loop principal.
    global _BB_LAYER_BY_PATH, _BB_ASPECT_BY_PATH
    _BB_LAYER_BY_PATH = {c: i for i, c in enumerate(caminhos_billboards)}
    _BB_ASPECT_BY_PATH = {c: aspects_billboards[i] for i, c in enumerate(caminhos_billboards)}