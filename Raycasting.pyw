# ══ UMA ENGINE DE RAYCASTING FEITA EM PYTHON! ═════════

import sys
import os
import re
import math
import time
import pygame
import moderngl
import numpy as np
from PIL import Image


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
    "move_speed": 0.035,
    "run_multiplier": 1.8,
    "mouse_sens_x": 0.004,
    "mouse_sens_y": 1.0,
    "max_look_y": 240,
    "bob_enabled": True,
    "bob_amount": 8.0,
    "bob_speed": 10.0,
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
    "wall_scale": 1.0,
}

LIGHT_RES_VALIDOS = (1, 2, 4, 8, 16, 32)


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
            celulas = [c for c in re.split(r"[\s,;]+", stripped) if c]
            dados["MAP"].append(celulas)
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
    cfg["num_rays"] = _to_int(d.get("num_rays", DEFAULT_CONFIG["num_rays"]), "NUM_RAYS")
    cfg["max_depth"] = _to_int(d.get("max_depth", 30), "MAX_DEPTH")
    cfg["move_speed"] = _to_float(d.get("move_speed", DEFAULT_CONFIG["move_speed"]), "MOVE_SPEED")
    cfg["run_multiplier"] = _to_float(d.get("run_multiplier", 1.8), "RUN_MULTIPLIER")
    cfg["mouse_sens_x"] = _to_float(d.get("mouse_sens_x", 0.004), "MOUSE_SENS_X")
    cfg["mouse_sens_y"] = _to_float(d.get("mouse_sens_y", 1.0), "MOUSE_SENS_Y")
    cfg["max_look_y"] = _to_int(d.get("max_look_y", 240), "MAX_LOOK_Y")
    cfg["bob_enabled"] = str(d.get("bob_enabled", "true")).strip().lower() in ("1", "true", "yes")
    cfg["bob_amount"] = _to_float(d.get("bob_amount", 8.0), "BOB_AMOUNT")
    cfg["bob_speed"] = _to_float(d.get("bob_speed", 10.0), "BOB_SPEED")
    cfg["fog"] = _to_float(d.get("fog", 1.4), "FOG")
    cfg["gradient_steps"] = _to_int(d.get("gradient_steps", 14), "GRADIENT_STEPS")
    cfg["ambient"] = _to_float(d.get("ambient", 0.07), "AMBIENT")
    cfg["floor_bands"] = _to_int(d.get("floor_bands", DEFAULT_CONFIG["floor_bands"]), "FLOOR_BANDS")
    cfg["floor_step"] = _to_int(d.get("floor_step", 2), "FLOOR_STEP")
    light_res = _to_int(d.get("light_res", 1), "LIGHT_RES")
    if light_res not in LIGHT_RES_VALIDOS:
        light_res = min(LIGHT_RES_VALIDOS, key=lambda v: abs(v - light_res))
    cfg["light_res"] = light_res
    cfg["light_soft_samples"] = _to_int(d.get("light_soft_samples", 6), "LIGHT_SOFT_SAMPLES")
    cfg["light_soft_radius"] = _to_float(d.get("light_soft_radius", 0.4), "LIGHT_SOFT_RADIUS")
    cfg["light_bounce"] = _to_float(d.get("light_bounce", 0.35), "LIGHT_BOUNCE")
    cfg["light_bounce_radius"] = _to_float(d.get("light_bounce_radius", 1.6), "LIGHT_BOUNCE_RADIUS")
    cfg["light_bounce_passes"] = max(1, _to_int(d.get("light_bounce_passes", 2), "LIGHT_BOUNCE_PASSES"))
    cfg["texture_size"] = max(2, _to_int(d.get("texture_size", 256), "TEXTURE_SIZE"))
    cfg["wall_scale"] = _to_float(d.get("wall_scale", 1.0), "WALL_SCALE")
    return cfg


def _parse_spawn(d, mapa, orb_min):
    w = len(mapa[0])
    h = len(mapa)
    x = _to_float(d.get("x", 1.5), "SPAWN X")
    y = _to_float(d.get("y", 1.5), "SPAWN Y")
    angle = math_radians(_to_float(d.get("angle", 0), "SPAWN ANGLE"))

    def livre(fx, fy):
        ix, iy = int(fx), int(fy)
        v = mapa[iy][ix] if (0 <= ix < w and 0 <= iy < h) else None
        return v is not None and v != INVISIBLE_WALL and (v == 0 or v >= orb_min)

    if not livre(x, y):
        for j in range(h):
            for i in range(w):
                if mapa[j][i] != INVISIBLE_WALL and (mapa[j][i] == 0 or mapa[j][i] >= orb_min):
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


SKY_DEFAULTS = {
    "cycle": False,
    "day_length": 120.0,
    "start_time": 8.0,
    "sun_peak": 45.0,
    "sun_color": "#fff2c0",
    "moon_color": "#b9c6e0",
    "stars": 0,
}


def _parse_sky(d):
    sky = dict(SKY_DEFAULTS)
    sky["enabled"] = bool(d)
    if not d:
        return sky
    sky["cycle"] = str(d.get("cycle", "false")).strip().lower() in ("1", "true", "yes")
    sky["day_length"] = max(1.0, _to_float(d.get("day_length", 120), "SKY DAY_LENGTH"))
    sky["start_time"] = _to_float(d.get("start_time", 8), "SKY START_TIME") % 24.0
    sky["sun_peak"] = max(10.0, min(90.0, _to_float(d.get("sun_peak", 45), "SKY SUN_PEAK")))
    sky["sun_color"] = _parse_color(d.get("sun_color", "#fff2c0"))
    sky["moon_color"] = _parse_color(d.get("moon_color", "#b9c6e0"))
    sky["stars"] = max(0, _to_int(d.get("stars", 140), "SKY STARS"))
    return sky


def _parse_textures(d):
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


WALL_MAX = 9
ORB_MIN = 100
INVISIBLE_WALL = 99


def _split_map_token(tok):
    partes = tok.split("+")
    return partes[0], partes[1:]


def _process_map_tokens(raw_rows):
    grid = []
    billboards = []
    particles = []
    light_cells = {}
    for j, row in enumerate(raw_rows):
        int_row = []
        for i, tok in enumerate(row):
            base, extras = _split_map_token(tok)
            up_base = base.upper()
            if up_base == "N":
                int_row.append(INVISIBLE_WALL)
            else:
                try:
                    int_row.append(int(base))
                except ValueError:
                    raise ValueError(f"valor inválido no mapa: {tok!r}")
            letras_vistas = set()
            for extra in extras:
                up = extra.upper()
                if len(up) < 2 or up[0] not in ("L", "B", "P") or not up[1:].isdigit():
                    raise ValueError(f"token de camada inválido em {tok!r}: {extra!r}")
                letra = up[0]
                if letra in letras_vistas:
                    raise ValueError(f"célula {tok!r}: no máximo 1 token '{letra}' por célula")
                letras_vistas.add(letra)
                n = int(up[1:])
                if not (1 <= n <= 9):
                    raise ValueError(f"{extra!r}: índice deve ser 1-9")
                if letra == "L":
                    light_cells[(i, j)] = ORB_MIN + (n - 1)
                elif letra == "B":
                    billboards.append((i + 0.5, j + 0.5, n))
                else:
                    particles.append((i + 0.5, j + 0.5, n))
        grid.append(int_row)
    return grid, billboards, particles, light_cells


AI_NONE = "none"
AI_FRIENDLY = "friendly"
AI_ENEMY = "enemy"
_AI_VALIDOS = (AI_NONE, AI_FRIENDLY, AI_ENEMY)


def _parse_billboards(d, pasta_base):
    billboards = {}
    for tipo, valor in d.items():
        try:
            tipo_int = int(tipo)
        except ValueError:
            raise ValueError(f"tipo de billboard inválido: {tipo!r}")
        partes = re.split(r"[\s,]+", valor)
        caminho_rel = partes[0].strip() if partes and partes[0] else ""
        if not caminho_rel:
            continue
        offset_y = float(partes[1]) if len(partes) >= 2 and partes[1] else 0.0
        escala = float(partes[2]) if len(partes) >= 3 and partes[2] else 1.0
        ai = partes[3].strip().lower() if len(partes) >= 4 and partes[3] else AI_NONE
        if ai not in _AI_VALIDOS:
            ai = AI_NONE
        if len(partes) >= 5 and partes[4]:
            try:
                speed = float(partes[4])
            except ValueError:
                speed = None
        else:
            speed = None
        if speed is None or speed <= 0:
            speed = AI_ENEMY_SPEED if ai == AI_ENEMY else AI_FRIENDLY_SPEED
        billboards[tipo_int] = (os.path.join(pasta_base, caminho_rel), offset_y, escala, ai, speed)
    return billboards


def _parse_billboard_sounds(d, pasta_base):
    sons = {}
    for tipo, valor in d.items():
        try:
            tipo_int = int(tipo)
        except ValueError:
            raise ValueError(f"tipo de som de billboard inválido: {tipo!r}")
        partes = re.split(r"[\s,]+", valor)
        caminho_rel = partes[0].strip() if partes and partes[0] else ""
        if not caminho_rel:
            continue
        raio = float(partes[1]) if len(partes) >= 2 and partes[1] else 8.0
        volume = float(partes[2]) if len(partes) >= 3 and partes[2] else 1.0
        volume = max(0.0, min(10.0, volume))
        sons[tipo_int] = (os.path.join(pasta_base, caminho_rel), raio, volume)
    return sons


PARTICLE_FLOAT_AMPLITUDE = 0.18
PARTICLE_SCALE = 0.35
PARTICLE_OFFSET_Y = 0.0


def _parse_particles(d, pasta_base):
    particles = {}
    for tipo, valor in d.items():
        try:
            tipo_int = int(tipo)
        except ValueError:
            raise ValueError(f"tipo de partícula inválido: {tipo!r}")
        partes = re.split(r"[\s,]+", valor)
        caminho_rel = partes[0].strip() if partes and partes[0] else ""
        if not caminho_rel:
            continue
        quantidade = int(partes[1]) if len(partes) >= 2 and partes[1] else 8
        velocidade = float(partes[2]) if len(partes) >= 3 and partes[2] else 0.5
        espalhamento = float(partes[3]) if len(partes) >= 4 and partes[3] else 0.4
        offset_y = float(partes[4]) if len(partes) >= 5 and partes[4] else PARTICLE_OFFSET_Y
        escala = float(partes[5]) if len(partes) >= 6 and partes[5] else PARTICLE_SCALE
        particles[tipo_int] = (os.path.join(pasta_base, caminho_rel), max(0, quantidade),
                                velocidade, max(0.0, espalhamento),
                                offset_y, max(0.0, escala))
    return particles


def _particle_instances(particle_cells, particle_defs):
    out = []
    for (cx, cy, tipo) in particle_cells:
        if tipo not in particle_defs:
            continue
        caminho_abs, quantidade, velocidade, raio, offset_y, escala = particle_defs[tipo]
        for k in range(quantidade):
            seed = (int(cx * 2) * 7349 + int(cy * 2) * 4519 + k * 131) & 0xFFFFFFFF
            rng = np.random.RandomState(seed)
            ang = rng.uniform(0.0, 2.0 * math.pi)
            r = raio * math.sqrt(rng.uniform(0.0, 1.0))
            fase = rng.uniform(0.0, 2.0 * math.pi)
            px = cx + math.cos(ang) * r
            py = cy + math.sin(ang) * r
            out.append((px, py, caminho_abs, offset_y, escala,
                         PARTICLE_FLOAT_AMPLITUDE, velocidade, fase, AI_NONE, 0.0))
    return out


def load_rcfg(caminho):
    dados = _parse_sections(caminho)
    if "MAP" not in dados or not dados["MAP"]:
        raise ValueError("nenhum mapa encontrado (seção [MAP])")
    raw_mapa = dados["MAP"]
    largura = len(raw_mapa[0])
    for i, row in enumerate(raw_mapa):
        if len(row) != largura:
            raise ValueError(f"linha {i + 1} tem {len(row)} colunas, o mapa precisa de {largura}")

    mapa, billboard_cells, particle_cells, light_cells = _process_map_tokens(raw_mapa)
    spawn = _parse_spawn(dados.get("SPAWN", {}), mapa, ORB_MIN)
    pasta_base = os.path.dirname(os.path.abspath(caminho))
    texturas_rel = _parse_textures(dados.get("TEXTURES", {}))
    texturas_abs = {t: os.path.join(pasta_base, rel) for t, rel in texturas_rel.items()}

    lights = _parse_lights(dados.get("LIGHTS", {}))
    lights = {ORB_MIN + (n - 1): v for n, v in lights.items() if 1 <= n <= 9}

    billboard_defs = _parse_billboards(dados.get("BILLBOARDS", {}), pasta_base)
    billboard_sound_defs = _parse_billboard_sounds(dados.get("BILLBOARD_SOUNDS", {}), pasta_base)
    billboard_instances = [
        (x, y, billboard_defs[tipo][0], billboard_defs[tipo][1], billboard_defs[tipo][2], 0.0, 0.0, 0.0, billboard_defs[tipo][3], billboard_defs[tipo][4])
        for (x, y, tipo) in billboard_cells
        if tipo in billboard_defs
    ]
    particle_defs = _parse_particles(dados.get("PARTICLES", {}), pasta_base)
    particle_instances = _particle_instances(particle_cells, particle_defs)

    bb_completo = billboard_instances + particle_instances
    bb_ai = []
    ai_cells = set()
    bb_sounds = []
    enemy_count = 0
    trio_blinky_bb_idx = None  # índice em bb_ai do BLINKY do trio corrente
    for (x, y, tipo) in billboard_cells:
        if tipo not in billboard_defs:
            continue
        _caminho, _off, _esc, ai, speed = billboard_defs[tipo]
        role = None
        blinky_idx = None
        if ai == AI_ENEMY:
            # role 0 = BLINKY, 1 = INKY, 2 = PINKY — contado só entre
            # inimigos (amigáveis no meio da lista não entram na conta).
            role = enemy_count % 3
            if role == 0:
                trio_blinky_bb_idx = len(bb_ai)  # este item é o novo BLINKY
            else:
                blinky_idx = trio_blinky_bb_idx  # INKY/PINKY referenciam o BLINKY do trio
            enemy_count += 1
        bb_ai.append({
            "x": x, "y": y, "ai": ai, "state": "IDLE",
            "spawn_x": x, "spawn_y": y, "speed": speed,
            "rx": x, "ry": y,
            "role": role, "blinky_idx": blinky_idx,
        })
        if ai != AI_NONE:
            ci, cj = int(x), int(y)
            ai_cells.add((ci, cj))
        snd = billboard_sound_defs.get(tipo)
        if snd is not None:
            bb_sounds.append({"path": snd[0], "radius": snd[1], "volume": snd[2], "channel": None})
        else:
            bb_sounds.append(None)

    return {
        "config": _parse_config(dados.get("CONFIG", {})),
        "spawn": spawn,
        "info": dict(dados.get("INFO", {})),
        "colors": _parse_colors(dados.get("COLORS", {})),
        "theme": _parse_theme(dados.get("THEME", {})),
        "sky": _parse_sky(dados.get("SKY", {})),
        "title": dados.get("TITLE", {}).get("value", ""),
        "map": mapa,
        "lights": lights,
        "textures": texturas_abs,
        "billboards": bb_completo,
        "bb_ai": bb_ai,
        "bb_sounds": bb_sounds,
        "ai_cells": ai_cells,
        "billboard_cells": billboard_cells,
        "particle_cells": particle_cells,
        "light_cells": light_cells,
    }


# ══ FIM DO CARREGADOR ══════════════════════════════════════════

BOOT_MAP_TOKENS = [
    ["1"] * 12,
    ["1"] + ["0"] * 10 + ["1"],
    ["1"] + ["0"] * 10 + ["1"],
    ["1"] + ["0"] * 10 + ["1"],
    ["1"] + ["0"] * 10 + ["1"],
    ["1", "0", "0", "0", "0", "0+L1", "0+L1", "0", "0", "0", "0", "1"],
    ["1", "0", "0", "0", "0", "0+L1", "0+L1", "0", "0", "0", "0", "1"],
    ["1"] + ["0"] * 10 + ["1"],
    ["1"] + ["0"] * 10 + ["1"],
    ["1"] + ["0"] * 10 + ["1"],
    ["1"] + ["0"] * 10 + ["1"],
    ["1"] * 12,
]
(BOOT_MAP, _boot_bb, _boot_particles, BOOT_LIGHT_CELLS) = _process_map_tokens(BOOT_MAP_TOKENS)
BOOT_LIGHT_ORBS = {ORB_MIN: ("#ffcc88", 4.0)}

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

NIGHT_SKY_BASE = "#02030f"
NIGHT_SKY_TOP = "#05061f"

# ══ ESTADO GLOBAL ═════════════════════════════════════════════
WIDTH, HEIGHT = DEFAULT_CONFIG["window_width"], DEFAULT_CONFIG["window_height"]
MM = DEFAULT_CONFIG["mm"]
FOV = DEFAULT_CONFIG["fov"]
MAX_DEPTH = DEFAULT_CONFIG["max_depth"]
MOVE_SPEED = DEFAULT_CONFIG["move_speed"]
RUN_MULTIPLIER = DEFAULT_CONFIG["run_multiplier"]
MOUSE_SENS_X = DEFAULT_CONFIG["mouse_sens_x"]
MOUSE_SENS_Y = DEFAULT_CONFIG["mouse_sens_y"]
MAX_LOOK_Y = DEFAULT_CONFIG["max_look_y"]
BOB_ENABLED = DEFAULT_CONFIG["bob_enabled"]
BOB_AMOUNT = DEFAULT_CONFIG["bob_amount"]
BOB_SPEED = DEFAULT_CONFIG["bob_speed"]
FOG = DEFAULT_CONFIG["fog"]
AMBIENT = DEFAULT_CONFIG["ambient"]

# ══ Céu: sol/lua/estrelas + ciclo dia-noite ══
SKY = dict(SKY_DEFAULTS)
SKY["enabled"] = False
SKY_TIME = SKY_DEFAULTS["start_time"]
SKY_PAUSED = False

MAP = [row[:] for row in BOOT_MAP]
MAP_W = len(MAP[0])
MAP_H = len(MAP)
WALL_COLORS = {}
WALL_TEXTURES = {}
TEXTURE_SIZE = DEFAULT_CONFIG["texture_size"]
THEME = dict(THEME_DEFAULTS)
LIGHT_ORBS = dict(BOOT_LIGHT_ORBS)
LIGHT_CELLS = dict(BOOT_LIGHT_CELLS)
LIGHT_RES = DEFAULT_CONFIG["light_res"]
LIGHT_SOFT_SAMPLES = DEFAULT_CONFIG["light_soft_samples"]
LIGHT_SOFT_RADIUS = DEFAULT_CONFIG["light_soft_radius"]
LIGHT_BOUNCE = DEFAULT_CONFIG["light_bounce"]
LIGHT_BOUNCE_RADIUS = DEFAULT_CONFIG["light_bounce_radius"]
LIGHT_BOUNCE_PASSES = DEFAULT_CONFIG["light_bounce_passes"]
WALL_SCALE = DEFAULT_CONFIG["wall_scale"]
light_grid = []
light_grid_np: "np.ndarray | None" = None
light_grid_floor_np: "np.ndarray | None" = None
LIGHT_W = MAP_W
LIGHT_H = MAP_H
px, py, pangle, look_y = 1.5, 1.5, 0.0, 0.0
bob_phase = 0.0
bob_amt = 0.0
bob_intensity = 0.0
SPAWN = (1.5, 1.5, 0.0)

# ══ Billboards e partículas ══
BILLBOARDS = []
BILLBOARD_CELLS = []
PARTICLE_CELLS = []
BB_AI = []
MAX_BILLBOARD_INSTANCES = 128
BILLBOARD_LAYERS = 9
_BB_LAYER_BY_PATH = {}
_BB_ASPECT_BY_PATH = {}
tex_bbTex: "moderngl.TextureArray | None" = None
# ══ Flags por célula pro minimapa ══
tex_mmFlags: "moderngl.Texture | None" = None

# ══ IA dos billboards (FSM + pathfinding) ══
AI_FRIENDLY_SPEED = 0.035
AI_ENEMY_SPEED = 0.05
AI_BB_CELLS = set()
GAME_OVER = False
GAME_OVER_START = 0.0
overlay_prog: "moderngl.Program | None" = None
overlay_vao: "moderngl.VertexArray | None" = None

# ══ Som posicional estéreo dos billboards ══
BB_SOUND = []
ACTIVE_SOUND_CHANNELS = []
WALL_ATTEN = 0.45
SOUND_MIXER_INIT = False

# ══ Contexto e texturas do renderer ══
ctx: "moderngl.Context | None" = None
tex_map: "moderngl.Texture | None" = None
tex_light: "moderngl.Texture | None" = None
tex_light_floor: "moderngl.Texture | None" = None
tex_orbs: "moderngl.Texture | None" = None
tex_palA: "moderngl.Texture | None" = None
tex_palB: "moderngl.Texture | None" = None
tex_wallArr: "moderngl.TextureArray | None" = None
tex_hasTex: "moderngl.Texture | None" = None

# ══ Billboards desenhados como geometria instanciada ══
bb_prog: "moderngl.Program | None" = None
bb_vao: "moderngl.VertexArray | None" = None
bb_inst_buf: "moderngl.Buffer | None" = None
cross_prog: "moderngl.Program | None" = None
cross_vao: "moderngl.VertexArray | None" = None
fbo = None
fbo_color: "moderngl.Texture | None" = None
fbo_depth: "moderngl.Texture | None" = None
_BB_VERT_POOL = np.zeros((MAX_BILLBOARD_INSTANCES * 6, 14), dtype="f4")
_BB_CORN = np.array([(-0.5, 0.0), (0.5, 0.0), (0.5, 1.0),
                     (-0.5, 0.0), (0.5, 1.0), (-0.5, 1.0)], dtype="f4")

# ══ Tela de carregamento (estado) ══
LOADING_SCREEN_THRESHOLD_CELLS = 256

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


# ══ CARREGADOR DE ASSETS ════════════════════════════════
_ASSET_CACHE = {}


def _fallback_array(tamanho):
    w, h = tamanho
    cel = max(1, min(w, h) // 8)
    yy, xx = np.ogrid[0:h, 0:w]
    checker = ((xx // cel) + (yy // cel)) & 1
    arr = np.empty((h, w, 4), dtype=np.uint8)
    arr[checker == 0] = (255, 0, 255, 255)
    arr[checker == 1] = (0, 0, 0, 255)
    return arr


def load_asset_image(caminho_abs, tamanho, contain=False):
    key = (caminho_abs, tamanho, contain)
    cached = _ASSET_CACHE.get(key)
    if cached is not None:
        return cached

    try:
        raw = Image.open(caminho_abs)
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
        resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        canvas.paste(resized, ((tw - new_w) // 2, (th - new_h) // 2), resized)
        img = canvas
    elif (w, h) != (tw, th):
        img = img.resize((tw, th), Image.Resampling.LANCZOS)

    final_arr = np.ascontiguousarray(np.array(img, dtype=np.uint8))
    result = (final_arr, aspect)
    _ASSET_CACHE[key] = result
    return result


def is_orb(c):
    return c >= ORB_MIN


def is_wall(c):
    return (1 <= c <= WALL_MAX) or c == INVISIBLE_WALL


def _blocks_light(c):
    return 1 <= c <= WALL_MAX


def _los_blocked_f(x0, y0, x1, y1):
    dx = x1 - x0
    dy = y1 - y0
    dist = math.hypot(dx, dy)
    if dist <= 1e-6:
        return False
    steps = int(dist / 0.2)
    if steps < 1:
        steps = 1
    map_local = MAP
    mw = MAP_W
    mh = MAP_H
    wmax = WALL_MAX
    inv_steps = 1.0 / steps
    for s in range(1, steps):
        t = s * inv_steps
        icx = int(x0 + dx * t)
        icy = int(y0 + dy * t)
        if 0 <= icx < mw and 0 <= icy < mh:
            c = map_local[icy][icx]
            if 1 <= c <= wmax:
                return True
    return False


_LIGHT_CACHE = {}


def _light_cache_sig():
    try:
        import hashlib
        h = hashlib.blake2b(digest_size=8)
        for row in MAP:
            h.update(bytes(row))
        for k in sorted(LIGHT_CELLS):
            h.update(f"{k}:{LIGHT_CELLS[k]};".encode())
        for k in sorted(LIGHT_ORBS):
            h.update(f"{k}:{LIGHT_ORBS[k]};".encode())
        for k in sorted(WALL_COLORS):
            h.update(f"{k}:{WALL_COLORS[k]};".encode())
        h.update(f"{LIGHT_RES}|{LIGHT_SOFT_SAMPLES}|{LIGHT_SOFT_RADIUS}|{LIGHT_BOUNCE}|{LIGHT_BOUNCE_RADIUS}|{LIGHT_BOUNCE_PASSES}|{AMBIENT}|{MAP_W}x{MAP_H}".encode())
        return h.digest()
    except Exception:
        return None


def compute_light_grid(on_progress=None):
    global light_grid, light_grid_np, light_grid_floor_np, LIGHT_W, LIGHT_H
    sig = _light_cache_sig()
    if sig is not None and sig in _LIGHT_CACHE:
        cached = _LIGHT_CACHE[sig]
        LIGHT_W, LIGHT_H = cached["LIGHT_W"], cached["LIGHT_H"]
        light_grid_np = cached["light_grid_np"]
        light_grid_floor_np = cached["light_grid_floor_np"]
        light_grid = cached["light_grid"]
        if on_progress is not None:
            on_progress(1.0)
        return

    res = max(1, LIGHT_RES)
    LIGHT_W = MAP_W * res
    LIGHT_H = MAP_H * res
    sub = 1.0 / res
    grid_np = np.full((LIGHT_H, LIGHT_W, 3), AMBIENT, dtype=np.float32)
    grid_floor_np = np.full((LIGHT_H, LIGHT_W, 3), AMBIENT, dtype=np.float32)

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
    disc_pts_t = tuple(disc_pts)
    inv_npts = 1.0 / n_pts if n_pts else 1.0

    map_local = MAP
    mw = MAP_W
    mh = MAP_H
    wmax = WALL_MAX
    ambient_local = AMBIENT

    def _los_blocked_local(x0, y0, x1, y1):
        dx = x1 - x0
        dy = y1 - y0
        d = math.hypot(dx, dy)
        if d <= 1e-6:
            return False
        steps = int(d / 0.2)
        if steps < 1:
            steps = 1
        inv = 1.0 / steps
        for s in range(1, steps):
            t = s * inv
            icx = int(x0 + dx * t)
            icy = int(y0 + dy * t)
            if 0 <= icx < mw and 0 <= icy < mh and 1 <= map_local[icy][icx] <= wmax:
                return True
        return False

    def add_light(x, y, raio, cor_rgb, occlude=True, target_np=None):
        if target_np is None:
            target_np = grid_np
        cx = x + 0.5
        cy = y + 0.5
        r = int(math.ceil(raio))
        r0 = cor_rgb[0]
        r1 = cor_rgb[1]
        r2 = cor_rgb[2]
        y0 = max(0, y - r)
        y1 = min(mh, y + r + 1)
        x0 = max(0, x - r)
        x1 = min(mw, x + r + 1)
        for j in range(y0, y1):
            base_row = j * res
            for i in range(x0, x1):
                base_col = i * res
                for sj in range(res):
                    wy = j + (sj + 0.5) * sub
                    dy = wy - cy
                    for si in range(res):
                        wx = i + (si + 0.5) * sub
                        dx = wx - cx
                        dist = math.hypot(dx, dy)
                        if dist > raio:
                            continue
                        if occlude:
                            vis = 0
                            for ox, oy in disc_pts_t:
                                if not _los_blocked_local(cx + ox, cy + oy, wx, wy):
                                    vis += 1
                            if vis == 0:
                                continue
                            vis_frac = vis * inv_npts
                        else:
                            vis_frac = 1.0
                        d = dist / raio
                        core = 1.0 / (1.0 + 6.0 * d * d)
                        edge = (1.0 - d) / 0.25
                        if edge < 0.0:
                            edge = 0.0
                        elif edge > 1.0:
                            edge = 1.0
                        edge = edge * edge * (3.0 - 2.0 * edge)
                        falloff = core * edge * vis_frac
                        if falloff <= 0:
                            continue
                        rr = base_row + sj
                        cc = base_col + si
                        target_np[rr, cc, 0] += r0 * falloff
                        target_np[rr, cc, 1] += r1 * falloff
                        target_np[rr, cc, 2] += r2 * falloff

    for y in range(mh):
        for x in range(mw):
            t = LIGHT_CELLS.get((x, y))
            if t is None:
                t = map_local[y][x]
                if t < ORB_MIN:
                    continue
            cor_hex, raio = LIGHT_ORBS.get(t, ("#ffcc88", 4.0))
            rr = int(cor_hex[1:3], 16); gg = int(cor_hex[3:5], 16); bb = int(cor_hex[5:7], 16)
            cor_rgb = (rr / 255.0 * 4.0, gg / 255.0 * 4.0, bb / 255.0 * 4.0)
            add_light(x, y, raio, cor_rgb, occlude=True, target_np=grid_np)
        if on_progress is not None:
            on_progress(0.7 * (y + 1) / mh)

    if LIGHT_BOUNCE > 0:
        passes = max(1, LIGHT_BOUNCE_PASSES)
        for passe in range(passes):
            luz_atual = grid_np.copy()
            decaimento = LIGHT_BOUNCE * (0.6 ** passe)
            for y in range(mh):
                for x in range(mw):
                    t = map_local[y][x]
                    if not (1 <= t <= wmax):
                        continue
                    cor_ns, cor_ew = WALL_COLORS.get(t, ("#888888", "#888888"))
                    r0 = (int(cor_ns[1:3], 16) + int(cor_ew[1:3], 16)) * 0.5 / 255.0
                    g0 = (int(cor_ns[3:5], 16) + int(cor_ew[3:5], 16)) * 0.5 / 255.0
                    b0 = (int(cor_ns[5:7], 16) + int(cor_ew[5:7], 16)) * 0.5 / 255.0
                    ci = x * res + res // 2
                    if ci >= LIGHT_W:
                        ci = LIGHT_W - 1
                    cj = y * res + res // 2
                    if cj >= LIGHT_H:
                        cj = LIGHT_H - 1
                    recv = (float(luz_atual[cj, ci, 0]) + float(luz_atual[cj, ci, 1]) + float(luz_atual[cj, ci, 2])) / 3.0
                    if recv <= ambient_local * 1.05:
                        continue
                    bounce_rgb = (r0 * recv * decaimento, g0 * recv * decaimento, b0 * recv * decaimento)
                    add_light(x, y, LIGHT_BOUNCE_RADIUS, bounce_rgb, occlude=False, target_np=grid_np)
                    add_light(x, y, LIGHT_BOUNCE_RADIUS, bounce_rgb, occlude=False, target_np=grid_floor_np)
                if on_progress is not None:
                    frac = (passe + (y + 1) / mh) / passes
                    on_progress(0.7 + 0.3 * frac)

    if on_progress is not None:
        on_progress(1.0)

    np.clip(grid_np, 0.0, 9.0, out=grid_np)
    light_grid_np = grid_np
    light_grid_floor_np = grid_floor_np
    light_grid = grid_np.tolist()
    if sig is not None:
        _LIGHT_CACHE[sig] = {"LIGHT_W": LIGHT_W, "LIGHT_H": LIGHT_H, "light_grid_np": light_grid_np, "light_grid_floor_np": light_grid_floor_np, "light_grid": light_grid}
        if len(_LIGHT_CACHE) > 8:
            oldest = next(iter(_LIGHT_CACHE))
            del _LIGHT_CACHE[oldest]


def open_cell(cx, cy):
    if not (0 <= cx < MAP_W and 0 <= cy < MAP_H):
        return True
    c = MAP[cy][cx]
    return c == 0 or is_orb(c)


def in_map(x, y):
    return 0 <= x < MAP_W and 0 <= y < MAP_H


# ══ SOM POSICIONAL ESTÉREO (billboards) ═══════════════════════════
_WALL_COUNT_CACHE = {}
_WALL_COUNT_CACHE_MAP_SIG = None

def _count_walls_between(x0, y0, x1, y1):
    global _WALL_COUNT_CACHE, _WALL_COUNT_CACHE_MAP_SIG
    sig = (MAP_W, MAP_H)
    if sig != _WALL_COUNT_CACHE_MAP_SIG:
        _WALL_COUNT_CACHE.clear()
        _WALL_COUNT_CACHE_MAP_SIG = sig
    key = (int(x0 * 4), int(y0 * 4), int(x1 * 4), int(y1 * 4))
    cached = _WALL_COUNT_CACHE.get(key)
    if cached is not None:
        return cached
    dx, dy = x1 - x0, y1 - y0
    dist = math.hypot(dx, dy)
    if dist <= 1e-6:
        _WALL_COUNT_CACHE[key] = 0
        return 0
    steps = int(dist / 0.1)
    if steps < 1:
        steps = 1
    count = 0
    prev_wall = False
    mw = MAP_W
    mh = MAP_H
    map_local = MAP
    wmax = WALL_MAX
    inv = 1.0 / steps
    for s in range(steps + 1):
        t = s * inv
        ix = int(x0 + dx * t)
        iy = int(y0 + dy * t)
        if 0 <= ix < mw and 0 <= iy < mh:
            c = map_local[iy][ix]
            is_w = (1 <= c <= wmax) or c == INVISIBLE_WALL
        else:
            is_w = False
        if is_w and not prev_wall:
            count += 1
        prev_wall = is_w
    _WALL_COUNT_CACHE[key] = count
    if len(_WALL_COUNT_CACHE) > 2048:
        _WALL_COUNT_CACHE.clear()
    return count


def _ensure_mixer():
    global SOUND_MIXER_INIT
    if not SOUND_MIXER_INIT:
        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=2)
            pygame.mixer.set_num_channels(64)
            SOUND_MIXER_INIT = True
        except Exception as e:
            print(f"[som] falha ao iniciar mixer: {e}", flush=True)
            SOUND_MIXER_INIT = False


def stop_billboard_sounds():
    global ACTIVE_SOUND_CHANNELS
    for chan in ACTIVE_SOUND_CHANNELS:
        try:
            chan.stop()
        except Exception:
            pass
    ACTIVE_SOUND_CHANNELS = []


def start_billboard_sounds(bb_sounds):
    global ACTIVE_SOUND_CHANNELS
    stop_billboard_sounds()
    _ensure_mixer()
    if not SOUND_MIXER_INIT:
        return
    for entry in bb_sounds:
        if entry is None:
            continue
        try:
            snd = pygame.mixer.Sound(entry["path"])
        except Exception as e:
            print(f"[som] não foi possível carregar {entry['path']!r}: {e}", flush=True)
            continue
        try:
            vol = float(entry["volume"])
        except (TypeError, ValueError):
            vol = 1.0
        vol = max(0.0, min(10.0, vol))
        if vol > 1.0:
            try:
                raw = snd.get_raw()
                samples = np.frombuffer(raw, dtype="<i2").astype(np.float32)
                samples = np.clip(samples * vol, -32768.0, 32767.0)
                snd = pygame.mixer.Sound(samples.astype("<i2").tobytes())
            except Exception as e:
                print(f"[som] falha ao amplificar {entry['path']!r}: {e}", flush=True)
        try:
            chan = snd.play(loops=-1)
        except Exception as e:
            print(f"[som] falha ao tocar {entry['path']!r}: {e}", flush=True)
            continue
        if chan is None:
            continue
        entry["channel"] = chan
        ACTIVE_SOUND_CHANNELS.append(chan)


_SND_UPDATE_FRAME = 0
_SND_WALL_CACHE = {}

def update_billboard_sounds(px, py, pangle):
    global _SND_UPDATE_FRAME
    if not SOUND_MIXER_INIT or not BB_SOUND:
        return
    _SND_UPDATE_FRAME += 1
    rx = -math.sin(pangle)
    ry = math.cos(pangle)
    for idx, entry in enumerate(BB_SOUND):
        if entry is None:
            continue
        chan = entry.get("channel")
        if chan is None:
            continue
        if idx >= len(BILLBOARDS):
            continue
        bx, by = BILLBOARDS[idx][0], BILLBOARDS[idx][1]
        dx = bx - px
        dy = by - py
        dist = math.hypot(dx, dy)
        raio = entry["radius"]
        if dist > raio or dist < 1e-6:
            try:
                chan.set_volume(0.0, 0.0)
            except Exception:
                pass
            continue
        r_fall = 1.0 - dist / raio
        if r_fall < 0.0:
            r_fall = 0.0
        elif r_fall > 1.0:
            r_fall = 1.0
        wc_key = (int(bx * 4), int(by * 4), int(px * 4), int(py * 4))
        wc = _SND_WALL_CACHE.get(wc_key)
        if wc is None or (_SND_UPDATE_FRAME % 3 == 0):
            wc = _count_walls_between(bx, by, px, py)
            _SND_WALL_CACHE[wc_key] = wc
            if len(_SND_WALL_CACHE) > 1024:
                _SND_WALL_CACHE.clear()
        w_fall = WALL_ATTEN ** wc
        atten = r_fall * w_fall
        proj = (dx * rx + dy * ry) / (dist if dist > 1e-3 else 1e-3)
        if proj < -1.0:
            proj = -1.0
        elif proj > 1.0:
            proj = 1.0
        last = entry.get("_last_vol")
        lv = atten * (0.5 - 0.5 * proj)
        rv = atten * (0.5 + 0.5 * proj)
        if last is not None and abs(last[0] - lv) < 0.005 and abs(last[1] - rv) < 0.005:
            continue
        entry["_last_vol"] = (lv, rv)
        try:
            chan.set_volume(lv, rv)
        except Exception:
            pass


# ══ PATHFINDING (Wavefront / BFS) ═════════════════════════════
import heapq
from collections import deque

_DIST_GRID_CACHE = {}
_DIST_GRID_CACHE_MAP_SIG = None
_DIST_AVOID_CACHE = {}

def _dist_cache_sig():
    return (MAP_W, MAP_H, tuple(tuple(row) for row in MAP))

def compute_dist_grid(tx, ty):
    global _DIST_GRID_CACHE, _DIST_GRID_CACHE_MAP_SIG
    sig = (MAP_W, MAP_H)
    if sig != _DIST_GRID_CACHE_MAP_SIG:
        _DIST_GRID_CACHE.clear()
        _DIST_AVOID_CACHE.clear()
        _DIST_GRID_CACHE_MAP_SIG = sig
    key = (int(tx), int(ty))
    cached = _DIST_GRID_CACHE.get(key)
    if cached is not None:
        return cached
    tw, th = MAP_W, MAP_H
    grid = [[999999] * tw for _ in range(th)]
    sx, sy = int(tx), int(ty)
    if 0 <= sx < tw and 0 <= sy < th:
        grid[sy][sx] = 0
        fila = deque()
        fila.append((sx, sy))
        map_local = MAP
        wmax = WALL_MAX
        orb_min = ORB_MIN
        while fila:
            x, y = fila.popleft()
            d = grid[y][x]
            nd = d + 1
            nx = x + 1
            if nx < tw and grid[y][nx] > nd:
                c = map_local[y][nx]
                if c == 0 or c >= orb_min:
                    grid[y][nx] = nd
                    fila.append((nx, y))
            nx = x - 1
            if nx >= 0 and grid[y][nx] > nd:
                c = map_local[y][nx]
                if c == 0 or c >= orb_min:
                    grid[y][nx] = nd
                    fila.append((nx, y))
            ny = y + 1
            if ny < th and grid[ny][x] > nd:
                c = map_local[ny][x]
                if c == 0 or c >= orb_min:
                    grid[ny][x] = nd
                    fila.append((x, ny))
            ny = y - 1
            if ny >= 0 and grid[ny][x] > nd:
                c = map_local[ny][x]
                if c == 0 or c >= orb_min:
                    grid[ny][x] = nd
                    fila.append((x, ny))
    if len(_DIST_GRID_CACHE) > 64:
        _DIST_GRID_CACHE.clear()
    _DIST_GRID_CACHE[key] = grid
    return grid


def compute_dist_grid_avoiding(tx, ty, avoid_x, avoid_y, avoid_radius, avoid_penalty):
    # Como compute_dist_grid, mas células perto de (avoid_x, avoid_y) custam
    # mais caro a atravessar — Dijkstra em vez de BFS. Usado pro Pinky nunca
    # "colar" no Blinky quando existe rota alternativa até o alvo (mesmo que
    # essa rota seja mais longa); se a única rota passa perto do Blinky, o
    # custo extra é finito, então ele ainda vai por ali em vez de travar.
    sig = (MAP_W, MAP_H)
    global _DIST_GRID_CACHE_MAP_SIG
    if sig != _DIST_GRID_CACHE_MAP_SIG:
        _DIST_GRID_CACHE.clear()
        _DIST_AVOID_CACHE.clear()
        _DIST_GRID_CACHE_MAP_SIG = sig
    key = (int(tx), int(ty), int(avoid_x * 2), int(avoid_y * 2), avoid_radius, avoid_penalty)
    cached = _DIST_AVOID_CACHE.get(key)
    if cached is not None:
        return cached
    tw, th = MAP_W, MAP_H
    grid = [[999999] * tw for _ in range(th)]
    sx, sy = int(tx), int(ty)
    if not (0 <= sx < tw and 0 <= sy < th):
        return grid
    grid[sy][sx] = 0
    r2 = avoid_radius * avoid_radius
    heap = [(0, sx, sy)]
    map_local = MAP
    orb_min = ORB_MIN
    while heap:
        d, x, y = heapq.heappop(heap)
        if d > grid[y][x]:
            continue
        nd_base = d + 1.0
        for ddx, ddy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx = x + ddx
            ny = y + ddy
            if 0 <= nx < tw and 0 <= ny < th:
                c = map_local[ny][nx]
                if not (c == 0 or c >= orb_min):
                    continue
                cost = 1.0
                ddx2 = (nx + 0.5 - avoid_x)
                ddy2 = (ny + 0.5 - avoid_y)
                if ddx2 * ddx2 + ddy2 * ddy2 <= r2:
                    cost += avoid_penalty
                nd = d + cost
                if nd < grid[ny][nx]:
                    grid[ny][nx] = nd # type: ignore
                    heapq.heappush(heap, (nd, nx, ny)) # type: ignore
    if len(_DIST_AVOID_CACHE) > 64:
        _DIST_AVOID_CACHE.clear()
    _DIST_AVOID_CACHE[key] = grid
    return grid


def _step_ai(bx, by, dist_grid, speed):
    tw, th = MAP_W, MAP_H
    cx, cy = int(bx), int(by)
    best = None
    best_d = dist_grid[cy][cx] if (0 <= cx < tw and 0 <= cy < th) else 999999
    for ddx, ddy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nx, ny = cx + ddx, cy + ddy
        if 0 <= nx < tw and 0 <= ny < th and open_cell(nx, ny):
            if dist_grid[ny][nx] < best_d:
                best_d = dist_grid[ny][nx]
                best = (nx, ny)
    if best is None:
        return bx, by
    tx, ty = best[0] + 0.5, best[1] + 0.5
    ddx, ddy = tx - bx, ty - by
    d = math.hypot(ddx, ddy)
    if d <= speed:
        return tx, ty
    return bx + ddx / d * speed, by + ddy / d * speed


def _step_toward(bx, by, tx, ty, speed):
    ddx, ddy = tx - bx, ty - by
    d = math.hypot(ddx, ddy)
    if d <= speed or d < 1e-6:
        return tx, ty
    return bx + ddx / d * speed, by + ddy / d * speed


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
layout(location = 0) out vec4 outColor;
layout(location = 1) out vec4 outDepth;
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
uniform float u_wallMax;
uniform float u_orbMin;
uniform sampler2D u_map;
uniform sampler2D u_light;
uniform sampler2D u_light_floor;
uniform sampler2D u_orbs;
uniform int u_orbCount;
const int MAX_ORBS = 1024;
uniform sampler2D u_palA;
uniform sampler2D u_palB;
uniform sampler2DArray u_wallTex;
uniform sampler2D u_hasTex;
uniform int u_bbCount;
uniform vec4 u_bbA[128];   // xy = pos, z = layer, w = yoff
uniform vec4 u_bbB[128];   // x = aspect, y = scale, z = amp, w = vel
uniform vec4 u_bbC[128];   // x = phase, y = ai
uniform float u_time;
uniform sampler2DArray u_bbTex;
uniform sampler2D u_mmFlags;
uniform vec3 u_skyB, u_skyT, u_floorB, u_floorT;
uniform float u_sunAngle, u_sunElev, u_nightFactor, u_starsCount, u_skyBodies;
uniform vec3 u_sunColor, u_moonColor;
uniform vec3 u_cross;
uniform vec3 u_mmPlayer;
uniform vec2 u_mmPos;
uniform vec2 u_mmSize;
uniform float u_mmCell;
uniform vec2 u_playerPix;
uniform vec2 u_dirPix;
vec2 mapTex(vec2 cell) { return vec2((cell.x + 0.5) / u_mapSize.x, (cell.y + 0.5) / u_mapSize.y); }
int cellType(vec2 cell) { return int(round(texture(u_map, mapTex(cell)).r)); }
vec3 softClip(vec3 x, float knee, float maxv) {
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
// Per-pixel orb lighting for the floor (uncapped orb count via u_orbs texture).
bool losClear(vec2 a, vec2 b) {
    vec2 d = b - a;
    float dist = length(d);
    if (dist < 1e-4) return true;
    vec2 dir = d / dist;
    vec2 cell = floor(a);
    vec2 deltaDist = vec2(
        abs(dir.x) < 1e-6 ? 1e30 : abs(1.0 / dir.x),
        abs(dir.y) < 1e-6 ? 1e30 : abs(1.0 / dir.y)
    );
    ivec2 stp;
    vec2 sideDist;
    if (dir.x < 0.0) { stp.x = -1; sideDist.x = (a.x - cell.x) * deltaDist.x; }
    else              { stp.x =  1; sideDist.x = (cell.x + 1.0 - a.x) * deltaDist.x; }
    if (dir.y < 0.0) { stp.y = -1; sideDist.y = (a.y - cell.y) * deltaDist.y; }
    else              { stp.y =  1; sideDist.y = (cell.y + 1.0 - a.y) * deltaDist.y; }
    for (int i = 0; i < 96; i++) {
        float nextT = min(sideDist.x, sideDist.y);
        if (nextT >= dist) break;
        if (sideDist.x < sideDist.y) { sideDist.x += deltaDist.x; cell.x += float(stp.x); }
        else                          { sideDist.y += deltaDist.y; cell.y += float(stp.y); }
        if (cell.x < 0.0 || cell.y < 0.0 || cell.x >= u_mapSize.x || cell.y >= u_mapSize.y) break;
        int ct = cellType(cell);
        if (ct >= 1 && ct <= int(u_wallMax)) return false;
    }
    return true;
}
vec3 directLight(vec2 world) {
    vec3 acc = vec3(0.0);
    for (int k = 0; k < MAX_ORBS; k++) {
        if (k >= u_orbCount) break;
        vec4 o0 = texelFetch(u_orbs, ivec2(k, 0), 0);
        vec4 o1 = texelFetch(u_orbs, ivec2(k, 1), 0);
        vec2 op = o0.xy;
        float raio = o0.z;
        vec3 ocol = o1.rgb;
        vec2 dd = world - op;
        float dist = length(dd);
        if (dist > raio) continue;
        if (!losClear(op, world)) continue;
        float dn = dist / raio;
        float core = 1.0 / (1.0 + 6.0 * dn * dn);
        float edge = clamp((1.0 - dn) / 0.25, 0.0, 1.0);
        edge = edge * edge * (3.0 - 2.0 * edge);
        acc += ocol * core * edge;
    }
    return acc;
}
vec3 floorLight(vec2 worldPos) {
    vec2 uvL = worldPos / u_mapSize;
    vec3 l = directLight(worldPos) + texture(u_light_floor, uvL).rgb;
    vec3 hdr = vec3(u_ambient) + l;
    return softClip(hdr, 3.0, 7.0);
}
const float KNEE = 4.0;
vec3 hdrShoulder(vec3 c) {
    float l = max(c.r, max(c.g, c.b));
    if (l > 1.0) c *= (1.0 + 0.35 * (l - 1.0) / (l + KNEE)) / l;
    return c;
}
vec3 palColor(float t, int useA) {
    vec2 c = vec2((t + 0.5) / 256.0, 0.5);
    return useA == 1 ? texture(u_palA, c).rgb : texture(u_palB, c).rgb;
}
float hasWallTex(float t) {
    return texture(u_hasTex, vec2((t + 0.5) / 256.0, 0.5)).r;
}
float starHash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}
vec3 celestialContrib(vec2 dirWorld, float elevSin, vec3 col, float pixX, float row) {
    float invDet = 1.0 / (u_plane.x * u_dir.y - u_dir.x * u_plane.y);
    float tx = invDet * (u_dir.y * dirWorld.x - u_dir.x * dirWorld.y);
    float ty = invDet * (-u_plane.y * dirWorld.x + u_plane.x * dirWorld.y);
    if (ty <= 0.02) return vec3(0.0);
    float screenX = (u_res.x * 0.5) * (1.0 + tx / ty);
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
        float focal = max(u_scale * 0.5, 1.0);
        float ndcX = pixX / max(u_res.x * 0.5, 1.0) - 1.0;
        float rx = length(u_plane) * ndcX;
        float ry = (u_horizon - row) / focal;
        float elevSin = ry / sqrt(rx * rx + ry * ry + 1.0);
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
    float row = (1.0 - uv.y) * u_res.y;
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
    int maxIt = int(u_depth) + 4;
    float perpDist = 0.0;
    float texU = 0.0;
    for (int it = 0; it < maxIt; it++) {
        if (sideDist.x < sideDist.y) { sideDist.x += delta.x; mapPos.x += float(step.x); side = 0; }
        else                          { sideDist.y += delta.y; mapPos.y += float(step.y); side = 1; }
        if (mapPos.x < 0.0 || mapPos.x >= u_mapSize.x || mapPos.y < 0.0 || mapPos.y >= u_mapSize.y) break;
        int t = cellType(mapPos);
        if (t >= 1 && t <= int(u_wallMax)) {
            float pd = (side == 0) ? (sideDist.x - delta.x) : (sideDist.y - delta.y);
            float lineH = u_scale / pd;
            float wTop = horizon - lineH * 0.5;
            float wBot = horizon + lineH * 0.5;
            if (row >= wTop && row <= wBot) {
                float tV = clamp((row - wTop) / max(1.0, wBot - wTop), 0.0, 1.0);
                vec2 hitWorld = u_pos + pd * rayDir;
                float tU = fract((side == 0) ? hitWorld.y : hitWorld.x);
                float alpha = 1.0;
                if (hasWallTex(float(t)) > 0.5) {
                    alpha = textureLod(u_wallTex, vec3(vec2(tU, tV), float(t) - 1.0), 0.0).a;
                }
                if (alpha > 0.5) {
                    hit = true;
                    wtype = t;
                    perpDist = pd;
                    texU = tU;
                    break;
                }
            }
        }
    }
    vec3 color;
    if (hit) {
        vec3 wcol = (side == 1) ? palColor(float(wtype), 1) : palColor(float(wtype), 0);
        vec2 hitWorld = u_pos + perpDist * rayDir;
        vec2 faceNormal = (side == 0) ? vec2(-float(step.x), 0.0) : vec2(0.0, -float(step.y));
        vec2 wallSample = hitWorld + faceNormal * 0.5;
        wallSample = clamp(wallSample, vec2(0.02), u_mapSize - vec2(0.02));
        vec3 lightv = lightAt(wallSample);
        float fogv = clamp((u_fog * perpDist) / u_depth, 0.0, 1.0);
        float hasTexFlag = hasWallTex(float(wtype));
        float lineH = u_scale / perpDist;
        float wallTop = horizon - lineH * 0.5;
        float wallBottom = horizon + lineH * 0.5;
        if (row >= wallTop && row <= wallBottom) {
            float texV = clamp((row - wallTop) / max(1.0, wallBottom - wallTop), 0.0, 1.0);
            vec3 wcolFinal;
            if (hasTexFlag > 0.5) {
                vec4 texSample = texture(u_wallTex, vec3(vec2(texU, texV), float(wtype) - 1.0));
                vec3 dynamicLight = lightv / (lightv + vec3(1.0));
                vec3 litBase = wcol * dynamicLight * 1.5;
                vec3 texColor = pow(texSample.rgb, vec3(2.2));
                vec3 litTex = pow(texColor * dynamicLight * 2.2, vec3(1.0 / 2.2));
                wcolFinal = mix(litBase, litTex, texSample.a);
            } else {
                vec3 dynamicLight = lightv / (lightv + vec3(1.0));
                wcolFinal = wcol * dynamicLight * 1.5;
            }
            vec2 sunDir = vec2(cos(u_sunAngle), sin(u_sunAngle));
            float ndl = max(dot(faceNormal, sunDir), 0.0);
            float sideShade = 0.6 + 0.4 * ndl;
            color = hdrShoulder(wcolFinal * sideShade) * (1.0 - fogv);
        } else if (row > wallBottom) {
            float rowDist = (u_scale * 0.5) / (row - horizon);
            vec2 fc = u_pos + rowDist * rayDir;
            float depthT = (row - horizon) / (u_scale * 0.5);
            vec3 fcol = mix(u_floorB, u_floorT, clamp(depthT, 0.0, 1.0));
            vec3 lv = floorLight(fc);
            float fv = clamp((u_fog * rowDist) / u_depth, 0.0, 1.0);
            color = hdrShoulder(fcol * lv) * (1.0 - fv);
        } else {
            color = skyColor(row, rayDir, uv.x * u_res.x);
        }
    } else {
        if (row > horizon) {
            float rowDist = (u_scale * 0.5) / (row - horizon);
            vec2 fc = u_pos + rowDist * rayDir;
            float depthT = (row - horizon) / (u_scale * 0.5);
            vec3 fcol = mix(u_floorB, u_floorT, clamp(depthT, 0.0, 1.0));
            vec3 lv = floorLight(fc);
            float fv = clamp((u_fog * rowDist) / u_depth, 0.0, 1.0);
            color = hdrShoulder(fcol * lv) * (1.0 - fv);
        } else {
            color = skyColor(row, rayDir, uv.x * u_res.x);
        }
    }
    vec2 pix = vec2(uv.x, 1.0 - uv.y) * u_res;
    float wallDepth = hit ? ((side == 0) ? (sideDist.x - delta.x) : (sideDist.y - delta.y)) : 1e9;
    outDepth = vec4(clamp(wallDepth / u_depth, 0.0, 1.0), 0.0, 0.0, 1.0);
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
                float stripe = fract((cellFrac.x + cellFrac.y) * 4.0);
                color = mix(vec3(0.06), vec3(0.498, 0.690, 1.0), stripe < 0.5 ? 0.5 : 0.15);
            } else if (fLight) {
                int lightIdx = (flags >> 4) & 15;
                float tLight = (lightIdx > 0) ? (u_orbMin + float(lightIdx - 1)) : float(max(t, int(u_orbMin)));
                vec3 lc = palColor(tLight, 1);
                color = (length(cellCenter) < 0.32) ? lc * 1.4 : vec3(0.06);
            } else {
                color = vec3(0.06);
            }
            if (fBB) {
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
        for (int b = 0; b < u_bbCount && b < 128; b++) {
            if (u_bbC[b].y < 0.5) continue;
            vec2 bbPix = u_mmPos + u_bbA[b].xy * u_mmCell;
            float bbd = length(pix - bbPix);
            if (bbd < 3.5) {
                color = (u_bbC[b].y < 1.5) ? vec3(0.878, 0.643, 0.345)
                                          : vec3(0.79, 0.34, 0.31);
            }
        }
    }
    outColor = vec4(color, 1.0);
}

"""

# ══ SHADERS DE BILLBOARDS (geometria instanciada) ══════════════════
BB_VERT = """
#version 330 core
in vec2 in_corner;   // x em [-0.5,0.5], y em [0,1] (0 = base, 1 = topo)
in vec4 in_a;        // bx, by, layer, yoff
in vec4 in_b;        // scale, aspect, amp, vel
in vec4 in_c;        // phase, ai, _, _
uniform vec2 u_res;
uniform vec2 u_pos;
uniform vec2 u_dir;
uniform vec2 u_plane;
uniform float u_horizon;
uniform float u_scale;
uniform float u_time;
out vec2 v_uv;
out float v_layer;
out float v_aspect;
out float v_depth;
void main() {
    vec2 sp = in_a.xy - u_pos;
    float invDet = 1.0 / (u_plane.x * u_dir.y - u_dir.x * u_plane.y);
    float tx = invDet * (u_dir.y * sp.x - u_dir.x * sp.y);
    float ty = invDet * (-u_plane.y * sp.x + u_plane.x * sp.y);
    v_depth = ty;
    v_layer = in_a.z;
    v_aspect = in_b.y;
    v_uv = vec2(in_corner.x + 0.5, in_corner.y);
    float screenX = (u_res.x * 0.5) * (1.0 + tx / ty);
    float size = (u_scale / ty) * in_b.x;
    float sizeX = size * in_b.y;
    float sizeY = size;
    float dynOff = in_a.w + in_b.z * sin(u_time * in_b.w + in_c.x);
    float shift = dynOff * (u_scale / ty);
    float bottom = u_horizon + sizeY * 0.5 - shift;
    float left = screenX - sizeX * 0.5;
    float px = left + v_uv.x * sizeX;
    float py = bottom - v_uv.y * sizeY;
    float ndcx = px / u_res.x * 2.0 - 1.0;
    float ndcy = 1.0 - py / u_res.y * 2.0;
    gl_Position = vec4(ndcx, ndcy, 0.0, 1.0);
}

"""

BB_FRAG = """
#version 330 core
in vec2 v_uv;
in float v_layer;
in float v_aspect;
in float v_depth;
out vec4 outColor;
uniform sampler2DArray u_bbTex;
uniform sampler2D u_wallDepth;
uniform vec2 u_res;
uniform vec2 u_pos;
uniform vec2 u_dir;
uniform vec2 u_plane;
uniform vec2 u_mapSize;
uniform sampler2D u_map;
uniform sampler2D u_light;
uniform sampler2D u_light_floor;
uniform sampler2D u_orbs;
uniform int u_orbCount;
const int MAX_ORBS = 1024;
uniform float u_ambient;
uniform float u_fog;
uniform float u_depth;
vec3 lightAt(vec2 worldPos) {
    vec2 uvL = worldPos / u_mapSize;
    vec3 l = texture(u_light, uvL).rgb;
    vec3 hdr = vec3(u_ambient) + l;
    vec3 over = max(hdr - vec3(3.0), vec3(0.0));
    vec3 comp = (7.0 - 3.0) * (vec3(1.0) - exp(-over / (7.0 - 3.0)));
    return min(hdr, vec3(3.0)) + comp;
}
vec2 mapTexBB(vec2 cell) { return vec2((cell.x + 0.5) / u_mapSize.x, (cell.y + 0.5) / u_mapSize.y); }
int cellTypeBB(vec2 cell) { return int(round(texture(u_map, mapTexBB(cell)).r)); }
bool losClearBB(vec2 a, vec2 b) {
    vec2 d = b - a;
    float dist = length(d);
    if (dist < 1e-4) return true;
    vec2 dir = d / dist;
    vec2 cell = floor(a);
    vec2 deltaDist = vec2(
        abs(dir.x) < 1e-6 ? 1e30 : abs(1.0 / dir.x),
        abs(dir.y) < 1e-6 ? 1e30 : abs(1.0 / dir.y)
    );
    ivec2 stp;
    vec2 sideDist;
    if (dir.x < 0.0) { stp.x = -1; sideDist.x = (a.x - cell.x) * deltaDist.x; }
    else              { stp.x =  1; sideDist.x = (cell.x + 1.0 - a.x) * deltaDist.x; }
    if (dir.y < 0.0) { stp.y = -1; sideDist.y = (a.y - cell.y) * deltaDist.y; }
    else              { stp.y =  1; sideDist.y = (cell.y + 1.0 - a.y) * deltaDist.y; }
    for (int i = 0; i < 96; i++) {
        float nextT = min(sideDist.x, sideDist.y);
        if (nextT >= dist) break;
        if (sideDist.x < sideDist.y) { sideDist.x += deltaDist.x; cell.x += float(stp.x); }
        else                          { sideDist.y += deltaDist.y; cell.y += float(stp.y); }
        if (cell.x < 0.0 || cell.y < 0.0 || cell.x >= u_mapSize.x || cell.y >= u_mapSize.y) break;
        int ct = cellTypeBB(cell);
        if (ct >= 1 && ct <= 9) return false;
    }
    return true;
}
vec3 directLightBB(vec2 world) {
    vec3 acc = vec3(0.0);
    for (int k = 0; k < MAX_ORBS; k++) {
        if (k >= u_orbCount) break;
        vec4 o0 = texelFetch(u_orbs, ivec2(k, 0), 0);
        vec4 o1 = texelFetch(u_orbs, ivec2(k, 1), 0);
        vec2 op = o0.xy;
        float raio = o0.z;
        vec3 ocol = o1.rgb;
        vec2 dd = world - op;
        float dist = length(dd);
        if (dist > raio) continue;
        if (!losClearBB(op, world)) continue;
        float dn = dist / raio;
        float core = 1.0 / (1.0 + 6.0 * dn * dn);
        float edge = clamp((1.0 - dn) / 0.25, 0.0, 1.0);
        edge = edge * edge * (3.0 - 2.0 * edge);
        acc += ocol * core * edge;
    }
    return acc;
}
vec3 floorLightBB(vec2 worldPos) {
    vec2 uvL = worldPos / u_mapSize;
    vec3 l = directLightBB(worldPos) + texture(u_light_floor, uvL).rgb;
    vec3 hdr = vec3(u_ambient) + l;
    vec3 over = max(hdr - vec3(3.0), vec3(0.0));
    vec3 comp = (7.0 - 3.0) * (vec3(1.0) - exp(-over / (7.0 - 3.0)));
    return min(hdr, vec3(3.0)) + comp;
}
const float KNEE = 4.0;
vec3 hdrShoulder(vec3 c) {
    float l = max(c.r, max(c.g, c.b));
    if (l > 1.0) c *= (1.0 + 0.35 * (l - 1.0) / (l + KNEE)) / l;
    return c;
}
void main() {
    if (v_depth <= 0.05) discard;
    float wd = texture(u_wallDepth, gl_FragCoord.xy / u_res).r * u_depth;
    if (v_depth >= wd) discard;
    float fx = min(1.0, v_aspect);
    float fy = min(1.0, 1.0 / v_aspect);
    vec2 uvBB = vec2(v_uv.x * fx + (1.0 - fx) * 0.5,
                     (1.0 - v_uv.y) * fy + (1.0 - fy) * 0.5);
    vec4 s = texture(u_bbTex, vec3(uvBB, v_layer));
    if (s.a < 0.05) discard;
    float ndcx = gl_FragCoord.x / u_res.x * 2.0 - 1.0;
    vec2 rayDir = u_dir + u_plane * ndcx;
    vec2 bWorld = clamp(u_pos + v_depth * rayDir, vec2(0.02), u_mapSize - vec2(0.02));
    vec3 lv = floorLightBB(bWorld);
    vec3 dyn = lv / (lv + vec3(1.0));
    vec3 lit = s.rgb * dyn * 2.0;
    float fogv = clamp((u_fog * v_depth) / u_depth, 0.0, 1.0);
    outColor = vec4(hdrShoulder(lit) * (1.0 - fogv), s.a);
}

"""

CROSS_FRAG = """
#version 330 core
in vec2 uv;
out vec4 outColor;
uniform vec2 u_res;
uniform vec3 u_cross;
void main() {
    vec2 pix = vec2(uv.x, 1.0 - uv.y) * u_res;
    vec2 ctr = u_res * 0.5;
    float ax = abs(pix.x - ctr.x);
    float ay = abs(pix.y - ctr.y);
    bool onH = (ay < 2.0) && (ax < 12.0) && (ax > 4.0);
    bool onV = (ax < 2.0) && (ay < 12.0) && (ay > 4.0);
    if (onH || onV) {
        outColor = vec4(u_cross, 0.8);
    } else {
        outColor = vec4(0.0);
    }
}
"""


# ══ TELA DE CARREGAMENTO (função) ════════════════════════════════
def _make_progress_drawer(width, height, label):
    pygame.init()
    pygame.font.init()
    font = pygame.font.SysFont(None, 26)

    if ctx is None:
        screen = pygame.display.set_mode((max(320, width), max(120, height)))
        pygame.display.set_caption("Carregando mapa...")

        def draw(pct):
            pct = max(0.0, min(1.0, pct))
            w, h = screen.get_size()
            screen.fill((12, 12, 18))
            bar_w, bar_h = int(w * 0.6), 22
            bx, by = (w - bar_w) // 2, h // 2
            pygame.draw.rect(screen, (55, 55, 68), (bx, by, bar_w, bar_h), border_radius=6)
            pygame.draw.rect(screen, (90, 200, 160), (bx, by, int(bar_w * pct), bar_h), border_radius=6)
            pygame.draw.rect(screen, (120, 120, 140), (bx, by, bar_w, bar_h), width=1, border_radius=6)
            txt = font.render(f"{label} — {int(pct * 100)}%", True, (230, 230, 230))
            screen.blit(txt, (bx, by - 32))
            pygame.event.pump()
            pygame.display.flip()

        draw(0.0)
        return draw

    sw, sh = ctx.screen.width, ctx.screen.height
    surf = pygame.Surface((sw, sh), pygame.SRCALPHA)
    bar_w, bar_h = int(sw * 0.6), 22
    bx, by = (sw - bar_w) // 2, sh // 2

    prog_loading: "moderngl.Program | None" = None
    vao_loading: "moderngl.VertexArray | None" = None
    quad_tex: "moderngl.Texture | None" = None

    def _ensure_gl():
        nonlocal prog_loading, vao_loading
        assert ctx is not None
        if prog_loading is not None:
            return
        prog_loading = ctx.program(vertex_shader="""
#version 330 core
in vec2 in_pos;
in vec2 in_uv;
out vec2 uv;
void main() {
    uv = in_uv;
    gl_Position = vec4(in_pos, 0.0, 1.0);
}
""", fragment_shader="""
#version 330 core
in vec2 uv;
out vec4 outColor;
uniform sampler2D u_tex;
void main() {
    outColor = texture(u_tex, uv);
}
""")
        verts = np.array([
            -1, -1, 0, 0,
             1, -1, 1, 0,
             1,  1, 1, 1,
            -1, -1, 0, 0,
             1,  1, 1, 1,
            -1,  1, 0, 1,
        ], dtype="f4")
        vbo = ctx.buffer(verts.tobytes())
        vao_loading = ctx.vertex_array(prog_loading, vbo, "in_pos", "in_uv")

    def draw(pct):
        nonlocal quad_tex
        assert ctx is not None
        pct = max(0.0, min(1.0, pct))
        surf.fill((12, 12, 18, 255))
        pygame.draw.rect(surf, (55, 55, 68), (bx, by, bar_w, bar_h), border_radius=6)
        pygame.draw.rect(surf, (90, 200, 160), (bx, by, int(bar_w * pct), bar_h), border_radius=6)
        pygame.draw.rect(surf, (120, 120, 140), (bx, by, bar_w, bar_h), width=1, border_radius=6)
        txt = font.render(f"{label} — {int(pct * 100)}%", True, (230, 230, 230))
        surf.blit(txt, (bx, by - 32))
        data = pygame.image.tobytes(surf, "RGBA", True)
        _ensure_gl()
        assert prog_loading is not None
        assert vao_loading is not None
        if quad_tex is None or quad_tex.width != sw or quad_tex.height != sh:
            if quad_tex is not None:
                quad_tex.release()
            quad_tex = ctx.texture((sw, sh), 4, data)
        else:
            quad_tex.write(data)
        quad_tex.use(0)
        prog_loading["u_tex"] = 0
        ctx.viewport = (0, 0, sw, sh)
        ctx.clear(color=(12 / 255, 12 / 255, 18 / 255, 1.0))
        vao_loading.render(mode=moderngl.TRIANGLES)
        pygame.event.pump()
        pygame.display.flip()

    draw(0.0)
    return draw


# ══ INICIALIZAÇÃO pygame + moderngl ═════════════════════════════
class _GLLoader:
    def __init__(self, lib, getproc):
        import ctypes
        proto = ctypes.CFUNCTYPE(ctypes.c_ulonglong, ctypes.c_char_p)
        proc = ctypes.cast(getproc, proto)
        self.load_opengl_function = (
            lambda n: proc(n.encode())
            or ctypes.cast(getattr(lib, n, 0), ctypes.c_void_p).value or 0
        )

    def __enter__(self):
        pass

    def __exit__(self, *args):
        pass


def create_gl_context():
    try:
        return moderngl.create_context()
    except Exception:
        pass
    import ctypes
    for libname in ("libGL.so", "libEGL.so"):
        try:
            lib = ctypes.CDLL(libname)
        except OSError:
            continue
        if libname == "libGL.so":
            has_ctx = lib.glXGetCurrentContext # type: ignore
            getproc = lib.glXGetProcAddress
        else:
            has_ctx = lib.eglGetCurrentContext # type: ignore
            getproc = lib.eglGetProcAddress
        if not has_ctx():
            continue
        try:
            moderngl.init_context(loader=_GLLoader(lib, getproc))
            return moderngl.get_context()
        except Exception:
            continue
    raise RuntimeError(
        "Nao foi possivel criar o contexto OpenGL. Instale libglvnd-dev "
        "(sudo apt-get install libglvnd-dev) e rode num display X11/Wayland."
    )


def resize_window(width, height):
    flags = pygame.OPENGL | pygame.DOUBLEBUF
    try:
        pygame.display.set_mode((width, height), flags, vsync=1)
    except pygame.error:
        pygame.display.set_mode((width, height), flags)
    if ctx is not None:
        ctx.viewport = (0, 0, width, height)
        init_fbo()


def get_monitor_refresh_rate():
    try:
        mode = pygame.display.get_desktop_display_mode(0) # type: ignore
        refresh_rate = float(getattr(mode, "refresh_rate", 0) or 0)
        if refresh_rate > 0:
            return max(1, int(round(refresh_rate)))
    except (AttributeError, pygame.error, TypeError, ValueError):
        pass
    return 60


def init_display():
    global ctx, prog, vao, tex_map, tex_light, tex_palA, tex_palB, tex_wallArr, tex_hasTex
    global tex_bbTex, overlay_prog, overlay_vao
    ctx = None
    pygame.init()
    resize_window(WIDTH, HEIGHT)
    pygame.display.set_caption("Raycasting FPS GPU")
    ctx = create_gl_context()
    ctx.viewport = (0, 0, WIDTH, HEIGHT)
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

    overlay_vert = """
#version 330 core
in vec2 in_pos;
in vec2 in_uv;
out vec2 uv;
void main() {
    uv = in_uv;
    gl_Position = vec4(in_pos, 0.0, 1.0);
}
"""
    overlay_frag = """
#version 330 core
in vec2 uv;
out vec4 outColor;
uniform sampler2D u_tex;
void main() {
    outColor = texture(u_tex, uv);
}
"""
    overlay_prog = ctx.program(vertex_shader=overlay_vert, fragment_shader=overlay_frag)
    overlay_vbo = ctx.buffer(verts.tobytes())
    overlay_vao = ctx.vertex_array(overlay_prog, overlay_vbo, "in_pos", "in_uv")

    global bb_prog, bb_vao, bb_inst_buf, cross_prog, cross_vao
    bb_prog = ctx.program(vertex_shader=BB_VERT, fragment_shader=BB_FRAG)
    bb_inst_buf = ctx.buffer(reserve=MAX_BILLBOARD_INSTANCES * 6 * 14 * 4)
    bb_vao = ctx.vertex_array(
        bb_prog,
        [(bb_inst_buf, "2f 4f 4f 4f", "in_corner", "in_a", "in_b", "in_c")],
    )

    cross_prog = ctx.program(vertex_shader=VERT, fragment_shader=CROSS_FRAG)
    cross_vao = ctx.vertex_array(cross_prog, ctx.buffer(verts.tobytes()), "in_pos", "in_uv")

    tex_map = tex_light = tex_palA = tex_palB = tex_wallArr = tex_hasTex = None
    tex_bbTex = None
    init_fbo()
    upload_textures()


TEXTURE_LAYERS = WALL_MAX


def init_fbo():
    global fbo, fbo_color, fbo_depth
    assert ctx is not None
    if fbo_color is not None:
        fbo_color.release()
    if fbo_depth is not None:
        fbo_depth.release()
    if fbo is not None:
        fbo.release()
    fbo_color = ctx.texture((WIDTH, HEIGHT), 4)
    fbo_color.filter = (moderngl.NEAREST, moderngl.NEAREST)
    fbo_depth = ctx.texture((WIDTH, HEIGHT), 4)
    fbo_depth.filter = (moderngl.NEAREST, moderngl.NEAREST)
    fbo = ctx.framebuffer(color_attachments=[fbo_color, fbo_depth])


def upload_textures():
    global tex_map, tex_light, tex_light_floor, tex_palA, tex_palB, tex_wallArr, tex_hasTex, tex_bbTex, tex_mmFlags
    assert ctx is not None
    if tex_map is not None:
        tex_map.release()
    if tex_light is not None:
        tex_light.release()
    if tex_light_floor is not None:
        tex_light_floor.release()
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

    map_data = np.array(MAP, dtype=np.float32)
    tex_map = ctx.texture((MAP_W, MAP_H), 1, map_data.tobytes(), dtype="f4")
    tex_map.filter = (moderngl.NEAREST, moderngl.NEAREST)

    mm_flags = np.zeros((MAP_H, MAP_W), dtype=np.uint8)
    for y in range(MAP_H):
        for x in range(MAP_W):
            t = MAP[y][x]
            f = 0
            if t == INVISIBLE_WALL:
                f |= 1
            light_t = LIGHT_CELLS.get((x, y))
            if light_t is not None:
                f |= 4
                n = max(1, min(9, light_t - ORB_MIN + 1))
                f |= (n << 4)
            elif is_orb(t):
                f |= 4
            mm_flags[y, x] = f
    for (cx, cy, _tipo) in BILLBOARD_CELLS:
        ix, iy = int(cx), int(cy)
        if 0 <= ix < MAP_W and 0 <= iy < MAP_H:
            if (ix, iy) not in AI_BB_CELLS:
                mm_flags[iy, ix] |= 2
    for (cx, cy, _tipo) in PARTICLE_CELLS:
        ix, iy = int(cx), int(cy)
        if 0 <= ix < MAP_W and 0 <= iy < MAP_H:
            mm_flags[iy, ix] |= 2
    tex_mmFlags = ctx.texture((MAP_W, MAP_H), 1, mm_flags.tobytes(), dtype="f1")
    tex_mmFlags.filter = (moderngl.NEAREST, moderngl.NEAREST)

    if light_grid_np is not None:
        tex_light = ctx.texture((LIGHT_W, LIGHT_H), 3, light_grid_np.tobytes(), dtype="f4")
        tex_light.filter = (moderngl.LINEAR, moderngl.LINEAR)
        tex_light.repeat_x = False
        tex_light.repeat_y = False
    if light_grid_floor_np is not None:
        tex_light_floor = ctx.texture((LIGHT_W, LIGHT_H), 3, light_grid_floor_np.tobytes(), dtype="f4")
        tex_light_floor.filter = (moderngl.LINEAR, moderngl.LINEAR)
        tex_light_floor.repeat_x = False
        tex_light_floor.repeat_y = False

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

    tam = (TEXTURE_SIZE, TEXTURE_SIZE)
    camadas = np.zeros((TEXTURE_LAYERS, tam[1], tam[0], 4), dtype=np.uint8)
    has_tex = np.zeros((256, 1), dtype=np.float32)
    for t, caminho_abs in WALL_TEXTURES.items():
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

    bb_camadas = np.zeros((BILLBOARD_LAYERS, tam[1], tam[0], 4), dtype=np.uint8)
    caminhos_billboards = sorted({caminho for (_, _, caminho, _, _, _, _, _, _, _) in BILLBOARDS})[:BILLBOARD_LAYERS]
    aspects_billboards = [1.0] * BILLBOARD_LAYERS
    for idx, caminho_abs in enumerate(caminhos_billboards):
        arr, aspect = load_asset_image(caminho_abs, tam, contain=True)
        bb_camadas[idx] = arr
        aspects_billboards[idx] = aspect
    tex_bbTex = ctx.texture_array((tam[0], tam[1], BILLBOARD_LAYERS), 4, bb_camadas.tobytes())
    tex_bbTex.filter = (moderngl.LINEAR, moderngl.LINEAR)
    tex_bbTex.repeat_x = False
    tex_bbTex.repeat_y = False
    global _BB_LAYER_BY_PATH, _BB_ASPECT_BY_PATH
    _BB_LAYER_BY_PATH = {c: i for i, c in enumerate(caminhos_billboards)}
    _BB_ASPECT_BY_PATH = {c: aspects_billboards[i] for i, c in enumerate(caminhos_billboards)}


_orb_cache_sig = None


def update_orb_texture():
    """Build/upload the orb light-list texture (uncapped orb count).

    Layout: RGBA32F texture of size (N, 2). Row 0 = (x+0.5, y+0.5, radius, _),
    row 1 = (r, g, b, _) with rgb already scaled like the CPU bake ((c/255)*4).
    Returns the number of orbs. Rebuilt only when the orb set changes.
    """
    global tex_orbs, _orb_cache_sig
    orbs = []
    for y in range(MAP_H):
        for x in range(MAP_W):
            t = LIGHT_CELLS.get((x, y))
            if t is None:
                t = MAP[y][x]
                if not is_orb(t):
                    continue
            cor_hex, raio = LIGHT_ORBS.get(t, ("#ffcc88", 4.0))
            orbs.append((x, y, raio, cor_hex))
    sig = tuple(orbs)
    if sig == _orb_cache_sig and tex_orbs is not None:
        return len(orbs)
    _orb_cache_sig = sig
    n = max(1, len(orbs))
    data = np.zeros((2, n, 4), dtype=np.float32)
    for idx, (x, y, raio, cor_hex) in enumerate(orbs):
        rr, gg, bb = _rgb(cor_hex)
        data[0, idx, 0] = x + 0.5
        data[0, idx, 1] = y + 0.5
        data[0, idx, 2] = raio
        data[1, idx, 0] = (rr / 255.0) * 4.0
        data[1, idx, 1] = (gg / 255.0) * 4.0
        data[1, idx, 2] = (bb / 255.0) * 4.0
    if tex_orbs is None or tex_orbs.width != n:
        if tex_orbs is not None:
            tex_orbs.release()
        assert ctx is not None
        tex_orbs = ctx.texture((n, 2), 4, data.tobytes(), dtype="f4")
        tex_orbs.filter = (moderngl.NEAREST, moderngl.NEAREST)
    else:
        tex_orbs.write(data.tobytes())
    return len(orbs)


def load_map_file(caminho, preserve_position=False):
    global MAP, MAP_W, MAP_H, WALL_COLORS, WALL_TEXTURES, TEXTURE_SIZE, THEME, LIGHT_ORBS, AMBIENT, FOG, LIGHT_RES
    global LIGHT_SOFT_SAMPLES, LIGHT_SOFT_RADIUS, LIGHT_BOUNCE, LIGHT_BOUNCE_RADIUS, LIGHT_BOUNCE_PASSES
    global WIDTH, HEIGHT, FOV, MAX_DEPTH, MOVE_SPEED, RUN_MULTIPLIER, MOUSE_SENS_X
    global MOUSE_SENS_Y, MAX_LOOK_Y, MM, SPAWN, px, py, pangle, look_y
    global BOB_ENABLED, BOB_AMOUNT, BOB_SPEED, bob_phase, bob_amt, bob_intensity
    global BILLBOARDS, WALL_SCALE, LIGHT_CELLS
    global SKY, SKY_TIME, SKY_PAUSED
    global BILLBOARD_CELLS, PARTICLE_CELLS, BB_AI, AI_BB_CELLS
    global GAME_OVER, GAME_OVER_START, BB_SOUND
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
    BOB_ENABLED = cfg["bob_enabled"]
    BOB_AMOUNT = cfg["bob_amount"]
    BOB_SPEED = cfg["bob_speed"]
    FOG = cfg["fog"]
    AMBIENT = cfg["ambient"]
    LIGHT_RES = cfg["light_res"]
    LIGHT_SOFT_SAMPLES = cfg["light_soft_samples"]
    LIGHT_SOFT_RADIUS = cfg["light_soft_radius"]
    LIGHT_BOUNCE = cfg["light_bounce"]
    LIGHT_BOUNCE_RADIUS = cfg["light_bounce_radius"]
    LIGHT_BOUNCE_PASSES = cfg["light_bounce_passes"]
    TEXTURE_SIZE = cfg["texture_size"]
    WALL_SCALE = cfg["wall_scale"]

    MAP = [row[:] for row in data["map"]]
    MAP_W = len(MAP[0])
    MAP_H = len(MAP)
    _DIST_GRID_CACHE.clear()
    _DIST_AVOID_CACHE.clear()
    _WALL_COUNT_CACHE.clear()
    _SND_WALL_CACHE.clear()
    WALL_COLORS = data["colors"]
    WALL_TEXTURES = data["textures"]
    THEME = dict(THEME_DEFAULTS)
    THEME.update(data["theme"])
    THEME["title"] = data["title"] or THEME["title"]
    LIGHT_ORBS = data["lights"]
    SKY = data["sky"]
    SKY_TIME = SKY["start_time"]
    SKY_PAUSED = False
    SPAWN = data["spawn"]
    if not preserve_position:
        px, py, pangle = SPAWN
        look_y = 0
        bob_phase = 0.0
        bob_amt = 0.0
        bob_intensity = 0.0
    BILLBOARDS = data["billboards"]
    BILLBOARD_CELLS = data["billboard_cells"]
    PARTICLE_CELLS = data["particle_cells"]
    LIGHT_CELLS = data["light_cells"]
    BB_AI = data["bb_ai"]
    AI_BB_CELLS = data["ai_cells"]
    GAME_OVER = False
    GAME_OVER_START = 0.0

    big_map = (MAP_W * MAP_H) >= LOADING_SCREEN_THRESHOLD_CELLS
    progress_cb = None
    if big_map:
        progress_cb = _make_progress_drawer(WIDTH, HEIGHT, f"Carregando {os.path.basename(caminho)}")
    compute_light_grid(on_progress=progress_cb)
    resize_window(WIDTH, HEIGHT)
    upload_textures()
    BB_SOUND = data["bb_sounds"]
    start_billboard_sounds(BB_SOUND)
    print(f"Mapa: {data['info'].get('name', caminho)}", flush=True)


# ══ LOOP PRINCIPAL ═════════════════════════════════════════════
def draw_game_over_overlay():
    assert ctx is not None
    assert overlay_prog is not None
    assert overlay_vao is not None
    surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    surf.fill((0, 0, 0, 180))
    font_big = pygame.font.SysFont(None, 96)
    font_small = pygame.font.SysFont(None, 28)
    t = font_big.render("GAME OVER", True, (220, 60, 60))
    sub = font_small.render("Reiniciando o mapa...", True, (220, 220, 220))
    surf.blit(t, ((WIDTH - t.get_width()) // 2, (HEIGHT - t.get_height()) // 2 - 20))
    surf.blit(sub, ((WIDTH - sub.get_width()) // 2, (HEIGHT - t.get_height()) // 2 + 60))
    data = pygame.image.tobytes(surf, "RGBA", True)
    tex = ctx.texture((WIDTH, HEIGHT), 4, data)
    tex.use(0)
    overlay_prog["u_tex"] = 0
    overlay_vao.render(mode=moderngl.TRIANGLES)
    tex.release()


def reset_after_game_over():
    global px, py, pangle, look_y, bob_phase, bob_amt, bob_intensity
    px, py, pangle = SPAWN
    look_y = 0
    bob_phase = 0.0
    bob_amt = 0.0
    bob_intensity = 0.0
    for idx, ai in enumerate(BB_AI):
        ai["x"] = ai["spawn_x"]
        ai["y"] = ai["spawn_y"]
        ai["rx"] = ai["spawn_x"]
        ai["ry"] = ai["spawn_y"]
        ai["state"] = "IDLE"
        old = BILLBOARDS[idx]
        BILLBOARDS[idx] = (ai["rx"], ai["ry"], old[2], old[3], old[4], old[5], old[6], old[7], old[8], old[9])


def main():
    global px, py, pangle, look_y
    global bob_phase, bob_amt, bob_intensity
    global SKY_TIME, SKY_PAUSED
    global GAME_OVER, GAME_OVER_START, BB_AI

    caminho = None
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        caminho = sys.argv[1]

    compute_light_grid()
    init_display()
    if caminho:
        load_map_file(caminho)
        restore_saved_position(caminho)

    hot_reload_last_check = time_sec()
    hot_reload_seen_stamp = None
    hot_reload_pending_stamp = None
    if caminho:
        try:
            st = os.stat(caminho)
            hot_reload_seen_stamp = (st.st_mtime, st.st_size)
        except OSError:
            pass

    captured = True
    pygame.mouse.set_visible(not captured)
    pygame.event.set_grab(captured)
    pygame.mouse.get_rel()

    clock = pygame.time.Clock()
    running = True
    t_start = time_sec()
    FPS_CAP = max(1, get_monitor_refresh_rate())
    fps_last = time.perf_counter()
    fps_smooth = 0.0

    while running:
        dt = clock.tick(FPS_CAP) / 1000.0
        dt = max(0.0, min(0.1, dt))

        if SKY["enabled"] and SKY["cycle"] and not SKY_PAUSED:
            SKY_TIME = (SKY_TIME + dt * (24.0 / SKY["day_length"])) % 24.0

        if caminho is not None:
            now_check = time_sec()
            if now_check - hot_reload_last_check >= 0.5:
                hot_reload_last_check = now_check
                try:
                    st = os.stat(caminho)
                    stamp = (st.st_mtime, st.st_size)
                except OSError:
                    stamp = None
                if stamp is not None and stamp != hot_reload_seen_stamp:
                    if stamp == hot_reload_pending_stamp:
                        hot_reload_seen_stamp = stamp
                        hot_reload_pending_stamp = None
                        try:
                            save_current_position(caminho)
                            load_map_file(caminho, preserve_position=True)
                            restore_saved_position(caminho)
                        except Exception:
                            import traceback
                            try:
                                log = os.path.join(os.path.dirname(os.path.abspath(__file__)), "erro.log")
                                with open(log, "a", encoding="utf-8") as f:
                                    f.write(f"[hot-reload] falha ao recarregar {caminho}:\n")
                                    traceback.print_exc(file=f)
                            except Exception:
                                pass
                    else:
                        hot_reload_pending_stamp = stamp

        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.DROPFILE:
                if os.path.isfile(getattr(e, "file")):
                    save_current_position(caminho)
                    caminho = getattr(e, "file")
                    load_map_file(caminho)
                    restore_saved_position(caminho)
                    hot_reload_seen_stamp = None
                    hot_reload_pending_stamp = None
                    try:
                        st = os.stat(caminho)
                        hot_reload_seen_stamp = (st.st_mtime, st.st_size)
                    except OSError:
                        pass
            elif e.type == pygame.KEYDOWN:
                if getattr(e, "key") == pygame.K_ESCAPE:
                    captured = not captured
                    pygame.mouse.set_visible(not captured)
                    pygame.event.set_grab(captured)
                    pygame.mouse.get_rel()
                elif getattr(e, "key") == pygame.K_r:
                    if caminho is not None:
                        load_map_file(caminho)
                        save_current_position(caminho)
                        hot_reload_pending_stamp = None
                        try:
                            st = os.stat(caminho)
                            hot_reload_seen_stamp = (st.st_mtime, st.st_size)
                        except OSError:
                            pass
                elif getattr(e, "key") == pygame.K_COMMA:
                    SKY_TIME = (SKY_TIME - 0.5) % 24.0
                elif getattr(e, "key") == pygame.K_PERIOD:
                    SKY_TIME = (SKY_TIME + 0.5) % 24.0
                elif getattr(e, "key") == pygame.K_p:
                    SKY_PAUSED = not SKY_PAUSED
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

        moved = False
        intensity = 0.0
        if not GAME_OVER:
            ox, oy = px, py
            nx, ny = px, py
            if keys[pygame.K_w] or keys[pygame.K_UP]:    nx += fdx; ny += fdy
            if keys[pygame.K_s] or keys[pygame.K_DOWN]:  nx -= fdx; ny -= fdy
            if keys[pygame.K_a] or keys[pygame.K_LEFT]:  nx -= sdx; ny -= sdy
            if keys[pygame.K_d] or keys[pygame.K_RIGHT]: nx += sdx; ny += sdy
            intended = math.hypot(nx - ox, ny - oy)

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
                bob_phase = 0.0
                bob_amt = 0.0
                bob_intensity = 0.0
            actual = math.hypot(px - ox, py - oy)
            if intended > 1e-9:
                intensity = min(1.0, actual / intended)
            moved = intensity > 0.0

        # ══ ANDADA REALISTA (head bob vertical) ══
        bob_intensity += (intensity - bob_intensity) * min(1.0, dt * 8.0)
        sprinting = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        if BOB_ENABLED and bob_intensity > 0.02:
            bob_phase += BOB_SPEED * dt * (RUN_MULTIPLIER if sprinting else 1.0) * bob_intensity
            bob_amt += (BOB_AMOUNT * bob_intensity - bob_amt) * min(1.0, dt * 10.0)
        else:
            bob_amt += (0.0 - bob_amt) * min(1.0, dt * 10.0)
        bob_offset = math.sin(bob_phase) * bob_amt

        # ══ ATUALIZAÇÃO DA IA DOS BILLBOARDS (FSM + PATHFINDING) ══
        if not GAME_OVER and BB_AI:
            def get_dist_grid(tx, ty):
                return compute_dist_grid(tx, ty)

            for idx, ai in enumerate(BB_AI):
                if ai["ai"] == AI_NONE:
                    continue
                bx, by = ai["x"], ai["y"]
                eudist = math.hypot(px - bx, py - by)
                if ai["ai"] == AI_FRIENDLY:
                    if eudist > 1.2:
                        ai["state"] = "FOLLOW"
                        bx, by = _step_ai(bx, by, get_dist_grid(px, py), ai["speed"] * (dt * 60.0))
                    else:
                        ai["state"] = "STAY_CLOSE"
                else:
                    if eudist < 0.5:
                        ai["state"] = "GAME_OVER_TRIGGER"
                        GAME_OVER = True
                        GAME_OVER_START = time_sec()
                    else:
                        ai["state"] = "CHASE"
                        if eudist < 1.0:
                            bx, by = _step_toward(bx, by, px, py, ai["speed"] * (dt * 60.0))
                        else:
                            # ══ Alvo tático por papel (Blinky/Inky/Pinky) ══
                            role = ai["role"]
                            avoid_bkx = avoid_bky = None
                            if ai["blinky_idx"] is not None:
                                avoid_bkx = BB_AI[ai["blinky_idx"]]["x"]
                                avoid_bky = BB_AI[ai["blinky_idx"]]["y"]
                            if role == 1 and avoid_bkx is not None:
                                # INKY: espelha o vetor Blinky→jogador para além do jogador (flanqueia pelo lado oposto).
                                tx = px + (px - avoid_bkx)
                                ty = py + (py - avoid_bky) # type: ignore
                            elif role == 2:
                                # PINKY: mira alguns tiles à frente da direção que o jogador está olhando/andando.
                                tx = px + math.cos(pangle) * 3.5
                                ty = py + math.sin(pangle) * 3.5
                            else:
                                # BLINKY (role 0) ou fallback: persegue direto.
                                tx, ty = px, py
                            tx = max(0.5, min(MAP_W - 0.5, tx))
                            ty = max(0.5, min(MAP_H - 0.5, ty))
                            if role == 2 and avoid_bkx is not None:
                                dg = compute_dist_grid_avoiding(
                                    tx, ty, avoid_bkx, avoid_bky,
                                    avoid_radius=2.0, avoid_penalty=6.0,
                                )
                            else:
                                dg = get_dist_grid(tx, ty)
                            ccx, ccy = int(bx), int(by)
                            if not (0 <= ccx < MAP_W and 0 <= ccy < MAP_H) or dg[ccy][ccx] >= 999999:
                                dg = get_dist_grid(px, py)
                            bx, by = _step_ai(bx, by, dg, ai["speed"] * (dt * 60.0))
                ai["x"], ai["y"] = bx, by
                
                smooth = 1.0 - math.exp(-6.0 * dt)
                ai["rx"] += (bx - ai["rx"]) * smooth
                ai["ry"] += (by - ai["ry"]) * smooth

                old = BILLBOARDS[idx]
                BILLBOARDS[idx] = (ai["rx"], ai["ry"], old[2], old[3], old[4], old[5], old[6], old[7], old[8], old[9])

        if not GAME_OVER:
            update_billboard_sounds(px, py, pangle)

        aspect = (WIDTH / HEIGHT) if HEIGHT else 1.0
        plane_len = math.tan(FOV / 2) * aspect
        plane_x = -math.sin(pangle) * plane_len
        plane_y = math.cos(pangle) * plane_len
        prog["u_res"] = (WIDTH, HEIGHT)
        prog["u_pos"] = (px, py)
        prog["u_dir"] = (math.cos(pangle), math.sin(pangle))
        prog["u_plane"] = (plane_x, plane_y)
        prog["u_mapSize"] = (MAP_W, MAP_H)
        prog["u_horizon"] = HEIGHT * 0.5 + look_y + bob_offset
        prog["u_scale"] = (HEIGHT / (2.0 * math.tan(FOV / 2))) * WALL_SCALE
        prog["u_ambient"] = AMBIENT
        prog["u_fog"] = FOG
        prog["u_depth"] = float(MAX_DEPTH)
        prog["u_wallMax"] = float(WALL_MAX)
        prog["u_orbMin"] = float(ORB_MIN)

        sun_angle = ((SKY_TIME - 12.0) / 24.0) * 2.0 * math.pi
        sun_time_angle = ((SKY_TIME - 6.0) / 24.0) * 2.0 * math.pi
        sun_elev = math.sin(sun_time_angle) * math.sin(math.radians(SKY["sun_peak"]))
        day_factor = max(0.0, min(1.0, sun_elev / max(math.sin(math.radians(SKY["sun_peak"])), 1e-4))) if SKY["enabled"] else 1.0
        night_factor = 1.0 - day_factor

        sb = [_rgb(THEME["sky_base"])[i] / 255.0 for i in range(3)]
        st = [_rgb(THEME["sky_top"])[i] / 255.0 for i in range(3)]
        if SKY["enabled"]:
            nb = [_rgb(NIGHT_SKY_BASE)[i] / 255.0 for i in range(3)]
            nt = [_rgb(NIGHT_SKY_TOP)[i] / 255.0 for i in range(3)]
            sb = [nb[i] + (sb[i] - nb[i]) * day_factor for i in range(3)]
            st = [nt[i] + (st[i] - nt[i]) * day_factor for i in range(3)]
        fb = [_rgb(THEME["floor_base"])[i] / 255.0 for i in range(3)]
        ft = [_rgb(THEME["floor_top"])[i] / 255.0 for i in range(3)]
        cr = [_rgb(THEME["crosshair"])[i] / 255.0 for i in range(3)]
        mp = [_rgb(THEME["minimap_player"])[i] / 255.0 for i in range(3)]
        prog["u_skyB"] = tuple(sb)
        prog["u_skyT"] = tuple(st)
        prog["u_skyBodies"] = 1.0 if SKY["enabled"] else 0.0
        prog["u_sunAngle"] = sun_angle
        prog["u_sunElev"] = sun_elev
        prog["u_nightFactor"] = night_factor
        prog["u_starsCount"] = float(SKY["stars"])
        prog["u_sunColor"] = tuple(c / 255.0 for c in _rgb(SKY["sun_color"]))
        prog["u_moonColor"] = tuple(c / 255.0 for c in _rgb(SKY["moon_color"]))
        prog["u_floorB"] = tuple(fb)
        prog["u_floorT"] = tuple(ft)
        prog["u_mmPlayer"] = tuple(mp)

        mm_cell = max(1, MM // max(MAP_W, MAP_H))
        mm_w = MAP_W * mm_cell
        mm_h = MAP_H * mm_cell
        mm_x = WIDTH - mm_w - 10
        mm_y = 10
        dir_x, dir_y = math.cos(pangle), math.sin(pangle)
        invDet = 1.0 / (plane_x * dir_y - dir_x * plane_y)
        frustum_margin = 1.2
        visible_bbs = []
        _px, _py = px, py
        _plane_x, _plane_y = plane_x, plane_y
        _dir_x, _dir_y = dir_x, dir_y
        _invDet = invDet
        _maxd = MAX_DEPTH
        for bb in BILLBOARDS:
            bx, by = bb[0], bb[1]
            spx = bx - _px
            spy = by - _py
            tx = _invDet * (_dir_y * spx - _dir_x * spy)
            ty = _invDet * (-_plane_y * spx + _plane_x * spy)
            if 0.01 < ty <= _maxd and abs(tx) <= ty * frustum_margin:
                visible_bbs.append(bb)
        if visible_bbs:
            if len(visible_bbs) > 16:
                d2 = np.array([(b[0]-_px)*(b[0]-_px)+(b[1]-_py)*(b[1]-_py) for b in visible_bbs], dtype=np.float32)
                order = np.argsort(d2)[::-1]
                visible_bbs = [visible_bbs[i] for i in order]
            else:
                visible_bbs.sort(key=lambda b: -((b[0]-_px)*(b[0]-_px)+(b[1]-_py)*(b[1]-_py)))
        bb_instances = visible_bbs[:MAX_BILLBOARD_INSTANCES]
        bb_pos = [(0.0, 0.0)] * MAX_BILLBOARD_INSTANCES
        bb_layer = [0.0] * MAX_BILLBOARD_INSTANCES
        bb_yoff = [0.0] * MAX_BILLBOARD_INSTANCES
        bb_aspect = [1.0] * MAX_BILLBOARD_INSTANCES
        bb_scale = [1.0] * MAX_BILLBOARD_INSTANCES
        bb_amp = [0.0] * MAX_BILLBOARD_INSTANCES
        bb_vel = [0.0] * MAX_BILLBOARD_INSTANCES
        bb_phase = [0.0] * MAX_BILLBOARD_INSTANCES
        bb_ai_type = [0.0] * MAX_BILLBOARD_INSTANCES
        for idx, (bx, by, caminho_abs, yoff, escala, amp, vel, fase, _ai, _sp) in enumerate(bb_instances):
            bb_pos[idx] = (bx, by)
            bb_layer[idx] = float(_BB_LAYER_BY_PATH.get(caminho_abs, 0))
            bb_yoff[idx] = yoff
            bb_aspect[idx] = float(_BB_ASPECT_BY_PATH.get(caminho_abs, 1.0))
            bb_scale[idx] = escala
            bb_amp[idx] = amp
            bb_vel[idx] = vel
            bb_phase[idx] = fase
            if idx < len(BB_AI):
                ai = BB_AI[idx]["ai"]
                bb_ai_type[idx] = 2.0 if ai == AI_ENEMY else (1.0 if ai == AI_FRIENDLY else 0.0)
        prog["u_bbCount"] = len(bb_instances)
        prog["u_bbA"] = [
            (bb_pos[i][0], bb_pos[i][1], bb_layer[i], bb_yoff[i])
            for i in range(MAX_BILLBOARD_INSTANCES)
        ]
        prog["u_bbC"] = [
            (bb_phase[i], bb_ai_type[i], 0.0, 0.0)
            for i in range(MAX_BILLBOARD_INSTANCES)
        ]

        prog["u_mmPos"] = (mm_x, mm_y)
        prog["u_mmSize"] = (mm_w, mm_h)
        prog["u_mmCell"] = float(mm_cell)
        prog["u_playerPix"] = (mm_x + px * mm_cell, mm_y + py * mm_cell)
        mm_dir_dist = max(0.9, 6.0 / mm_cell)
        prog["u_dirPix"] = (mm_x + (px + math.cos(pangle) * mm_dir_dist) * mm_cell,
                                  mm_y + (py + math.sin(pangle) * mm_dir_dist) * mm_cell)

        assert tex_map is not None
        tex_map.use(0)
        if tex_light is not None:
            tex_light.use(1)
        assert tex_palA is not None
        tex_palA.use(2)
        assert tex_palB is not None
        tex_palB.use(3)
        assert tex_wallArr is not None
        tex_wallArr.use(4)
        assert tex_hasTex is not None
        tex_hasTex.use(5)
        if tex_mmFlags is not None:
            tex_mmFlags.use(7)
        orb_count = update_orb_texture()
        if tex_light_floor is not None:
            tex_light_floor.use(6)
        if tex_orbs is not None:
            tex_orbs.use(8)
        prog["u_map"] = 0
        prog["u_light"] = 1
        prog["u_palA"] = 2
        prog["u_palB"] = 3
        prog["u_wallTex"] = 4
        prog["u_hasTex"] = 5
        prog["u_mmFlags"] = 7
        prog["u_light_floor"] = 6
        prog["u_orbs"] = 8
        prog["u_orbCount"] = orb_count

        assert fbo is not None and ctx is not None
        ctx.viewport = (0, 0, WIDTH, HEIGHT)
        fbo.use()
        vao.render(mode=moderngl.TRIANGLES)
        ctx.screen.use()

        assert overlay_prog is not None and overlay_vao is not None
        assert fbo_color is not None
        fbo_color.use(0)
        overlay_prog["u_tex"] = 0
        overlay_vao.render(mode=moderngl.TRIANGLES)

        assert bb_prog is not None and bb_vao is not None and bb_inst_buf is not None
        bb_count = len(bb_instances)
        if bb_count > 0:
            if bb_count > 1:
                d2 = [(bb_instances[i][0]-px)*(bb_instances[i][0]-px)+(bb_instances[i][1]-py)*(bb_instances[i][1]-py) for i in range(bb_count)]
                order = sorted(range(bb_count), key=lambda i: -d2[i])
            else:
                order = [0]
            bb_vert = _BB_VERT_POOL
            CORN = _BB_CORN
            for slot, i in enumerate(order):
                bx, by, caminho_abs, yoff, escala, amp, vel, fase, _ai, _sp = bb_instances[i]
                layer = float(_BB_LAYER_BY_PATH.get(caminho_abs, 0))
                aspect = float(_BB_ASPECT_BY_PATH.get(caminho_abs, 1.0))
                ai = bb_ai_type[i]
                base = slot * 6
                bb_vert[base:base + 6, 0:2] = CORN
                bb_vert[base:base + 6, 2] = bx
                bb_vert[base:base + 6, 3] = by
                bb_vert[base:base + 6, 4] = layer
                bb_vert[base:base + 6, 5] = yoff
                bb_vert[base:base + 6, 6] = escala
                bb_vert[base:base + 6, 7] = aspect
                bb_vert[base:base + 6, 8] = amp
                bb_vert[base:base + 6, 9] = vel
                bb_vert[base:base + 6, 10] = fase
                bb_vert[base:base + 6, 11] = ai
            bb_inst_buf.write(bb_vert[:bb_count * 6].tobytes())
        bb_prog["u_res"] = (WIDTH, HEIGHT)
        bb_prog["u_pos"] = (px, py)
        bb_prog["u_dir"] = (math.cos(pangle), math.sin(pangle))
        bb_prog["u_plane"] = (plane_x, plane_y)
        bb_prog["u_horizon"] = HEIGHT * 0.5 + look_y + bob_offset
        bb_prog["u_scale"] = (HEIGHT / (2.0 * math.tan(FOV / 2))) * WALL_SCALE
        bb_prog["u_time"] = time_sec() - t_start
        bb_prog["u_mapSize"] = (MAP_W, MAP_H)
        bb_prog["u_ambient"] = AMBIENT
        bb_prog["u_fog"] = FOG
        bb_prog["u_depth"] = float(MAX_DEPTH)
        assert tex_bbTex is not None
        tex_bbTex.use(6)
        assert fbo_depth is not None
        fbo_depth.use(7)
        if tex_map is not None:
            tex_map.use(8)
        if tex_light_floor is not None:
            tex_light_floor.use(9)
        if tex_orbs is not None:
            tex_orbs.use(10)
        bb_prog["u_bbTex"] = 6
        bb_prog["u_wallDepth"] = 7
        bb_prog["u_map"] = 8
        bb_prog["u_light_floor"] = 9
        bb_prog["u_orbs"] = 10
        bb_prog["u_orbCount"] = orb_count
        if bb_count > 0:
            bb_vao.render(mode=moderngl.TRIANGLES, vertices=bb_count * 6)

        assert cross_prog is not None and cross_vao is not None
        cross_prog["u_res"] = (WIDTH, HEIGHT)
        cross_prog["u_cross"] = tuple(cr)
        cross_vao.render(mode=moderngl.TRIANGLES)

        if GAME_OVER:
            draw_game_over_overlay()
            if time_sec() - GAME_OVER_START >= 2.0:
                reset_after_game_over()
                GAME_OVER = False

        pygame.display.flip()

        now_perf = time.perf_counter()
        frame_dt = now_perf - fps_last
        fps_last = now_perf
        if frame_dt > 0:
            inst = 1.0 / frame_dt
            fps_smooth += (inst - fps_smooth) * 0.1
        pygame.display.set_caption(f"Raycasting FPS GPU — {fps_smooth:.0f} fps")

    pygame.quit()


def time_sec():
    import time
    return time.perf_counter()


MAX_RESTART_ATTEMPTS = 3
_RESTART_ENV_VAR = "RC_RESTART_COUNT"


def format_smart_traceback(exc_type, exc, tb):
    import traceback

    this_file = os.path.abspath(__file__)
    frames = traceback.extract_tb(tb)
    frames_locais = [f for f in frames if os.path.abspath(f.filename) == this_file]
    frame_culpado = frames_locais[-1] if frames_locais else (frames[-1] if frames else None)

    # ── Dicionário de tradução: tipo de exceção → explicação amigável ──
    def explicar():
        nome_arq = getattr(exc, "filename", None)
        if isinstance(exc, FileNotFoundError):
            alvo = f' ("{os.path.basename(nome_arq)}")' if nome_arq else ""
            return f"Um arquivo necessário não foi encontrado{alvo}."
        if isinstance(exc, PermissionError):
            alvo = f' ("{os.path.basename(nome_arq)}")' if nome_arq else ""
            return f"Não foi possível acessar um arquivo{alvo} por falta de permissão."
        if isinstance(exc, IsADirectoryError):
            return "Uma pasta foi usada onde se esperava um arquivo."
        if isinstance(exc, (ZeroDivisionError,)):
            return "Uma conta internamente tentou dividir um valor por zero."
        if isinstance(exc, KeyError):
            chave = exc.args[0] if exc.args else "?"
            return f'Uma configuração ou dado esperado ("{chave}") não foi encontrado.'
        if isinstance(exc, IndexError):
            return "O motor tentou acessar um item de uma lista que não existe (posição fora do intervalo)."
        if isinstance(exc, AttributeError):
            return "Uma parte do código tentou usar um recurso que não estava disponível no momento."
        if isinstance(exc, TypeError):
            return "Um tipo de dado incompatível foi usado em algum cálculo ou função."
        if isinstance(exc, ValueError):
            return "Um valor inválido ou fora do esperado foi fornecido em algum lugar."
        if isinstance(exc, ImportError):
            modulo = getattr(exc, "name", None)
            alvo = f' ("{modulo}")' if modulo else ""
            return f"Uma biblioteca necessária{alvo} não pôde ser carregada."
        if isinstance(exc, MemoryError):
            return "O computador ficou sem memória suficiente para continuar."
        if isinstance(exc, RecursionError):
            return "O motor entrou em um loop de chamadas que nunca terminava."
        if isinstance(exc, OSError):
            return "Ocorreu um problema de sistema (arquivo, tela ou dispositivo)."
        return "Ocorreu um erro inesperado durante a execução."

    explicacao = explicar()

    linhas = ["Algo deu errado e o motor precisou parar."]
    linhas.append("")

    if frame_culpado:
        nome_funcao = frame_culpado.name.replace("_", " ")
        if nome_funcao == "modulo":
            local_amigavel = "logo no início do motor"
        else:
            local_amigavel = f'na parte responsável por "{nome_funcao}"'
        linhas.append(f"{explicacao} Isso aconteceu {local_amigavel}, na linha {frame_culpado.lineno} do motor.")
    else:
        linhas.append(explicacao)

    return "\n".join(linhas)

if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback

        exc_type, exc_value, exc_tb = sys.exc_info()

        # 1. Salvar o traceback completo (cru) em erro.log — sem perder detalhe algum
        try:
            log = os.path.join(os.path.dirname(os.path.abspath(__file__)), "erro.log")
            with open(log, "w", encoding="utf-8") as f:
                traceback.print_exc(file=f)
        except Exception:
            pass

        # Resumo inteligente: só o que importa para diagnosticar rápido
        try:
            resumo = format_smart_traceback(exc_type, exc_value, exc_tb)
        except Exception:
            resumo = traceback.format_exc().strip()

        # 2. Fechar o contexto gráfico (Pygame/OpenGL) com segurança
        try:
            pygame.quit()
        except Exception:
            pass

        attempt = int(os.environ.get(_RESTART_ENV_VAR, "0")) + 1
        pode_reiniciar = attempt <= MAX_RESTART_ATTEMPTS

        # 3. Exibir popup nativo do sistema, independente do estado da janela do motor
        try:
            import tkinter as tk
            import subprocess
            import platform

            def abrir_erro_log(_evento=None):
                try:
                    caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "erro.log")
                    sistema = platform.system()
                    if sistema == "Windows":
                        os.startfile(caminho)  # type: ignore[attr-defined]
                    elif sistema == "Darwin":
                        subprocess.Popen(["open", caminho])
                    else:
                        subprocess.Popen(["xdg-open", caminho])
                except Exception:
                    pass

            if pode_reiniciar:
                titulo = "Ops! O motor travou 🙁"
                corpo = (
                    f"{resumo}\n\n"
                    f"Não se preocupe — o motor vai reiniciar sozinho agora "
                    f"(tentativa {attempt} de {MAX_RESTART_ATTEMPTS})."
                )
            else:
                titulo = "O motor não conseguiu se recuperar 😔"
                corpo = (
                    f"{resumo}\n\n"
                    f"Já tentamos reiniciar {MAX_RESTART_ATTEMPTS} vezes e o problema "
                    "continua acontecendo, então o motor vai ficar fechado por agora."
                )

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)

            janela = tk.Toplevel(root)
            janela.title(titulo)
            janela.resizable(False, False)
            janela.attributes("-topmost", True)
            janela.configure(bg="#f0f0f0", padx=24, pady=20)

            tk.Label(
                janela, text=titulo, font=("Segoe UI", 12, "bold"),
                bg="#f0f0f0", justify="left", anchor="w",
            ).pack(fill="x")

            tk.Label(
                janela, text=corpo, font=("Segoe UI", 10),
                bg="#f0f0f0", justify="left", anchor="w", wraplength=420,
            ).pack(fill="x", pady=(10, 4))

            linha_log = tk.Frame(janela, bg="#f0f0f0")
            linha_log.pack(fill="x", pady=(0, 14))
            tk.Label(
                linha_log, text="Detalhes técnicos salvos em:",
                font=("Segoe UI", 10), bg="#f0f0f0",
            ).pack(side="left")
            link = tk.Label(
                linha_log, text="erro.log", font=("Segoe UI", 10, "underline"),
                bg="#f0f0f0", fg="#1a73e8", cursor="hand2",
            )
            link.pack(side="left", padx=(4, 0))
            link.bind("<Button-1>", abrir_erro_log)

            tk.Button(
                janela, text="OK", width=10, command=janela.destroy,
            ).pack(anchor="e")

            janela.protocol("WM_DELETE_WINDOW", janela.destroy)
            janela.update_idletasks()
            largura = janela.winfo_width()
            altura = janela.winfo_height()
            x = (janela.winfo_screenwidth() - largura) // 2
            y = (janela.winfo_screenheight() - altura) // 2
            janela.geometry(f"+{x}+{y}")

            janela.grab_set()
            root.wait_window(janela)
            root.destroy()
        except Exception:
            pass

        # 4. Reiniciar a engine do zero, até MAX_RESTART_ATTEMPTS vezes
        if pode_reiniciar:
            try:
                python = sys.executable
                env = os.environ.copy()
                env[_RESTART_ENV_VAR] = str(attempt)
                os.execve(python, [python] + sys.argv, env)
            except Exception:
                raise
        else:
            raise
