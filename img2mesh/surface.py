"""Extract a smooth, watertight surface from a 3D occupancy / density grid.

Uses Naive Surface Nets: one vertex per grid cell that straddles the iso-level
(placed at the mean of the edge crossings), and one quad per grid edge that
crosses the iso-level, joining the four cells around that edge.
"""

from __future__ import annotations

import numpy as np

from .mesh import Mesh

def gaussian_blur3d(grid: np.ndarray, sigma: float) -> np.ndarray:
    """Separable Gaussian blur (no SciPy dependency)."""
    if sigma <= 0:
        return grid.astype(np.float64)
    radius = max(1, int(round(3 * sigma)))
    x = np.arange(-radius, radius + 1)
    kernel = np.exp(-(x**2) / (2 * sigma**2))
    kernel /= kernel.sum()
    out = grid.astype(np.float64)
    for axis in range(3):
        out = np.apply_along_axis(lambda m: np.convolve(m, kernel, mode="same"), axis, out)
    return out


def surface_nets(
    field: np.ndarray, iso: float = 0.5, spacing=(1.0, 1.0, 1.0), valid: np.ndarray | None = None
) -> Mesh:
    """Mesh the boundary of the region where `field > iso`.

    The field is padded with "outside" values, so without `valid` the result is
    always closed. If a boolean `valid` mask is given (e.g. "this voxel was seen
    by a camera"), no surface is created next to invalid samples, which gives an
    open surface instead of inventing geometry nobody observed.
    Vertex coordinates are in grid units (multiplied by `spacing`) with the
    first sample of the unpadded field at the origin.

    Works on the list of iso-crossing edges only, so memory grows with the
    surface area rather than the grid volume.
    """
    field = np.asarray(field, dtype=np.float32)
    f = np.pad(field, 1, constant_values=min(iso - 1, float(field.min())))
    ok = np.ones(f.shape, dtype=bool) if valid is None else np.pad(valid, 1, constant_values=True)
    inside = f > iso
    cell_dims = np.array(f.shape) - 1

    edge_pts, edge_cells = [], []
    for axis in range(3):
        u, v = [(1, 2), (2, 0), (0, 1)][axis]  # (u, v, axis) is right-handed
        sl_a = [slice(None)] * 3
        sl_b = [slice(None)] * 3
        sl_a[axis] = slice(0, -1)
        sl_b[axis] = slice(1, None)
        a_in, b_in = inside[tuple(sl_a)], inside[tuple(sl_b)]
        edges = np.argwhere((a_in != b_in) & ok[tuple(sl_a)] & ok[tuple(sl_b)])
        if len(edges) == 0:
            continue
        fa = f[tuple(edges.T)]
        nxt = edges.copy()
        nxt[:, axis] += 1
        fb = f[tuple(nxt.T)]
        point = edges.astype(np.float64)
        point[:, axis] += (iso - fa) / (fb - fa)

        # The 4 cells around the edge, ordered so the quad faces outward.
        cells = []
        for du, dv in ((1, 1), (0, 1), (0, 0), (1, 0)):
            c = edges.copy()
            c[:, u] -= du
            c[:, v] -= dv
            cells.append(np.ravel_multi_index(tuple(c.T), cell_dims))
        cells = np.stack(cells, axis=1)
        flip = ~a_in[tuple(edges.T)]  # outside -> inside along +axis
        cells[flip] = cells[flip][:, ::-1]
        edge_pts.append(point)
        edge_cells.append(cells)

    if not edge_pts:
        return Mesh(np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64))
    points = np.concatenate(edge_pts)
    quads_cells = np.concatenate(edge_cells)

    # One vertex per cell touched by a crossing edge, at the mean of its crossings.
    unique_cells, quads = np.unique(quads_cells, return_inverse=True)
    quads = quads.reshape(-1, 4)
    owner = quads.ravel()
    pts4 = np.repeat(points, 4, axis=0)
    count = np.bincount(owner, minlength=len(unique_cells))
    vertices = np.stack(
        [np.bincount(owner, pts4[:, k], len(unique_cells)) for k in range(3)], axis=1
    ) / count[:, None]
    vertices = (vertices - 1) * np.asarray(spacing)  # -1 undoes the padding

    # Split each quad along the shorter diagonal for nicer triangles.
    p = vertices[quads]
    use02 = np.linalg.norm(p[:, 0] - p[:, 2], axis=1) <= np.linalg.norm(p[:, 1] - p[:, 3], axis=1)
    tris = np.empty((len(quads) * 2, 3), dtype=np.int64)
    tris[0::2] = np.where(use02[:, None], quads[:, [0, 1, 2]], quads[:, [0, 1, 3]])
    tris[1::2] = np.where(use02[:, None], quads[:, [0, 2, 3]], quads[:, [1, 2, 3]])
    return Mesh(vertices, tris)
