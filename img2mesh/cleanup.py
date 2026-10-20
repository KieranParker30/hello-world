"""Mesh clean-up for scanned surfaces: tidy ragged borders, fill pinholes,
drop floating fragments."""

from __future__ import annotations

import numpy as np

from .mesh import Mesh


def _boundary_halfedges(faces: np.ndarray) -> np.ndarray:
    """Directed edges (a, b) of faces whose twin (b, a) does not exist."""
    he = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    n = int(faces.max()) + 1 if len(faces) else 1
    key = he[:, 0] * n + he[:, 1]
    twin = he[:, 1] * n + he[:, 0]
    return he[~np.isin(twin, key)]


def remove_unused_vertices(mesh: Mesh) -> Mesh:
    used = np.unique(mesh.faces)
    remap = np.full(len(mesh.vertices), -1)
    remap[used] = np.arange(len(used))
    pick = lambda a: None if a is None else a[used]  # noqa: E731
    return Mesh(mesh.vertices[used], remap[mesh.faces], pick(mesh.colors), pick(mesh.uvs),
                pick(mesh.normals), mesh.texture, mesh.normal_map)


def keep_large_components(mesh: Mesh, min_fraction: float = 0.01) -> Mesh:
    """Drop pieces with fewer than `min_fraction` of all faces."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components

    n = len(mesh.vertices)
    e = np.concatenate([mesh.faces[:, [0, 1]], mesh.faces[:, [1, 2]]])
    graph = coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n, n))
    _, labels = connected_components(graph, directed=False)
    face_label = labels[mesh.faces[:, 0]]
    ids, counts = np.unique(face_label, return_counts=True)
    keep = np.isin(face_label, ids[counts >= min_fraction * len(mesh.faces)])
    return remove_unused_vertices(Mesh(mesh.vertices, mesh.faces[keep]))


def trim_ragged_border(mesh: Mesh, iterations: int = 4) -> Mesh:
    """Repeatedly remove border triangles that stick out (two or more open edges)
    and triangles hanging on by a single vertex, which turns frayed scan edges
    into clean ones."""
    faces = mesh.faces
    for _ in range(iterations):
        bnd = _boundary_halfedges(faces)
        if len(bnd) == 0:
            break
        n = len(mesh.vertices)
        bkey = set((bnd[:, 0] * n + bnd[:, 1]).tolist())
        he = np.stack([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]], axis=1)
        open_edges = np.isin(he[..., 0] * n + he[..., 1], list(bkey)).sum(axis=1)
        drop = open_edges >= 2
        if not drop.any():
            break
        faces = faces[~drop]
    return remove_unused_vertices(Mesh(mesh.vertices, faces))


def fill_small_holes(mesh: Mesh, max_edges: int = 40) -> Mesh:
    """Close holes whose border has at most `max_edges` edges with a fan of
    triangles around a new centre vertex. Larger openings (the true edge of the
    scan, unseen areas) are left alone."""
    bnd = _boundary_halfedges(mesh.faces)
    if len(bnd) == 0:
        return mesh
    # Walk hole borders; skip vertices where the border branches (non-manifold).
    starts, counts = np.unique(bnd[:, 0], return_counts=True)
    simple = set(starts[counts == 1].tolist())
    nxt = {int(a): int(b) for a, b in bnd if a in simple}
    seen: set[int] = set()
    new_vertices, new_faces = [], []
    base = len(mesh.vertices)
    for start in list(nxt):
        if start in seen:
            continue
        loop = [start]
        seen.add(start)
        cur = nxt[start]
        ok = True
        while cur != start:
            if cur not in nxt or cur in seen or len(loop) > max_edges:
                ok = False
                break
            loop.append(cur)
            seen.add(cur)
            cur = nxt[cur]
        if not ok or len(loop) < 3:
            continue
        centre = mesh.vertices[loop].mean(axis=0)
        c = base + len(new_vertices)
        new_vertices.append(centre)
        for a, b in zip(loop, loop[1:] + loop[:1]):
            new_faces.append((b, a, c))  # reverse of the border edge a->b
    if not new_vertices:
        return mesh
    return Mesh(np.vstack([mesh.vertices, new_vertices]),
                np.vstack([mesh.faces, np.array(new_faces)]))


def clean_scan(mesh: Mesh, hole_edges: int = 40) -> Mesh:
    mesh = keep_large_components(mesh)
    mesh = trim_ragged_border(mesh)
    mesh = fill_small_holes(mesh, hole_edges)
    return keep_large_components(mesh)
