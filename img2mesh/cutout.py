"""One product photo -> textured 3D cut-out (AI depth, "2.5D").

For when a single photo is all there is (e.g. a shop's product shot):
1. Keep only the object, using the photo's transparency or, failing that, its
   difference from the border colour.
2. Estimate depth with Depth Anything V2.
3. Build a closed solid: the front follows the estimated depth, the back is a
   shallower mirror of it, and the two meet in rounded edges at the outline.
4. Texture it with the photo itself.

The result looks right from the photo's viewpoint and nearby angles. Sides and
back the photo never showed are estimated, not measured; for a true all-round
model, photograph the object from all sides and use `img2mesh scan`.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageOps

from .carve import silhouette
from .mesh import Mesh
from .texture import fill_holes

DEPTH_MODEL = "depth-anything/Depth-Anything-V2-Base-hf"
_estimators: dict = {}


def object_mask(image: Image.Image, threshold: float = 40.0) -> np.ndarray:
    """Foreground mask; holes inside the outline (e.g. between parts) are kept."""
    return silhouette(image, threshold, fill_holes=False)


def estimate_depth(rgb: Image.Image, model: str = DEPTH_MODEL) -> np.ndarray:
    """Relative depth at the image's resolution, larger = closer to the camera."""
    try:
        import torch
        from transformers import pipeline
    except ImportError as exc:
        raise SystemExit(
            "Cut-out models need extra packages:  pip install 'img2mesh[ai]'\n"
            "(or: pip install torch transformers)"
        ) from exc
    if model not in _estimators:
        _estimators[model] = pipeline("depth-estimation", model=model)
    pred = _estimators[model](rgb)["predicted_depth"]
    pred = pred.reshape(1, 1, *pred.shape[-2:]).float()
    pred = torch.nn.functional.interpolate(pred, size=(rgb.height, rgb.width),
                                           mode="bicubic", align_corners=False)
    return pred[0, 0].numpy().astype(np.float64)


def _smooth_within(values: np.ndarray, mask: np.ndarray, sigma: float) -> np.ndarray:
    if sigma <= 0:
        return values
    try:
        from scipy.ndimage import gaussian_filter
    except ImportError:
        return values
    m = mask.astype(np.float64)
    num = gaussian_filter(values * m, sigma)
    den = gaussian_filter(m, sigma)
    return np.where(den > 1e-6, num / np.maximum(den, 1e-6), values)


def cutout_model(
    path: str,
    width: float = 300.0,
    depth: float = 0.35,
    back: float = 0.6,
    resolution: int = 400,
    texture_size: int = 2048,
    smooth: float = 1.0,
    edge: float = 0.03,
    threshold: float = 40.0,
    model: str = DEPTH_MODEL,
) -> Mesh:
    """Textured cut-out model, `width` mm wide, front facing -Y, +Z up.

    `depth` is how deep the front relief is as a fraction of the width;
    `back` is the back's depth relative to the front's; `edge` is how far in
    from the outline (fraction of the width) the edges round over.
    """
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)
        im.load()
    mask_full = object_mask(im, threshold)
    if mask_full.sum() < 100:
        raise ValueError(f"No object found in {path}")

    # Crop to the object, with a small margin.
    rows, cols = np.nonzero(mask_full)
    pad = int(0.02 * max(im.size))
    r0, r1 = max(rows.min() - pad, 0), min(rows.max() + pad + 1, im.height)
    c0, c1 = max(cols.min() - pad, 0), min(cols.max() + pad + 1, im.width)
    rgba = im.convert("RGBA").crop((c0, r0, c1, r1))
    mask_full = mask_full[r0:r1, c0:c1]
    white = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    white.alpha_composite(rgba)
    rgb = white.convert("RGB")

    # Depth, normalised over the object only (robust to a few outliers).
    d = estimate_depth(rgb, model)
    lo, hi = np.percentile(d[mask_full], [2, 98])
    d = np.clip((d - lo) / max(hi - lo, 1e-9), 0, 1)

    # Texture: the photo, with the background replaced by nearby object
    # colours so edges don't pick up white when filtered.
    tex = fill_holes(np.asarray(rgb, np.float32), mask_full)
    texture = np.asarray(Image.fromarray(np.clip(tex + 0.5, 0, 255).astype(np.uint8))
                         .resize((texture_size, texture_size), Image.LANCZOS))

    # Geometry grid at `resolution` on the long side.
    h, w = mask_full.shape
    scale = min(1.0, resolution / max(h, w))
    gh, gw = max(2, round(h * scale)), max(2, round(w * scale))
    m_small = np.asarray(Image.fromarray(mask_full.astype(np.uint8) * 255)
                         .resize((gw, gh), Image.BILINEAR)) > 127
    d_small = np.asarray(Image.fromarray(d.astype(np.float32)).resize((gw, gh), Image.BILINEAR),
                         dtype=np.float64)
    d_small = _smooth_within(d_small, m_small, smooth)

    pitch = width / (gw - 1)
    relief = depth * width
    min_thickness = 0.01 * width
    # Thickness tapers to nothing at the outline, so the edges are rounded
    # rather than straight walls stretching the photo's edge pixels.
    from scipy.ndimage import distance_transform_edt

    inside = distance_transform_edt(m_small)  # 1 on the outline pixels
    taper = np.sqrt(np.clip((inside - 1) / max(edge * gw, 1), 0, 1))
    rr, cc = np.mgrid[0:gh, 0:gw]
    x = cc * pitch
    z = (gh - 1 - rr) * pitch
    front_y = -d_small * relief
    back_y = front_y + ((1 + back) * d_small * relief + min_thickness) * taper
    n = gh * gw
    vertices = np.concatenate([
        np.stack([x, front_y, z], -1).reshape(-1, 3),
        np.stack([x, back_y, z], -1).reshape(-1, 3),
    ])
    uv = np.stack([(cc + 0.5) / gw, (rr + 0.5) / gh], -1).reshape(-1, 2)
    uvs = np.concatenate([uv, uv])

    # Cells whose four corners are all on the object.
    idx = np.arange(n).reshape(gh, gw)
    cell = m_small[:-1, :-1] & m_small[:-1, 1:] & m_small[1:, :-1] & m_small[1:, 1:]
    tl, tr = idx[:-1, :-1][cell], idx[:-1, 1:][cell]
    bl, br = idx[1:, :-1][cell], idx[1:, 1:][cell]
    # Seen from -Y (the viewer), x right and z up: counter-clockwise.
    front = np.concatenate([np.stack([tl, bl, br], 1), np.stack([tl, br, tr], 1)])

    # Back faces use their own vertices, except along the outline where the
    # back meets the front: there they share the front's vertices.
    he = np.concatenate([front[:, [0, 1]], front[:, [1, 2]], front[:, [2, 0]]])
    key = he[:, 0] * n + he[:, 1]
    border = he[~np.isin(he[:, 1] * n + he[:, 0], key)]
    back_index = np.arange(n) + n
    back_index[np.unique(border)] = np.unique(border)
    back_faces = back_index[front[:, ::-1]]

    faces = np.concatenate([front, back_faces])
    used = np.unique(faces)
    remap = np.full(len(vertices), -1)
    remap[used] = np.arange(len(used))
    mesh = Mesh(vertices[used], remap[faces], uvs=uvs[used], texture=texture)
    # Exactly `width` across the object itself, centred, standing on z=0.
    lo, hi = mesh.bounds()
    v = (mesh.vertices - [(lo[0] + hi[0]) / 2, 0, lo[2]]) * (width / (hi[0] - lo[0]))
    return Mesh(v, mesh.faces, uvs=mesh.uvs, texture=texture)
