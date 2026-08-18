// ══ SHADER: VERT ══════════════════════════════════════════
#version 330 core
in vec2 in_pos;
in vec2 in_uv;
out vec2 uv;
void main() {
    uv = in_uv;
    gl_Position = vec4(in_pos, 0.0, 1.0);
}

// ══ SHADER: FRAG ══════════════════════════════════════════
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

// ══ SHADER: BB_VERT ══════════════════════════════════════════
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

// ══ SHADER: BB_FRAG ══════════════════════════════════════════
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

// ══ SHADER: CROSS_FRAG ══════════════════════════════════════════
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
