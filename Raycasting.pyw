# Raycasting FPS — versão GPU (pygame + moderngl / OpenGL)
# Raycasting por pixel executado no fragment shader (GPU real).
# Reusa o formato .rcfg e a grade de luz por orbes (light_grid) da engine Tk.
import sys
import os
import re
import math
import pygame
import moderngl
import numpy as np


# ══ CARREGADOR DE MAPAS (.RCFG) ══════════════════════════════════
def math_radians(deg):
    return math.pi * deg / 180.0


DEFAULT_CONFIG = {
    "window_width": 960,
    "window_height": 560,
    "mm": 140,
    "fov": math_radians(60),
    "num_rays": 200,
    "max_depth": 30,
    "move_speed": 0.06,
    "run_multiplier": 1.8,
    "mouse_sens_x": 0.004,
    "mouse_sens_y": 1.0,
    "max_look_y": 240,
    "fog": 1.4,
    "gradient_steps": 14,
    "ambient": 0.07,
    "floor_bands": 3,
    "floor_step": 2,
    "light_res": 1,
    "light_soft_samples": 6,
    "light_soft_radius": 0.4,
    "light_bounce": 0.35,
    "light_bounce_radius": 1.6,
    "light_bounce_passes": 2,
    "texture_size": 256,
}

LIGHT_RES_VALIDOS = (1, 2, 4, 8, 16, 32)

ORB_MIN = 7
WALL_MAX = 6


def _parse_color(text):
    text = text.strip().lstrip("#")
    if re.fullmatch(r"[0-9a-fA-F]{6}", text):
        return "#" + text.lower()
    raise ValueError(f"cor inválida: {text!r}")


def _strip_comment(linha):
    if linha.lstrip().startswith("#"):
        return ""
    m = re.search(r"(?:\s#(?=\s)|#\s*$)", linha)
    if m:
        return linha[:m.start()]
    return linha


def _to_int(v, nome):
    try:
        return int(v)
    except (TypeError, ValueError):
        raise ValueError(f"{nome} inválido: {v!r}")


def _to_float(v, nome):
    try:
        return float(v)
    except (TypeError, ValueError):
        raise ValueError(f"{nome} inválido: {v!r}")


def _parse_sections(caminho):
    with open(caminho, "r", encoding="utf-8") as f:
        linhas = f.read().splitlines()

    section = None
    dados = {}

    for linha in linhas:
        linha = _strip_comment(linha).rstrip()
        if not linha.strip():
            continue
        stripped = linha.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1].strip().upper()
            if section == "MAP":
                dados.setdefault(section, [])
            else:
                dados.setdefault(section, {})
            continue
        if section is None:
            continue

        if section == "MAP":
            celulas = re.split(r"[\s,;]+", stripped)
            try:
                dados["MAP"].append([int(c) for c in celulas if c])
            except ValueError:
                raise ValueError(f"valor inválido na linha do mapa: {linha!r}")
        elif section == "TITLE":
            dados["TITLE"]["value"] = stripped
        else:
            partes = re.split(r"[\s,]+", stripped, maxsplit=1)
            chave = partes[0].strip().lower()
            valor = partes[1].strip() if len(partes) > 1 else ""
            dados[section][chave] = valor

    return dados


def _parse_config(d):
    if not d:
        return dict(DEFAULT_CONFIG)
    cfg = dict(DEFAULT_CONFIG)
    w, h = d.get("window", "960 560").split()
    cfg["window_width"] = _to_int(w, "WINDOW")
    cfg["window_height"] = _to_int(h, "WINDOW")
    cfg["mm"] = _to_int(d.get("mm", 140), "MM")
    cfg["fov"] = math_radians(_to_float(d.get("fov", 60), "FOV"))
    cfg["num_rays"] = _to_int(d.get("num_rays", 180), "NUM_RAYS")
    cfg["max_depth"] = _to_int(d.get("max_depth", 30), "MAX_DEPTH")
    cfg["move_speed"] = _to_float(d.get("move_speed", 0.06), "MOVE_SPEED")
    cfg["run_multiplier"] = _to_float(d.get("run_multiplier", 1.8), "RUN_MULTIPLIER")
    cfg["mouse_sens_x"] = _to_float(d.get("mouse_sens_x", 0.004), "MOUSE_SENS_X")
    cfg["mouse_sens_y"] = _to_float(d.get("mouse_sens_y", 1.0), "MOUSE_SENS_Y")
    cfg["max_look_y"] = _to_int(d.get("max_look_y", 240), "MAX_LOOK_Y")
    cfg["fog"] = _to_float(d.get("fog", 1.4), "FOG")
    cfg["gradient_steps"] = _to_int(d.get("gradient_steps", 14), "GRADIENT_STEPS")
    cfg["ambient"] = _to_float(d.get("ambient", 0.07), "AMBIENT")
    cfg["floor_bands"] = _to_int(d.get("floor_bands", 4), "FLOOR_BANDS")
    cfg["floor_step"] = _to_int(d.get("floor_step", 2), "FLOOR_STEP")
    light_res = _to_int(d.get("light_res", 1), "LIGHT_RES")
    if light_res not in LIGHT_RES_VALIDOS:
        # ajusta para o valor válido mais próximo em vez de travar o mapa
        light_res = min(LIGHT_RES_VALIDOS, key=lambda v: abs(v - light_res))
    cfg["light_res"] = light_res
    cfg["light_soft_samples"] = _to_int(d.get("light_soft_samples", 6), "LIGHT_SOFT_SAMPLES")
    cfg["light_soft_radius"] = _to_float(d.get("light_soft_radius", 0.4), "LIGHT_SOFT_RADIUS")
    cfg["light_bounce"] = _to_float(d.get("light_bounce", 0.35), "LIGHT_BOUNCE")
    cfg["light_bounce_radius"] = _to_float(d.get("light_bounce_radius", 1.6), "LIGHT_BOUNCE_RADIUS")
    cfg["light_bounce_passes"] = max(1, _to_int(d.get("light_bounce_passes", 2), "LIGHT_BOUNCE_PASSES"))
    cfg["texture_size"] = max(2, _to_int(d.get("texture_size", 256), "TEXTURE_SIZE"))
    return cfg


def _parse_spawn(d, mapa):
    w = len(mapa[0])
    h = len(mapa)
    x = _to_float(d.get("x", 1.5), "SPAWN X")
    y = _to_float(d.get("y", 1.5), "SPAWN Y")
    angle = math_radians(_to_float(d.get("angle", 0), "SPAWN ANGLE"))

    def livre(fx, fy):
        ix, iy = int(fx), int(fy)
        return 0 <= ix < w and 0 <= iy < h and (mapa[iy][ix] == 0 or mapa[iy][ix] >= ORB_MIN)

    if not livre(x, y):
        for j in range(h):
            for i in range(w):
                if mapa[j][i] == 0 or mapa[j][i] >= ORB_MIN:
                    x, y = i + 0.5, j + 0.5
                    break
            else:
                continue
            break
        else:
            x, y = 0.5, 0.5
    return x, y, angle


def _parse_colors(d):
    cores = {}
    for tipo, valor in d.items():
        partes = re.split(r"[\s,]+", valor)
        if len(partes) < 2:
            raise ValueError(f"linha de cor inválida: {tipo} {valor!r}")
        try:
            tipo_int = int(tipo)
        except ValueError:
            raise ValueError(f"tipo de parede inválido: {tipo!r}")
        cores[tipo_int] = (_parse_color(partes[0]), _parse_color(partes[1]))
    return cores


def _parse_theme(d):
    tema = {}
    for chave, valor in d.items():
        if chave in ("crosshair", "hud_light", "hud_alert", "minimap_player",
                     "sky_base", "sky_top", "floor_base", "floor_top"):
            tema[chave] = _parse_color(valor)
        else:
            tema[chave] = valor
    return tema


def _parse_textures(d):
    # Seção [TEXTURES]: "tipo caminho/relativo/textura.png" — mesmo padrão
    # de [COLORS], mas o valor é só um caminho (resolvido depois, relativo
    # à pasta do .rcfg, em load_rcfg). Tipos sem entrada aqui continuam
    # usando [COLORS] normalmente (fallback).
    texturas = {}
    for tipo, valor in d.items():
        try:
            tipo_int = int(tipo)
        except ValueError:
            raise ValueError(f"tipo de parede inválido em [TEXTURES]: {tipo!r}")
        caminho_rel = valor.strip()
        if not caminho_rel:
            continue
        texturas[tipo_int] = caminho_rel
    return texturas


def _parse_lights(d):
    if not d:
        return {}
    lights = {}
    for tipo, valor in d.items():
        try:
            tipo_int = int(tipo)
        except ValueError:
            raise ValueError(f"tipo de orb inválido: {tipo!r}")
        partes = re.split(r"[\s,]+", valor)
        cor = _parse_color(partes[0]) if partes and partes[0] else "#ffcc88"
        raio = float(partes[1]) if len(partes) >= 2 and partes[1] else 4.0
        lights[tipo_int] = (cor, raio)
    return lights


def load_rcfg(caminho):
    dados = _parse_sections(caminho)
    if "MAP" not in dados or not dados["MAP"]:
        raise ValueError("nenhum mapa encontrado (seção [MAP])")
    mapa = dados["MAP"]
    largura = len(mapa[0])
    for i, row in enumerate(mapa):
        if len(row) != largura:
            raise ValueError(f"linha {i + 1} tem {len(row)} colunas, o mapa precisa de {largura}")
    spawn = _parse_spawn(dados.get("SPAWN", {}), mapa)
    pasta_base = os.path.dirname(os.path.abspath(caminho))
    texturas_rel = _parse_textures(dados.get("TEXTURES", {}))
    texturas_abs = {t: os.path.join(pasta_base, rel) for t, rel in texturas_rel.items()}
    return {
        "config": _parse_config(dados.get("CONFIG", {})),
        "spawn": spawn,
        "info": dict(dados.get("INFO", {})),
        "colors": _parse_colors(dados.get("COLORS", {})),
        "theme": _parse_theme(dados.get("THEME", {})),
        "title": dados.get("TITLE", {}).get("value", ""),
        "map": mapa,
        "lights": _parse_lights(dados.get("LIGHTS", {})),
        "textures": texturas_abs,
    }


# ══ FIM DO CARREGADOR ══════════════════════════════════════════

BOOT_MAP = [
    [1,1,1,1,1,1,1,1,1,1,1,1],
    [1,0,0,0,0,0,0,0,0,0,0,1],
    [1,0,0,0,0,0,0,0,0,0,0,1],
    [1,0,0,0,0,0,0,0,0,0,0,1],
    [1,0,0,0,0,0,0,0,0,0,0,1],
    [1,0,0,0,0,7,7,0,0,0,0,1],
    [1,0,0,0,0,7,7,0,0,0,0,1],
    [1,0,0,0,0,0,0,0,0,0,0,1],
    [1,0,0,0,0,0,0,0,0,0,0,1],
    [1,0,0,0,0,0,0,0,0,0,0,1],
    [1,0,0,0,0,0,0,0,0,0,0,1],
    [1,1,1,1,1,1,1,1,1,1,1,1],
]

THEME_DEFAULTS = {
    "sky_base": "#080a23",
    "sky_top": "#181c55",
    "floor_base": "#080808",
    "floor_top": "#181818",
    "crosshair": "#ffffff",
    "hud_light": "#00ffcc",
    "hud_alert": "#ffcc00",
    "minimap_player": "#00ffcc",
    "title": "Raycasting FPS GPU",
}

# ── ESTADO GLOBAL ─────────────────────────────────────────────
WIDTH, HEIGHT = DEFAULT_CONFIG["window_width"], DEFAULT_CONFIG["window_height"]
MM = DEFAULT_CONFIG["mm"]
FOV = DEFAULT_CONFIG["fov"]
MAX_DEPTH = DEFAULT_CONFIG["max_depth"]
MOVE_SPEED = DEFAULT_CONFIG["move_speed"]
RUN_MULTIPLIER = DEFAULT_CONFIG["run_multiplier"]
MOUSE_SENS_X = DEFAULT_CONFIG["mouse_sens_x"]
MOUSE_SENS_Y = DEFAULT_CONFIG["mouse_sens_y"]
MAX_LOOK_Y = DEFAULT_CONFIG["max_look_y"]
FOG = DEFAULT_CONFIG["fog"]
AMBIENT = DEFAULT_CONFIG["ambient"]

MAP = [row[:] for row in BOOT_MAP]
MAP_W = len(MAP[0])
MAP_H = len(MAP)
WALL_COLORS = {}
WALL_TEXTURES = {}   # tipo -> caminho absoluto (resolvido a partir do .rcfg)
TEXTURE_SIZE = DEFAULT_CONFIG["texture_size"]
THEME = dict(THEME_DEFAULTS)
LIGHT_ORBS = {}
LIGHT_RES = DEFAULT_CONFIG["light_res"]
LIGHT_SOFT_SAMPLES = DEFAULT_CONFIG["light_soft_samples"]
LIGHT_SOFT_RADIUS = DEFAULT_CONFIG["light_soft_radius"]
LIGHT_BOUNCE = DEFAULT_CONFIG["light_bounce"]
LIGHT_BOUNCE_RADIUS = DEFAULT_CONFIG["light_bounce_radius"]
LIGHT_BOUNCE_PASSES = DEFAULT_CONFIG["light_bounce_passes"]
light_grid = []
light_grid_np = None
LIGHT_W = MAP_W
LIGHT_H = MAP_H
px, py, pangle, look_y = 1.5, 1.5, 0.0, 0.0
SPAWN = (1.5, 1.5, 0.0)

# Cache em memória (não vai pro disco): caminho absoluto do .rcfg -> última
# posição/direção da câmera nele. Vive só enquanto o processo está rodando,
# tipo um "localStorage" da sessão. Ao voltar pra um mapa já visitado nessa
# mesma execução, a câmera reaparece de onde você tinha saído em vez de
# voltar pro SPAWN do arquivo.
MAP_POSITIONS = {}


def _map_key(caminho):
    return os.path.abspath(caminho)


def save_current_position(caminho):
    if caminho is not None:
        MAP_POSITIONS[_map_key(caminho)] = (px, py, pangle, look_y)


def restore_saved_position(caminho):
    global px, py, pangle, look_y
    salvo = MAP_POSITIONS.get(_map_key(caminho))
    if salvo is not None:
        px, py, pangle, look_y = salvo


def _rgb(h):
    return (int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16))


# ══ CARREGADOR DE ASSETS (Fase 1) ════════════════════════════════
# Cache em memória: (caminho_absoluto, tamanho) -> pygame.Surface já pronta
# (RGBA, redimensionada). Evita recarregar/redimensionar a mesma imagem
# várias vezes (ex: dois tipos de parede usando a mesma textura).
_ASSET_CACHE = {}


def _fallback_surface(tamanho):
    # Xadrez magenta/preto — "textura de erro" clássica, bem visível, pra
    # avisar que um asset referenciado no .rcfg não foi encontrado sem
    # travar o carregamento do mapa inteiro.
    w, h = tamanho
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    cel = max(1, min(w, h) // 8)
    magenta = (255, 0, 255, 255)
    preto = (0, 0, 0, 255)
    for j in range(0, h, cel):
        for i in range(0, w, cel):
            cor = magenta if ((i // cel) + (j // cel)) % 2 == 0 else preto
            surf.fill(cor, pygame.Rect(i, j, cel, cel))
    return surf


def load_asset_image(caminho_abs, tamanho):
    # Todo caminho de asset já deve chegar aqui RESOLVIDO (absoluto),
    # relativo à pasta do .rcfg — ver load_rcfg(). tamanho é obrigatório
    # aqui pq o texture array da GPU exige que todas as camadas tenham o
    # mesmo tamanho (ver upload_wall_textures).
    key = (caminho_abs, tamanho)
    cached = _ASSET_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        surf = pygame.image.load(caminho_abs).convert_alpha()
    except Exception as e:
        print(f"[assets] falha ao carregar {caminho_abs!r}: {e}", flush=True)
        surf = _fallback_surface(tamanho)
    if surf.get_size() != tamanho:
        surf = pygame.transform.smoothscale(surf, tamanho)
    _ASSET_CACHE[key] = surf
    return surf


def is_orb(c):
    return c >= ORB_MIN


def is_wall(c):
    return 1 <= c <= WALL_MAX


def _los_blocked_f(x0, y0, x1, y1):
    # Igual a antes, mas trabalha com posições contínuas (float) em vez de
    # células inteiras — usado pra testar visibilidade a partir de cada
    # amostra do "disco" da luz.
    dx, dy = x1 - x0, y1 - y0
    dist = math.hypot(dx, dy)
    if dist <= 1e-6:
        return False
    steps = max(1, int(dist / 0.2))
    for s in range(1, steps):
        t = s / steps
        icx, icy = int(x0 + dx * t), int(y0 + dy * t)
        if 0 <= icx < MAP_W and 0 <= icy < MAP_H and is_wall(MAP[icy][icx]):
            return True
    return False


def compute_light_grid():
    # Cada subcelula guarda luz em RGB (não só intensidade), o que permite
    # tochas coloridas e luz "quicando" nas paredes (bounce/GI simples).
    #
    # Penumbra: em vez de testar visibilidade de um único ponto da luz,
    # testamos um pequeno "disco" de amostras ao redor do centro dela. Perto
    # de uma quina, parte das amostras enxerga a luz e parte não — o
    # resultado é uma fração (ex: 0.33, 0.66) em vez de um binário
    # bloqueado/livre, o que cria uma transição suave de sombra em vez de
    # um corte seco.
    #
    # Esse teste de visibilidade é feito por CÉLULA inteira (não por
    # subcelula) pra manter o custo baixo — a suavidade final na tela vem
    # da combinação disso com a interpolação LINEAR da textura e com a
    # queda de intensidade calculada por subcelula.
    global light_grid, light_grid_np, LIGHT_W, LIGHT_H
    res = max(1, LIGHT_RES)
    LIGHT_W = MAP_W * res
    LIGHT_H = MAP_H * res
    sub = 1.0 / res
    grid = [[[AMBIENT, AMBIENT, AMBIENT] for _ in range(LIGHT_W)] for _ in range(LIGHT_H)]

    n_soft = max(1, LIGHT_SOFT_SAMPLES)
    soft_r = max(0.0, LIGHT_SOFT_RADIUS)
    if n_soft <= 1 or soft_r <= 0:
        disc_pts = [(0.0, 0.0)]
    else:
        disc_pts = [(math.cos(2 * math.pi * k / n_soft) * soft_r,
                     math.sin(2 * math.pi * k / n_soft) * soft_r)
                    for k in range(n_soft)]
        disc_pts.append((0.0, 0.0))
    n_pts = len(disc_pts)

    def add_light(x, y, raio, cor_rgb):
        cx, cy = x + 0.5, y + 0.5
        r = int(math.ceil(raio))
        for j in range(max(0, y - r), min(MAP_H, y + r + 1)):
            for i in range(max(0, x - r), min(MAP_W, x + r + 1)):
                tcx, tcy = i + 0.5, j + 0.5
                vis = 0
                for ox, oy in disc_pts:
                    if not _los_blocked_f(cx + ox, cy + oy, tcx, tcy):
                        vis += 1
                if vis == 0:
                    continue
                vis_frac = vis / n_pts
                base_row = j * res
                base_col = i * res
                for sj in range(res):
                    wy = j + (sj + 0.5) * sub
                    dy = wy - cy
                    row = grid[base_row + sj]
                    for si in range(res):
                        wx = i + (si + 0.5) * sub
                        dist = math.hypot(wx - cx, dy)
                        if dist > raio:
                            continue
                        # Atenuação "inverse-square windowed" (o mesmo tipo de
                        # curva usada em point lights de motores tipo UE4) em
                        # vez de rampa linear (1 - dist/raio). A luz real cai
                        # com o quadrado da distância — bem concentrada perto
                        # da fonte e com uma cauda mais longa e suave, em vez
                        # da rampa reta que "parece feita à mão".
                        d = dist / raio
                        # smoothstep em vez da curva "inverse-square windowed"
                        # anterior (d^4 janelado + termo racional). Aquela
                        # curva era íngreme/muito não-linear perto da borda,
                        # e a suavidade da sombra/penumbra depende de a
                        # queda de luz ser razoavelmente gradual — o teste de
                        # visibilidade é feito por CÉLULA inteira (ver
                        # comentário acima), então uma curva de intensidade
                        # muito curvada "quebra" a transição suave que vinha
                        # da interpolação linear da textura. O smoothstep
                        # ainda dá um núcleo mais concentrado e uma borda
                        # mais macia que a rampa reta original, mas sem essa
                        # curvatura agressiva.
                        t = max(0.0, min(1.0, 1.0 - d))
                        falloff = (t * t * (3.0 - 2.0 * t)) * vis_frac
                        if falloff <= 0:
                            continue
                        cell = row[base_col + si]
                        cell[0] += cor_rgb[0] * falloff
                        cell[1] += cor_rgb[1] * falloff
                        cell[2] += cor_rgb[2] * falloff

    # luz direta das tochas/orbes
    for y in range(MAP_H):
        for x in range(MAP_W):
            t = MAP[y][x]
            if not is_orb(t):
                continue
            cor_hex, raio = LIGHT_ORBS.get(t, ("#ffcc88", 4.0))
            cor_rgb = tuple((c / 255.0) * 4.0 for c in _rgb(cor_hex))
            add_light(x, y, raio, cor_rgb)

    # bounce: paredes iluminadas reemitem uma fração da própria cor pras
    # celulas vizinhas — luz vermelha perto de parede azul tinge o entorno.
    # Fazemos vários PASSES: cada passe congela o estado atual da grade
    # (luz direta + bounces anteriores) e deixa as paredes reemitirem de
    # novo a partir dali. Isso aproxima uma iluminação global de verdade
    # (radiosity) — a luz "quica" mais de uma vez e se espalha mais longe
    # pelos cantos, em vez de um único salto que mal sai da célula ao lado
    # da tocha. Cada passe usa uma cópia congelada (nunca a grade "viva"),
    # senão uma parede processada no meio do loop já reemitiria o bounce
    # de vizinhas processadas antes dela no MESMO passe — cascata que
    # se acumula mais forte nas quinas.
    if LIGHT_BOUNCE > 0:
        for passe in range(max(1, LIGHT_BOUNCE_PASSES)):
            luz_atual = [[list(cell) for cell in row] for row in grid]
            decaimento = LIGHT_BOUNCE * (0.6 ** passe)  # cada passe extra contribui menos
            for y in range(MAP_H):
                for x in range(MAP_W):
                    t = MAP[y][x]
                    if not is_wall(t):
                        continue
                    cor_ns, cor_ew = WALL_COLORS.get(t, ("#888888", "#888888"))
                    wall_rgb = tuple(((a + b) / 2.0) / 255.0 for a, b in zip(_rgb(cor_ns), _rgb(cor_ew)))
                    ci = min(LIGHT_W - 1, x * res + res // 2)
                    cj = min(LIGHT_H - 1, y * res + res // 2)
                    recv_intensity = sum(luz_atual[cj][ci]) / 3.0
                    if recv_intensity <= AMBIENT * 1.05:
                        continue  # parede às escuras não quica nada relevante
                    bounce_rgb = tuple(wall_rgb[k] * recv_intensity * decaimento for k in range(3))
                    add_light(x, y, LIGHT_BOUNCE_RADIUS, bounce_rgb)

    for row in grid:
        for cell in row:
            cell[0] = min(9.0, cell[0])
            cell[1] = min(9.0, cell[1])
            cell[2] = min(9.0, cell[2])

    light_grid = grid
    light_grid_np = np.array(grid, dtype=np.float32)  # shape (H, W, 3)



def open_cell(cx, cy):
    if not (0 <= cx < MAP_W and 0 <= cy < MAP_H):
        return True
    c = MAP[cy][cx]
    return c == 0 or is_orb(c)


def in_map(x, y):
    return 0 <= x < MAP_W and 0 <= y < MAP_H


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
#define ORB_MIN 7
in vec2 uv;
out vec4 outColor;

uniform vec2 u_res;
uniform vec2 u_pos;
uniform vec2 u_dir;
uniform vec2 u_plane;
uniform vec2 u_mapSize;
uniform float u_horizon;
uniform float u_ambient;
uniform float u_fog;
uniform float u_depth;

uniform sampler2D u_map;    // tipo de celula (R32F)
uniform sampler2D u_light;  // grade de luz (R32F)
uniform sampler2D u_palA;   // cor A por tipo (RGBA32F)
uniform sampler2D u_palB;   // cor B por tipo
uniform sampler2DArray u_wallTex;  // texturas por tipo (Fase 2), 1 camada por tipo
uniform sampler2D u_hasTex;        // 1.0 = tipo tem textura própria, 0.0 = usa cor sólida

uniform vec3 u_skyB, u_skyT, u_floorB, u_floorT;
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
        if (t >= 1 && t <= 6) { hit = true; wtype = t; }
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

        float lineH = u_res.y / perpDist;
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
            float rowDist = (u_res.y * 0.5) / (row - horizon);
            vec2 fc = u_pos + rowDist * rayDir;
            float depthT = (row - horizon) / (u_res.y * 0.5);
            vec3 fcol = mix(u_floorB, u_floorT, clamp(depthT, 0.0, 1.0));
            vec3 lv = lightAt(fc);
            float fv = clamp((u_fog * rowDist) / u_depth, 0.0, 1.0);
            color = fcol * lv * (1.0 - fv);
        } else {
            color = mix(u_skyB, u_skyT, clamp(row / max(horizon, 1.0), 0.0, 1.0));
        }
    } else {
        if (row > horizon) {
            float rowDist = (u_res.y * 0.5) / (row - horizon);
            vec2 fc = u_pos + rowDist * rayDir;
            float depthT = (row - horizon) / (u_res.y * 0.5);
            vec3 fcol = mix(u_floorB, u_floorT, clamp(depthT, 0.0, 1.0));
            vec3 lv = lightAt(fc);
            float fv = clamp((u_fog * rowDist) / u_depth, 0.0, 1.0);
            color = fcol * lv * (1.0 - fv);
        } else {
            color = mix(u_skyB, u_skyT, clamp(row / max(horizon, 1.0), 0.0, 1.0));
        }
    }

    // crosshair (braços curtos, com vão no centro)
    vec2 pix = vec2(uv.x, 1.0 - uv.y) * u_res;
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
            if (t >= 1 && t <= 6) {
                color = palColor(float(t), 1);
            } else if (t >= ORB_MIN) {
                color = palColor(float(t), 1) * 1.4;
            } else {
                color = vec3(0.06);
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


# ══ INICIALIZAÇÃO pygame + moderngl ═════════════════════════════
def init_display():
    global ctx, prog, vao, tex_map, tex_light, tex_palA, tex_palB, tex_wallArr, tex_hasTex
    pygame.init()
    pygame.display.set_mode((WIDTH, HEIGHT), pygame.OPENGL | pygame.DOUBLEBUF)
    pygame.display.set_caption("Raycasting FPS GPU")
    ctx = moderngl.create_context()
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
    upload_textures()


TEXTURE_LAYERS = WALL_MAX  # 1 camada do array por tipo de parede (1..6)


def upload_textures():
    global tex_map, tex_light, tex_palA, tex_palB, tex_wallArr, tex_hasTex
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
    if tex_hasTex is not None:
        tex_hasTex.release()

    map_data = np.array(MAP, dtype=np.float32)
    tex_map = ctx.texture((MAP_W, MAP_H), 1, map_data.tobytes(), dtype="f4")
    tex_map.filter = (moderngl.NEAREST, moderngl.NEAREST)

    if light_grid_np is not None:
        tex_light = ctx.texture((LIGHT_W, LIGHT_H), 3, light_grid_np.tobytes(), dtype="f4")
        tex_light.filter = (moderngl.LINEAR, moderngl.LINEAR)
        tex_light.repeat_x = False
        tex_light.repeat_y = False

    palA = np.zeros((256, 4), dtype=np.float32)
    palB = np.zeros((256, 4), dtype=np.float32)
    for t, (ns, ew) in WALL_COLORS.items():
        if 1 <= t <= 255:
            palA[t] = [*[c / 255.0 for c in _rgb(ns)], 1.0]
            palB[t] = [*[c / 255.0 for c in _rgb(ew)], 1.0]
    for t, (cor, raio) in LIGHT_ORBS.items():
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
    tam = (TEXTURE_SIZE, TEXTURE_SIZE)
    camadas = np.zeros((TEXTURE_LAYERS, tam[1], tam[0], 4), dtype=np.uint8)
    has_tex = np.zeros((256, 1), dtype=np.float32)
    for t, caminho_abs in WALL_TEXTURES.items():
        if not (1 <= t <= TEXTURE_LAYERS):
            continue
        surf = load_asset_image(caminho_abs, tam)
        pixels = pygame.image.tostring(surf, "RGBA")
        camadas[t - 1] = np.frombuffer(pixels, dtype=np.uint8).reshape(tam[1], tam[0], 4)
        has_tex[t, 0] = 1.0

    tex_wallArr = ctx.texture_array((tam[0], tam[1], TEXTURE_LAYERS), 4, camadas.tobytes())
    tex_wallArr.filter = (moderngl.LINEAR, moderngl.LINEAR)
    tex_wallArr.repeat_x = True
    tex_wallArr.repeat_y = True
    tex_wallArr.build_mipmaps()

    tex_hasTex = ctx.texture((256, 1), 1, has_tex.tobytes(), dtype="f4")
    tex_hasTex.filter = (moderngl.NEAREST, moderngl.NEAREST)


def load_map_file(caminho):
    global MAP, MAP_W, MAP_H, WALL_COLORS, WALL_TEXTURES, TEXTURE_SIZE, THEME, LIGHT_ORBS, AMBIENT, FOG, LIGHT_RES
    global LIGHT_SOFT_SAMPLES, LIGHT_SOFT_RADIUS, LIGHT_BOUNCE, LIGHT_BOUNCE_RADIUS, LIGHT_BOUNCE_PASSES
    global WIDTH, HEIGHT, FOV, MAX_DEPTH, MOVE_SPEED, RUN_MULTIPLIER, MOUSE_SENS_X
    global MOUSE_SENS_Y, MAX_LOOK_Y, MM, SPAWN, px, py, pangle, look_y
    data = load_rcfg(caminho)
    cfg = data["config"]
    WIDTH, HEIGHT = cfg["window_width"], cfg["window_height"]
    MM = cfg["mm"]
    FOV = cfg["fov"]
    MAX_DEPTH = cfg["max_depth"]
    MOVE_SPEED = cfg["move_speed"]
    RUN_MULTIPLIER = cfg["run_multiplier"]
    MOUSE_SENS_X = cfg["mouse_sens_x"]
    MOUSE_SENS_Y = cfg["mouse_sens_y"]
    MAX_LOOK_Y = cfg["max_look_y"]
    FOG = cfg["fog"]
    AMBIENT = cfg["ambient"]
    LIGHT_RES = cfg["light_res"]
    LIGHT_SOFT_SAMPLES = cfg["light_soft_samples"]
    LIGHT_SOFT_RADIUS = cfg["light_soft_radius"]
    LIGHT_BOUNCE = cfg["light_bounce"]
    LIGHT_BOUNCE_RADIUS = cfg["light_bounce_radius"]
    LIGHT_BOUNCE_PASSES = cfg["light_bounce_passes"]
    TEXTURE_SIZE = cfg["texture_size"]

    MAP = [row[:] for row in data["map"]]
    MAP_W = len(MAP[0])
    MAP_H = len(MAP)
    WALL_COLORS = data["colors"]
    WALL_TEXTURES = data["textures"]
    THEME = dict(THEME_DEFAULTS)
    THEME.update(data["theme"])
    THEME["title"] = data["title"] or THEME["title"]
    LIGHT_ORBS = data["lights"]
    SPAWN = data["spawn"]
    px, py, pangle = SPAWN
    look_y = 0

    compute_light_grid()
    pygame.display.set_mode((WIDTH, HEIGHT), pygame.OPENGL | pygame.DOUBLEBUF)
    upload_textures()
    print(f"Mapa: {data['info'].get('name', caminho)}", flush=True)


# ══ LOOP PRINCIPAL ═════════════════════════════════════════════
def main():
    global px, py, pangle, look_y

    caminho = None
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        caminho = sys.argv[1]

    compute_light_grid()
    init_display()
    if caminho:
        load_map_file(caminho)
        restore_saved_position(caminho)

    captured = True
    pygame.mouse.set_visible(not captured)
    pygame.event.set_grab(captured)
    pygame.mouse.get_rel()

    clock = pygame.time.Clock()
    running = True
    frames = 0
    tot_frames = 0
    t_start = time_sec()
    t0 = t_start
    fps = 0
    test = os.environ.get("RC_TEST_FRAMES")
    FPS_CAP = int(os.environ.get("RC_FPS_CAP", "144"))

    while running:
        dt = clock.tick(FPS_CAP) / 1000.0
        dt = max(0.0, min(0.1, dt))
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.DROPFILE:
                if os.path.isfile(e.file):
                    save_current_position(caminho)
                    caminho = e.file
                    load_map_file(caminho)
                    restore_saved_position(caminho)
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    captured = not captured
                    pygame.mouse.set_visible(not captured)
                    pygame.event.set_grab(captured)
                    pygame.mouse.get_rel()
                elif e.key == pygame.K_r:
                    if caminho is not None:
                        load_map_file(caminho)  # já deixa px,py,pangle,look_y no SPAWN do arquivo
                        save_current_position(caminho)  # sobrescreve o cache com o reset
            elif e.type == pygame.MOUSEBUTTONDOWN and not captured:
                captured = True
                pygame.mouse.set_visible(False)
                pygame.event.set_grab(True)
                pygame.mouse.get_rel()

        keys = pygame.key.get_pressed()
        if captured:
            rel = pygame.mouse.get_rel()
            pangle += rel[0] * MOUSE_SENS_X
            look_y = max(-MAX_LOOK_Y, min(MAX_LOOK_Y, look_y - rel[1] * MOUSE_SENS_Y))

        speed = MOVE_SPEED * (RUN_MULTIPLIER if (keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]) else 1) * (dt * 60.0)
        fdx = math.cos(pangle) * speed
        fdy = math.sin(pangle) * speed
        sdx = math.cos(pangle + math.pi / 2) * speed
        sdy = math.sin(pangle + math.pi / 2) * speed

        nx, ny = px, py
        if keys[pygame.K_w] or keys[pygame.K_UP]:    nx += fdx; ny += fdy
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:  nx -= fdx; ny -= fdy
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:  nx -= sdx; ny -= sdy
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]: nx += sdx; ny += sdy

        m = 0.25
        tcx = int(nx + m * math.copysign(1, nx - px))
        tcy = int(ny + m * math.copysign(1, ny - py))
        if open_cell(tcx, int(py)):
            px = nx
        if open_cell(int(px), tcy):
            py = ny
        if not in_map(px, py):
            px, py, pangle = SPAWN
            look_y = 0

        # ── uniforms ──
        plane_len = math.tan(FOV / 2)
        plane_x = -math.sin(pangle) * plane_len
        plane_y = math.cos(pangle) * plane_len
        prog["u_res"].value = (WIDTH, HEIGHT)
        prog["u_pos"].value = (px, py)
        prog["u_dir"].value = (math.cos(pangle), math.sin(pangle))
        prog["u_plane"].value = (plane_x, plane_y)
        prog["u_mapSize"].value = (MAP_W, MAP_H)
        prog["u_horizon"].value = HEIGHT * 0.5 + look_y
        prog["u_ambient"].value = AMBIENT
        prog["u_fog"].value = FOG
        prog["u_depth"].value = float(MAX_DEPTH)

        sb = [_rgb(THEME["sky_base"])[i] / 255.0 for i in range(3)]
        st = [_rgb(THEME["sky_top"])[i] / 255.0 for i in range(3)]
        fb = [_rgb(THEME["floor_base"])[i] / 255.0 for i in range(3)]
        ft = [_rgb(THEME["floor_top"])[i] / 255.0 for i in range(3)]
        cr = [_rgb(THEME["crosshair"])[i] / 255.0 for i in range(3)]
        mp = [_rgb(THEME["minimap_player"])[i] / 255.0 for i in range(3)]
        prog["u_skyB"].value = tuple(sb)
        prog["u_skyT"].value = tuple(st)
        prog["u_floorB"].value = tuple(fb)
        prog["u_floorT"].value = tuple(ft)
        prog["u_cross"].value = tuple(cr)
        prog["u_mmPlayer"].value = tuple(mp)

        mm_cell = max(1, MM // max(MAP_W, MAP_H))
        mm_w = MAP_W * mm_cell
        mm_h = MAP_H * mm_cell
        mm_x = WIDTH - mm_w - 10
        mm_y = 10
        prog["u_mmPos"].value = (mm_x, mm_y)
        prog["u_mmSize"].value = (mm_w, mm_h)
        prog["u_mmCell"].value = float(mm_cell)
        prog["u_playerPix"].value = (mm_x + px * mm_cell, mm_y + py * mm_cell)
        prog["u_dirPix"].value = (mm_x + (px + math.cos(pangle) * 2.2) * mm_cell,
                                  mm_y + (py + math.sin(pangle) * 2.2) * mm_cell)

        tex_map.use(0)
        if tex_light is not None:
            tex_light.use(1)
        tex_palA.use(2)
        tex_palB.use(3)
        tex_wallArr.use(4)
        tex_hasTex.use(5)
        prog["u_map"].value = 0
        prog["u_light"].value = 1
        prog["u_palA"].value = 2
        prog["u_palB"].value = 3
        prog["u_wallTex"].value = 4
        prog["u_hasTex"].value = 5

        vao.render(mode=moderngl.TRIANGLES)
        pygame.display.flip()

        frames += 1
        tot_frames += 1
        now = time_sec()
        if now - t0 >= 1.0:
            fps = frames / (now - t0)
            pygame.display.set_caption(f"Raycasting FPS GPU — {fps:.0f} fps")
            frames = 0
            t0 = now
        if test and tot_frames >= int(test):
            print(f"FPS={tot_frames / (now - t_start):.0f}", flush=True)
            shot = os.environ.get("RC_TEST_SHOT")
            if shot:
                w = ctx.screen.width
                h = ctx.screen.height
                data = ctx.read(viewport=(0, 0, w, h), components=3)
                arr = np.frombuffer(data, dtype=np.uint8).reshape(h, w, 3)[::-1]
                from PIL import Image
                Image.fromarray(arr, "RGB").save(shot)
            running = False

    pygame.quit()


def time_sec():
    import time
    return time.time()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        try:
            log = os.path.join(os.path.dirname(os.path.abspath(__file__)), "erro.log")
            with open(log, "w", encoding="utf-8") as f:
                traceback.print_exc(file=f)
        except Exception:
            pass
        raise