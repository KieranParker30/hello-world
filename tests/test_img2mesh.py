import struct

import numpy as np
import pytest
from PIL import Image

from img2mesh import Mesh, carve, heightmap_to_mesh, image_to_relief, silhouette, surface_nets
from img2mesh.cli import main
from img2mesh.surface import gaussian_blur3d


def inside_object(x, y, z):
    """Asymmetric test object: a box with a sphere stuck on one corner (pixel units)."""
    box = (np.abs(x) < 40) & (np.abs(y) < 20) & (z > 20) & (z < 120)
    sphere = (x - 30) ** 2 + (y - 15) ** 2 + (z - 120) ** 2 < 25**2
    return box | sphere


def render_view(angle_deg, size=200, background=(240, 240, 240), colour=(180, 40, 40)):
    """Orthographic turntable photo of `inside_object` (axis at image centre)."""
    t = np.radians(angle_deg)
    cx = (size - 1) / 2
    rows, cols = np.mgrid[0:size, 0:size]
    s, z = cols - cx, size - 20 - rows
    hit = np.zeros((size, size), dtype=bool)
    for d in np.linspace(-80, 80, 161):
        x = s * np.cos(t) + d * np.sin(t)
        y = -s * np.sin(t) + d * np.cos(t)
        hit |= inside_object(x, y, z)
    img = np.empty((size, size, 3), dtype=np.uint8)
    img[:] = background
    img[hit] = colour
    return Image.fromarray(img)


def test_surface_nets_sphere_is_closed_with_correct_volume():
    g = np.mgrid[-20:21, -20:21, -20:21]
    field = gaussian_blur3d((np.sqrt((g**2).sum(0)) < 15).astype(float), 1.0)
    mesh = surface_nets(field)
    assert mesh.is_watertight()
    assert mesh.volume() == pytest.approx(4 / 3 * np.pi * 15**3, rel=0.06)


def test_relief_mesh_is_closed_and_sized():
    heights = np.random.default_rng(0).random((30, 40))
    heights[5, 5] = 1.0
    mesh = heightmap_to_mesh(heights, width=80, max_height=5, base=1)
    assert mesh.is_watertight()
    assert mesh.volume() > 0
    lo, hi = mesh.bounds()
    assert hi[0] - lo[0] == pytest.approx(80)
    assert lo[2] == 0 and hi[2] == pytest.approx(6)


def test_relief_bright_is_high_and_not_mirrored(tmp_path):
    img = np.zeros((20, 40), dtype=np.uint8)
    img[:10, 30:] = 255  # bright patch in the top-right of the image
    path = tmp_path / "in.png"
    Image.fromarray(img).save(path)
    mesh = image_to_relief(str(path), width=40, max_height=10, base=0)
    tall = mesh.vertices[mesh.vertices[:, 2] > 5]
    assert len(tall) and (tall[:, 0] > 25).all() and (tall[:, 1] > 9).all()


def test_silhouette_from_plain_background_and_alpha():
    mask = silhouette(render_view(0))
    assert mask[100, 100] and not mask[2, 2]
    rgba = np.zeros((50, 50, 4), dtype=np.uint8)
    rgba[10:40, 20:30] = (255, 255, 255, 255)
    alpha_mask = silhouette(Image.fromarray(rgba))
    assert alpha_mask.sum() == 300


def test_carve_reconstructs_asymmetric_object():
    angles = [i * 30 for i in range(12)]
    masks = [silhouette(render_view(a)) for a in angles]
    mesh = carve(masks, angles, resolution=80, smooth=0.8)
    assert mesh.is_watertight()

    true_volume = inside_object(*np.mgrid[-80:80, -80:80, 0:180]).sum()
    assert mesh.volume() == pytest.approx(true_volume, rel=0.15)

    # The sphere sits at +x, +y: the mesh must not be mirrored.
    v = mesh.vertices
    lo, hi = v.min(0), v.max(0)
    top = v[v[:, 2] > hi[2] - 0.2 * (hi[2] - lo[2])]
    assert top[:, 0].mean() > 0 and top[:, 1].mean() > 0


def test_writers(tmp_path):
    mesh = heightmap_to_mesh(np.zeros((3, 3)))
    mesh.save(tmp_path / "m.stl")
    data = (tmp_path / "m.stl").read_bytes()
    (count,) = struct.unpack("<I", data[80:84])
    assert count == len(mesh.faces) and len(data) == 84 + 50 * count

    mesh.save(tmp_path / "m.obj")
    lines = (tmp_path / "m.obj").read_text().splitlines()
    assert sum(l.startswith("f ") for l in lines) == len(mesh.faces)

    mesh.save(tmp_path / "m.ply")
    assert (tmp_path / "m.ply").read_bytes().startswith(b"ply\n")

    with pytest.raises(ValueError):
        mesh.save(tmp_path / "m.xyz")


def test_cli_end_to_end(tmp_path, capsys):
    paths = []
    for i in range(8):
        p = tmp_path / f"view_{i:02d}.png"
        render_view(i * 45).save(p)
        paths.append(str(p))
    out = tmp_path / "model.stl"
    assert main(["carve", *paths, "-o", str(out), "--resolution", "48", "--size", "50"]) == 0
    assert out.exists() and "Saved" in capsys.readouterr().out

    out2 = tmp_path / "relief.obj"
    assert main(["relief", paths[0], "-o", str(out2), "--resolution", "32"]) == 0
    assert out2.exists()

    assert main(["carve", paths[0], "-o", str(out)]) == 1
    assert isinstance(Mesh([[0, 0, 0]], []), Mesh)


def test_surface_nets_valid_mask_leaves_unobserved_side_open():
    g = np.mgrid[-10:11, -10:11, -10:11]
    field = (np.sqrt((g**2).sum(0)) < 7).astype(float)
    closed = surface_nets(field)
    valid = np.ones(field.shape, dtype=bool)
    valid[:, :, :10] = False  # bottom half never observed
    open_mesh = surface_nets(field, valid=valid)
    assert closed.is_watertight() and not open_mesh.is_watertight()
    assert 0 < len(open_mesh.faces) < len(closed.faces)
    assert open_mesh.vertices[:, 2].min() >= 9  # nothing invented below the cut


def test_coloured_ply_and_obj(tmp_path):
    mesh = heightmap_to_mesh(np.zeros((3, 3)))
    mesh = Mesh(mesh.vertices, mesh.faces, np.tile([255, 0, 0], (len(mesh.vertices), 1)))
    mesh.save(tmp_path / "c.ply")
    data = (tmp_path / "c.ply").read_bytes()
    assert b"property uchar red" in data
    end = data.index(b"end_header\n") + 11
    assert len(data) == end + 15 * len(mesh.vertices) + 13 * len(mesh.faces)
    mesh.save(tmp_path / "c.obj")
    assert "1.0000 0.0000 0.0000" in (tmp_path / "c.obj").read_text()
