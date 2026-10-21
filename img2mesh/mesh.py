"""Triangle mesh container and file writers (STL, OBJ, PLY, GLB)."""

from __future__ import annotations

import io
import json
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class Mesh:
    vertices: np.ndarray  # (N, 3) float, millimetres, +Z up
    faces: np.ndarray  # (M, 3) int, counter-clockwise when viewed from outside
    colors: np.ndarray | None = None  # optional (N, 3) uint8 per-vertex RGB
    uvs: np.ndarray | None = None  # optional (N, 2) texture coords, v pointing down the image
    normals: np.ndarray | None = None  # optional (N, 3) shading normals
    texture: np.ndarray | None = None  # optional (H, W, 3) uint8 colour map
    normal_map: np.ndarray | None = None  # optional (H, W, 3) uint8 tangent-space normals
    tangents: np.ndarray | None = None  # optional (N, 4) frames the normal map was baked with

    def __post_init__(self) -> None:
        self.vertices = np.asarray(self.vertices, dtype=np.float64).reshape(-1, 3)
        self.faces = np.asarray(self.faces, dtype=np.int64).reshape(-1, 3)
        if self.colors is not None:
            self.colors = np.asarray(self.colors, dtype=np.uint8).reshape(-1, 3)
        if self.uvs is not None:
            self.uvs = np.asarray(self.uvs, dtype=np.float64).reshape(-1, 2)
        if self.normals is not None:
            self.normals = np.asarray(self.normals, dtype=np.float64).reshape(-1, 3)
        if self.tangents is not None:
            self.tangents = np.asarray(self.tangents, dtype=np.float64).reshape(-1, 4)

    def _with(self, vertices: np.ndarray, normals: np.ndarray | None,
              tangents: np.ndarray | None = None) -> "Mesh":
        return Mesh(vertices, self.faces, self.colors, self.uvs, normals,
                    self.texture, self.normal_map, tangents)

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
        return self._with(v, self.normals, self.tangents)

    def rotated(self, R: np.ndarray) -> "Mesh":
        n = None if self.normals is None else self.normals @ R.T
        t = None
        if self.tangents is not None:
            t = np.hstack([self.tangents[:, :3] @ R.T, self.tangents[:, 3:]])
        return self._with(self.vertices @ R.T, n, t)

    def vertex_normals(self) -> np.ndarray:
        if self.normals is not None:
            return self.normals
        v = self.vertices[self.faces]
        face_n = np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])  # area-weighted
        n = np.zeros_like(self.vertices)
        for i in range(3):
            np.add.at(n, self.faces[:, i], face_n)
        length = np.linalg.norm(n, axis=1, keepdims=True)
        n = n / np.where(length == 0, 1, length)
        n[length[:, 0] == 0] = [0, 0, 1]  # only touches zero-area faces
        return n

    def vertex_colors(self) -> np.ndarray | None:
        """Per-vertex colours, sampled from the texture if there is one."""
        if self.colors is not None or self.texture is None or self.uvs is None:
            return self.colors
        h, w = self.texture.shape[:2]
        x = np.clip(np.round(self.uvs[:, 0] * w - 0.5), 0, w - 1).astype(int)
        y = np.clip(np.round(self.uvs[:, 1] * h - 0.5), 0, h - 1).astype(int)
        return self.texture[y, x]

    def save(self, path: str | Path, draco: bool = False, jpeg_quality: int = 90,
             quantize: bool = False) -> None:
        """Write the mesh. For .glb, `draco` compresses geometry with Draco (smallest,
        needs a Draco decoder); `quantize` stores it with KHR_mesh_quantization
        (compact integer attributes that every major glTF viewer reads natively)."""
        path = Path(path)
        ext = path.suffix.lower()
        if ext not in (".stl", ".obj", ".ply", ".glb"):
            raise ValueError(f"Unsupported output format '{ext}' (use .stl, .obj, .ply or .glb)")
        path.parent.mkdir(parents=True, exist_ok=True)
        if ext == ".glb":
            _write_glb(self, path, draco, jpeg_quality, quantize)
        elif ext == ".obj":
            _write_obj(self, path, jpeg_quality)
        else:
            {".stl": _write_stl, ".ply": _write_ply}[ext](self, path)


def _srgb_to_linear(srgb: np.ndarray) -> np.ndarray:
    return np.where(srgb <= 0.04045, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4)


def _encode_image(img: np.ndarray, quality: int) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.fromarray(img).save(buf, "JPEG", quality=quality, subsampling=0, optimize=True)
    return buf.getvalue()


def _write_stl(mesh: Mesh, path: Path) -> None:
    record = np.dtype([("normal", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")])
    data = np.zeros(len(mesh.faces), dtype=record)
    data["normal"] = mesh.face_normals()
    data["v"] = mesh.vertices[mesh.faces]
    with open(path, "wb") as fh:
        fh.write(b"img2mesh binary STL".ljust(80, b"\0"))
        fh.write(struct.pack("<I", len(data)))
        fh.write(data.tobytes())


def _write_obj(mesh: Mesh, path: Path, jpeg_quality: int = 90) -> None:
    textured = mesh.texture is not None and mesh.uvs is not None
    colors = None if textured else mesh.vertex_colors()
    with open(path, "w") as fh:
        fh.write("# img2mesh\n")
        if textured:
            stem = path.stem
            fh.write(f"mtllib {stem}.mtl\nusemtl scan\n")
            mtl = f"newmtl scan\nKa 1 1 1\nKd 1 1 1\nKs 0 0 0\nmap_Kd {stem}_color.jpg\n"
            (path.parent / f"{stem}_color.jpg").write_bytes(_encode_image(mesh.texture, jpeg_quality))
            if mesh.normal_map is not None:
                mtl += f"norm {stem}_normal.jpg\n"
                (path.parent / f"{stem}_normal.jpg").write_bytes(
                    _encode_image(mesh.normal_map, max(jpeg_quality, 95)))
            (path.parent / f"{stem}.mtl").write_text(mtl)
        if colors is None:
            np.savetxt(fh, mesh.vertices, fmt="v %.6f %.6f %.6f")
        else:  # widely supported "v x y z r g b" extension
            np.savetxt(fh, np.hstack([mesh.vertices, colors / 255.0]),
                       fmt="v %.6f %.6f %.6f %.4f %.4f %.4f")
        if textured:
            # OBJ's v axis points up the image.
            np.savetxt(fh, np.c_[mesh.uvs[:, 0], 1 - mesh.uvs[:, 1]], fmt="vt %.6f %.6f")
            np.savetxt(fh, np.repeat(mesh.faces + 1, 2, axis=1), fmt="f %d/%d %d/%d %d/%d")
        else:
            np.savetxt(fh, mesh.faces + 1, fmt="f %d %d %d")


def _write_ply(mesh: Mesh, path: Path) -> None:
    colors = mesh.vertex_colors()
    header = (
        "ply\nformat binary_little_endian 1.0\n"
        f"element vertex {len(mesh.vertices)}\n"
        "property float x\nproperty float y\nproperty float z\n"
        + ("property uchar red\nproperty uchar green\nproperty uchar blue\n"
           if colors is not None else "")
        + f"element face {len(mesh.faces)}\n"
        "property list uchar int vertex_indices\nend_header\n"
    )
    face_rec = np.dtype([("n", "u1"), ("idx", "<i4", 3)])
    faces = np.zeros(len(mesh.faces), dtype=face_rec)
    faces["n"] = 3
    faces["idx"] = mesh.faces
    with open(path, "wb") as fh:
        fh.write(header.encode("ascii"))
        if colors is None:
            fh.write(mesh.vertices.astype("<f4").tobytes())
        else:
            rec = np.dtype([("xyz", "<f4", 3), ("rgb", "u1", 3)])
            verts = np.zeros(len(mesh.vertices), dtype=rec)
            verts["xyz"], verts["rgb"] = mesh.vertices, colors
            fh.write(verts.tobytes())
        fh.write(faces.tobytes())


def _write_glb(mesh: Mesh, path: Path, draco: bool = False, jpeg_quality: int = 90,
               quantize: bool = False) -> None:
    """Binary glTF 2.0: the standard 3D format for the web (three.js, <model-viewer>,
    Babylon.js), and it opens in Blender, Windows 3D Viewer and on phones.

    glTF is Y-up and in metres, so our Z-up millimetre coordinates are converted.
    """
    to_gltf = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], dtype=np.float64)  # Z-up -> Y-up
    pos = (mesh.vertices @ to_gltf.T / 1000.0).astype("<f4")
    nrm = (mesh.vertex_normals() @ to_gltf.T).astype("<f4")
    textured = mesh.texture is not None and mesh.uvs is not None
    vcol = None if textured else mesh.vertex_colors()
    tan = None
    if textured and mesh.normal_map is not None and mesh.tangents is not None:
        tan = np.hstack([mesh.tangents[:, :3] @ to_gltf.T, mesh.tangents[:, 3:]]).astype("<f4")
    idx = mesh.faces.astype("<u4")
    if draco and vcol is not None:
        raise ValueError("Draco export supports textured or plain meshes, not vertex colours")
    if draco and quantize:
        raise ValueError("Choose either Draco compression or quantization, not both")
    node: dict = {"mesh": 0}

    blob = bytearray()
    views: list[dict] = []
    accessors: list[dict] = []

    def add_view(data: bytes, target: int | None = None) -> int:
        while len(blob) % 4:
            blob.append(0)
        view = {"buffer": 0, "byteOffset": len(blob), "byteLength": len(data)}
        if target:
            view["target"] = target
        views.append(view)
        blob.extend(data)
        return len(views) - 1

    def add_accessor(view: int | None, comp: int, count: int, kind: str, **extra) -> int:
        acc = {"componentType": comp, "count": count, "type": kind, **extra}
        if view is not None:
            acc["bufferView"] = view
        accessors.append(acc)
        return len(accessors) - 1

    bounds = {"min": pos.min(0).tolist(), "max": pos.max(0).tolist()}
    primitive: dict = {"attributes": {}, "material": 0}
    extensions_used: list[str] = []
    if draco:
        import DracoPy

        uv = mesh.uvs.astype(np.float64) if textured else None
        encoded = DracoPy.encode(
            pos, idx.astype(np.uint32), quantization_bits=16, compression_level=7,
            tex_coord=uv, normals=nrm.astype(np.float64), tex_coord_quantization_bits=14,
            normal_quantization_bits=10, preserve_order=True,
            generic_attributes=None if tan is None else {0: tan.astype(np.float64)},
        )
        ids = _draco_attribute_ids(encoded)
        attrs = {"POSITION": add_accessor(None, 5126, len(pos), "VEC3", **bounds),
                 "NORMAL": add_accessor(None, 5126, len(pos), "VEC3")}
        if textured:
            attrs["TEXCOORD_0"] = add_accessor(None, 5126, len(pos), "VEC2")
        if tan is not None:
            attrs["TANGENT"] = add_accessor(None, 5126, len(pos), "VEC4")
        primitive["attributes"] = attrs
        primitive["indices"] = add_accessor(None, 5125, idx.size, "SCALAR")
        primitive["extensions"] = {"KHR_draco_mesh_compression": {
            "bufferView": add_view(encoded),
            "attributes": {name: ids[name] for name in attrs}}}
        extensions_used.append("KHR_draco_mesh_compression")
    elif quantize:
        # KHR_mesh_quantization: 16-bit positions placed by the node's transform,
        # 8-bit normals/tangents, 16-bit UVs. Attributes are padded to 4 bytes.
        centre = (pos.min(0) + pos.max(0)) / 2
        half = float(max((pos.max(0) - pos.min(0)).max() / 2, 1e-9))
        q = np.round((pos - centre) / half * 32767).astype("<i2")
        q4 = np.zeros((len(q), 4), "<i2")
        q4[:, :3] = q
        node.update(translation=[float(c) for c in centre], scale=[half / 32767] * 3)

        def snorm8(a: np.ndarray, n: int) -> bytes:
            out = np.zeros((len(a), 4), "i1")
            out[:, :n] = np.round(np.clip(a[:, :n], -1, 1) * 127)
            return out.tobytes()

        def strided(data: bytes, stride: int) -> int:
            view = add_view(data, 34962)
            views[view]["byteStride"] = stride
            return view

        attrs = primitive["attributes"]
        attrs["POSITION"] = add_accessor(strided(q4.tobytes(), 8), 5122, len(q), "VEC3",
                                         min=q.min(0).tolist(), max=q.max(0).tolist())
        attrs["NORMAL"] = add_accessor(strided(snorm8(nrm, 3), 4), 5120, len(q), "VEC3",
                                       normalized=True)
        if textured:
            uv16 = np.round(np.clip(mesh.uvs, 0, 1) * 65535).astype("<u2")
            attrs["TEXCOORD_0"] = add_accessor(strided(uv16.tobytes(), 4), 5123, len(q),
                                               "VEC2", normalized=True)
        if tan is not None:
            t8 = np.hstack([tan[:, :3], np.sign(tan[:, 3:])])
            attrs["TANGENT"] = add_accessor(strided(snorm8(t8, 4), 4), 5120, len(q), "VEC4",
                                            normalized=True)
        if vcol is not None:  # linear, 16-bit RGBA keeps dark tones and 4-byte alignment
            linear = _srgb_to_linear(vcol / 255.0)
            rgba = np.hstack([linear, np.ones((len(q), 1))])
            attrs["COLOR_0"] = add_accessor(
                add_view(np.round(rgba * 65535).astype("<u2").tobytes(), 34962),
                5123, len(q), "VEC4", normalized=True)
        if len(q) < 65536:
            primitive["indices"] = add_accessor(
                add_view(idx.astype("<u2").tobytes(), 34963), 5123, idx.size, "SCALAR")
        else:
            primitive["indices"] = add_accessor(
                add_view(idx.tobytes(), 34963), 5125, idx.size, "SCALAR")
        extensions_used.append("KHR_mesh_quantization")
    else:
        primitive["attributes"]["POSITION"] = add_accessor(
            add_view(pos.tobytes(), 34962), 5126, len(pos), "VEC3", **bounds)
        primitive["attributes"]["NORMAL"] = add_accessor(
            add_view(nrm.tobytes(), 34962), 5126, len(pos), "VEC3")
        if textured:
            primitive["attributes"]["TEXCOORD_0"] = add_accessor(
                add_view(mesh.uvs.astype("<f4").tobytes(), 34962), 5126, len(pos), "VEC2")
        if tan is not None:
            primitive["attributes"]["TANGENT"] = add_accessor(
                add_view(tan.tobytes(), 34962), 5126, len(pos), "VEC4")
        if vcol is not None:  # glTF vertex colours are linear, not sRGB
            linear = _srgb_to_linear(vcol / 255.0)
            primitive["attributes"]["COLOR_0"] = add_accessor(
                add_view(linear.astype("<f4").tobytes(), 34962), 5126, len(pos), "VEC3")
        primitive["indices"] = add_accessor(add_view(idx.tobytes(), 34963), 5125, idx.size, "SCALAR")

    material: dict = {"pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1],
                                               "metallicFactor": 0, "roughnessFactor": 1},
                      "doubleSided": True}
    images, textures = [], []
    if textured:
        for key, img, quality in (("baseColorTexture", mesh.texture, jpeg_quality),
                                  ("normalTexture", mesh.normal_map, max(jpeg_quality, 95))):
            if img is None:
                continue
            images.append({"bufferView": add_view(_encode_image(img, quality)),
                           "mimeType": "image/jpeg"})
            textures.append({"source": len(images) - 1, "sampler": 0})
            ref = {"index": len(textures) - 1}
            if key == "baseColorTexture":
                material["pbrMetallicRoughness"][key] = ref
            else:
                material[key] = ref

    gltf: dict = {
        "asset": {"version": "2.0", "generator": "img2mesh"},
        "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [node],
        "meshes": [{"primitives": [primitive]}],
        "materials": [material],
        "accessors": accessors, "bufferViews": views,
    }
    if images:
        gltf["images"], gltf["textures"] = images, textures
        gltf["samplers"] = [{"magFilter": 9729, "minFilter": 9987, "wrapS": 33071, "wrapT": 33071}]
    if extensions_used:
        gltf["extensionsUsed"] = gltf["extensionsRequired"] = extensions_used
    while len(blob) % 4:
        blob.append(0)
    gltf["buffers"] = [{"byteLength": len(blob)}]
    js = json.dumps(gltf, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    with open(path, "wb") as fh:
        fh.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(blob)))
        fh.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
        fh.write(struct.pack("<II", len(blob), 0x004E4942) + bytes(blob))


def _draco_attribute_ids(encoded: bytes) -> dict[str, int]:
    """Read the unique id of each attribute from a Draco buffer."""
    import DracoPy

    mesh = DracoPy.decode(encoded)
    ids = {}
    for attr in mesh.attributes:
        kind = attr["attribute_type"]
        name = {DracoPy.AttributeType.POSITION: "POSITION",
                DracoPy.AttributeType.NORMAL: "NORMAL",
                DracoPy.AttributeType.TEX_COORD: "TEXCOORD_0",
                DracoPy.AttributeType.GENERIC: "TANGENT"}.get(kind)
        if name:
            ids[name] = int(attr["unique_id"])
    return ids
