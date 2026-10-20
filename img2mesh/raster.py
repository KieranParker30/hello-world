"""Vectorised z-buffered triangle rasterizer (numpy only).

Used to render depth maps of a mesh from each camera (for visibility) and to
find which surface point every texel of a texture atlas covers.
"""

from __future__ import annotations

import numpy as np

_MAX_CANDIDATES = 4_000_000  # pixels tested per batch, bounds memory use


def rasterize(xy: np.ndarray, z: np.ndarray | None, faces: np.ndarray, width: int, height: int):
    """Rasterize triangles given 2D pixel coordinates per vertex.

    Pixel (col, row) has its centre at xy = (col, row). With `z`, the nearest
    triangle wins (smaller z); without it, later triangles overwrite earlier ones
    (fine for non-overlapping UV charts).
    Returns (face_id (H, W) int32 with -1 for empty, barycentrics (H, W, 3) float32,
    depth (H, W) float32 with inf for empty).
    """
    face_id = np.full(width * height, -1, dtype=np.int32)
    bary = np.zeros((width * height, 3), dtype=np.float32)
    zbuf = np.full(width * height, np.inf, dtype=np.float32)

    tri = xy[faces]  # (F, 3, 2)
    lo = np.ceil(tri.min(axis=1)).astype(np.int64)
    hi = np.floor(tri.max(axis=1)).astype(np.int64)
    lo = np.maximum(lo, 0)
    hi[:, 0] = np.minimum(hi[:, 0], width - 1)
    hi[:, 1] = np.minimum(hi[:, 1], height - 1)
    ext = hi - lo + 1
    a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
    area = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    usable = (ext > 0).all(axis=1) & (np.abs(area) > 1e-12)
    if z is not None:
        usable &= (z[faces] > 0).all(axis=1)

    side = ext.max(axis=1)
    size_class = np.where(usable, np.ceil(np.log2(np.maximum(side, 1))).astype(int), -1)
    for k in range(size_class.max() + 1 if usable.any() else 0):
        ids = np.nonzero(size_class == k)[0]
        if len(ids) == 0:
            continue
        S = 1 << k
        oy, ox = np.mgrid[0:S, 0:S]
        ox, oy = ox.ravel(), oy.ravel()
        step = max(1, _MAX_CANDIDATES // (S * S))
        for start in range(0, len(ids), step):
            f = ids[start:start + step]
            px = lo[f, 0:1] + ox  # (n, S*S)
            py = lo[f, 1:2] + oy
            inside = (px <= hi[f, 0:1]) & (py <= hi[f, 1:2])
            ax, ay = a[f, 0:1], a[f, 1:2]
            bx, by = b[f, 0:1], b[f, 1:2]
            cx, cy = c[f, 0:1], c[f, 1:2]
            ar = area[f][:, None]
            w0 = ((bx - px) * (cy - py) - (by - py) * (cx - px)) / ar
            w1 = ((cx - px) * (ay - py) - (cy - py) * (ax - px)) / ar
            w2 = 1.0 - w0 - w1
            eps = -1e-6
            inside &= (w0 >= eps) & (w1 >= eps) & (w2 >= eps)
            if not inside.any():
                continue
            row, col = np.nonzero(inside)
            fid = f[row]
            pix = py[row, col] * width + px[row, col]
            wts = np.stack([w0[row, col], w1[row, col], w2[row, col]], axis=1)
            if z is None:
                face_id[pix] = fid
                bary[pix] = wts
                continue
            depth = (wts * z[faces[fid]]).sum(axis=1).astype(np.float32)
            np.minimum.at(zbuf, pix, depth)
            win = depth <= zbuf[pix]
            face_id[pix[win]] = fid[win]
            bary[pix[win]] = wts[win]

    if z is None:
        zbuf[face_id >= 0] = 0
    return (face_id.reshape(height, width), bary.reshape(height, width, 3),
            zbuf.reshape(height, width))
