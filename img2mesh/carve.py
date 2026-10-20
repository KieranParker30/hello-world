"""Several photos around an object -> full 3D model (visual hull / shape from silhouette).

Assumes the photos are taken from the same height and distance while the object
turns on a turntable (or you walk around it), roughly evenly spaced over 360
degrees, against a plain background or with a transparent background.
Projection is treated as orthographic, so a longer lens / greater distance
gives better results.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter, ImageOps

from .mesh import Mesh
from .surface import gaussian_blur3d, surface_nets

MAX_IMAGE_SIDE = 400


def silhouette(image: Image.Image, threshold: float = 40.0, fill_holes: bool = True) -> np.ndarray:
    """Boolean foreground mask. Uses the alpha channel if present, otherwise
    treats pixels that differ from the border colour as the object."""
    image = ImageOps.exif_transpose(image)
    if image.mode in ("RGBA", "LA", "PA") or "transparency" in image.info:
        alpha = np.asarray(image.convert("RGBA"))[..., 3]
        if alpha.min() < 128:
            mask = alpha >= 128
            return _fill_holes(mask) if fill_holes else mask

    rgb = np.asarray(image.convert("RGB").filter(ImageFilter.MedianFilter(3)), dtype=np.float64)
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    background = np.median(border, axis=0)
    mask = np.abs(rgb - background).max(axis=2) > threshold
    return _fill_holes(mask) if fill_holes else mask


def _fill_holes(mask: np.ndarray) -> np.ndarray:
    """Fill background regions not connected to the image border."""
    reachable = np.zeros_like(mask)
    reachable[0], reachable[-1], reachable[:, 0], reachable[:, -1] = (
        ~mask[0], ~mask[-1], ~mask[:, 0], ~mask[:, -1],
    )
    free = ~mask
    while True:
        grown = reachable.copy()
        grown[1:] |= reachable[:-1]
        grown[:-1] |= reachable[1:]
        grown[:, 1:] |= reachable[:, :-1]
        grown[:, :-1] |= reachable[:, 1:]
        grown &= free
        if np.array_equal(grown, reachable):
            return ~reachable
        reachable = grown


def carve(
    masks: list[np.ndarray],
    angles_deg: list[float],
    resolution: int = 128,
    axis_x: float = 0.5,
    reverse: bool = False,
    smooth: float = 1.0,
) -> Mesh:
    """Intersect the silhouette cones (orthographic) of every view.

    `axis_x` is the turntable axis position as a fraction of image width.
    Returns a mesh in pixel units with +Z up.
    """
    rows, cols = masks[0].shape
    if any(m.shape != (rows, cols) for m in masks):
        raise ValueError("All silhouettes must have the same size")
    if not all(m.any() for m in masks):
        raise ValueError("Object not found in at least one image (try a different --threshold)")

    cx = axis_x * (cols - 1)
    union = np.logical_or.reduce(masks)
    r_idx, c_idx = np.nonzero(union)
    radius = max(np.abs(c_idx - cx).max(), 1) + 1
    top, bottom = r_idx.min() - 1, r_idx.max() + 1

    voxel = max(2 * radius, bottom - top) / resolution
    xs = np.arange(-radius, radius + voxel, voxel)
    zs = np.arange(bottom, top - voxel, -voxel)  # image row for each height level
    X, Y = np.meshgrid(xs, xs, indexing="ij")
    occupied = np.ones((len(xs), len(xs), len(zs)), dtype=bool)
    row_idx = np.clip(np.round(zs).astype(int), 0, rows - 1)
    row_ok = (zs >= 0) & (zs <= rows - 1)

    sign = 1.0 if reverse else -1.0
    for mask, angle in zip(masks, angles_deg):
        t = np.radians(angle)
        col = np.round(cx + X * np.cos(t) + sign * Y * np.sin(t)).astype(int)
        col_ok = (col >= 0) & (col < cols)
        hit = mask[row_idx[None, None, :], np.clip(col, 0, cols - 1)[..., None]]
        occupied &= hit & col_ok[..., None] & row_ok[None, None, :]

    if not occupied.any():
        raise ValueError("Carving removed everything; check the image order, angles and --axis")
    field = gaussian_blur3d(occupied.astype(np.float64), smooth)
    mesh = surface_nets(field, 0.5, spacing=(voxel, voxel, voxel))
    return mesh


def images_to_model(
    paths: list[str],
    angles_deg: list[float] | None = None,
    resolution: int = 128,
    size: float = 100.0,
    threshold: float = 40.0,
    axis_x: float = 0.5,
    reverse: bool = False,
    smooth: float = 1.0,
    fill_holes: bool = True,
    save_masks: str | None = None,
) -> Mesh:
    if len(paths) < 2:
        raise ValueError("Carving needs at least 2 images (8-36 around the object works best)")
    if angles_deg is None:
        angles_deg = [i * 360.0 / len(paths) for i in range(len(paths))]
    if len(angles_deg) != len(paths):
        raise ValueError("Number of angles must match number of images")

    masks, target = [], None
    for path in paths:
        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image)
            if target is None:
                scale = min(1.0, MAX_IMAGE_SIDE / max(image.size))
                target = (round(image.width * scale), round(image.height * scale))
            mask = silhouette(image.resize(target, Image.LANCZOS), threshold, fill_holes)
        masks.append(mask)
        if save_masks:
            from pathlib import Path

            out = Path(save_masks)
            out.mkdir(parents=True, exist_ok=True)
            Image.fromarray(mask.astype(np.uint8) * 255).save(out / f"{Path(path).stem}_mask.png")

    mesh = carve(masks, angles_deg, resolution, axis_x, reverse, smooth)
    return mesh.scaled_to(size)
