"""Turn a dense scanned mesh into a lightweight, textured mesh for the web.

1. Decimate to a triangle budget (quadric edge collapse).
2. UV-unwrap into a texture atlas (xatlas).
3. Bake a colour texture from the original photos: every texel is coloured
   from the cameras that see it best (facing it, close, not occluded), with
   smooth blending between neighbouring views to hide seams.
4. Bake a tangent-space normal map from the high-resolution surface (the
   signed distance field), so the light mesh keeps the fine detail.

Needs: xatlas, fast-simplification (installed with img2mesh[photo]).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from .mesh import Mesh
from .raster import rasterize


@dataclass
class Camera:
    K: np.ndarray  # intrinsics for `image`
    R: np.ndarray  # world -> camera
    t: np.ndarray
    image: np.ndarray  # (h, w, 3) uint8

    @property
    def centre(self) -> np.ndarray:
        return -self.R.T @ self.t


def decimate(mesh: Mesh, target_faces: int) -> Mesh:
    if len(mesh.faces) <= target_faces:
        return mesh
    import fast_simplification

    v, f = fast_simplification.simplify(
        mesh.vertices.astype(np.float32), mesh.faces.astype(np.int32),
        target_reduction=1 - target_faces / len(mesh.faces), agg=5,
    )
    return Mesh(v, f)


def unwrap(mesh: Mesh, size: int, padding: int = 4) -> Mesh:
    """Return a copy with per-vertex UVs (vertices are split along seams)."""
    import xatlas

    atlas = xatlas.Atlas()
    atlas.add_mesh(mesh.vertices.astype(np.float32), mesh.faces.astype(np.uint32))
    chart = xatlas.ChartOptions()
    pack = xatlas.PackOptions()
    pack.resolution = size
    pack.padding = padding
    pack.bilinear = True
    atlas.generate(chart, pack)
    vmapping, faces, uvs = atlas[0]
    # Our texture rows run top-down, which is also glTF's UV convention.
    return Mesh(mesh.vertices[vmapping], faces.astype(np.int64), uvs=uvs.astype(np.float64))


def _tangents(mesh: Mesh) -> tuple[np.ndarray, np.ndarray]:
    """Per-vertex dP/du and dP/dv, accumulated from faces."""
    v, uv, f = mesh.vertices, mesh.uvs, mesh.faces
    e1, e2 = v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]]
    d1, d2 = uv[f[:, 1]] - uv[f[:, 0]], uv[f[:, 2]] - uv[f[:, 0]]
    det = d1[:, 0] * d2[:, 1] - d2[:, 0] * d1[:, 1]
    r = np.where(np.abs(det) > 1e-20, 1.0 / np.where(det == 0, 1, det), 0)[:, None]
    du = (e1 * d2[:, 1:2] - e2 * d1[:, 1:2]) * r
    dv = (e2 * d1[:, 0:1] - e1 * d2[:, 0:1]) * r
    T = np.zeros_like(v)
    B = np.zeros_like(v)
    for k in range(3):
        np.add.at(T, f[:, k], du)
        np.add.at(B, f[:, k], dv)
    return T, B


def _normalize(a: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(a, axis=-1, keepdims=True)
    return a / np.where(n == 0, 1, n)


def bilinear(img: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    x = np.clip(x, 0, w - 1.001)
    y = np.clip(y, 0, h - 1.001)
    x0, y0 = np.floor(x).astype(np.int64), np.floor(y).astype(np.int64)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    i = img.astype(np.float32) if img.dtype != np.float32 else img
    top = i[y0, x0] * (1 - fx) + i[y0, x0 + 1] * fx
    bot = i[y0 + 1, x0] * (1 - fx) + i[y0 + 1, x0 + 1] * fx
    return top * (1 - fy) + bot * fy


def fill_holes(img: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Push-pull fill: holes take smoothly blended values from nearby texels.

    Also pads chart borders, so texture filtering and mipmaps don't bleed in
    background colour.
    """
    img = img.astype(np.float32)
    if mask.all() or not mask.any():
        return img
    h, w = mask.shape
    H, W = h + h % 2, w + w % 2
    big = np.zeros((H, W) + img.shape[2:], np.float32)
    m = np.zeros((H, W), np.float32)
    big[:h, :w] = img * mask[..., None]
    m[:h, :w] = mask
    s = big.reshape(H // 2, 2, W // 2, 2, -1).sum(axis=(1, 3))
    c = m.reshape(H // 2, 2, W // 2, 2).sum(axis=(1, 3))
    coarse = fill_holes(s / np.maximum(c, 1)[..., None], c > 0)
    up = np.repeat(np.repeat(coarse, 2, axis=0), 2, axis=1)[:h, :w]
    return np.where(mask[..., None], img, up)


def bake(
    mesh: Mesh,
    cameras: list[Camera],
    size: int,
    field: Callable[[np.ndarray], tuple[np.ndarray, np.ndarray]] | None = None,
    visibility_size: int = 1000,
    log=print,
) -> tuple[np.ndarray, np.ndarray | None, np.ndarray]:
    """Bake colour (and, given `field`, a normal map) for a UV-mapped mesh.

    `field(points)` returns (outward normals, valid mask) of the detailed
    surface at world points. Returns (texture, normal_map, vertex_normals).
    """
    V, F, UV = mesh.vertices, mesh.faces, mesh.uvs
    vnorm = mesh.vertex_normals()
    Tv, Bv = _tangents(mesh)

    # Which surface point does each texel show?
    fid, bary, _ = rasterize(UV * size - 0.5, None, F, size, size)
    texel = np.nonzero(fid.ravel() >= 0)[0]
    f = fid.ravel()[texel]
    w = bary.reshape(-1, 3)[texel].astype(np.float64)
    P = np.einsum("nk,nkd->nd", w, V[F[f]])
    N = _normalize(np.einsum("nk,nkd->nd", w, vnorm[F[f]]))
    del fid, bary

    # Visibility: depth maps of this mesh from every camera.
    log(f"      Rendering visibility for {len(cameras)} photos...")
    depth_maps = []
    for cam in cameras:
        h, w_ = cam.image.shape[:2]
        s = min(1.0, visibility_size / max(h, w_))
        Kv = cam.K.copy()  # same camera at visibility resolution (pixel centres at integers)
        Kv[0, 0] *= s
        Kv[1, 1] *= s
        Kv[0, 2] = (cam.K[0, 2] + 0.5) * s - 0.5
        Kv[1, 2] = (cam.K[1, 2] + 0.5) * s - 0.5
        cv = V @ cam.R.T + cam.t
        xy = np.stack([Kv[0, 0] * cv[:, 0] / cv[:, 2] + Kv[0, 2],
                       Kv[1, 1] * cv[:, 1] / cv[:, 2] + Kv[1, 2]], axis=1)
        vh, vw = round(h * s), round(w_ * s)
        _, _, zb = rasterize(xy, cv[:, 2], F, vw, vh)
        depth_maps.append((Kv, zb))
    span = np.linalg.norm(V.max(0) - V.min(0))

    def view_weights(i: int, idx: slice):
        cam = cameras[i]
        Kv, zb = depth_maps[i]
        p = P[idx]
        c = p @ cam.R.T + cam.t
        z = c[:, 2]
        ok = z > 1e-9
        zs = np.where(ok, z, 1)
        u = Kv[0, 0] * c[:, 0] / zs + Kv[0, 2]
        v = Kv[1, 1] * c[:, 1] / zs + Kv[1, 2]
        vh, vw = zb.shape
        ok &= (u >= 0) & (u <= vw - 1) & (v >= 0) & (v <= vh - 1)
        ui = np.clip(np.round(u).astype(int), 0, vw - 1)
        vi = np.clip(np.round(v).astype(int), 0, vh - 1)
        ok &= np.abs(zb[vi, ui] - z) < 0.004 * span + 0.01 * z  # not hidden behind something
        to_cam = _normalize(cam.centre - p)
        cos = np.einsum("nd,nd->n", N[idx], to_cam)
        ok &= cos > 0.15
        border = np.minimum.reduce([u, vw - 1 - u, v, vh - 1 - v]) / (0.04 * vw)
        detail = (Kv[0, 0] / zs) ** 2  # photo pixels per unit area
        wgt = np.where(ok, cos**2 * detail * np.clip(border, 0, 1), 0.0)
        return wgt

    # Colour: each texel blends the views within 70% of its best view's score,
    # so transitions between photos are gradual instead of hard seams.
    log("      Baking colour texture from the photos...")
    n = len(texel)
    colour = np.zeros((n, 3), np.float32)
    seen = np.zeros(n, bool)
    chunk = 1_500_000
    for start in range(0, n, chunk):
        idx = slice(start, min(n, start + chunk))
        weights = [view_weights(i, idx) for i in range(len(cameras))]
        best = np.max(weights, axis=0)
        acc = np.zeros((idx.stop - idx.start, 3), np.float64)
        tot = np.zeros(idx.stop - idx.start)
        for i, cam in enumerate(cameras):
            blend = np.clip((weights[i] / np.maximum(best, 1e-30) - 0.7) / 0.3, 0, 1)
            blend[best <= 0] = 0
            use = blend > 0
            if not use.any():
                continue
            c = P[idx][use] @ cam.R.T + cam.t
            x = cam.K[0, 0] * c[:, 0] / c[:, 2] + cam.K[0, 2]
            y = cam.K[1, 1] * c[:, 1] / c[:, 2] + cam.K[1, 2]
            acc[use] += bilinear(cam.image, x, y) * blend[use, None]
            tot[use] += blend[use]
        colour[idx] = acc / np.maximum(tot, 1e-12)[:, None]
        seen[idx] = tot > 0

    tex = np.zeros((size * size, 3), np.float32)
    known = np.zeros(size * size, bool)
    tex[texel[seen]] = colour[seen]
    known[texel[seen]] = True
    texture = fill_holes(tex.reshape(size, size, 3), known.reshape(size, size))
    texture = np.clip(texture + 0.5, 0, 255).astype(np.uint8)

    normal_map = None
    if field is not None:
        log("      Baking normal map from the detailed surface...")
        Tn = _normalize(np.einsum("nk,nkd->nd", w, Tv[F[f]]))
        Bdv = np.einsum("nk,nkd->nd", w, Bv[F[f]])
        Tn = _normalize(Tn - N * np.einsum("nd,nd->n", N, Tn)[:, None])
        up = np.cross(N, Tn)
        # glTF tangent space: +Y points up the image, i.e. against dP/dv.
        up *= np.where(np.einsum("nd,nd->n", up, -Bdv) < 0, -1.0, 1.0)[:, None]
        detail_n, valid = field(P)
        detail_n = np.where(valid[:, None], detail_n, N)
        ts = np.stack([np.einsum("nd,nd->n", detail_n, Tn),
                       np.einsum("nd,nd->n", detail_n, up),
                       np.einsum("nd,nd->n", detail_n, N)], axis=1)
        ts[:, 2] = np.maximum(ts[:, 2], 0.05)  # never point into the surface
        ts = _normalize(ts)
        nm = np.zeros((size * size, 3), np.float32)
        nm_known = np.zeros(size * size, bool)
        nm[texel] = (ts + 1) * 127.5
        nm_known[texel] = True
        filled = fill_holes(nm.reshape(size, size, 3), nm_known.reshape(size, size))
        normal_map = np.clip(filled + 0.5, 0, 255).astype(np.uint8)

    return texture, normal_map, vnorm
