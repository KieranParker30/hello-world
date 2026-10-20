import numpy as np

from img2mesh.cleanup import (
    _boundary_halfedges, fill_small_holes, keep_large_components, trim_ragged_border,
)
from img2mesh.relief import heightmap_to_mesh
from img2mesh.surface import surface_nets
from img2mesh.mesh import Mesh


def _sphere():
    g = np.mgrid[-12:13, -12:13, -12:13]
    return surface_nets(8 - np.sqrt((g**2).sum(0)), 0.0)


def test_fill_small_holes_closes_pinholes_only():
    sphere = _sphere()
    assert sphere.is_watertight()
    # Punch a small hole (the faces around one vertex).
    holed = Mesh(sphere.vertices, sphere.faces[~(sphere.faces == 0).any(axis=1)])
    assert not holed.is_watertight()
    filled = fill_small_holes(holed, max_edges=40)
    assert filled.is_watertight() and filled.volume() > 0

    # An open grid's outer border is far longer than 40 edges: left alone.
    sheet = heightmap_to_mesh(np.zeros((20, 20)))
    top = Mesh(sheet.vertices, sheet.faces[: 2 * 19 * 19])
    assert len(fill_small_holes(top, 40).faces) == len(top.faces)


def test_trim_ragged_border_removes_spikes():
    sheet = heightmap_to_mesh(np.zeros((10, 10)))
    top = sheet.faces[: 2 * 9 * 9]
    spike_v = len(sheet.vertices)
    vertices = np.vstack([sheet.vertices, [[50, 200, 2]]])
    # A lone triangle sticking out from the border, sharing only one edge.
    spiky = Mesh(vertices, np.vstack([top, [[0, 1, spike_v]]]))
    trimmed = trim_ragged_border(spiky)
    assert len(trimmed.faces) < len(spiky.faces)
    assert trimmed.vertices[:, 1].max() < 200  # the spike vertex is gone
    assert len(_boundary_halfedges(trimmed.faces)) > 0


def test_keep_large_components_drops_fragments():
    sphere = _sphere()
    crumb = Mesh(sphere.vertices[:3] + 100, [[0, 1, 2]])
    both = Mesh(np.vstack([sphere.vertices, crumb.vertices]),
                np.vstack([sphere.faces, crumb.faces + len(sphere.vertices)]))
    kept = keep_large_components(both)
    assert len(kept.faces) == len(sphere.faces) and kept.is_watertight()
