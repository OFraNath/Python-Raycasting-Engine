# Núcleo de carregamento — entrada de dados (.rcfg) + feedback de progresso.
#
# Possui todo o parser do formato .rcfg (seções, cores, tema, céu, texturas,
# luzes, billboards, partículas), o carregador de assets de imagem, a tela de
# carregamento e o `load_map_file`, que aplica o .rcfg no estado do jogo
# (núcleo lógico) e dispara o recarregamento das texturas (núcleo gráfico).
import math
import os
import re

import moderngl
import numpy as np
import pygame

from . import logic
from . import render


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
            # Guarda os TOKENS crus (strings) em vez de já converter pra int
            # aqui — os tokens podem ser números (parede/vazio) ou, no novo
            # formato (Fase 4), letras: "L1".."L9" para luzes e "B1".."B9"
            # para billboards. A tradução pra inteiro (o que a engine usa
            # internamente) acontece em _process_map_tokens(), depois que
            # já lemos o mapa inteiro e sabemos se é formato legado ou novo.
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
        return dict(logic.DEFAULT_CONFIG)
    cfg = dict(logic.DEFAULT_CONFIG)
    w, h = d.get("window", "960 560").split()
    cfg["window_width"] = _to_int(w, "WINDOW")
    cfg["window_height"] = _to_int(h, "WINDOW")
    cfg["mm"] = _to_int(d.get("mm", 140), "MM")
    cfg["fov"] = logic.math_radians(_to_float(d.get("fov", 60), "FOV"))
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
    cfg["wall_scale"] = _to_float(d.get("wall_scale", 1.0), "WALL_SCALE")
    return cfg


def _parse_spawn(d, mapa, orb_min):
    w = len(mapa[0])
    h = len(mapa)
    x = _to_float(d.get("x", 1.5), "SPAWN X")
    y = _to_float(d.get("y", 1.5), "SPAWN Y")
    angle = logic.math_radians(_to_float(d.get("angle", 0), "SPAWN ANGLE"))

    def livre(fx, fy):
        ix, iy = int(fx), int(fy)
        v = mapa[iy][ix] if (0 <= ix < w and 0 <= iy < h) else None
        return v is not None and v != logic.INVISIBLE_WALL and (v == 0 or v >= orb_min)

    if not livre(x, y):
        for j in range(h):
            for i in range(w):
                if mapa[j][i] != logic.INVISIBLE_WALL and (mapa[j][i] == 0 or mapa[j][i] >= orb_min):
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


def _parse_sky(d):
    # Seção [SKY] é opcional (PLANO.md item 2): sem ela, sky fica igual ao
    # comportamento atual (só o gradiente do THEME, sem sol/lua/estrelas).
    sky = dict(logic.SKY_DEFAULTS)
    sky["enabled"] = bool(d)
    if not d:
        return sky
    sky["cycle"] = str(d.get("cycle", "false")).strip().lower() in ("1", "true", "yes")
    sky["day_length"] = max(1.0, _to_float(d.get("day_length", 120), "SKY DAY_LENGTH"))
    sky["start_time"] = _to_float(d.get("start_time", 8), "SKY START_TIME") % 24.0
    # sun_peak: maior elevação que o sol atinge ao meio-dia (graus acima do
    # horizonte), default 45. 45 = o arco inteiro (nascer→zênite→pôr) fica
    # visível no viewport olhando reto: o topo da tela cobre ~54.5° no showcase
    # (FOV 70) e ~49° no garden (FOV 60), então um pico de 60 fazia o astro
    # subir para fora da tela no meio-dia (a trajetória parecia "à distância").
    # 90 = zênite (passa exatamente por cima da cabeça — no viewport o astro
    # fica acima da tela mesmo olhando para cima); valores menores deixam o
    # arco mais baixo/raso. A curva de luz do dia (day_factor/night_factor) é
    # normalizada por sin(sun_peak): o meio-dia continua no brilho máximo.
    sky["sun_peak"] = max(10.0, min(90.0, _to_float(d.get("sun_peak", 45), "SKY SUN_PEAK")))
    sky["sun_color"] = _parse_color(d.get("sun_color", "#fff2c0"))
    sky["moon_color"] = _parse_color(d.get("moon_color", "#b9c6e0"))
    sky["stars"] = max(0, _to_int(d.get("stars", 140), "SKY STARS"))
    return sky


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


def _parse_billboards(d, pasta_base):
    # Seção [BILLBOARDS]: "ID caminho/imagem.png offset_y [escala]"
    # offset_y é a distância vertical (unidades de mundo) entre o chão e a
    # base do sprite — 0.0 encosta no chão, valores positivos deixam o
    # sprite "flutuando" a uma altura fixa (ex: pés de um personagem que
    # deve tocar o chão visualmente, mas a imagem tem uma margem embaixo).
    # escala é opcional (default 1.0) — multiplica o tamanho do sprite,
    # que por padrão ocupa 1 unidade de mundo de altura.
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
        billboards[tipo_int] = (os.path.join(pasta_base, caminho_rel), offset_y, escala)
    return billboards


# Amplitude fixa (unidades de mundo) do flutuar vertical das partículas —
# não é exposta no .rcfg de propósito (PLANO.md item 3 só pede caminho,
# quantidade, velocidade e espalhamento por tipo).
PARTICLE_FLOAT_AMPLITUDE = 0.18
PARTICLE_SCALE = 0.35


def _parse_particles(d, pasta_base):
    # Seção [PARTICLES]: "ID caminho/imagem.png quantidade velocidade espalhamento"
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
        particles[tipo_int] = (os.path.join(pasta_base, caminho_rel), max(0, quantidade),
                                velocidade, max(0.0, espalhamento))
    return particles


def _particle_instances(particle_cells, particle_defs):
    # Posição inicial pseudo-aleatória determinística (seed = posição da
    # célula + índice da instância), dentro do raio de espalhamento —
    # mesmo mapa sempre gera as mesmas partículas (PLANO.md item 3).
    out = []
    for (cx, cy, tipo) in particle_cells:
        if tipo not in particle_defs:
            continue
        caminho_abs, quantidade, velocidade, raio = particle_defs[tipo]
        for k in range(quantidade):
            seed = (int(cx * 2) * 7349 + int(cy * 2) * 4519 + k * 131) & 0xFFFFFFFF
            rng = np.random.RandomState(seed)
            ang = rng.uniform(0.0, 2.0 * math.pi)
            r = raio * math.sqrt(rng.uniform(0.0, 1.0))
            fase = rng.uniform(0.0, 2.0 * math.pi)
            px = cx + math.cos(ang) * r
            py = cy + math.sin(ang) * r
            out.append((px, py, caminho_abs, 0.0, PARTICLE_SCALE,
                         PARTICLE_FLOAT_AMPLITUDE, velocidade, fase))
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

    mapa, billboard_cells, particle_cells, light_cells, wall_max, orb_min, is_new_format = logic._process_map_tokens(raw_mapa)
    spawn = _parse_spawn(dados.get("SPAWN", {}), mapa, orb_min)
    pasta_base = os.path.dirname(os.path.abspath(caminho))
    texturas_rel = _parse_textures(dados.get("TEXTURES", {}))
    texturas_abs = {t: os.path.join(pasta_base, rel) for t, rel in texturas_rel.items()}

    lights = _parse_lights(dados.get("LIGHTS", {}))
    if is_new_format:
        # No formato novo, a seção [LIGHTS] é escrita com índices 1-9
        # (correspondendo a L1..L9), então traduzimos pras mesmas chaves
        # internas (orb_min + n-1) usadas na grade do mapa.
        lights = {orb_min + (n - 1): v for n, v in lights.items() if 1 <= n <= 9}

    billboard_defs = _parse_billboards(dados.get("BILLBOARDS", {}), pasta_base)
    # (x, y, caminho, offset_y, escala, amplitude, velocidade, fase) — os
    # últimos 3 campos só são != 0 pras partículas (flutuar animado);
    # billboard estático fica com amplitude 0 (sem movimento).
    billboard_instances = [
        (x, y, billboard_defs[tipo][0], billboard_defs[tipo][1], billboard_defs[tipo][2], 0.0, 0.0, 0.0)
        for (x, y, tipo) in billboard_cells
        if tipo in billboard_defs
    ]
    particle_defs = _parse_particles(dados.get("PARTICLES", {}), pasta_base)
    particle_instances = _particle_instances(particle_cells, particle_defs)

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
        "wall_max": wall_max,
        "orb_min": orb_min,
        "billboards": billboard_instances + particle_instances,
        "light_cells": light_cells,
    }


# ══ FIM DO CARREGADOR ══════════════════════════════════════════


# ══ TELA DE CARREGAMENTO (Fase 2) ════════════════════════════════
def _make_progress_drawer(width, height, label):
    # Desenha a barra de progresso NA PRÓPRIA janela OpenGL via moderngl,
    # em vez de abrir uma janela 2D separada com pygame.display.set_mode().
    #
    # Por quê: set_mode() sem a flag OPENGL destrói a janela/contexto GL que
    # já está de pé (init_display) e, quando a janela é recriada logo depois
    # (resize_window), os objetos do moderngl (prog/vao) continuam apontando
    # pro contexto morto — o resultado era tela preta ao carregar mapas
    # grandes (≥ 4096 células, que é quando a barra aparece). Aqui o quadro
    # é montado numa superfície 2D offscreen e enviado como textura pra um
    # quad em tela cheia, então o contexto GL nunca é mexido.
    #
    # Usada como callback dentro de compute_light_grid().
    pygame.init()
    pygame.font.init()
    font = pygame.font.SysFont(None, 26)

    if render.ctx is None:
        # Defensivo: sem contexto GL ainda (não acontece nos fluxos atuais,
        # onde a barra só roda depois de init_display), cai pro comportamento
        # antigo de janela 2D simples.
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
            # processa a fila de eventos pra o SO não achar que o app travou
            # (mensagem "não está respondendo") durante o cálculo pesado.
            pygame.event.pump()
            pygame.display.flip()

        draw(0.0)
        return draw

    sw, sh = render.ctx.screen.width, render.ctx.screen.height
    surf = pygame.Surface((sw, sh))
    bar_w, bar_h = int(sw * 0.6), 22
    bx, by = (sw - bar_w) // 2, sh // 2

    prog_loading = None
    vao_loading = None
    quad_tex = None

    def _ensure_gl():
        nonlocal prog_loading, vao_loading
        if prog_loading is not None:
            return
        prog_loading = render.ctx.program(vertex_shader="""
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
        vbo = render.ctx.buffer(verts.tobytes())
        vao_loading = render.ctx.vertex_array(prog_loading, vbo, "in_pos", "in_uv")

    def draw(pct):
        nonlocal quad_tex
        pct = max(0.0, min(1.0, pct))
        surf.fill((12, 12, 18))
        pygame.draw.rect(surf, (55, 55, 68), (bx, by, bar_w, bar_h), border_radius=6)
        pygame.draw.rect(surf, (90, 200, 160), (bx, by, int(bar_w * pct), bar_h), border_radius=6)
        pygame.draw.rect(surf, (120, 120, 140), (bx, by, bar_w, bar_h), width=1, border_radius=6)
        txt = font.render(f"{label} — {int(pct * 100)}%", True, (230, 230, 230))
        surf.blit(txt, (bx, by - 32))
        # o GL trata o eixo Y ao contrário do pygame: tobytes(flipped=True)
        # já devolve as linhas de baixo pra cima (primeiro texel = canto
        # inferior), que é a ordem que o quad espera em (0,0)=inferior.
        data = pygame.image.tobytes(surf, "RGBA", True)
        _ensure_gl()
        if quad_tex is not None:
            quad_tex.release()
        quad_tex = render.ctx.texture((sw, sh), 4, data)
        quad_tex.use(0)
        prog_loading["u_tex"].value = 0
        render.ctx.viewport = (0, 0, sw, sh)
        vao_loading.render(mode=moderngl.TRIANGLES)
        # processa a fila de eventos pra o SO não achar que o app travou
        # (mensagem "não está respondendo") durante o cálculo pesado.
        pygame.event.pump()
        pygame.display.flip()

    draw(0.0)
    return draw


def load_map_file(caminho, preserve_position=False):
    data = load_rcfg(caminho)
    cfg = data["config"]
    logic.WIDTH, logic.HEIGHT = cfg["window_width"], cfg["window_height"]
    logic.MM = cfg["mm"]
    logic.FOV = cfg["fov"]
    logic.MAX_DEPTH = cfg["max_depth"]
    logic.MOVE_SPEED = cfg["move_speed"]
    logic.RUN_MULTIPLIER = cfg["run_multiplier"]
    logic.MOUSE_SENS_X = cfg["mouse_sens_x"]
    logic.MOUSE_SENS_Y = cfg["mouse_sens_y"]
    logic.MAX_LOOK_Y = cfg["max_look_y"]
    logic.FOG = cfg["fog"]
    logic.AMBIENT = cfg["ambient"]
    logic.LIGHT_RES = cfg["light_res"]
    logic.LIGHT_SOFT_SAMPLES = cfg["light_soft_samples"]
    logic.LIGHT_SOFT_RADIUS = cfg["light_soft_radius"]
    logic.LIGHT_BOUNCE = cfg["light_bounce"]
    logic.LIGHT_BOUNCE_RADIUS = cfg["light_bounce_radius"]
    logic.LIGHT_BOUNCE_PASSES = cfg["light_bounce_passes"]
    logic.TEXTURE_SIZE = cfg["texture_size"]
    logic.WALL_SCALE = cfg["wall_scale"]

    logic.MAP = [row[:] for row in data["map"]]
    logic.MAP_W = len(logic.MAP[0])
    logic.MAP_H = len(logic.MAP)
    logic.WALL_COLORS = data["colors"]
    logic.WALL_TEXTURES = data["textures"]
    logic.THEME = dict(logic.THEME_DEFAULTS)
    logic.THEME.update(data["theme"])
    logic.THEME["title"] = data["title"] or logic.THEME["title"]
    logic.LIGHT_ORBS = data["lights"]
    logic.SKY = data["sky"]
    logic.SKY_TIME = logic.SKY["start_time"]
    logic.SKY_PAUSED = False
    logic.SPAWN = data["spawn"]
    if not preserve_position:
        # hot-reload (fastloading, ver PLANO.md) pula este reset pra manter o
        # jogador exatamente onde estava enquanto o .rcfg é editado ao vivo.
        logic.px, logic.py, logic.pangle = logic.SPAWN
        logic.look_y = 0
    logic.WALL_MAX = data["wall_max"]
    logic.ORB_MIN = data["orb_min"]
    logic.BILLBOARDS = data["billboards"]
    logic.LIGHT_CELLS = data["light_cells"]

    big_map = (logic.MAP_W * logic.MAP_H) >= logic.LOADING_SCREEN_THRESHOLD_CELLS
    progress_cb = None
    if big_map:
        progress_cb = _make_progress_drawer(logic.WIDTH, logic.HEIGHT, f"Carregando {os.path.basename(caminho)}")
    logic.compute_light_grid(on_progress=progress_cb)
    render.resize_window(logic.WIDTH, logic.HEIGHT)
    render.upload_textures()
    print(f"Mapa: {data['info'].get('name', caminho)}", flush=True)