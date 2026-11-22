"""Moteur de montage : plans (vidéo, photo, polaroïds, carte, écran titre, rembobinage VHS),
transitions animées, titres animés (ASS/libass), mixage audio (musiques, ambiances, effets, ducking).

Principe :
  1. chaque plan est rendu une fois en ProRes dans le cache (clé = hash de ses paramètres) ;
  2. une boucle finale lit les plans, fabrique les transitions image par image et envoie tout
     à l'encodeur final, qui incruste les textes (ASS) et ajoute le mix audio.
"""
import os, json, hashlib, subprocess, math, shutil
from concurrent.futures import ThreadPoolExecutor
import numpy as np, cv2, soundfile as sf
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter
try:
    import pillow_heif; pillow_heif.register_heif_opener()
except Exception: pass

ATELIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = ATELIER + '/fonts'
SONS = ATELIER + '/sons'
SR = 48000
VERSIONS = {'carte': 3}
HDR_TM = 'zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p'

# ============================================================ looks (LUT 3D)
def _smooth(x): return x * x * (3 - 2 * x)
def look_fn(nom):
    def vacances(c):
        l = (0.2126 * c[..., 0] + 0.7152 * c[..., 1] + 0.0722 * c[..., 2])[..., None]
        c = l + (c - l) * 1.16                               # saturation
        c = c + 0.30 * (_smooth(np.clip(c, 0, 1)) - c)      # contraste en S
        sh = (1 - l) ** 2; hi = l ** 2
        c = c + sh * np.array([-0.020, 0.008, 0.030]) + hi * np.array([0.035, 0.012, -0.025])
        return np.clip(c, 0, 1) ** 0.97
    def nostalgie(c):
        l = (0.2126 * c[..., 0] + 0.7152 * c[..., 1] + 0.0722 * c[..., 2])[..., None]
        c = l + (c - l) * 0.80
        c = c + 0.15 * (_smooth(np.clip(c, 0, 1)) - c)
        c = 0.055 + c * 0.875                                # noirs délavés, blancs adoucis
        sh = (1 - l) ** 2; hi = l ** 2
        c = c + sh * np.array([0.000, 0.012, 0.010]) + hi * np.array([0.045, 0.018, -0.040])
        c = c * np.array([1.03, 1.0, 0.93])
        return np.clip(c, 0, 1)
    def nb(c):
        l = (0.25 * c[..., 0] + 0.65 * c[..., 1] + 0.10 * c[..., 2])[..., None]
        l = l + 0.35 * (_smooth(np.clip(l, 0, 1)) - l)
        return np.clip(np.repeat(l, 3, -1) * np.array([1.0, 0.98, 0.94]) + 0.02, 0, 1)
    def neutre(c): return c
    return dict(vacances=vacances, nostalgie=nostalgie, nb=nb, neutre=neutre)[nom]

def lut_path(nom):
    p = f'{ATELIER}/looks/{nom}.cube'
    if not os.path.exists(p):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        N = 33; g = np.linspace(0, 1, N)
        b, gg, r = np.meshgrid(g, g, g, indexing='ij')
        out = look_fn(nom)(np.stack([r, gg, b], -1).reshape(-1, 3))
        with open(p, 'w') as f:
            f.write(f'TITLE "{nom}"\nLUT_3D_SIZE {N}\n')
            for v in out: f.write(f'{v[0]:.5f} {v[1]:.5f} {v[2]:.5f}\n')
    return p

# ============================================================ utilitaires
def ease(p, kind='inout'):
    p = min(1.0, max(0.0, p))
    if kind == 'in': return p ** 3
    if kind == 'out': return 1 - (1 - p) ** 3
    if kind == 'back':  # dépasse légèrement puis revient
        c1, c3 = 1.70158, 2.70158; return 1 + c3 * (p - 1) ** 3 + c1 * (p - 1) ** 2
    return 4 * p ** 3 if p < 0.5 else 1 - (-2 * p + 2) ** 3 / 2

def probe(src):
    j = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-print_format', 'json', '-show_streams', '-show_format', src],
                                  capture_output=True, text=True).stdout)
    v = next(s for s in j['streams'] if s['codec_type'] == 'video')
    rot = 0
    for sd in v.get('side_data_list', []):
        if 'rotation' in sd: rot = int(sd['rotation'])
    w, h = v['width'], v['height']
    if abs(rot) % 180 == 90: w, h = h, w
    return dict(w=w, h=h, hdr=v.get('color_transfer') in ('arib-std-b67', 'smpte2084'),
                son=any(s['codec_type'] == 'audio' for s in j['streams']), duree=float(j['format'].get('duration', 0)))

class Lecteur:
    """Lit des images brutes BGR depuis ffmpeg."""
    def __init__(self, args, w, h):
        self.w, self.h = w, h; self.n = w * h * 3
        self.p = subprocess.Popen(['ffmpeg', '-v', 'error'] + args + ['-f', 'rawvideo', '-pix_fmt', 'bgr24', '-'],
                                  stdout=subprocess.PIPE, bufsize=self.n * 2)
        self.last = None; self.eof = False
    def lire(self):
        b = self.p.stdout.read(self.n)
        if len(b) == self.n: self.last = np.frombuffer(b, np.uint8).reshape(self.h, self.w, 3).copy()
        else: self.eof = True
        return self.last
    def fermer(self):
        try: self.p.stdout.close(); self.p.kill(); self.p.wait()
        except Exception: pass

class Ecrivain:
    def __init__(self, out, w, h, fps, extra_in=(), vf=None, codec='prores', audio=None):
        a = ['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{w}x{h}', '-r', str(fps), '-i', '-']
        if audio: a += ['-i', audio]
        if vf: a += ['-vf', vf]
        if codec == 'prores':
            a += ['-c:v', 'prores_ks', '-profile:v', '2', '-pix_fmt', 'yuv422p10le']
        else:
            a += ['-c:v', 'libx264', '-preset', 'slow', '-crf', '18', '-profile:v', 'high', '-pix_fmt', 'yuv420p',
                  '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-movflags', '+faststart']
        if audio: a += ['-c:a', 'aac', '-b:a', '320k', '-shortest']
        self.p = subprocess.Popen(a + [out], stdin=subprocess.PIPE, bufsize=w * h * 6)
    def ecrire(self, f): self.p.stdin.write(np.ascontiguousarray(f).tobytes())
    def fermer(self):
        self.p.stdin.close(); r = self.p.wait()
        if r: raise RuntimeError('encodage échoué')

# ============================================================ effets image
class Effets:
    def __init__(self, W, H, seed=0):
        self.W, self.H = W, H; rng = np.random.default_rng(seed)
        g = [cv2.GaussianBlur(rng.normal(0, 1, (H, W)).astype(np.float32), (0, 0), 0.8) for _ in range(6)]
        self.grain = [(x / x.std()).astype(np.float32) for x in g]
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        d = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2) / math.sqrt(2)
        self.vign = d
    def vignette(self, f, force=0.35):
        m = (1 - force * np.clip(self.vign * 1.25 - 0.25, 0, 1) ** 1.8)
        return (f.astype(np.float32) * m[..., None]).astype(np.uint8)
    def grain_(self, f, k, force=9.0):
        n = self.grain[k % len(self.grain)] * force
        return np.clip(f.astype(np.float32) + n[..., None], 0, 255).astype(np.uint8)

def transform(img, W, H, zoom=1.0, fx=0.5, fy=0.5, dx=0.0, dy=0.0, rot=0.0, mode='remplir', interp=cv2.INTER_LINEAR):
    """Cadre l'image source dans W x H : 'remplir' (recadre) ou 'flou' (image entière sur fond flouté)."""
    sh, sw = img.shape[:2]
    if mode == 'remplir':
        c = max(W / sw, H / sh) * zoom
        hw, hh = W / (2 * c), H / (2 * c)
        cx = min(max(fx * sw, hw), sw - hw) if sw > 2 * hw else sw / 2
        cy = min(max(fy * sh, hh), sh - hh) if sh > 2 * hh else sh / 2
        M = cv2.getRotationMatrix2D((cx, cy), rot, c)
        M[0, 2] += W / 2 - cx + dx; M[1, 2] += H / 2 - cy + dy
        return cv2.warpAffine(img, M, (W, H), flags=interp, borderMode=cv2.BORDER_REFLECT)
    # mode flou
    c = max(W / sw, H / sh) * 1.08
    small = cv2.resize(img, (max(1, int(sw * c / 10)), max(1, int(sh * c / 10))), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (0, 0), 6)
    bg = cv2.resize(small, (int(sw * c), int(sh * c)), interpolation=cv2.INTER_LINEAR)
    y0, x0 = (bg.shape[0] - H) // 2, (bg.shape[1] - W) // 2
    bg = (bg[y0:y0 + H, x0:x0 + W].astype(np.float32) * 0.55).astype(np.uint8)
    cf = min(W / sw, H / sh) * zoom
    M = cv2.getRotationMatrix2D((sw / 2, sh / 2), rot, cf)
    M[0, 2] += W / 2 - sw / 2 + dx; M[1, 2] += H / 2 - sh / 2 + dy
    fg = cv2.warpAffine(img, M, (W, H), flags=interp, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))
    mask = cv2.warpAffine(np.full((sh, sw), 255, np.uint8), M, (W, H), flags=cv2.INTER_LINEAR)
    # ombre douce sous l'image
    sh_m = cv2.GaussianBlur(mask, (0, 0), 18).astype(np.float32) / 255 * 0.5
    bg = (bg * (1 - sh_m[..., None])).astype(np.uint8)
    a = mask.astype(np.float32)[..., None] / 255
    return (fg * a + bg * (1 - a)).astype(np.uint8)

def secousse(t, amp, seed=1):
    return (amp * (math.sin(t * 37.1 + seed) * 0.6 + math.sin(t * 61.7 + 2 * seed) * 0.4),
            amp * (math.sin(t * 43.3 + 3 * seed) * 0.6 + math.sin(t * 71.9 + seed) * 0.4))


def camera(p, t):
    """Position de caméra à l'instant t : zoom/panoramique de base + zooms « punch » + secousses."""
    z0, z1 = p.get('zoom', (1.0, 1.0)); f0 = p.get('focus', (0.5, 0.5)); f1 = p.get('focus_fin', f0)
    q = ease(t / max(1e-6, p['duree']), p.get('courbe', 'inout'))
    z = z0 + (z1 - z0) * q; fx = f0[0] + (f1[0] - f0[0]) * q; fy = f0[1] + (f1[1] - f0[1]) * q
    for (tp, zp, foc, dp) in p.get('punch', []):
        if t >= tp:
            e = ease((t - tp) / 0.16, 'out') if t < tp + dp else max(0, 1 - ease((t - tp - dp) / 0.12, 'inout'))
            z = z * (1 + (zp - 1) * e); fx = fx + (foc[0] - fx) * e; fy = fy + (foc[1] - fy) * e
    dx = dy = 0.0
    for (ts, amp, dur) in p.get('secousse', []):
        if ts <= t < ts + dur:
            a = amp * (1 - (t - ts) / dur); dx, dy = secousse(t, a)
    return z, fx, fy, dx, dy

# ============================================================ polaroïds
def charger_photo(src, look='neutre', maxdim=2600):
    """Charge une photo (y compris HEIC), orientation corrigée, look appliqué via LUT ffmpeg."""
    im = ImageOps.exif_transpose(Image.open(src)).convert('RGB')
    im.thumbnail((maxdim, maxdim), Image.LANCZOS)
    arr = cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2BGR)
    if look != 'neutre':
        lut = lut_path(look)
        h, w = arr.shape[:2]
        r = subprocess.run(['ffmpeg', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{w}x{h}', '-i', '-',
                            '-vf', f'lut3d={lut}:interp=tetrahedral', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-'],
                           input=arr.tobytes(), capture_output=True)
        arr = np.frombuffer(r.stdout, np.uint8).reshape(h, w, 3).copy()
    return arr

def fabriquer_polaroid(photo_bgr, largeur, legende='', focus=(0.5, 0.5), seed=0, police='PatrickHand_400Regular'):
    """Carte polaroïd RGBA (avec ombre) : bord fin en haut/côtés, large en bas avec légende manuscrite."""
    rng = np.random.default_rng(seed)
    sh, sw = photo_bgr.shape[:2]
    portrait = sh > sw * 1.1
    ia = 3 / 4 if portrait else 1.0  # zone image : carrée (paysage) ou 3:4 (portrait)
    b = int(largeur * 0.055); iw = largeur - 2 * b; ih = int(iw / ia); bas = int(largeur * 0.24)
    H = b + ih + bas
    # recadrage de la photo
    c = max(iw / sw, ih / sh)
    img = transform(photo_bgr, iw, ih, 1.0, focus[0], focus[1], interp=cv2.INTER_AREA if c < 1 else cv2.INTER_CUBIC)
    card = np.zeros((H, largeur, 3), np.float32)
    card[:] = (226, 236, 242)  # BGR : blanc cassé chaud
    card += rng.normal(0, 2.2, (H, largeur, 1)).astype(np.float32)
    card[b:b + ih, b:b + iw] = img
    # léger voile intérieur sur la photo (aspect tirage)
    card[b:b + ih, b:b + iw] = card[b:b + ih, b:b + iw] * 0.97 + 4
    card = np.clip(card, 0, 255).astype(np.uint8)
    pil = Image.fromarray(cv2.cvtColor(card, cv2.COLOR_BGR2RGB))
    if legende:
        d = ImageDraw.Draw(pil); fs = int(bas * 0.36)
        f = ImageFont.truetype(f'{FONTS}/{police}.ttf', fs)
        while d.textlength(legende, font=f) > iw * 0.95 and fs > 10:
            fs -= 2; f = ImageFont.truetype(f'{FONTS}/{police}.ttf', fs)
        tw = d.textlength(legende, font=f)
        d.text(((largeur - tw) / 2, b + ih + (bas - fs) / 2 - fs * 0.15), legende, font=f, fill=(48, 52, 70))
    rgba = np.dstack([cv2.cvtColor(np.asarray(pil), cv2.COLOR_RGB2BGR), np.full((H, largeur), 255, np.uint8)])
    return rgba

def coller(dst, sprite, cx, cy, scale=1.0, rot=0.0, ombre=0.45, alpha=1.0):
    """Colle un sprite BGRA centré en (cx, cy) avec rotation, échelle et ombre portée."""
    H, W = dst.shape[:2]; sh, sw = sprite.shape[:2]
    M = cv2.getRotationMatrix2D((sw / 2, sh / 2), rot, scale)
    M[0, 2] += cx - sw / 2; M[1, 2] += cy - sh / 2
    if ombre > 0:
        off = 14 * scale
        Ms = M.copy(); Ms[0, 2] += off * 0.5; Ms[1, 2] += off
        a = cv2.warpAffine(sprite[..., 3], Ms, (W, H), flags=cv2.INTER_LINEAR)
        a = cv2.GaussianBlur(a, (0, 0), 16 * scale + 2).astype(np.float32) / 255 * ombre * alpha
        dst[:] = (dst * (1 - a[..., None])).astype(np.uint8)
    rgb = cv2.warpAffine(sprite[..., :3], M, (W, H), flags=cv2.INTER_LINEAR)
    a = cv2.warpAffine(sprite[..., 3], M, (W, H), flags=cv2.INTER_LINEAR).astype(np.float32)[..., None] / 255 * alpha
    dst[:] = (rgb * a + dst * (1 - a)).astype(np.uint8)
    return dst

def fond_table(W, H, teinte=(38, 52, 70), seed=0):
    """Fond chaud texturé (bois sombre / papier) pour les polaroïds."""
    rng = np.random.default_rng(seed)
    base = np.zeros((H, W, 3), np.float32); base[:] = teinte
    n = cv2.resize(rng.normal(0, 1, (H // 8, W // 8)).astype(np.float32), (W, H), interpolation=cv2.INTER_CUBIC)
    streak = cv2.resize(rng.normal(0, 1, (H // 2, 6)).astype(np.float32), (W, H), interpolation=cv2.INTER_CUBIC)
    base += (n * 6 + streak * 7)[..., None] + rng.normal(0, 2, (H, W, 1))
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    light = 1.15 - 0.55 * np.sqrt(((xx - W * 0.45) / W) ** 2 + ((yy - H * 0.4) / H) ** 2)
    return np.clip(base * light[..., None], 0, 255).astype(np.uint8)

# ============================================================ carte
def _proj(lon, lat): return lon, -lat / math.cos(math.radians(16))  # équirectangulaire corrigée

class Carte:
    def __init__(self, W, H):
        self.W, self.H = W, H
        d = json.load(open(ATELIER + '/carte.json'))
        self.polys = [np.array([_proj(*p) for p in poly], np.float64) for poly in d['vn']]
        self.stops = {s['id']: s for s in d['stops']}
        s = min(W, H) / 1080
        self.f_nom = ImageFont.truetype(f'{FONTS}/BeVietnamPro_700Bold.ttf', int(60 * s))
        self.labels = {}
    def label(self, nom):
        if nom not in self.labels:
            d = ImageDraw.Draw(Image.new('RGBA', (10, 10))); w = int(d.textlength(nom, font=self.f_nom)) + 40
            h = int(self.f_nom.size * 1.6); im = Image.new('RGBA', (w, h), (0, 0, 0, 0)); dr = ImageDraw.Draw(im)
            dr.text((20, h * 0.12), nom, font=self.f_nom, fill=(255, 255, 255, 255), stroke_width=4, stroke_fill=(10, 30, 45, 255))
            a = np.asarray(im); self.labels[nom] = np.dstack([cv2.cvtColor(a[..., :3], cv2.COLOR_RGB2BGR), a[..., 3]])
        return self.labels[nom]
    def vue(self, pts, marge=2.2):
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        span = max((max(xs) - min(xs)) * self.H / self.W, max(ys) - min(ys), 1.2) * marge
        return cx, cy, self.H / span
    def frame(self, cam, visites, trajet=None, p=0.0, t=0.0):
        W, H = self.W, self.H; cx, cy, sc = cam; S = 4  # sous-pixels (shift=2)
        f = np.zeros((H, W, 3), np.uint8); f[:] = (58, 40, 14)  # océan BGR
        yy = np.linspace(0, 1, H)[:, None, None]; f = (f * (0.85 + 0.3 * yy)).astype(np.uint8)
        for g in range(96, 116):  # quadrillage (méridiens / parallèles)
            x = int(((_proj(g, 0)[0] - cx) * sc + W / 2) * S)
            cv2.line(f, (x, 0), (x, H * S), (78, 58, 30), 1, cv2.LINE_AA, shift=2)
        for g in range(4, 28):
            y = int(((_proj(0, g)[1] - cy) * sc + H / 2) * S)
            cv2.line(f, (0, y), (W * S, y), (78, 58, 30), 1, cv2.LINE_AA, shift=2)
        def P(lon, lat):
            x, y = _proj(lon, lat); return ((x - cx) * sc + W / 2, (y - cy) * sc + H / 2)
        for poly in self.polys:
            pts = np.stack([(poly[:, 0] - cx) * sc + W / 2, (poly[:, 1] - cy) * sc + H / 2], 1)
            ip = (pts * S).astype(np.int32)
            sh = ip + np.array([int(6 * S), int(10 * S)])
            cv2.fillPoly(f, [sh], (40, 26, 8), cv2.LINE_AA, shift=2)
            cv2.fillPoly(f, [ip], (205, 228, 240), cv2.LINE_AA, shift=2)
            cv2.polylines(f, [ip], True, (150, 190, 215), max(1, int(2 * sc / 300)), cv2.LINE_AA, shift=2)
        rr = max(8, int(min(W, H) / 85))
        for sid in visites:
            s = self.stops[sid]; x, y = P(s['lon'], s['lat'])
            cv2.circle(f, (int(x * S), int(y * S)), int(rr * S), (60, 90, 230), -1, cv2.LINE_AA, shift=2)
            cv2.circle(f, (int(x * S), int(y * S)), int(rr * S), (255, 255, 255), max(2, rr // 3), cv2.LINE_AA, shift=2)
        if trajet:
            a, b = self.stops[trajet[0]], self.stops[trajet[1]]
            (x0, y0), (x1, y1) = P(a['lon'], a['lat']), P(b['lon'], b['lat'])
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2; nx, ny = -(y1 - y0), (x1 - x0)
            bend = 0.22; qx, qy = mx + nx * bend, my + ny * bend
            pe = ease(p, 'inout'); N = 80
            ts = np.linspace(0, pe, max(2, int(N * pe)))
            curve = np.stack([(1 - ts) ** 2 * x0 + 2 * (1 - ts) * ts * qx + ts ** 2 * x1,
                              (1 - ts) ** 2 * y0 + 2 * (1 - ts) * ts * qy + ts ** 2 * y1], 1)
            # trait pointillé
            for k in range(0, len(curve) - 1, 2):
                cv2.line(f, tuple((curve[k] * S).astype(int)), tuple((curve[k + 1] * S).astype(int)), (255, 255, 255),
                         max(3, rr // 2), cv2.LINE_AA, shift=2)
            hx, hy = curve[-1]
            pulse = 1 + 0.25 * math.sin(t * 10)
            cv2.circle(f, (int(hx * S), int(hy * S)), int(rr * 1.6 * pulse * S), (70, 110, 255), -1, cv2.LINE_AA, shift=2)
            cv2.circle(f, (int(hx * S), int(hy * S)), int(rr * 0.7 * S), (255, 255, 255), -1, cv2.LINE_AA, shift=2)
            if p > 0.92:
                cv2.circle(f, (int(x1 * S), int(y1 * S)), int(rr * (1 + (p - 0.92) * 40) * S), (255, 255, 255), 2, cv2.LINE_AA, shift=2)
        for sid in visites + ([trajet[1]] if trajet and p > 0.85 else []):
            s = self.stops[sid]; x, y = P(s['lon'], s['lat']); lab = self.label(s['name'])
            right = x + rr * 2 + lab.shape[1] < W - 40
            lx = x + rr * 2 + lab.shape[1] / 2 if right else x - rr * 2 - lab.shape[1] / 2
            coller(f, lab, lx, y, ombre=0)
        return f

# ============================================================ VHS
def vhs(f, t, rng, force=1.0):
    H, W = f.shape[:2]
    out = f.copy()
    sh = int(6 * force)
    out[..., 2] = np.roll(f[..., 2], sh, 1); out[..., 0] = np.roll(f[..., 0], -sh, 1)
    # lignes qui sautent
    for _ in range(int(6 * force)):
        y = rng.integers(0, H); h = rng.integers(2, 30); dx = int(rng.normal(0, 25 * force))
        out[y:y + h] = np.roll(out[y:y + h], dx, 1)
    # bande de tracking
    by = int((t * 0.35 % 1.0) * (H + 200)) - 100; bh = int(40 + 30 * force)
    y0, y1 = max(0, by), min(H, by + bh)
    if y1 > y0:
        noise = rng.integers(0, 255, (y1 - y0, W, 1), dtype=np.uint8)
        out[y0:y1] = (out[y0:y1] * 0.45 + noise * 0.55).astype(np.uint8)
    out[::2] = (out[::2] * 0.86).astype(np.uint8)  # lignes de balayage
    out = cv2.GaussianBlur(out, (3, 1), 0)
    hsv = cv2.cvtColor(out, cv2.COLOR_BGR2HSV); hsv[..., 1] = (hsv[..., 1] * 0.8).astype(np.uint8)
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)

# ============================================================ transitions
def _shift(img, dx, dy):
    M = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(img, M, (img.shape[1], img.shape[0]), borderMode=cv2.BORDER_REFLECT)

def _zoom(img, z):
    H, W = img.shape[:2]; M = cv2.getRotationMatrix2D((W / 2, H / 2), 0, z)
    return cv2.warpAffine(img, M, (W, H), borderMode=cv2.BORDER_REFLECT)

def light_leak(W, H, p, seed=0):
    rng = np.random.default_rng(seed); small = np.zeros((H // 8, W // 8, 3), np.float32)
    h, w = small.shape[:2]; yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    for k in range(3):
        cx = w * (-0.3 + 1.6 * p + rng.uniform(-0.2, 0.2)); cy = h * rng.uniform(0.2, 0.8); r = w * rng.uniform(0.25, 0.45)
        g = np.exp(-(((xx - cx) / r) ** 2 + ((yy - cy) / (r * 1.4)) ** 2))
        col = np.array([[40, 120, 255], [60, 170, 255], [90, 60, 230]][k], np.float32)
        small += g[..., None] * col
    return cv2.resize(small, (W, H), interpolation=cv2.INTER_CUBIC)

def transition(kind, A, B, p, i=0, rng=None):
    """Mélange A (sortant) et B (entrant) pour la progression p (0..1)."""
    H, W = A.shape[:2]
    if kind == 'fondu':
        return cv2.addWeighted(A, 1 - p, B, p, 0)
    if kind == 'fondu_noir':
        return (A * max(0, 1 - 2 * p)).astype(np.uint8) if p < 0.5 else (B * min(1, 2 * p - 1)).astype(np.uint8)
    if kind == 'fondu_blanc' or kind == 'flash':
        k = ease(p, 'inout'); base = A if p < 0.5 else B
        w = 1 - abs(2 * p - 1); w = w ** (0.6 if kind == 'flash' else 1.0)
        return cv2.addWeighted(base, 1 - w, np.full_like(base, 255), w, 0)
    if kind.startswith('whip'):
        d = kind.split('_')[1] if '_' in kind else 'gauche'
        vx, vy = {'gauche': (-1, 0), 'droite': (1, 0), 'haut': (0, -1), 'bas': (0, 1)}[d]
        L = W if vx else H; acc = np.zeros(A.shape, np.float32); n = 8
        for s in range(n):
            q = ease(min(1, p + (s - n / 2) / n * 0.12), 'inout'); off = q * L
            a = _shift(A, vx * off, vy * off); b = _shift(B, vx * (off - L), vy * (off - L))
            # côté A ou B selon la position
            if vx: m = (np.arange(W)[None, :] < W - off) if vx < 0 else (np.arange(W)[None, :] >= off)
            else: m = (np.arange(H)[:, None] < H - off) if vy < 0 else (np.arange(H)[:, None] >= off)
            m = np.broadcast_to(m, (H, W))[..., None]
            acc += np.where(m, a, b)
        return (acc / n).astype(np.uint8)
    if kind == 'zoom':  # zoom avant à travers A puis B qui se pose
        acc = np.zeros(A.shape, np.float32); n = 6
        if p < 0.5:
            q = ease(p * 2, 'in')
            for s in range(n): acc += _zoom(A, 1 + q * 1.5 * (1 + s * 0.06))
        else:
            q = 1 - ease((p - 0.5) * 2, 'out')
            for s in range(n): acc += _zoom(B, 1 + q * 0.8 * (1 + s * 0.06))
        out = (acc / n).astype(np.uint8)
        w = max(0, 1 - abs(p - 0.5) * 6) * 0.5
        return cv2.addWeighted(out, 1 - w, np.full_like(out, 255), w, 0)
    if kind == 'glitch':
        rng = rng or np.random.default_rng(i)
        base = (A if p < 0.5 else B).copy()
        other = B if p < 0.5 else A
        f = 1 - abs(2 * p - 1)
        for _ in range(int(12 * f) + 2):
            y = rng.integers(0, H); h = rng.integers(8, 90); dx = int(rng.normal(0, 80 * f))
            src = other if rng.random() < 0.35 else base
            base[y:y + h] = np.roll(src[y:y + h], dx, 1)
        s = int(14 * f)
        base[..., 2] = np.roll(base[..., 2], s, 1); base[..., 0] = np.roll(base[..., 0], -s, 1)
        return base
    if kind == 'brulure':  # fondu + brûlure de pellicule / fuite de lumière
        mix = cv2.addWeighted(A, 1 - ease(p), B, ease(p), 0).astype(np.float32)
        leak = light_leak(W, H, p, seed=i) * (1 - abs(2 * p - 1)) ** 0.7 * 1.3
        return np.clip(mix + leak, 0, 255).astype(np.uint8)
    if kind == 'rideau':  # volet doux
        x = int(ease(p) * (W + 200)) - 100
        m = np.clip((np.arange(W) - x) / 100 + 0.5, 0, 1)[None, :, None]
        return (B * (1 - m) + A * m).astype(np.uint8)
    raise ValueError(kind)

SONS_TRANSITION = {'whip_gauche': 'whoosh', 'whip_droite': 'whoosh', 'whip_haut': 'whoosh', 'whip_bas': 'whoosh',
                   'zoom': 'whoosh_long', 'glitch': 'glitch', 'flash': None, 'brulure': None, 'fondu': None,
                   'fondu_noir': None, 'fondu_blanc': None, 'rideau': 'whoosh_inverse'}

# ============================================================ textes (ASS)
def ass_time(t):
    t = max(0, t); h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f'{h}:{m:02d}:{s:05.2f}'

class Textes:
    def __init__(self, W, H):
        self.W, self.H = W, H; self.k = min(W, H) / 1080; self.ev = []
    def _add(self, t, d, txt, style='Base', layer=1):
        self.ev.append(f'Dialogue: {layer},{ass_time(t)},{ass_time(t + d)},{style},,0,0,0,,{txt}')
    def px(self, v): return int(v * self.k)

    def lieu(self, t, d, nom, sous='', pos='bas_gauche'):
        """Grand nom de lieu (lettres qui s'écartent) + petit sous-titre + trait animé."""
        W, H, k = self.W, self.H, self.k; ms = int(d * 1000)
        x = self.px(110); y = H - self.px(215)
        if pos == 'centre': x, an = W // 2, 2; y = H // 2 + self.px(40)
        else: an = 1
        self._add(t, d, f'{{\\an{an}\\pos({x},{y})\\fnAnton\\fs{self.px(235)}\\c&HFFFFFF&\\bord0\\shad{self.px(5)}\\4c&H000000&\\4a&H80&'
                        f'\\fsp{self.px(2)}\\fad(250,350)\\t(0,{ms},\\fsp{self.px(14)})\\blur0.6}}{nom.upper()}')
        if sous:
            self._add(t + 0.25, d - 0.25, f'{{\\an{an + 6}\\pos({x},{y + self.px(22)})\\fnMontserrat SemiBold\\fs{self.px(56)}\\c&HE8F4FF&'
                                         f'\\bord{self.px(2)}\\3c&H000000&\\3a&HA0&\\shad{self.px(2)}\\4a&H70&\\fsp{self.px(3)}\\fad(300,300)}}{sous}')
        lw = self.px(300); ly = y + self.px(4)
        lx = x if an == 1 else x - lw // 2
        self._add(t + 0.1, d - 0.1, f'{{\\an7\\pos({lx},{ly})\\p1\\c&H4A6BFF&\\bord0\\shad0\\fscx0\\t(0,450,\\fscx100)\\fad(0,300)}}'
                                    f'm 0 0 l {lw} 0 {lw} {self.px(9)} 0 {self.px(9)}{{\\p0}}')

    def titre(self, t, d, txt, taille=300, police='Anton', y=None, couleur='FFFFFF', espacement=(4, 30), fad=(300, 500)):
        ms = int(d * 1000); y = y if y is not None else self.H // 2
        self._add(t, d, f'{{\\an5\\pos({self.W // 2},{y})\\fn{police}\\fs{self.px(taille)}\\c&H{couleur}&\\bord0'
                        f'\\shad{self.px(6)}\\4a&H60&\\3c&H000000&\\3a&HC0&\\bord{self.px(3)}\\fsp{self.px(espacement[0])}\\fad({fad[0]},{fad[1]})'
                        f'\\t(0,{ms},0.6,\\fsp{self.px(espacement[1])})}}{txt}')

    def sous_titre(self, t, d, txt, y=None, taille=60, police='Montserrat SemiBold', couleur='FFFFFF', fad=(250, 300)):
        y = y if y is not None else self.H // 2 + self.px(130)
        self._add(t, d, f'{{\\an5\\pos({self.W // 2},{y})\\fn{police}\\fs{self.px(taille)}\\c&H{couleur}&\\bord0'
                        f'\\bord{self.px(2)}\\3c&H000000&\\3a&HA0&\\shad{self.px(2)}\\4a&H60&\\fsp{self.px(6)}\\fad({fad[0]},{fad[1]})}}{txt}')

    def meme(self, t, d, txt, pos='haut', taille=150):
        """Texte façon mème : gros, blanc, contour noir, apparition « pop »."""
        y = self.px(60) if pos == 'haut' else self.H - self.px(60)
        an = 8 if pos == 'haut' else 2
        self._add(t, d, f'{{\\an{an}\\pos({self.W // 2},{y})\\fnAnton\\fs{self.px(taille)}\\c&HFFFFFF&\\3c&H000000&'
                        f'\\bord{self.px(10)}\\shad0\\fscx135\\fscy135\\t(0,140,\\fscx100\\fscy100)\\fad(0,150)}}{txt.upper()}')

    def bulle(self, t, d, txt, x=None, y=None, taille=66):
        """Sous-titre « parole » dans un bandeau (ce que dit quelqu'un)."""
        x = x or self.W // 2; y = y or self.H - self.px(90)
        self._add(t, d, f'{{\\an2\\pos({x},{y})\\fnMontserrat ExtraBold\\fs{self.px(taille)}\\c&H000000&\\3c&HFFFFFF&'
                        f'\\bord{self.px(14)}\\shad0\\fscx80\\fscy80\\t(0,120,\\fscx100\\fscy100)\\fad(0,120)}}{txt}', style='Boite')

    def manuscrit(self, t, d, txt, x=None, y=None, taille=122, police='Dancing Script', couleur='E6F2FF', an=5, rot=0):
        x = x if x is not None else self.W // 2; y = y if y is not None else self.H // 2
        self._add(t, d, f'{{\\an{an}\\pos({x},{y})\\frz{rot}\\fn{police}\\fs{self.px(taille)}\\c&H{couleur}&\\bord0'
                        f'\\shad{self.px(4)}\\4a&H50&\\blur10\\t(0,700,\\blur0.6)\\fad(600,600)}}{txt}')

    def vhs_osd(self, t, d, haut='PLAY', date_txt=None, rew=False):
        k = lambda v: self.px(v * 1.35)
        if rew:
            tri = f'm 0 {k(22)} l {k(26)} 0 {k(26)} {k(44)} m {k(28)} {k(22)} l {k(54)} 0 {k(54)} {k(44)}'
        else:
            tri = f'm 0 0 l {k(36)} {k(22)} 0 {k(44)}'
        st = f'\\bord0\\shad{k(3)}\\4a&H30&'
        self._add(t, d, f'{{\\an7\\pos({k(70)},{k(60)})\\p1\\c&HFFFFFF&{st}}}{tri}{{\\p0}}')
        self._add(t, d, f'{{\\an4\\pos({k(70) + k(72)},{k(60) + k(24)})\\fnVT323\\fs{k(80)}\\c&HFFFFFF&{st}}}{haut}')
        if date_txt:
            self._add(t, d, f'{{\\an6\\pos({self.W - k(70)},{self.H - k(70)})\\fnVT323\\fs{k(74)}\\c&HFFFFFF&{st}}}{date_txt}')

    def ecrire(self, path):
        k = self.k
        head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {self.W}
PlayResY: {self.H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Base,Montserrat,{int(48 * k)},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,0,2,5,40,40,40,1
Style: Boite,Montserrat ExtraBold,{int(48 * k)},&H00000000,&H00FFFFFF,&H00FFFFFF,&H00FFFFFF,0,0,0,0,100,100,0,0,3,{int(14 * k)},0,2,40,40,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        open(path, 'w', encoding='utf-8').write(head + '\n'.join(self.ev) + '\n')

# ============================================================ projet
class Projet:
    def __init__(self, nom, W=1920, H=1080, fps=30, dossier=None):
        self.nom, self.W, self.H, self.fps = nom, W, H, fps
        self.dossier = dossier or f'{ATELIER}/rendus/{nom}'
        self.cache = f'{ATELIER}/cache'
        os.makedirs(self.dossier, exist_ok=True); os.makedirs(self.cache, exist_ok=True)
        self.plans, self.trans, self.musiques, self.sfx = [], [], [], []
        self.textes = Textes(W, H); self.fx = Effets(W, H)
        self.ambiances = []  # (son, t0, t1, gain)

    # ---------- construction
    def plan(self, **p):
        """type: video | photo | pile | carte | ecran | rembobinage ; duree obligatoire (secondes à l'écran)."""
        p.setdefault('look', 'vacances'); self.plans.append(p)
        if len(self.plans) > 1 and len(self.trans) < len(self.plans) - 1: self.trans.append(dict(type='coupe', duree=0))
        return len(self.plans) - 1
    def transition(self, type='coupe', duree=0.4, son='auto', gain=-4):
        """Transition entre le dernier plan ajouté et le suivant."""
        self.trans.append(dict(type=type, duree=duree if type != 'coupe' else 0, son=son, gain=gain))
    def musique(self, fichier, debut, offset=0.0, fin=None, gain=0.0, fondu_in=0.0, fondu_out=1.5):
        self.musiques.append(dict(fichier=fichier, debut=debut, offset=offset, fin=fin, gain=gain, fin_in=fondu_in, fin_out=fondu_out))
    def son(self, nom, t, gain=0.0):
        self.sfx.append((nom, t, gain))
    def ambiance(self, nom, t0, t1, gain=-18):
        self.ambiances.append((nom, t0, t1, gain))

    # ---------- timeline
    def timeline(self):
        fps = self.fps; S = [0]; N = [int(round(p['duree'] * fps)) for p in self.plans]
        while len(self.trans) < len(self.plans) - 1: self.trans.append(dict(type='coupe', duree=0))
        D = [int(round(t['duree'] * fps)) for t in self.trans]
        for i in range(1, len(self.plans)): S.append(S[i - 1] + N[i - 1] - D[i - 1])
        return S, N, D
    def debut(self, i): S, _, _ = self.timeline(); return S[i] / self.fps
    def coupe(self, i):
        """Instant (s) du milieu de la transition entre le plan i et i+1."""
        S, N, D = self.timeline(); return (S[i + 1] + D[i] / 2) / self.fps
    def duree_totale(self):
        S, N, D = self.timeline(); return (S[-1] + N[-1]) / self.fps

    # ---------- rendu d'un plan
    def _cle(self, p):
        q = {k: v for k, v in p.items() if k not in ('textes', 'sons', 'son', 'duck')}
        q['_WH'] = (self.W, self.H, self.fps, 7)
        q['_v'] = VERSIONS.get(p['type'], 1)
        if p['type'] == 'rembobinage': q['_src'] = [self._cle(self.plans[j]) for j in p['plans']]
        for k in ('src',):
            if k in q and os.path.exists(q[k]): q['_mt'] = os.path.getmtime(q[k])
        return hashlib.md5(json.dumps(q, sort_keys=True, default=str).encode()).hexdigest()[:16]
    def fichier_plan(self, i): return f'{self.cache}/{self._cle(self.plans[i])}.mov'

    def rendre_plan(self, i):
        p = self.plans[i]; out = self.fichier_plan(i)
        if os.path.exists(out): return out
        tmp = out + '.tmp.mov'
        W, H, fps = self.W, self.H, self.fps; n_out = int(round(p['duree'] * fps))
        wr = Ecrivain(tmp, W, H, fps)
        gen = getattr(self, '_gen_' + p['type'])(p, n_out)
        nost = p.get('nostalgie', p['look'] == 'nostalgie')
        rng = np.random.default_rng(i)
        for k, f in enumerate(gen):
            if k >= n_out: break
            if nost:
                f = self.fx.vignette(f, 0.45)
                b = 1 + 0.025 * math.sin(k * 1.7) * math.sin(k * 0.37)
                if p['type'] in ('video', 'photo'):
                    f = _shift(f, rng.normal(0, 0.6), rng.normal(0, 0.6))
                f = self.fx.grain_(cv2.convertScaleAbs(f, alpha=b), k, 7)
            elif p.get('vignette', 0):
                f = self.fx.vignette(f, p['vignette'])
            wr.ecrire(f)
        wr.fermer(); os.replace(tmp, out)
        return out

    def _gen_video(self, p, n_out):
        W, H, fps = self.W, self.H, self.fps
        info = probe(p['src']); v = p.get('vitesse', 1.0)
        gel = p.get('gel')  # (t_ecran, duree, style)
        gel_d = gel[1] if gel else 0
        span = (p['duree'] - gel_d) * v
        debut = p.get('debut', 0.0)
        zmax = max([1.0] + [z for z in p.get('zoom', (1, 1))] + [pp[1] for pp in p.get('punch', [])]) * (1.0 if p.get('cadrage', 'remplir') == 'remplir' else 1.0)
        c = max(W / info['w'], H / info['h']) if p.get('cadrage', 'remplir') == 'remplir' else min(W / info['w'], H / info['h'])
        dw = int(min(info['w'], info['w'] * c * zmax * 1.05)) // 2 * 2; dh = int(dw * info['h'] / info['w']) // 2 * 2
        vf = []
        if info['hdr']: vf.append(HDR_TM)
        if p.get('inverse'): vf.append('reverse')
        vf.append(f'setpts=(PTS-STARTPTS)/{v}')
        if p.get('lisse') and v < 1: vf.append(f'minterpolate=fps={fps}:mi_mode=mci:mc_mode=aobmc:vsbmc=1')
        else: vf.append(f'fps={fps}')
        vf.append(f'scale={dw}:{dh}:flags=lanczos')
        look = 'nb' if p.get('nb') else p['look']
        if look != 'neutre': vf.append(f'lut3d={lut_path(look)}:interp=tetrahedral')
        if p.get('stab'):
            trf = f'{self.cache}/{self._cle(p)}.trf'
            if not os.path.exists(trf):
                subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(debut), '-t', str(span / v * v), '-i', p['src'], '-vf',
                                f'vidstabdetect=shakiness=6:accuracy=12:result={trf}', '-f', 'null', '-'])
            vf.insert(0, f'vidstabtransform=input={trf}:smoothing=20:zoom=4')
        rd = Lecteur(['-ss', f'{debut:.3f}', '-t', f'{span + 0.2:.3f}', '-i', p['src'], '-vf', ','.join(vf), '-an'], dw, dh)
        z0, z1 = p.get('zoom', (1.0, 1.0)); f0 = p.get('focus', (0.5, 0.5)); f1 = p.get('focus_fin', f0)
        mode = p.get('cadrage', 'remplir'); frozen = None
        for k in range(n_out):
            t = k / fps
            if gel and gel[0] <= t < gel[0] + gel_d:
                if frozen is None: frozen = rd.lire() if rd.last is None else rd.last
                src = frozen; tt = gel[0]
            else:
                src = rd.lire(); tt = t - (gel_d if gel and t >= gel[0] + gel_d else 0)
            if src is None: src = np.zeros((dh, dw, 3), np.uint8)
            z, fx, fy, dx, dy = camera(p, t)
            f = transform(src, W, H, z, fx, fy, dx, dy, mode=mode)
            if gel and gel[0] <= t < gel[0] + gel_d and len(gel) > 2 and gel[2] == 'nb':
                f = cv2.cvtColor(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
                ff = min(1, (t - gel[0]) / 0.08); f = cv2.addWeighted(f, 1, np.full_like(f, 255), (1 - ff) * 0.6, 0)
            yield f
        rd.fermer()

    def _gen_photo(self, p, n_out):
        W, H, fps = self.W, self.H, self.fps
        img = charger_photo(p['src'], 'nb' if p.get('nb') else p['look'])
        z0, z1 = p.get('zoom', (1.0, 1.12)); f0 = p.get('focus', (0.5, 0.5)); f1 = p.get('focus_fin', f0)
        mode = p.get('cadrage', 'remplir')
        h, w = img.shape[:2]; c = max(W / w, H / h) * max(z0, z1)
        if c < 1: img = cv2.resize(img, (int(w * c * 1.5), int(h * c * 1.5)), interpolation=cv2.INTER_AREA) if c * 1.5 < 1 else img
        p = dict(p); p.setdefault('zoom', (z0, z1))
        for k in range(n_out):
            z, fx, fy, dx, dy = camera(p, k / fps)
            yield transform(img, W, H, z, fx, fy, dx, dy, mode=mode, interp=cv2.INTER_CUBIC)

    def _gen_pile(self, p, n_out):
        """Polaroïds qui tombent un à un sur une table ; la caméra avance doucement."""
        W, H, fps = self.W, self.H, self.fps; rng = np.random.default_rng(p.get('seed', 4))
        bg = fond_table(W, H, seed=p.get('seed', 4))
        larg = int(min(W, H) * p.get('taille', 0.62))
        cards = []
        for j, ph in enumerate(p['photos']):
            src = ph['src'] if isinstance(ph, dict) else ph
            leg = ph.get('legende', '') if isinstance(ph, dict) else ''
            foc = ph.get('focus', (0.5, 0.5)) if isinstance(ph, dict) else (0.5, 0.5)
            sp = fabriquer_polaroid(charger_photo(src, p['look']), larg, leg, foc, seed=j)
            cx = W / 2 + rng.uniform(-0.17, 0.17) * W; cy = H / 2 + rng.uniform(-0.06, 0.06) * H
            if W < H: cx = W / 2 + rng.uniform(-0.1, 0.1) * W; cy = H / 2 + rng.uniform(-0.12, 0.12) * H
            rot = rng.uniform(-9, 9); t_in = ph.get('t', None) if isinstance(ph, dict) else None
            cards.append(dict(sp=sp, cx=cx, cy=cy, rot=rot, t=t_in if t_in is not None else j * p.get('intervalle', 1.2)))
        settled = bg.copy(); n_set = 0; chute = 0.42
        for k in range(n_out):
            t = k / fps
            while n_set < len(cards) and t >= cards[n_set]['t'] + chute:
                c = cards[n_set]; coller(settled, c['sp'], c['cx'], c['cy'], 1.0, c['rot']); n_set += 1
            f = settled.copy()
            for c in cards[n_set:]:
                if c['t'] <= t < c['t'] + chute:
                    q = (t - c['t']) / chute; e = ease(q, 'out')
                    sc = 1.35 - 0.35 * e; rot = c['rot'] + (1 - e) * 14; al = min(1, q * 3)
                    coller(f, c['sp'], c['cx'] + (1 - e) * W * 0.05, c['cy'] - (1 - e) * H * 0.08, sc, rot, ombre=0.45 * e, alpha=al)
            zc = 1 + p.get('travelling', 0.10) * (k / max(1, n_out - 1))
            yield _zoom(f, zc)

    def _gen_carte(self, p, n_out):
        W, H, fps = self.W, self.H, self.fps; carte = Carte(W, H)
        a, b = carte.stops[p['de']], carte.stops[p['a']]
        pa, pb = _proj(a['lon'], a['lat']), _proj(b['lon'], b['lat'])
        tous = [_proj(x['lon'], x['lat']) for x in carte.stops.values()]
        cam0 = carte.vue(tous, 1.12) if p.get('cam_depart') is None else p['cam_depart']
        cam1 = carte.vue([pa, pb], p.get('marge', 2.4))
        t_trace = p.get('t_trace', (0.15, 0.8))
        for k in range(n_out):
            q = k / max(1, n_out - 1); t = k / fps
            e = ease(min(1, q / 0.55), 'inout')
            cam = tuple(cam0[j] + (cam1[j] - cam0[j]) * e for j in range(3))
            pr = min(1, max(0, (q - t_trace[0]) / (t_trace[1] - t_trace[0])))
            yield carte.frame(cam, p.get('visites', [p['de']]), (p['de'], p['a']), pr, t)

    def _gen_ecran(self, p, n_out):
        W, H = self.W, self.H; c = p.get('couleur', (16, 14, 12))
        f = np.zeros((H, W, 3), np.uint8); f[:] = c
        if p.get('degrade'):
            c2 = np.array(p['degrade'], np.float32); yy = np.linspace(0, 1, H)[:, None, None]
            f = (np.array(c, np.float32) * (1 - yy) + c2 * yy).astype(np.uint8) * np.ones((1, W, 1), np.uint8)
        for k in range(n_out): yield f

    def _gen_rembobinage(self, p, n_out):
        """Rembobinage VHS : relit des plans précédents à l'envers en accéléré, avec effets de cassette."""
        W, H, fps = self.W, self.H, self.fps; frames = []
        for i in p['plans']:
            rd = Lecteur(['-i', self.fichier_plan(i), '-vf', f'select=not(mod(n\\,2)),scale={W // 2}:{H // 2}', '-fps_mode', 'passthrough'], W // 2, H // 2)
            while True:
                f = rd.lire()
                if rd.eof or len(frames) > 4000: break
                frames.append(f)
            rd.fermer()
        frames = frames[::-1]; rng = np.random.default_rng(9)
        step = max(1, len(frames) / max(1, n_out))
        for k in range(n_out):
            src = frames[min(len(frames) - 1, int(k * step))] if frames else np.zeros((H // 2, W // 2, 3), np.uint8)
            f = cv2.resize(src, (W, H), interpolation=cv2.INTER_LINEAR)
            force = 0.7 + 0.5 * (k / n_out)
            yield vhs(f, k / fps, rng, force)

    # ---------- audio
    def _audio_plan(self, i):
        p = self.plans[i]
        if p['type'] != 'video' or not p.get('son', 0): return None
        if not probe(p['src'])['son']: return None
        v = p.get('vitesse', 1.0); gel = p.get('gel'); gel_d = gel[1] if gel else 0
        span = (p['duree'] - gel_d) * v
        out = f'{self.cache}/a_{self._cle(p)}_{i}.wav'
        if not os.path.exists(out):
            af = []
            if p.get('inverse'): af.append('areverse')
            x = v; chain = []
            while x < 0.5: chain.append('atempo=0.5'); x /= 0.5
            while x > 2.0: chain.append('atempo=2.0'); x /= 2.0
            chain.append(f'atempo={x:.4f}'); af += chain
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', f"{p.get('debut', 0):.3f}", '-t', f'{span:.3f}', '-i', p['src'],
                            '-vn', '-af', ','.join(af), '-ar', str(SR), '-ac', '2', out], check=True)
        a, _ = sf.read(out, dtype='float32', always_2d=True)
        if gel:
            cut = int(gel[0] * SR); a = np.concatenate([a[:cut], np.zeros((int(gel_d * SR), 2), np.float32), a[cut:]])
        return a

    def mixer(self, out):
        total = self.duree_totale(); n = int((total + 0.5) * SR)
        mus = np.zeros((n, 2), np.float32); dia = np.zeros((n, 2), np.float32); fx = np.zeros((n, 2), np.float32)
        duck = np.zeros(n, np.float32)
        def place(buf, a, t, g=1.0):
            i = int(round(t * SR))
            if i < 0: a = a[-i:]; i = 0
            j = min(n, i + len(a))
            if j > i: buf[i:j] += a[:j - i] * g
        def lire(path):
            a, sr = sf.read(path, dtype='float32', always_2d=True)
            if a.shape[1] == 1: a = np.repeat(a, 2, 1)
            if sr != SR:
                r = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-ar', str(SR), '-ac', '2', '-f', 'f32le', '-'], capture_output=True)
                a = np.frombuffer(r.stdout, np.float32).reshape(-1, 2)
            return a
        # musiques
        for m in self.musiques:
            a = lire(m['fichier'])[int(m['offset'] * SR):]
            fin = m['fin'] if m['fin'] is not None else total
            a = a[:int((fin - m['debut']) * SR)].copy()
            if m['fin_in'] > 0: k = int(m['fin_in'] * SR); a[:k] *= np.linspace(0, 1, min(k, len(a)))[:, None]
            if m['fin_out'] > 0:
                k = min(len(a), int(m['fin_out'] * SR)); a[len(a) - k:] *= np.linspace(1, 0, k)[:, None] ** 1.5
            place(mus, a, m['debut'], 10 ** (m['gain'] / 20))
        # sons des plans + ducking
        S, N, D = self.timeline()
        for i, p in enumerate(self.plans):
            a = self._audio_plan(i)
            if a is not None:
                k = min(len(a), int(0.04 * SR)); a = a.copy(); a[:k] *= np.linspace(0, 1, k)[:, None]; a[-k:] *= np.linspace(1, 0, k)[:, None]
                place(dia, a, S[i] / self.fps, p.get('son', 0))
            if p.get('duck'):
                t0 = S[i] / self.fps; t1 = t0 + N[i] / self.fps
                i0, i1 = int(t0 * SR), int(t1 * SR); duck[i0:i1] = np.maximum(duck[i0:i1], p['duck'])
            for s in p.get('sons', []):
                self.sfx.append((s['son'], S[i] / self.fps + s['t'], s.get('gain', 0)))
            for tx in p.get('textes', []):
                pass
        # sons des transitions
        for i, tr in enumerate(self.trans):
            nom = SONS_TRANSITION.get(tr['type']) if tr.get('son', 'auto') == 'auto' else tr.get('son')
            if nom:
                a = lire(f'{SONS}/{nom}.wav'); c = self.coupe(i)
                lead = {'whoosh': 0.5, 'whoosh_long': 0.55, 'whoosh_inverse': 0.5, 'glitch': 0.5, 'riser': 1.0,
                        'impact': 0.0, 'declic_photo': 0.0, 'scratch': 0.1}.get(nom, 0.5)
                place(fx, a, c - lead * len(a) / SR, 10 ** (tr.get('gain', -4) / 20))
        for nom, t, g in self.sfx:
            place(fx, lire(f'{SONS}/{nom}.wav'), t, 10 ** (g / 20))
        for nom, t0, t1, g in self.ambiances:
            a = lire(f'{SONS}/{nom}.wav'); L = int((t1 - t0) * SR); reps = int(np.ceil(L / len(a)))
            a = np.tile(a, (reps, 1))[:L].copy(); k = min(L, int(1.0 * SR))
            a[:k] *= np.linspace(0, 1, k)[:, None]; a[-k:] *= np.linspace(1, 0, k)[:, None]
            place(fx, a, t0, 10 ** (g / 20))
        # ducking lissé
        if duck.any():
            from scipy.ndimage import uniform_filter1d
            g = 10 ** (-uniform_filter1d(duck, int(0.35 * SR)) / 20)
            mus *= g[:, None]
        mix = mus + dia + fx
        tmp = out + '.brut.wav'; sf.write(tmp, mix, SR, subtype='FLOAT')
        r = subprocess.run(['ffmpeg', '-v', 'info', '-hide_banner', '-i', tmp, '-af', 'loudnorm=I=-14:TP=-1.0:LRA=11:print_format=json', '-f', 'null', '-'],
                           capture_output=True, text=True).stderr
        js = json.loads(r[r.rfind('{'):r.rfind('}') + 1])
        af = (f"loudnorm=I=-14:TP=-1.0:LRA=11:measured_I={js['input_i']}:measured_TP={js['input_tp']}:measured_LRA={js['input_lra']}"
              f":measured_thresh={js['input_thresh']}:offset={js['target_offset']}:linear=true,aresample=48000,alimiter=limit=0.85:level=0")
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', tmp, '-af', af, '-ar', str(SR), out], check=True)
        os.remove(tmp)
        return out

    # ---------- rendu final
    def rendre(self, sortie=None, workers=3, apercu=False):
        sortie = sortie or f'{self.dossier}/{self.nom}.mp4'
        # textes rattachés aux plans
        S, N, D = self.timeline()
        for i, p in enumerate(self.plans):
            for tx in p.get('textes', []):
                tx = dict(tx); kind = tx.pop('style'); t = S[i] / self.fps + tx.pop('t', 0)
                getattr(self.textes, kind)(t, tx.pop('d'), **tx)
        # 1) plans (en parallèle, sauf les rembobinages qui dépendent des autres)
        normaux = [i for i, p in enumerate(self.plans) if p['type'] != 'rembobinage']
        with ThreadPoolExecutor(workers) as ex: list(ex.map(self.rendre_plan, normaux))
        for i, p in enumerate(self.plans):
            if p['type'] == 'rembobinage': self.rendre_plan(i)
        # 2) audio
        wav = self.mixer(f'{self.dossier}/{self.nom}_mix.wav')
        # 3) textes
        ass = f'{self.dossier}/{self.nom}.ass'; self.textes.ecrire(ass)
        # 4) assemblage + transitions + incrustation des textes
        W, H, fps = self.W, self.H, self.fps
        vf = f"subtitles={ass}:fontsdir={FONTS}"
        if apercu: vf += f",scale={W // 2}:{H // 2}"
        wr = Ecrivain(sortie, W, H, fps, vf=vf, codec='h264', audio=wav)
        total = S[-1] + N[-1]
        lecteurs = {}
        def frame_de(i, k):
            if i not in lecteurs: lecteurs[i] = [Lecteur(['-i', self.fichier_plan(i)], W, H), -1]
            rd = lecteurs[i]
            while rd[1] < k: rd[0].lire(); rd[1] += 1
            return rd[0].last if rd[0].last is not None else np.zeros((H, W, 3), np.uint8)
        for g in range(total):
            act = [i for i in range(len(self.plans)) if S[i] <= g < S[i] + N[i]]
            if len(act) == 1:
                f = frame_de(act[0], g - S[act[0]])
            else:
                a, b = act[0], act[1]; d = D[a]
                p = (g - S[b] + 0.5) / d
                f = transition(self.trans[a]['type'], frame_de(a, g - S[a]), frame_de(b, g - S[b]), p, i=a)
            for i in list(lecteurs):
                if g >= S[i] + N[i]: lecteurs[i][0].fermer(); del lecteurs[i]
            wr.ecrire(f)
        wr.fermer()
        return sortie


def exporter_leger(src, out, mbps=4.5, hauteur=1080):
    """Version légère (téléphone / WhatsApp) : 2 passes x264 au débit visé."""
    log = out + '.log'
    common = ['-vf', f'scale=-2:{hauteur}:flags=lanczos', '-c:v', 'libx264', '-preset', 'slow', '-b:v', f'{mbps}M',
              '-maxrate', f'{mbps * 1.6}M', '-bufsize', f'{mbps * 3}M', '-pix_fmt', 'yuv420p', '-profile:v', 'high',
              '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-passlogfile', log]
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', src] + common + ['-pass', '1', '-an', '-f', 'null', '-'], check=True)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', src] + common + ['-pass', '2', '-c:a', 'aac', '-b:a', '192k',
                    '-movflags', '+faststart', out], check=True)
    for f in os.listdir(os.path.dirname(out) or '.'):
        if f.startswith(os.path.basename(log)): os.remove(os.path.join(os.path.dirname(out) or '.', f))
    return out


def remixer(projet, video):
    """Refait seulement le mixage audio d'un rendu existant (sans recalculer l'image)."""
    S, N, D = projet.timeline()
    wav = projet.mixer(f'{projet.dossier}/{projet.nom}_mix.wav')
    tmp = video + '.tmp.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', video, '-i', wav, '-map', '0:v', '-map', '1:a', '-c:v', 'copy',
                    '-c:a', 'aac', '-b:a', '320k', '-movflags', '+faststart', tmp], check=True)
    os.replace(tmp, video)
    return video
