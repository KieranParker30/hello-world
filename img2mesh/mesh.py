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
    colors: np.ndarray | None = None  # optional (N, 3) uint8 per-vertex RGB

    def __post_init__(self) -> None:
        self.vertices = np.asarray(self.vertices, dtype=np.float64).reshape(-1, 3)
        self.faces = np.asarray(self.faces, dtype=np.int64).reshape(-1, 3)
        if self.colors is not None:
            self.colors = np.asarray(self.colors, dtype=np.uint8).reshape(-1, 3)

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
        return Mesh(v, self.faces, self.colors)

    def vertex_normals(self) -> np.ndarray:
        v = self.vertices[self.faces]
        face_n = np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])  # area-weighted
        n = np.zeros_like(self.vertices)
        for i in range(3):
            np.add.at(n, self.faces[:, i], face_n)
        length = np.linalg.norm(n, axis=1, keepdims=True)
        n = n / np.where(length == 0, 1, length)
        n[length[:, 0] == 0] = [0, 0, 1]  # only touches zero-area faces
        return n

    def save(self, path: str | Path) -> None:
        path = Path(path)
        ext = path.suffix.lower()
        writers = {".stl": _write_stl, ".obj": _write_obj, ".ply": _write_ply, ".glb": _write_glb}
        if ext not in writers:
            raise ValueError(f"Unsupported output format '{ext}' (use .stl, .obj, .ply or .glb)")
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
        if mesh.colors is None:
            np.savetxt(fh, mesh.vertices, fmt="v %.6f %.6f %.6f")
        else:  # widely supported "v x y z r g b" extension
            np.savetxt(fh, np.hstack([mesh.vertices, mesh.colors / 255.0]),
                       fmt="v %.6f %.6f %.6f %.4f %.4f %.4f")
        np.savetxt(fh, mesh.faces + 1, fmt="f %d %d %d")


def _write_ply(mesh: Mesh, path: Path) -> None:
    header = (
        "ply\nformat binary_little_endian 1.0\n"
        f"element vertex {len(mesh.vertices)}\n"
        "property float x\nproperty float y\nproperty float z\n"
        + ("property uchar red\nproperty uchar green\nproperty uchar blue\n"
           if mesh.colors is not None else "")
        + f"element face {len(mesh.faces)}\n"
        "property list uchar int vertex_indices\nend_header\n"
    )
    face_rec = np.dtype([("n", "u1"), ("idx", "<i4", 3)])
    faces = np.zeros(len(mesh.faces), dtype=face_rec)
    faces["n"] = 3
    faces["idx"] = mesh.faces
    with open(path, "wb") as fh:
        fh.write(header.encode("ascii"))
        if mesh.colors is None:
            fh.write(mesh.vertices.astype("<f4").tobytes())
        else:
            rec = np.dtype([("xyz", "<f4", 3), ("rgb", "u1", 3)])
            verts = np.zeros(len(mesh.vertices), dtype=rec)
            verts["xyz"], verts["rgb"] = mesh.vertices, mesh.colors
            fh.write(verts.tobytes())
        fh.write(faces.tobytes())


def _write_glb(mesh: Mesh, path: Path) -> None:
    """Binary glTF 2.0 (opens in Windows 3D Viewer, Blender, web viewers, phones).

    glTF is Y-up, so our Z-up coordinates are rotated on export.
    """
    import json

    pos = mesh.vertices[:, [0, 2, 1]].astype("<f4")
    pos[:, 2] *= -1
    chunks = [pos.tobytes(), mesh.vertex_normals()[:, [0, 2, 1]].astype("<f4")]
    chunks[1][:, 2] *= -1
    chunks[1] = chunks[1].tobytes()
    attributes = {"POSITION": 0, "NORMAL": 1}
    accessors = [
        {"bufferView": 0, "componentType": 5126, "count": len(pos), "type": "VEC3",
         "min": pos.min(0).tolist(), "max": pos.max(0).tolist()},
        {"bufferView": 1, "componentType": 5126, "count": len(pos), "type": "VEC3"},
    ]
    if mesh.colors is not None:  # glTF vertex colours are linear, not sRGB
        srgb = mesh.colors / 255.0
        linear = np.where(srgb <= 0.04045, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4)
        chunks.append(linear.astype("<f4").tobytes())
        attributes["COLOR_0"] = 2
        accessors.append({"bufferView": 2, "componentType": 5126, "count": len(pos),
                          "type": "VEC3"})
    chunks.append(mesh.faces.astype("<u4").tobytes())
    accessors.append({"bufferView": len(chunks) - 1, "componentType": 5125,
                      "count": mesh.faces.size, "type": "SCALAR"})

    views, offset, blob = [], 0, b""
    for i, chunk in enumerate(chunks):
        target = 34963 if i == len(chunks) - 1 else 34962  # index / vertex data
        views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(chunk),
                      "target": target})
        blob += chunk + b"\0" * (-len(chunk) % 4)
        offset = len(blob)
    gltf = {
        "asset": {"version": "2.0", "generator": "img2mesh"},
        "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [{"attributes": attributes, "indices": len(accessors) - 1,
                                    "material": 0}]}],
        "materials": [{"pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1],
                                                "metallicFactor": 0, "roughnessFactor": 1},
                       "doubleSided": True}],
        "accessors": accessors, "bufferViews": views, "buffers": [{"byteLength": len(blob)}],
    }
    js = json.dumps(gltf, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    with open(path, "wb") as fh:
        fh.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(blob)))
        fh.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
        fh.write(struct.pack("<II", len(blob), 0x004E4942) + blob)
