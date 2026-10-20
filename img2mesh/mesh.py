"""Triangle mesh container and file writers (STL, OBJ, PLY)."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class Mesh:
    vertices: np.ndarray  # (N, 3) float
    faces: np.ndarray  # (M, 3) int, counter-clockwise when viewed from outside

    def __post_init__(self) -> None:
        self.vertices = np.asarray(self.vertices, dtype=np.float64).reshape(-1, 3)
        self.faces = np.asarray(self.faces, dtype=np.int64).reshape(-1, 3)

    def face_normals(self) -> np.ndarray:
        v = self.vertices[self.faces]
        n = np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])
        length = np.linalg.norm(n, axis=1, keepdims=True)
        return n / np.where(length == 0, 1, length)

    def volume(self) -> float:
        """Signed volume; positive for a closed, outward-facing mesh."""
        v = self.vertices[self.faces]
        return float(np.einsum("ij,ij->i", v[:, 0], np.cross(v[:, 1], v[:, 2])).sum() / 6)

    def is_watertight(self) -> bool:
        """True if every edge is shared by exactly two faces with opposite winding."""
        f = self.faces
        edges = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
        directed = {tuple(e) for e in edges.tolist()}
        if len(directed) != len(edges):
            return False
        return all((b, a) in directed for a, b in directed)

    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        return self.vertices.min(axis=0), self.vertices.max(axis=0)

    def scaled_to(self, size: float) -> "Mesh":
        """Uniformly scale so the largest dimension equals `size`, resting on z=0."""
        lo, hi = self.bounds()
        extent = (hi - lo).max()
        scale = size / extent if extent > 0 else 1.0
        centre = (lo + hi) / 2
        v = (self.vertices - centre) * scale
        v[:, 2] -= v[:, 2].min()
        return Mesh(v, self.faces)

    def save(self, path: str | Path) -> None:
        path = Path(path)
        ext = path.suffix.lower()
        writers = {".stl": _write_stl, ".obj": _write_obj, ".ply": _write_ply}
        if ext not in writers:
            raise ValueError(f"Unsupported output format '{ext}' (use .stl, .obj or .ply)")
        path.parent.mkdir(parents=True, exist_ok=True)
        writers[ext](self, path)


def _write_stl(mesh: Mesh, path: Path) -> None:
    record = np.dtype([("normal", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")])
    data = np.zeros(len(mesh.faces), dtype=record)
    data["normal"] = mesh.face_normals()
    data["v"] = mesh.vertices[mesh.faces]
    with open(path, "wb") as fh:
        fh.write(b"img2mesh binary STL".ljust(80, b"\0"))
        fh.write(struct.pack("<I", len(data)))
        fh.write(data.tobytes())


def _write_obj(mesh: Mesh, path: Path) -> None:
    with open(path, "w") as fh:
        fh.write("# img2mesh\n")
        np.savetxt(fh, mesh.vertices, fmt="v %.6f %.6f %.6f")
        np.savetxt(fh, mesh.faces + 1, fmt="f %d %d %d")


def _write_ply(mesh: Mesh, path: Path) -> None:
    header = (
        "ply\nformat binary_little_endian 1.0\n"
        f"element vertex {len(mesh.vertices)}\n"
        "property float x\nproperty float y\nproperty float z\n"
        f"element face {len(mesh.faces)}\n"
        "property list uchar int vertex_indices\nend_header\n"
    )
    face_rec = np.dtype([("n", "u1"), ("idx", "<i4", 3)])
    faces = np.zeros(len(mesh.faces), dtype=face_rec)
    faces["n"] = 3
    faces["idx"] = mesh.faces
    with open(path, "wb") as fh:
        fh.write(header.encode("ascii"))
        fh.write(mesh.vertices.astype("<f4").tobytes())
        fh.write(faces.tobytes())
