"""Extract a smooth, watertight surface from a 3D occupancy / density grid.

Uses Naive Surface Nets: one vertex per grid cell that straddles the iso-level
(placed at the mean of the edge crossings), and one quad per grid edge that
crosses the iso-level, joining the four cells around that edge.
"""

from __future__ import annotations

import numpy as np

from .mesh import Mesh

# The 12 edges of a unit cell as (corner offset, axis).
_CELL_EDGES = [
    ((0, 0, 0), 0), ((0, 1, 0), 0), ((0, 0, 1), 0), ((0, 1, 1), 0),
    ((0, 0, 0), 1), ((1, 0, 0), 1), ((0, 0, 1), 1), ((1, 0, 1), 1),
    ((0, 0, 0), 2), ((1, 0, 0), 2), ((0, 1, 0), 2), ((1, 1, 0), 2),
]


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


def surface_nets(field: np.ndarray, iso: float = 0.5, spacing=(1.0, 1.0, 1.0)) -> Mesh:
    """Mesh the boundary of the region where `field > iso`.

    The field is padded with "outside" values, so the result is always closed.
    Vertex coordinates are in grid units (multiplied by `spacing`) with the
    first sample of the unpadded field at the origin.
    """
    f = np.pad(np.asarray(field, dtype=np.float64), 1, constant_values=min(iso - 1, field.min()))
    inside = f > iso
    nx, ny, nz = f.shape
    cell_shape = (nx - 1, ny - 1, nz - 1)

    # Vertex placement: average of iso-crossings on the cell's 12 edges.
    acc = np.zeros(cell_shape + (3,))
    count = np.zeros(cell_shape)
    cx, cy, cz = cell_shape
    for (ox, oy, oz), axis in _CELL_EDGES:
        a = f[ox:ox + cx, oy:oy + cy, oz:oz + cz]
        step = [0, 0, 0]
        step[axis] = 1
        bx, by, bz = ox + step[0], oy + step[1], oz + step[2]
        b = f[bx:bx + cx, by:by + cy, bz:bz + cz]
        crosses = (a > iso) != (b > iso)
        denom = np.where(crosses, b - a, 1.0)
        t = np.where(crosses, (iso - a) / denom, 0.0)
        pos = np.zeros(cell_shape + (3,))
        pos[..., 0], pos[..., 1], pos[..., 2] = ox, oy, oz
        pos[..., axis] += t
        acc += pos * crosses[..., None]
        count += crosses

    active = count > 0
    vert_index = np.full(cell_shape, -1, dtype=np.int64)
    vert_index[active] = np.arange(active.sum())
    cell_coords = np.argwhere(active)
    local = acc[active] / count[active][:, None]
    vertices = (cell_coords + local - 1) * np.asarray(spacing)  # -1 undoes padding

    # Faces: one quad per sign-changing grid edge, around the 4 adjacent cells.
    quads = []
    for axis in range(3):
        u, v = [(1, 2), (2, 0), (0, 1)][axis]  # (u, v, axis) is right-handed
        sl_a = [slice(None)] * 3
        sl_b = [slice(None)] * 3
        sl_a[axis] = slice(0, -1)
        sl_b[axis] = slice(1, None)
        a_in = inside[tuple(sl_a)]
        b_in = inside[tuple(sl_b)]
        edges = np.argwhere(a_in != b_in)
        # Only edges with 4 surrounding cells (always true thanks to padding).
        edges = edges[(edges[:, u] >= 1) & (edges[:, v] >= 1)]
        outward_positive = a_in[tuple(edges.T)]  # inside -> outside along +axis

        def cell(du, dv):
            c = edges.copy()
            c[:, u] -= du
            c[:, v] -= dv
            return vert_index[tuple(c.T)]

        q = np.stack([cell(1, 1), cell(0, 1), cell(0, 0), cell(1, 0)], axis=1)
        q[~outward_positive] = q[~outward_positive][:, ::-1]
        quads.append(q)

    quads = np.concatenate(quads)
    # Split each quad along the shorter diagonal for nicer triangles.
    p = vertices[quads]
    d02 = np.linalg.norm(p[:, 0] - p[:, 2], axis=1)
    d13 = np.linalg.norm(p[:, 1] - p[:, 3], axis=1)
    use02 = d02 <= d13
    tris = np.empty((len(quads) * 2, 3), dtype=np.int64)
    tris[0::2] = np.where(use02[:, None], quads[:, [0, 1, 2]], quads[:, [0, 1, 3]])
    tris[1::2] = np.where(use02[:, None], quads[:, [0, 2, 3]], quads[:, [1, 2, 3]])
    return Mesh(vertices, tris)
