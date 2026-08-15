# Raycasting FPS — LANÇADOR (entry point).
#
# Este arquivo é o único que o usuário vê/interage: arraste um .rcfg para
# cima dele para iniciar a engine direto com o mapa carregado (mesmo
# comportamento de sempre). O motor em si vive nos núcleos em ENGINE/:
#   ENGINE/loader.py  — núcleo de carregamento (.rcfg + barra de progresso)
#   ENGINE/logic.py   — núcleo lógico (estado do jogo, helpers, grade de luz)
#   ENGINE/render.py  — núcleo gráfico (shaders, contexto GPU, texturas)
# O erro.log continua sendo gravado ao lado deste .pyw.
import math
import os
import sys

import moderngl
import numpy as np
import pygame

from ENGINE import loader, logic, render


def time_sec():
    import time
    return time.time()


def main():
    caminho = None
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        caminho = sys.argv[1]

    logic.compute_light_grid()
    render.init_display()
    if caminho:
        loader.load_map_file(caminho)
        logic.restore_saved_position(caminho)

    # ── fastloading (PLANO.md item 4): observa o .rcfg em disco e recarrega
    # sozinho quando o editor salva, sem resetar o jogador pro SPAWN. ──
    hot_reload_last_check = time_sec()
    hot_reload_seen_stamp = None   # (mtime, size) já carregado/tentado com sucesso
    hot_reload_pending_stamp = None  # (mtime, size) visto na checagem anterior, aguardando confirmação de estabilidade
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

        # ── ciclo dia-noite (PLANO.md item 2) ──
        if logic.SKY["enabled"] and logic.SKY["cycle"] and not logic.SKY_PAUSED:
            logic.SKY_TIME = (logic.SKY_TIME + dt * (24.0 / logic.SKY["day_length"])) % 24.0

        # ── fastloading: checa o arquivo a cada ~0.5s (não a cada frame) ──
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
                        # mesmo tamanho/mtime em duas checagens seguidas: o save
                        # do editor já terminou de escrever, é seguro recarregar.
                        hot_reload_seen_stamp = stamp
                        hot_reload_pending_stamp = None
                        try:
                            logic.save_current_position(caminho)
                            loader.load_map_file(caminho, preserve_position=True)
                            logic.restore_saved_position(caminho)
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
                if os.path.isfile(e.file):
                    logic.save_current_position(caminho)
                    caminho = e.file
                    loader.load_map_file(caminho)
                    logic.restore_saved_position(caminho)
                    hot_reload_seen_stamp = None
                    hot_reload_pending_stamp = None
                    try:
                        st = os.stat(caminho)
                        hot_reload_seen_stamp = (st.st_mtime, st.st_size)
                    except OSError:
                        pass
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    captured = not captured
                    pygame.mouse.set_visible(not captured)
                    pygame.event.set_grab(captured)
                    pygame.mouse.get_rel()
                elif e.key == pygame.K_r:
                    if caminho is not None:
                        loader.load_map_file(caminho)  # já deixa px,py,pangle,look_y no SPAWN do arquivo
                        logic.save_current_position(caminho)  # sobrescreve o cache com o reset
                        hot_reload_pending_stamp = None
                        try:
                            st = os.stat(caminho)
                            hot_reload_seen_stamp = (st.st_mtime, st.st_size)
                        except OSError:
                            pass
                elif e.key == pygame.K_COMMA:
                    logic.SKY_TIME = (logic.SKY_TIME - 0.5) % 24.0
                elif e.key == pygame.K_PERIOD:
                    logic.SKY_TIME = (logic.SKY_TIME + 0.5) % 24.0
                elif e.key == pygame.K_p:
                    logic.SKY_PAUSED = not logic.SKY_PAUSED
            elif e.type == pygame.MOUSEBUTTONDOWN and not captured:
                captured = True
                pygame.mouse.set_visible(False)
                pygame.event.set_grab(True)
                pygame.mouse.get_rel()

        keys = pygame.key.get_pressed()
        if captured:
            rel = pygame.mouse.get_rel()
            logic.pangle += rel[0] * logic.MOUSE_SENS_X
            logic.look_y = max(-logic.MAX_LOOK_Y, min(logic.MAX_LOOK_Y, logic.look_y - rel[1] * logic.MOUSE_SENS_Y))

        speed = logic.MOVE_SPEED * (logic.RUN_MULTIPLIER if (keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]) else 1) * (dt * 60.0)
        fdx = math.cos(logic.pangle) * speed
        fdy = math.sin(logic.pangle) * speed
        sdx = math.cos(logic.pangle + math.pi / 2) * speed
        sdy = math.sin(logic.pangle + math.pi / 2) * speed

        nx, ny = logic.px, logic.py
        if keys[pygame.K_w] or keys[pygame.K_UP]:    nx += fdx; ny += fdy
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:  nx -= fdx; ny -= fdy
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:  nx -= sdx; ny -= sdy
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]: nx += sdx; ny += sdy

        m = 0.25
        tcx = int(nx + m * math.copysign(1, nx - logic.px))
        tcy = int(ny + m * math.copysign(1, ny - logic.py))
        if logic.open_cell(tcx, int(logic.py)):
            logic.px = nx
        if logic.open_cell(int(logic.px), tcy):
            logic.py = ny
        if not logic.in_map(logic.px, logic.py):
            logic.px, logic.py, logic.pangle = logic.SPAWN
            logic.look_y = 0

        # ── uniforms ──
        # plane_len é multiplicado pelo aspect ratio (largura/altura) da
        # janela (Fase 1: bug relacionado ao das bordas pretas). Sem isso,
        # o FOV horizontal configurado no .rcfg só ficava correto numa
        # proporção de tela específica; em janelas bem largas ou bem
        # estreitas a imagem saía "esticada"/com FOV horizontal errado.
        aspect = (logic.WIDTH / logic.HEIGHT) if logic.HEIGHT else 1.0
        plane_len = math.tan(logic.FOV / 2) * aspect
        plane_x = -math.sin(logic.pangle) * plane_len
        plane_y = math.cos(logic.pangle) * plane_len
        render.prog["u_res"].value = (logic.WIDTH, logic.HEIGHT)
        render.prog["u_pos"].value = (logic.px, logic.py)
        render.prog["u_dir"].value = (math.cos(logic.pangle), math.sin(logic.pangle))
        render.prog["u_plane"].value = (plane_x, plane_y)
        render.prog["u_mapSize"].value = (logic.MAP_W, logic.MAP_H)
        render.prog["u_horizon"].value = logic.HEIGHT * 0.5 + logic.look_y
        render.prog["u_scale"].value = (logic.HEIGHT / (2.0 * math.tan(logic.FOV / 2))) * logic.WALL_SCALE
        render.prog["u_ambient"].value = logic.AMBIENT
        render.prog["u_fog"].value = logic.FOG
        render.prog["u_depth"].value = float(logic.MAX_DEPTH)
        render.prog["u_wallMax"].value = float(logic.WALL_MAX)
        render.prog["u_orbMin"].value = float(logic.ORB_MIN)

        # Azimute do sol: meio-dia aponta para +X, a frente do jogador na carga
        # (pangle=0). Assim o arco passa por cima À frente da câmera — o sol sobe
        # pela esquerda, cruza o topo no meio-dia e desce pela direita. Antes o
        # azimute era (SKY_TIME/24·2π), que punha o meio-dia em -X (atrás), e o
        # sol só ficava na frente durante a noite, abaixo do horizonte.
        sun_angle = ((logic.SKY_TIME - 12.0) / 24.0) * 2.0 * math.pi
        # Fase corrigida do ciclo solar: 6h amanhece (sin=0), 12h meio-dia no
        # zênite (sin=1), 18h entardecer (sin=0), meia-noite embaixo (sin=-1).
        # O pico é escalado por sun_peak (graus de elevação máxima). O day_factor
        # é normalizado por sin(sun_peak): o meio-dia (sun_elev = sin(sun_peak))
        # vira 1.0 sempre, então baixar o pico para caber o arco no viewport não
        # escurece o meio-dia.
        sun_time_angle = ((logic.SKY_TIME - 6.0) / 24.0) * 2.0 * math.pi
        sun_elev = math.sin(sun_time_angle) * math.sin(math.radians(logic.SKY["sun_peak"]))
        day_factor = max(0.0, min(1.0, sun_elev / max(math.sin(math.radians(logic.SKY["sun_peak"])), 1e-4))) if logic.SKY["enabled"] else 1.0
        night_factor = 1.0 - day_factor

        sb = [logic._rgb(logic.THEME["sky_base"])[i] / 255.0 for i in range(3)]
        st = [logic._rgb(logic.THEME["sky_top"])[i] / 255.0 for i in range(3)]
        if logic.SKY["enabled"]:
            nb = [logic._rgb(logic.NIGHT_SKY_BASE)[i] / 255.0 for i in range(3)]
            nt = [logic._rgb(logic.NIGHT_SKY_TOP)[i] / 255.0 for i in range(3)]
            sb = [nb[i] + (sb[i] - nb[i]) * day_factor for i in range(3)]
            st = [nt[i] + (st[i] - nt[i]) * day_factor for i in range(3)]
        fb = [logic._rgb(logic.THEME["floor_base"])[i] / 255.0 for i in range(3)]
        ft = [logic._rgb(logic.THEME["floor_top"])[i] / 255.0 for i in range(3)]
        cr = [logic._rgb(logic.THEME["crosshair"])[i] / 255.0 for i in range(3)]
        mp = [logic._rgb(logic.THEME["minimap_player"])[i] / 255.0 for i in range(3)]
        render.prog["u_skyB"].value = tuple(sb)
        render.prog["u_skyT"].value = tuple(st)
        render.prog["u_skyBodies"].value = 1.0 if logic.SKY["enabled"] else 0.0
        render.prog["u_sunAngle"].value = sun_angle
        render.prog["u_sunElev"].value = sun_elev
        render.prog["u_nightFactor"].value = night_factor
        render.prog["u_starsCount"].value = float(logic.SKY["stars"])
        render.prog["u_sunColor"].value = tuple(c / 255.0 for c in logic._rgb(logic.SKY["sun_color"]))
        render.prog["u_moonColor"].value = tuple(c / 255.0 for c in logic._rgb(logic.SKY["moon_color"]))
        render.prog["u_floorB"].value = tuple(fb)
        render.prog["u_floorT"].value = tuple(ft)
        render.prog["u_cross"].value = tuple(cr)
        render.prog["u_mmPlayer"].value = tuple(mp)

        mm_cell = max(1, logic.MM // max(logic.MAP_W, logic.MAP_H))
        mm_w = logic.MAP_W * mm_cell
        mm_h = logic.MAP_H * mm_cell
        mm_x = logic.WIDTH - mm_w - 10
        mm_y = 10
        # ── billboards + partículas (Fase 5 / PLANO.md item 3): arrays de instância pro shader ──
        bb_instances = logic.BILLBOARDS[:render.MAX_BILLBOARD_INSTANCES]
        bb_pos = [(0.0, 0.0)] * render.MAX_BILLBOARD_INSTANCES
        bb_layer = [0.0] * render.MAX_BILLBOARD_INSTANCES
        bb_yoff = [0.0] * render.MAX_BILLBOARD_INSTANCES
        bb_aspect = [1.0] * render.MAX_BILLBOARD_INSTANCES
        bb_scale = [1.0] * render.MAX_BILLBOARD_INSTANCES
        bb_amp = [0.0] * render.MAX_BILLBOARD_INSTANCES
        bb_vel = [0.0] * render.MAX_BILLBOARD_INSTANCES
        bb_phase = [0.0] * render.MAX_BILLBOARD_INSTANCES
        for idx, (bx, by, caminho_abs, yoff, escala, amp, vel, fase) in enumerate(bb_instances):
            bb_pos[idx] = (bx, by)
            bb_layer[idx] = float(render._BB_LAYER_BY_PATH.get(caminho_abs, 0))
            bb_yoff[idx] = yoff
            bb_aspect[idx] = float(render._BB_ASPECT_BY_PATH.get(caminho_abs, 1.0))
            bb_scale[idx] = escala
            bb_amp[idx] = amp
            bb_vel[idx] = vel
            bb_phase[idx] = fase
        render.prog["u_bbCount"].value = len(bb_instances)
        render.prog["u_bbPos"].value = bb_pos
        render.prog["u_bbLayer"].value = bb_layer
        render.prog["u_bbYOff"].value = bb_yoff
        render.prog["u_bbAspect"].value = bb_aspect
        render.prog["u_bbScale"].value = bb_scale
        render.prog["u_bbAmp"].value = bb_amp
        render.prog["u_bbVel"].value = bb_vel
        render.prog["u_bbPhase"].value = bb_phase
        render.prog["u_time"].value = time_sec() - t_start

        render.prog["u_mmPos"].value = (mm_x, mm_y)
        render.prog["u_mmSize"].value = (mm_w, mm_h)
        render.prog["u_mmCell"].value = float(mm_cell)
        render.prog["u_playerPix"].value = (mm_x + logic.px * mm_cell, mm_y + logic.py * mm_cell)
        # distância (em células) entre o ponto do player e a ponta do ponteiro de
        # direção no minimapa — reduzida pra ficarem mais próximos, com piso de
        # segurança pra não sobrepor os dois círculos (r=3.5px + r=2.5px=6px) em
        # mapas grandes onde mm_cell fica pequeno.
        mm_dir_dist = max(0.9, 6.0 / mm_cell)
        render.prog["u_dirPix"].value = (mm_x + (logic.px + math.cos(logic.pangle) * mm_dir_dist) * mm_cell,
                                         mm_y + (logic.py + math.sin(logic.pangle) * mm_dir_dist) * mm_cell)

        render.tex_map.use(0)
        if render.tex_light is not None:
            render.tex_light.use(1)
        render.tex_palA.use(2)
        render.tex_palB.use(3)
        render.tex_wallArr.use(4)
        render.tex_hasTex.use(5)
        render.tex_bbTex.use(6)
        if render.tex_mmFlags is not None:
            render.tex_mmFlags.use(7)
        render.prog["u_map"].value = 0
        render.prog["u_light"].value = 1
        render.prog["u_palA"].value = 2
        render.prog["u_palB"].value = 3
        render.prog["u_wallTex"].value = 4
        render.prog["u_hasTex"].value = 5
        render.prog["u_bbTex"].value = 6
        render.prog["u_mmFlags"].value = 7

        render.vao.render(mode=moderngl.TRIANGLES)
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
                w = render.ctx.screen.width
                h = render.ctx.screen.height
                data = render.ctx.screen.read(viewport=(0, 0, w, h), components=3)
                arr = np.frombuffer(data, dtype=np.uint8).reshape(h, w, 3)[::-1]
                from PIL import Image
                Image.fromarray(arr, "RGB").save(shot)
            running = False

    pygame.quit()


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