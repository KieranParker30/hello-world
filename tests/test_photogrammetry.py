"""End-to-end photogrammetry check against a ray-traced scene with known geometry."""

import json
import struct

import numpy as np
import pytest
from PIL import Image

pytest.importorskip("pycolmap")
pytest.importorskip("cv2")
pytest.importorskip("scipy")

from img2mesh import photogrammetry as pg  # noqa: E402
from img2mesh.surface import surface_nets  # noqa: E402

from synthetic_scene import (  # noqa: E402
    DENT_CENTRE, DENT_RADIUS, camera_orbit, look_at, render, scene_sdf,
)


@pytest.fixture(scope="module")
def scene(tmp_path_factory):
    folder = tmp_path_factory.mktemp("photos")
    centres = camera_orbit(18)
    paths = []
    for i, c in enumerate(centres):
        R, t = look_at(c)
        path = folder / f"view_{i:02d}.png"
        Image.fromarray(render(R, t, size=(480, 360), focal=420.0)).save(path)
        paths.append(str(path))
    return paths, centres, tmp_path_factory.mktemp("work")


def _align(src, dst):
    """Similarity transform (scale, R, t) mapping src points onto dst (Umeyama)."""
    mu_s, mu_d = src.mean(0), dst.mean(0)
    A, B = src - mu_s, dst - mu_d
    U, D, Vt = np.linalg.svd(B.T @ A)
    C = np.eye(3)
    C[2, 2] = np.sign(np.linalg.det(U @ Vt))
    R = U @ C @ Vt
    s = (D * np.diag(C)).sum() / (A**2).sum()
    return s, R, mu_d - s * R @ mu_s


def test_reconstruction_matches_ground_truth_including_dent(scene):
    paths, centres, work = scene
    rec, image_dir = pg.run_sfm(paths, work, log=lambda *a: None)
    views, sparse = pg.load_views(rec, image_dir, 1000)
    assert len(views) >= 15

    s, R, t = _align(np.array([v.centre for v in views]),
                     np.array([centres[int(v.name[:4])] for v in views]))
    points = {k: p.xyz for k, p in rec.points3D.items()}
    nbrs = pg.pick_neighbours(views, points)
    for i, v in enumerate(views):
        v.depth = pg.compute_depth(v, [views[j] for j in nbrs[i]], points)
    lo, hi = pg.fusion_bounds(views, sparse)
    tsdf, weight, voxel = pg.fuse(views, lo, hi, 120)
    mesh = surface_nets(-tsdf, 0.0, valid=weight >= 2)
    world = s * (lo + (mesh.vertices + 0.5) * voxel) @ R.T + t

    err = np.abs(scene_sdf(world))
    assert np.median(err) < 0.02  # block is 1.2 wide: under 2% error
    # The dent (invisible to silhouette carving) must be reconstructed.
    on_dent = np.abs(np.linalg.norm(world - DENT_CENTRE, axis=1) - DENT_RADIUS) < 0.04
    deep = on_dent & (world[:, 1] > DENT_CENTRE[1] + 0.2)
    assert deep.sum() > 20


def test_full_pipeline_writes_textured_web_glb(scene, tmp_path):
    paths, _, _ = scene
    mesh = pg.reconstruct(paths, quality="draft", faces=4000, texture_size=512, size=50,
                          log=lambda *a: None)
    assert mesh.texture.shape == (512, 512, 3) and mesh.normal_map.shape == (512, 512, 3)
    assert mesh.uvs is not None and 3000 < len(mesh.faces) <= 4000
    assert (mesh.bounds()[1] - mesh.bounds()[0]).max() == pytest.approx(50)
    # The texture holds the scene's colours, not a blank fill.
    assert mesh.texture.reshape(-1, 3).std(axis=0).mean() > 20

    out = tmp_path / "scan.glb"
    mesh.save(out, draco=True)
    data = out.read_bytes()
    magic, version, length = struct.unpack("<III", data[:12])
    assert magic == 0x46546C67 and version == 2 and length == len(data)
    js_len = struct.unpack("<I", data[12:16])[0]
    gltf = json.loads(data[20:20 + js_len])
    assert gltf["extensionsRequired"] == ["KHR_draco_mesh_compression"]
    assert "normalTexture" in gltf["materials"][0]


def test_find_ground_detects_floor_under_object():
    rng = np.random.default_rng(1)
    floor = np.c_[rng.uniform(-2, 2, (600, 2)), rng.normal(0, 0.002, 600)]
    box = rng.uniform([-0.5, -0.5, 0.0], [0.5, 0.5, 1.0], (400, 3))
    n, d = pg.find_ground(np.vstack([floor, box]), np.array([0, 0, 1.0]), focus_height=0.5)
    assert n[2] > 0.99 and 0 < d < 0.08
    # Nothing level below the object: no ground.
    assert pg.find_ground(box, np.array([0, 0, 1.0]), focus_height=0.5) is None
