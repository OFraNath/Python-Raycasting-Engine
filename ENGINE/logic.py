# Núcleo lógico — dono do estado do jogo.
#
# Possui o estado global (mapa, jogador, iluminação, céu, configuração),
# o mapa de boot (placeholder sem .rcfg), os helpers de jogo (colisão,
# linha-de-sight, cache de posição) e a matemática da grade de luz.
# Os núcleos vizinhos (loader/render) acessam o estado AQUI; este módulo
# não importa nenhum dos dois — é a base do grafo de dependências.
import math
import os

import numpy as np


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
    "wall_scale": 1.0,
}

ORB_MIN = 7
WALL_MAX = 6

# Formato LEGADO (compatível com mapas antigos): dígitos 0-9 direto.
#   0 = vazio, 1-6 = parede, 7+ = luz (ORB_MIN_LEGADO)
WALL_MAX_LEGADO = 6
ORB_MIN_LEGADO = 7

# Formato NOVO (Fase 4): luz vira letra "L" em vez de dígito, o que libera
# os dígitos 7, 8 e 9 pra serem usados como paredes/texturas extras.
#   0 = vazio, 1-9 = parede, "L1".."L9" = luz, "B1".."B9" = billboard
WALL_MAX_NOVO = 9
ORB_MIN_NOVO = 100  # offset interno alto, só pra não colidir com paredes 1-9

# Parede invisível ("N" no [MAP]): bloqueia o jogador (is_wall) mas fica fora da
# faixa 1..WALL_MAX que o shader testa pra desenhar/colidir com o raio — então
# nunca é renderizada nem aparece no minimapa. Um único tipo, sem cor/textura.
# Valor 99: fica no vão livre entre WALL_MAX_NOVO (9) e ORB_MIN_NOVO (100), então
# também não é confundido com luz/orb pelo shader (que testa "t >= u_orbMin").
INVISIBLE_WALL = 99


def _split_map_token(tok):
    # Divide um token do [MAP] em (base, extras) — PLANO.md item 4: célula
    # aceita "base[+extra...]", onde extra é "L#"/"B#"/"P#". Um token que já
    # COMEÇA com L/B/P (formato antigo, sem "+", ex. "L1" sozinho) é tratado
    # como extra isolado com base implícita "0" — retrocompatível.
    partes = tok.split("+")
    base = partes[0]
    extras = partes[1:]
    up_base = base.upper()
    if len(up_base) >= 2 and up_base[0] in ("L", "B", "P") and up_base[1:].isdigit():
        extras = [base] + extras
        base = "0"
    return base, extras


def _process_map_tokens(raw_rows):
    # Detecta automaticamente se o mapa usa o formato novo (com L/B/P/N/"+")
    # ou o legado (só dígitos) — assim mapas antigos continuam funcionando
    # exatamente como antes, sem precisar de nenhuma migração manual.
    is_new_format = False
    for row in raw_rows:
        for tok in row:
            base, extras = _split_map_token(tok)
            if extras or base.upper() == "N":
                is_new_format = True
                break
        if is_new_format:
            break
    wall_max = WALL_MAX_NOVO if is_new_format else WALL_MAX_LEGADO
    orb_min = ORB_MIN_NOVO if is_new_format else ORB_MIN_LEGADO

    grid = []
    billboards = []  # lista de (x_central, y_central, tipo)
    particles = []   # lista de (x_central, y_central, tipo) — mesmo padrão de billboards
    light_cells = {}  # (x, y) -> valor de luz codificado (orb_min + n - 1)
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
                    light_cells[(i, j)] = orb_min + (n - 1)
                elif letra == "B":
                    billboards.append((i + 0.5, j + 0.5, n))
                else:
                    particles.append((i + 0.5, j + 0.5, n))
        grid.append(int_row)
    return grid, billboards, particles, light_cells, wall_max, orb_min, is_new_format


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
# Placeholder da tela sem .rcfg carregado. Usa o mesmo tokenizer de qualquer
# mapa real (token "L1" em vez do dígito legado "7") — assim a luz cai em
# LIGHT_CELLS e ganha cor certa tanto no minimapa quanto na cena 3D (ver
# BOOT_LIGHT_ORBS abaixo), sem precisar de um caminho de código à parte.
(BOOT_MAP, _boot_bb, _boot_particles, BOOT_LIGHT_CELLS,
 BOOT_WALL_MAX, BOOT_ORB_MIN, _boot_is_new) = _process_map_tokens(BOOT_MAP_TOKENS)
BOOT_LIGHT_ORBS = {BOOT_ORB_MIN: ("#ffcc88", 4.0)}  # cor da luz L1 do placeholder

SKY_DEFAULTS = {
    "cycle": False,
    "day_length": 120.0,
    "start_time": 8.0,
    "sun_peak": 45.0,
    "sun_color": "#fff2c0",
    "moon_color": "#b9c6e0",
    "stars": 0,
}

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

# Preset de céu noturno usado no lerp dia/noite (PLANO.md item 2) — mais
# escuro/azulado que o gradiente diurno do [THEME].
NIGHT_SKY_BASE = "#02030f"
NIGHT_SKY_TOP = "#05061f"


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

# ── Céu: sol/lua/estrelas + ciclo dia-noite (PLANO.md item 2) ──
SKY = dict(SKY_DEFAULTS)
SKY["enabled"] = False
SKY_TIME = SKY_DEFAULTS["start_time"]   # 0..24, horas "de jogo"
SKY_PAUSED = False                      # tecla P pausa/retoma o ciclo

MAP = [row[:] for row in BOOT_MAP]
MAP_W = len(MAP[0])
MAP_H = len(MAP)
WALL_COLORS = {}
WALL_TEXTURES = {}   # tipo -> caminho absoluto (resolvido a partir do .rcfg)
TEXTURE_SIZE = DEFAULT_CONFIG["texture_size"]
THEME = dict(THEME_DEFAULTS)
LIGHT_ORBS = dict(BOOT_LIGHT_ORBS)
LIGHT_CELLS = dict(BOOT_LIGHT_CELLS)  # (x, y) -> valor de luz codificado; camada separada da grade (PLANO.md item 4)
ORB_MIN = BOOT_ORB_MIN
WALL_MAX = BOOT_WALL_MAX
LIGHT_RES = DEFAULT_CONFIG["light_res"]
LIGHT_SOFT_SAMPLES = DEFAULT_CONFIG["light_soft_samples"]
LIGHT_SOFT_RADIUS = DEFAULT_CONFIG["light_soft_radius"]
LIGHT_BOUNCE = DEFAULT_CONFIG["light_bounce"]
LIGHT_BOUNCE_RADIUS = DEFAULT_CONFIG["light_bounce_radius"]
LIGHT_BOUNCE_PASSES = DEFAULT_CONFIG["light_bounce_passes"]
WALL_SCALE = DEFAULT_CONFIG["wall_scale"]
light_grid = []
light_grid_np = None
LIGHT_W = MAP_W
LIGHT_H = MAP_H
px, py, pangle, look_y = 1.5, 1.5, 0.0, 0.0
SPAWN = (1.5, 1.5, 0.0)

# ── Billboards (Fase 5): lista de (x, y, caminho_abs_textura, offset_y) ──
BILLBOARDS = []

# ── Tela de carregamento (Fase 2) ──
# Mapas com essa quantidade de células (largura*altura) ou mais mostram uma
# barra de progresso durante o cálculo de iluminação, em vez de travar a
# janela sem feedback nenhum.
LOADING_SCREEN_THRESHOLD_CELLS = 4096  # ex: um mapa 64x64 ou maior

# Cache em memória (não vai pro disco): caminho absoluto do .rcfg -> última
# posição/direção da câmera nele. Vive só enquanto o processo está rodando,
# tipo um "localStorage" da sessão. Ao voltar pra um mapa já visitado nessa
# mesma execução, a câmera reaparece de onde você tinha saído em vez de
# voltar pro SPAWN do arquivo.
MAP_POSITIONS = {}


def _rgb(h):
    return (int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16))


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


def is_orb(c):
    return c >= ORB_MIN


def is_wall(c):
    return (1 <= c <= WALL_MAX) or c == INVISIBLE_WALL


def _blocks_light(c):
    # Só paredes de verdade bloqueiam luz — a parede invisível (99) não é
    # desenhada, então não deve projetar sombra (ver PLANO.md item 1).
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
        if 0 <= icx < MAP_W and 0 <= icy < MAP_H and _blocks_light(MAP[icy][icx]):
            return True
    return False


def compute_light_grid(on_progress=None):
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
                        # comentário acima). Fórmula com núcleo concentrado
                        # (quase constante perto da fonte, cauda em lei de
                        # potência inversa) + corte final suavizado só nos
                        # últimos 25% do raio (PLANO.md item 5) — sombra
                        # mais forte e fading mais natural, sem mudar custo.
                        core = 1.0 / (1.0 + 6.0 * d * d)
                        edge = max(0.0, min(1.0, (1.0 - d) / 0.25))
                        edge = edge * edge * (3.0 - 2.0 * edge)
                        falloff = core * edge * vis_frac
                        if falloff <= 0:
                            continue
                        cell = row[base_col + si]
                        cell[0] += cor_rgb[0] * falloff
                        cell[1] += cor_rgb[1] * falloff
                        cell[2] += cor_rgb[2] * falloff

    # luz direta das tochas/orbes
    # Pesos de progresso: a passada direta costuma dominar o custo total
    # (cresce com nº de luzes x raio^2), então ela recebe 70% da barra; os
    # 30% restantes ficam pros passes de bounce/GI abaixo. Não é uma medida
    # exata de tempo, mas dá um feedback razoável e monotônico pro usuário.
    for y in range(MAP_H):
        for x in range(MAP_W):
            # Formato novo: luz vive em LIGHT_CELLS (camada separada da
            # grade, PLANO.md item 4), o que permite luz coexistir com
            # parede/piso/billboard/partícula na mesma célula. Formato
            # legado continua com a luz codificada direto no valor da
            # grade (dígito >= ORB_MIN) — fallback abaixo preserva isso.
            t = LIGHT_CELLS.get((x, y))
            if t is None:
                t = MAP[y][x]
                if not is_orb(t):
                    continue
            cor_hex, raio = LIGHT_ORBS.get(t, ("#ffcc88", 4.0))
            cor_rgb = tuple((c / 255.0) * 4.0 for c in _rgb(cor_hex))
            add_light(x, y, raio, cor_rgb)
        if on_progress is not None:
            on_progress(0.7 * (y + 1) / MAP_H)

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
                if on_progress is not None:
                    passes = max(1, LIGHT_BOUNCE_PASSES)
                    frac = (passe + (y + 1) / MAP_H) / passes
                    on_progress(0.7 + 0.3 * frac)

    if on_progress is not None:
        on_progress(1.0)

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