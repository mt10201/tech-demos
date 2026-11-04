"""Photo → relief: a raised pet-portrait bas-relief in a memorial-stone frame.

photo ─► BiRefNet-lite (MIT) mask ─► crop head + chest ─► Depth Anything V2 Small (Apache-2.0) depth
      ─► gradient-domain compression + depth unsharp + photo high-pass ─► height field (mm)
      ─► rounded-trapezoid slab, recessed niche, hammered border, engraved text
      ─► one height field ∩ outline prism (manifold3d) ─► watertight, single shell, genus 0 STL.

It is a height field by construction: no undercuts, so it is mold friendly. Both models run on CPU with
onnxruntime (≈1 s depth, ≈10 s mask on 8 cores). Weights are fetched once from Hugging Face (~320 MB)."""
from __future__ import annotations

import functools
import os
import time
from dataclasses import dataclass, field

import numpy as np
import trimesh
from PIL import Image
from scipy import fft, ndimage as ndi

import scan_repair as sr

SEG_MODEL = ("onnx-community/BiRefNet_lite-ONNX", "onnx/model.onnx")          # MIT
DEPTH_MODEL = ("onnx-community/depth-anything-v2-small", "onnx/model.onnx")    # Apache-2.0
LICENCE_NOTE = ("Models: BiRefNet-lite (MIT) for the background and Depth Anything V2 **Small** (Apache-2.0) "
                "for depth; both allow commercial use. (DA-V2 Base/Large are CC-BY-NC and Depth Pro and BRIA "
                "RMBG are non-commercial, so they are not used.) The photo must be your own or cleared; "
                "a customer's pet photo needs their permission.")
_MEAN = np.array([0.485, 0.456, 0.406], np.float32)
_STD = np.array([0.229, 0.224, 0.225], np.float32)


@dataclass
class ReliefParams:
    width: float = 150.0          # frame, mm
    height: float = 140.0
    thickness: float = 25.0
    niche_depth: float = 6.0
    relief_mm: float = 12.0       # max relief above the niche floor (scaled with frame height / 150)
    detail_mm: float = 0.6        # photo high-pass amplitude
    compress: float = 0.5         # 0 = raw depth, 1 = strong gradient compression
    sharpen: float = 1.5          # depth unsharp (mid-scale form: eyes, brows, muzzle)
    smooth_mm: float = 0.25
    feather_mm: float = 2.0
    plateau: float = 0.18       # share of the relief height given to the whole silhouette
    detail_gate: float = 2.6    # photo high-pass below ~this many std devs is suppressed
    texture: bool = True
    texture_mm: float = 0.22
    text: str = ""
    text_mm: float = 9.0
    res_mm: float = 0.25
    crop: tuple | None = None     # (x0, y0, x1, y1) as fractions of the photo; None = auto head + chest
    seed: int = 7


@dataclass
class ReliefReport:
    faces: int = 0
    watertight: bool = False
    is_volume: bool = False
    euler: int = 0
    pieces: int = 0
    extents_mm: tuple = ()
    volume_cm3: float = 0.0
    fits_bed: bool = False
    timings: dict = field(default_factory=dict)

    def ok(self) -> bool:
        return self.watertight and self.is_volume and self.euler == 2 and self.pieces == 1


# ---------------------------------------------------------------- models (onnxruntime, CPU)
@functools.lru_cache(maxsize=4)
def _session(repo: str, fn: str):
    import onnxruntime as ort
    from huggingface_hub import hf_hub_download

    so = ort.SessionOptions()
    so.intra_op_num_threads = os.cpu_count() or 4
    return ort.InferenceSession(hf_hub_download(repo, fn), so, providers=["CPUExecutionProvider"])


def _prep(img: Image.Image, w: int, h: int) -> np.ndarray:
    a = np.asarray(img.convert("RGB").resize((w, h), Image.BICUBIC), np.float32) / 255
    return ((a - _MEAN) / _STD).transpose(2, 0, 1)[None].astype(np.float32)


def segment(img: Image.Image) -> np.ndarray:
    """Foreground probability (H, W) in 0..1 at the photo's size (BiRefNet-lite, 1024²)."""
    s = _session(*SEG_MODEL)
    o = s.run(None, {s.get_inputs()[0].name: _prep(img, 1024, 1024)})[-1][0, 0]
    m = 1 / (1 + np.exp(-o.astype(np.float64)))
    return np.asarray(Image.fromarray((m * 255).astype(np.uint8)).resize(img.size, Image.BILINEAR),
                      np.float32) / 255


def depth(img: Image.Image, long_side: int = 1036) -> np.ndarray:
    """Relative inverse depth (bigger = nearer) at the image's size (Depth Anything V2 Small)."""
    s = _session(*DEPTH_MODEL)
    k = long_side / max(img.size)
    w, h = (max(14, int(round(v * k / 14)) * 14) for v in img.size)
    o = s.run(None, {s.get_inputs()[0].name: _prep(img, w, h)})[0][0]
    return ndi.zoom(o, (img.size[1] / o.shape[0], img.size[0] / o.shape[1]), order=1)


def auto_crop(mask: np.ndarray, aspect: float) -> tuple:
    """Head + chest box (pixels) from the mask: subject width × 1.06, height = width × aspect, from the top."""
    H, W = mask.shape
    ys, xs = np.nonzero(mask > 0.5)
    if len(ys) == 0:
        return 0, 0, W, H
    top = ys.min()
    band = (ys < top + 0.45 * (ys.max() - top))           # ears + head set the width
    x0, x1 = np.percentile(xs[band], [0.5, 99.5])
    cw = (x1 - x0) * 1.10
    ch = cw * aspect
    cx = (x0 + x1) / 2
    y0 = top - 0.07 * ch
    box = [cx - cw / 2, y0, cx + cw / 2, y0 + ch]
    return tuple(int(round(v)) for v in box)


# ---------------------------------------------------------------- bas-relief from depth
def _poisson(gx: np.ndarray, gy: np.ndarray) -> np.ndarray:
    """Least-squares height from a gradient field (Neumann, DCT solve)."""
    H, W = gx.shape
    div = np.zeros((H, W))
    div[:, 1:] += gx[:, 1:] - gx[:, :-1]; div[:, 0] += gx[:, 0]
    div[1:, :] += gy[1:, :] - gy[:-1, :]; div[0, :] += gy[0, :]
    d = fft.dctn(div, type=2, norm="ortho")
    ky = 2 * np.cos(np.pi * np.arange(H) / H) - 2
    kx = 2 * np.cos(np.pi * np.arange(W) / W) - 2
    den = ky[:, None] + kx[None, :]
    den[0, 0] = 1
    d /= den; d[0, 0] = 0
    return fft.idctn(d, type=2, norm="ortho")


def bas_relief(disp: np.ndarray, mask: np.ndarray, lum: np.ndarray, px_mm: float, p: ReliefParams,
               relief_mm: float) -> np.ndarray:
    """Relief height (mm) on the crop's pixel grid. px_mm = mm per pixel."""
    m = mask > 0.5
    if not m.any():
        return np.zeros_like(disp)
    d = disp - np.percentile(disp[m], 1)
    d = np.clip(d / max(np.percentile(d[m], 99.7), 1e-6), 0, 1.2) * m
    # gradient-domain compression: big steps (silhouette, nose cone) shrink, fine steps stay
    gx = np.zeros_like(d); gy = np.zeros_like(d)
    gx[:, :-1] = d[:, 1:] - d[:, :-1]
    gy[:-1, :] = d[1:, :] - d[:-1, :]
    mag = np.hypot(gx, gy)
    t = np.percentile(mag[m], 60) + 1e-9
    a = 1.0 / (1.0 + p.compress * (mag / t) ** 0.8)
    h = _poisson(gx * a, gy * a)
    h -= np.median(h[~m]) if (~m).any() else h.min()
    h = np.clip(h, 0, None) * m
    # depth unsharp: lift mid-scale form (brow, eye sockets, muzzle) above the overall dome
    s = 4.0 / px_mm
    h = h + p.sharpen * (h - _masked_blur(h, m, s)) * m
    h = np.clip(h, 0, None)
    h /= max(np.percentile(h[m], 99.5), 1e-6)
    h = np.clip(h, 0, 1.05)
    # feather the silhouette into the niche floor
    f = ndi.gaussian_filter(m.astype(np.float32), p.feather_mm / px_mm)
    f = np.clip((f - 0.15) / 0.7, 0, 1); f = f * f * (3 - 2 * f)
    # a low plateau under the whole subject so thin far parts (ears) still stand off the floor
    h = relief_mm * (p.plateau * f + (1 - p.plateau) * h * f)
    # fine detail from the photo, gated so only strong local contrast survives (eyes, nostrils, mouth,
    # ear folds) and the low-contrast blotches of fur/skin don't turn into lumps
    if p.detail_mm > 0:
        L = lum.astype(np.float32)
        hp = L - ndi.gaussian_filter(L, 0.9 / px_mm)
        hp = ndi.gaussian_filter(hp, 0.15 / px_mm)
        hp /= (np.std(hp[m]) + 1e-6)
        g = hp ** 2 / (hp ** 2 + p.detail_gate ** 2)
        h += np.clip(hp * g, -3, 3) / 3 * p.detail_mm * f
    if p.smooth_mm > 0:
        h = ndi.gaussian_filter(h, p.smooth_mm / px_mm)
    return np.clip(h, 0, None)


def _masked_blur(h, m, s):
    w = ndi.gaussian_filter(m.astype(np.float32), s)
    return ndi.gaussian_filter(h * m, s) / np.maximum(w, 1e-3)


# ---------------------------------------------------------------- frame template
def outline(p: ReliefParams):
    """Rounded, slightly irregular trapezoid like a cut memorial stone (shapely polygon, mm)."""
    from shapely.geometry import Polygon

    W, H = p.width, p.height
    pts = [(0, 0), (W, 0), (W * 0.985, H * 0.55), (W * 0.90, H), (W * 0.45, H * 0.955),
           (W * 0.14, H * 0.86), (W * 0.035, H * 0.45)]
    r = min(W, H) * 0.09
    return Polygon(pts).buffer(-r, join_style=1).buffer(r, join_style=1)


def niche_box(p: ReliefParams) -> tuple:
    """(cx, cy, a, b) of the superellipse niche, mm."""
    W, H = p.width, p.height
    bottom = H * (0.19 if p.text.strip() else 0.09)
    top = H * 0.875
    return W * 0.5, (bottom + top) / 2, W * 0.33, (top - bottom) / 2


def _niche_q(X, Y, p):
    """Arch-shaped niche: round top (n = 2.2), squarer bottom (n = 4). q <= 1 inside."""
    cx, cy, a, b = niche_box(p)
    n = np.where(Y > cy, 2.2, 4.0)
    return np.abs((X - cx) / a) ** n + np.abs((Y - cy) / b) ** n


def _edt_mm(inside: np.ndarray, res: float) -> np.ndarray:
    return ndi.distance_transform_edt(inside) * res


def frame_heightfield(p: ReliefParams):
    """Front-surface height (mm) of the slab on a res_mm grid; row 0 is the bottom edge (y = 0)."""
    from skimage.draw import polygon as rpoly

    res = p.res_mm
    o = -1.0 - 0.37 * res          # pad, and keep the outline's straight base off the grid lines
    nx, ny = int(np.ceil((p.width + 2) / res)) + 1, int(np.ceil((p.height + 2) / res)) + 1
    xs, ys = o + np.arange(nx) * res, o + np.arange(ny) * res
    poly = outline(p)
    ex = np.asarray(poly.exterior.coords)
    inside = np.zeros((ny, nx), bool)
    rr, cc = rpoly((ex[:, 1] - o) / res, (ex[:, 0] - o) / res, inside.shape)
    inside[rr, cc] = True
    d_out = _edt_mm(inside, res)
    T = p.thickness
    re = 4.0                                                 # rounded front edge
    z = T - re + np.sqrt(np.clip(re ** 2 - (re - np.minimum(d_out, re)) ** 2, 0, None))
    X, Y = np.meshgrid(xs, ys)
    niche = _niche_q(X, Y, p) <= 1
    d_in = _edt_mm(niche, res)
    wall = 5.0                                               # cove wall ~65°: reads crisp, still draws from a mold
    t = np.minimum(d_in / wall, 1)
    drop = p.niche_depth * (1 - (1 - t) ** 2) * niche
    z = z - drop
    if p.texture and p.texture_mm > 0:
        rng = np.random.default_rng(p.seed)
        n = (ndi.gaussian_filter(rng.standard_normal((ny, nx)), (2.4 / res, 0.9 / res))
             + 0.6 * ndi.gaussian_filter(rng.standard_normal((ny, nx)), 3.5 / res))
        n /= n.std()
        n = -np.log1p(np.exp(-2.0 * n)) / 2.0                 # soft-min: shallow hammer dents, flat tops
        n = (n - n.mean()) / n.std()
        d_niche_out = _edt_mm(~niche, res)
        wt = np.clip((d_niche_out - 1.0) / 4.0, 0, 1)
        z = z + n * p.texture_mm * wt
    if p.text.strip():
        z = z - _text_mask(p, nx, ny, res) * 1.0
    return z, (xs, ys), niche, poly, inside


def _text_mask(p, nx, ny, res):
    from PIL import ImageDraw, ImageFont

    up = 2
    img = Image.new("L", (nx * up, ny * up), 0)
    dr = ImageDraw.Draw(img)
    px = int(p.text_mm / res * up)
    for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"):
        if os.path.exists(f):
            font = ImageFont.truetype(f, px); break
    else:
        font = ImageFont.load_default()
    _, cy, _, b = niche_box(p)
    ytxt = (cy - b) / 2 + 1.0                                # midway between base and niche bottom
    x0, y0, x1, y1 = dr.textbbox((0, 0), p.text, font=font)
    w = x1 - x0
    while w > p.width * 0.7 / res * up and px > 10:
        px = int(px * 0.9); font = font.font_variant(size=px)
        x0, y0, x1, y1 = dr.textbbox((0, 0), p.text, font=font); w = x1 - x0
    hh = y1 - y0
    o = -1.0 - 0.37 * res
    dr.text((((p.width / 2 - o) / res) * up - w / 2 - x0, (ny - (ytxt - o) / res) * up - hh / 2 - y0), p.text, fill=255, font=font)
    a = np.asarray(img.resize((nx, ny), Image.LANCZOS), np.float32)[::-1] / 255
    return ndi.gaussian_filter(a, 0.12 / res)


# ---------------------------------------------------------------- assemble
def place_relief(z, grid, niche, relief_px, p: ReliefParams):
    """Map the crop's relief onto the niche box (mm) and union it (max) with the frame surface."""
    xs, ys = grid
    cx, cy, a, b = niche_box(p)
    H, W = relief_px.shape
    X, Y = np.meshgrid(xs, ys)
    u = (X - (cx - a)) / (2 * a) * (W - 1)
    v = ((cy + b) - Y) / (2 * b) * (H - 1)
    r = ndi.map_coordinates(relief_px, [v, u], order=1, mode="constant", cval=0.0)
    floor = p.thickness - p.niche_depth
    return np.maximum(z, floor + r)


def heightfield_mesh(z, grid, poly, base=0.0) -> trimesh.Trimesh:
    """Closed slab: front = z, flat back at `base`, cut by the outline prism (manifold3d)."""
    import manifold3d as mf

    xs, ys = grid
    ny, nx = z.shape
    X, Y = np.meshgrid(xs, ys)
    top = np.c_[X.ravel(), Y.ravel(), z.ravel()]
    bot = np.c_[X.ravel(), Y.ravel(), np.full(z.size, base - 1.0)]
    V = np.r_[top, bot].astype(np.float32)
    idx = np.arange(nx * ny).reshape(ny, nx)
    a, b_, c, d = idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel(), idx[1:, 1:].ravel(), idx[1:, :-1].ravel()
    n = nx * ny
    F = [np.c_[a, b_, c], np.c_[a, c, d], np.c_[a + n, c + n, b_ + n], np.c_[a + n, d + n, c + n]]
    ring = np.r_[idx[0, :], idx[1:, -1], idx[-1, -2::-1], idx[-2:0:-1, 0]]
    r2 = np.roll(ring, -1)
    F += [np.c_[ring, ring + n, r2], np.c_[r2, ring + n, r2 + n]]
    F = np.vstack(F).astype(np.uint32)
    slab = mf.Manifold(mf.Mesh(vert_properties=V, tri_verts=F))
    if slab.status() != mf.Error.NoError:            # winding the other way round
        F = F[:, ::-1].copy()
        slab = mf.Manifold(mf.Mesh(vert_properties=V, tri_verts=F))
    ex = np.asarray(poly.exterior.coords)[:-1]
    if poly.exterior.is_ccw is False:
        ex = ex[::-1]
    prism = mf.CrossSection([ex.tolist()]).extrude(float(z.max()) + 5.0).translate([0, 0, base])
    out = (slab ^ prism)
    out = out.simplify(0.01)
    m = out.to_mesh()
    # process=False: trimesh's tolerance merge would collapse the boolean's sub-micron slivers into
    # non-manifold edges; manifold3d's own output is already a closed 2-manifold
    t = trimesh.Trimesh(np.asarray(m.vert_properties)[:, :3].astype(np.float64), np.asarray(m.tri_verts),
                        process=False)
    if t.volume < 0:
        t.invert()
    return t


def check(m: trimesh.Trimesh, rep: ReliefReport) -> ReliefReport:
    rep.faces = len(m.faces)
    rep.watertight = bool(m.is_watertight)
    rep.is_volume = bool(m.is_volume)
    rep.euler = int(m.euler_number)
    rep.pieces = len(m.split(only_watertight=False))
    rep.extents_mm = tuple(round(float(x), 2) for x in m.extents)
    rep.volume_cm3 = round(float(m.volume) / 1000, 1)
    rep.fits_bed = sr.fits_bed(m)
    return rep


def analyse(img: Image.Image, crop: tuple | None, aspect: float, timings: dict | None = None):
    """Mask + depth for the crop. Returns (crop_img, mask, disp, box_px)."""
    tm = timings if timings is not None else {}
    t = time.time()
    mask_full = segment(img)
    tm["mask_s"] = round(time.time() - t, 1)
    W, H = img.size
    if crop:
        box = (int(crop[0] * W), int(crop[1] * H), int(crop[2] * W), int(crop[3] * H))
    else:
        box = auto_crop(mask_full, aspect)
    ci = _crop_pad(img.convert("RGB"), box)
    cm = np.asarray(_crop_pad(Image.fromarray((mask_full * 255).astype(np.uint8)), box), np.float32) / 255
    t = time.time()
    disp = depth(ci)
    tm["depth_s"] = round(time.time() - t, 1)
    return ci, cm, disp, box


def _crop_pad(im: Image.Image, box):
    x0, y0, x1, y1 = box
    out = Image.new(im.mode, (x1 - x0, y1 - y0), 0)
    out.paste(im.crop((max(x0, 0), max(y0, 0), min(x1, im.width), min(y1, im.height))),
              (max(0, -x0), max(0, -y0)))
    return out


def photo_to_relief(photo, p: ReliefParams | None = None, analysed=None, log=print):
    """Returns (mesh, report, extras) where extras has the crop, mask, depth, relief and front height map."""
    p = p or ReliefParams()
    rep = ReliefReport()
    t0 = time.time()
    _, _, a, b = niche_box(p)
    aspect = b / a
    img = Image.open(photo) if isinstance(photo, (str, os.PathLike)) else photo
    if analysed is None:
        analysed = analyse(img, p.crop, aspect, rep.timings)
    ci, cm, disp, box = analysed
    t = time.time()
    px_mm = 2 * a / ci.width
    lum = np.asarray(ci.convert("L"), np.float32) / 255
    rel = bas_relief(disp, cm, lum, px_mm, p, p.relief_mm)
    z, grid, niche, poly, inside = frame_heightfield(p)
    z = place_relief(z, grid, niche, rel, p)
    rep.timings["relief_s"] = round(time.time() - t, 1)
    t = time.time()
    mesh = heightfield_mesh(z, grid, poly)
    rep.timings["mesh_s"] = round(time.time() - t, 1)
    check(mesh, rep)
    rep.timings["total_s"] = round(time.time() - t0, 1)
    log(f"relief: {rep.faces} faces, watertight={rep.watertight}, euler={rep.euler}, pieces={rep.pieces}, "
        f"{rep.extents_mm} mm, fits bed 225x225x245: {rep.fits_bed}, {rep.timings}")
    return mesh, rep, dict(crop=ci, mask=cm, depth=disp, relief=rel, z=z, grid=grid, box=box, inside=inside)


# ---------------------------------------------------------------- previews
def shade(z: np.ndarray, res: float, inside=None, light=(-0.55, 0.75, 0.38), color=(236, 226, 205),
          ambient=0.28, bg=(46, 44, 42)):
    """Matte stone shading of a height map (front view, grazing light from upper left). Row 0 = bottom."""
    gy, gx = np.gradient(z, res)
    n = np.dstack([-gx, -gy, np.ones_like(z)])
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    L = np.asarray(light, float); L /= np.linalg.norm(L)
    lam = np.clip(n @ L, 0, 1)
    # cheap cast shadows along the light direction
    sh = np.ones_like(z)
    step = np.array([L[1], L[0]]) / np.hypot(L[0], L[1])
    slope = L[2] / np.hypot(L[0], L[1])
    for k in range(1, 80, 2):
        dy, dx = step * k
        zz = ndi.shift(z, (-dy, -dx), order=1, mode="nearest")
        sh = np.minimum(sh, np.where(zz - z > slope * k * res, 0.45, 1.0))
    sh = ndi.gaussian_filter(sh, 1.0)
    v = ambient + (1 - ambient) * lam * sh
    rgb = np.clip(v[..., None] * np.asarray(color, float), 0, 255)
    if inside is not None:
        w = ndi.gaussian_filter(inside.astype(np.float32), 0.7)[..., None]
        rgb = rgb * w + np.asarray(bg, float) * (1 - w)
    rgb = rgb.astype(np.uint8)
    return Image.fromarray(rgb[::-1])


def synthetic_photo(size=(384, 512)) -> tuple:
    """Offline test input: a soft 'head' disc with two eyes and a nose on a plain wall (photo, mask, disp)."""
    W, H = size
    Y, X = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.hypot((X - W / 2) / (W * 0.33), (Y - H * 0.45) / (H * 0.33))
    mask = (r < 1).astype(np.float32)
    disp = np.clip(1 - r ** 2, 0, None) + 0.6 * np.exp(-(((X - W / 2) / 30) ** 2 + ((Y - H * 0.55) / 25) ** 2))
    img = np.full((H, W, 3), 225, np.uint8)
    img[mask > 0] = 245
    for ex in (W * 0.38, W * 0.62):
        img[np.hypot(X - ex, Y - H * 0.4) < 12] = 40
    img[np.hypot(X - W / 2, Y - H * 0.56) < 16] = 30
    return Image.fromarray(img), mask, disp.astype(np.float32)
