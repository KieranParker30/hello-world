import json
import struct

import numpy as np
import pytest

from img2mesh import Mesh
from img2mesh.raster import rasterize
from img2mesh.texture import Camera, bake, fill_holes


def test_rasterize_coverage_and_depth_order():
    xy = np.array([[2, 2], [12, 2], [12, 12], [2, 12], [7, 7], [17, 7], [17, 17], [7, 17]], float)
    z = np.array([5, 5, 5, 5, 1, 1, 1, 1.0])
    faces = np.array([[0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7]])
    fid, bary, depth = rasterize(xy, z, faces, 20, 20)
    assert (fid >= 0).sum() == 121 + 121 - 36  # two 11x11 squares overlapping 6x6
    assert (fid[7:13, 7:13] >= 2).all()  # the nearer square wins
    assert np.allclose(bary[fid >= 0].sum(axis=1), 1)
    assert depth[3, 3] == pytest.approx(5) and depth[10, 10] == pytest.approx(1)


def test_fill_holes_spreads_known_values():
    img = np.zeros((16, 16, 3), np.float32)
    mask = np.zeros((16, 16), bool)
    img[4:8, 4:8] = 200
    mask[4:8, 4:8] = True
    out = fill_holes(img, mask)
    assert np.allclose(out[mask], 200) and np.allclose(out, 200)


def _plane_scene(size=64):
    """A 2x2 square at z=0 facing +z, a camera above it, and a photo of a pattern."""
    verts = np.array([[-1, -1, 0], [1, -1, 0], [1, 1, 0], [-1, 1, 0]], float)
    faces = np.array([[0, 1, 2], [0, 2, 3]])
    uvs = np.array([[0.05, 0.95], [0.95, 0.95], [0.95, 0.05], [0.05, 0.05]])
    mesh = Mesh(verts, faces, uvs=uvs)
    # Camera at z=4 looking down -z; camera x = world x, camera y = -world y.
    R = np.diag([1.0, -1.0, -1.0])
    t = -R @ np.array([0, 0, 4.0])
    K = np.array([[200.0, 0, 199.5], [0, 200.0, 199.5], [0, 0, 1]])
    photo = np.zeros((400, 400, 3), np.uint8)
    photo[:, :200] = (220, 30, 30)  # world x < 0 is red
    photo[:, 200:] = (30, 30, 220)  # world x > 0 is blue
    photo[:200, :, 1] = 200  # world y > 0 (top of photo) gets green added
    return mesh, Camera(K, R, t, photo), size


def test_bake_projects_photo_onto_texture():
    mesh, cam, size = _plane_scene()
    texture, normal_map, normals = bake(mesh, [cam], size, log=lambda *a: None)
    assert normal_map is None and np.allclose(normals[:, 2], 1)

    def texel(u, v):
        return texture[int(v * size), int(u * size)].astype(int)

    # uv (0.2, 0.8) -> world (-0.67, -0.67): red, no green
    assert texel(0.2, 0.8)[0] > 180 and texel(0.2, 0.8)[1] < 60
    # uv (0.8, 0.2) -> world (+0.67, +0.67): blue with green
    c = texel(0.8, 0.2)
    assert c[2] > 180 and c[1] > 160 and c[0] < 60


def test_bake_normal_map_is_flat_for_a_flat_field():
    mesh, cam, size = _plane_scene(32)

    def field(points):
        return np.tile([0.0, 0.0, 1.0], (len(points), 1)), np.ones(len(points), bool)

    _, normal_map, _ = bake(mesh, [cam], size, field=field, log=lambda *a: None)
    assert np.abs(normal_map.reshape(-1, 3).astype(int) - [128, 128, 255]).max() <= 1


def _glb_json(data: bytes) -> dict:
    js_len = struct.unpack("<I", data[12:16])[0]
    return json.loads(data[20:20 + js_len])


@pytest.mark.parametrize("draco", [False, True])
def test_textured_glb(tmp_path, draco):
    if draco:
        pytest.importorskip("DracoPy")
    mesh, cam, size = _plane_scene(32)
    texture, _, normals = bake(mesh, [cam], size, log=lambda *a: None)
    textured = Mesh(mesh.vertices * 50, mesh.faces, uvs=mesh.uvs, normals=normals,
                    texture=texture, normal_map=np.full_like(texture, 128))
    path = tmp_path / "t.glb"
    textured.save(path, draco=draco)
    gltf = _glb_json(path.read_bytes())
    mat = gltf["materials"][0]
    assert "baseColorTexture" in mat["pbrMetallicRoughness"] and "normalTexture" in mat
    assert len(gltf["images"]) == 2
    # Metres, Y-up: the 100 mm square becomes 0.1 m wide and flat in Y.
    acc = gltf["accessors"][gltf["meshes"][0]["primitives"][0]["attributes"]["POSITION"]]
    assert acc["max"][0] - acc["min"][0] == pytest.approx(0.1)
    assert acc["max"][1] == pytest.approx(acc["min"][1])
    if draco:
        import DracoPy

        ext = gltf["meshes"][0]["primitives"][0]["extensions"]["KHR_draco_mesh_compression"]
        view = gltf["bufferViews"][ext["bufferView"]]
        data = path.read_bytes()
        js_len = struct.unpack("<I", data[12:16])[0]
        start = 20 + js_len + 8 + view["byteOffset"]
        decoded = DracoPy.decode(data[start:start + view["byteLength"]])
        by_id = {a["unique_id"]: a for a in decoded.attributes}
        assert by_id[ext["attributes"]["TEXCOORD_0"]]["num_components"] == 2
        assert np.allclose(by_id[ext["attributes"]["TEXCOORD_0"]]["data"], mesh.uvs, atol=1e-3)


def test_textured_obj_writes_material_and_images(tmp_path):
    mesh, cam, size = _plane_scene(16)
    texture, _, _ = bake(mesh, [cam], size, log=lambda *a: None)
    Mesh(mesh.vertices, mesh.faces, uvs=mesh.uvs, texture=texture).save(tmp_path / "m.obj")
    assert (tmp_path / "m.mtl").read_text().count("map_Kd m_color.jpg") == 1
    assert (tmp_path / "m_color.jpg").exists()
    assert "f 1/1 2/2 3/3" in (tmp_path / "m.obj").read_text()
