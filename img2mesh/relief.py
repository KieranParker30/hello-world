"""Single image -> relief / heightmap mesh (bas-relief, lithophane, terrain)."""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter, ImageOps

from .mesh import Mesh

AI_MODEL = "depth-anything/Depth-Anything-V2-Small-hf"


def load_heightmap(
    image: Image.Image,
    resolution: int = 256,
    depth: str = "brightness",
    invert: bool = False,
    smooth: float = 0.0,
) -> np.ndarray:
    """Return a (rows, cols) array in [0, 1] where 1 is the highest point."""
    image = ImageOps.exif_transpose(image).convert("RGB")
    if depth == "ai":
        gray = _ai_depth(image)  # brighter = closer to the camera
    elif depth == "brightness":
        gray = image.convert("L")
    else:
        raise ValueError(f"Unknown depth mode '{depth}' (use 'brightness' or 'ai')")

    scale = resolution / max(gray.size)
    if scale < 1:
        size = (max(2, round(gray.width * scale)), max(2, round(gray.height * scale)))
        gray = gray.resize(size, Image.LANCZOS)
    if smooth > 0:
        gray = gray.filter(ImageFilter.GaussianBlur(smooth))

    h = np.asarray(gray, dtype=np.float64)
    span = h.max() - h.min()
    h = (h - h.min()) / span if span > 0 else np.zeros_like(h)
    return 1 - h if invert else h


def _ai_depth(image: Image.Image) -> Image.Image:
    try:
        from transformers import pipeline
    except ImportError as exc:
        raise SystemExit(
            "AI depth needs extra packages:  pip install 'img2mesh[ai]'\n"
            "(or: pip install torch transformers)"
        ) from exc
    estimator = pipeline("depth-estimation", model=AI_MODEL)
    return estimator(image)["depth"].convert("L")


def heightmap_to_mesh(
    heights: np.ndarray, width: float = 100.0, max_height: float = 10.0, base: float = 2.0
) -> Mesh:
    """Build a closed, printable slab whose top surface follows `heights`.

    The model lies in the XY plane (image seen from above, +Z up), `width` wide
    along X, with a flat bottom at z=0 and top at base + heights * max_height.
    """
    rows, cols = heights.shape
    pitch = width / (cols - 1)
    xs = np.arange(cols) * pitch
    ys = (rows - 1 - np.arange(rows)) * pitch  # row 0 (top of image) at max Y
    gx, gy = np.meshgrid(xs, ys)
    top = np.stack([gx, gy, base + heights * max_height], axis=-1).reshape(-1, 3)
    bottom = np.stack([gx, gy, np.zeros_like(gx)], axis=-1).reshape(-1, 3)
    n = rows * cols
    vertices = np.concatenate([top, bottom])

    idx = np.arange(n).reshape(rows, cols)
    tl, tr = idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel()
    bl, br = idx[1:, :-1].ravel(), idx[1:, 1:].ravel()
    top_faces = np.concatenate([np.stack([tl, bl, br], 1), np.stack([tl, br, tr], 1)])
    bottom_faces = top_faces[:, ::-1] + n

    # Boundary loop, counter-clockwise seen from above.
    loop = np.concatenate([
        idx[:, 0],            # left edge, top -> bottom
        idx[-1, 1:],          # bottom edge, left -> right
        idx[-2::-1, -1],      # right edge, bottom -> top
        idx[0, -2:0:-1],      # top edge, right -> left
    ])
    a, b = loop, np.roll(loop, -1)
    walls = np.concatenate([np.stack([a, a + n, b + n], 1), np.stack([a, b + n, b], 1)])

    return Mesh(vertices, np.concatenate([top_faces, bottom_faces, walls]))


def image_to_relief(
    path: str,
    width: float = 100.0,
    max_height: float = 10.0,
    base: float = 2.0,
    resolution: int = 256,
    depth: str = "brightness",
    invert: bool = False,
    smooth: float = 0.0,
) -> Mesh:
    with Image.open(path) as image:
        heights = load_heightmap(image, resolution, depth, invert, smooth)
    return heightmap_to_mesh(heights, width, max_height, base)
