import numpy as np
import pytest
from PIL import Image

from img2mesh import cutout
from img2mesh.cli import main


@pytest.fixture
def product_photo(tmp_path, monkeypatch):
    """A red disc on a transparent background; depth is a dome (closest at the centre)."""
    size = 200
    yy, xx = np.mgrid[0:size, 0:size]
    r = np.hypot(xx - 100, yy - 100)
    rgba = np.zeros((size, size, 4), np.uint8)
    rgba[r < 60] = (200, 30, 30, 255)
    path = tmp_path / "product.png"
    Image.fromarray(rgba).save(path)

    def fake_depth(rgb, model=None):
        h, w = rgb.height, rgb.width
        y, x = np.mgrid[0:h, 0:w]
        return np.clip(1 - np.hypot(x - w / 2, y - h / 2) / (w / 2), 0, 1)

    monkeypatch.setattr(cutout, "estimate_depth", fake_depth)
    return path


def test_cutout_builds_textured_solid_facing_viewer(product_photo):
    mesh = cutout.cutout_model(str(product_photo), width=100, depth=0.3, resolution=80,
                               texture_size=64)
    lo, hi = mesh.bounds()
    assert hi[0] - lo[0] == pytest.approx(100, rel=0.05)  # width from the object only
    assert lo[2] == 0
    assert mesh.volume() > 0 and mesh.texture.shape == (64, 64, 3)
    # The dome bulges towards the viewer (-Y) in the middle of the front.
    mid = np.abs(mesh.vertices[:, 0]) < 5
    assert mesh.vertices[mid, 1].min() < -20
    # Texture is the object's colour, also where the background was (edge padding).
    assert (np.abs(mesh.texture.reshape(-1, 3).astype(int) - [200, 30, 30]).max(axis=1) < 40).all()


def test_cutout_rejects_empty_photo(tmp_path, monkeypatch):
    path = tmp_path / "empty.png"
    Image.fromarray(np.zeros((50, 50, 4), np.uint8)).save(path)
    with pytest.raises(ValueError):
        cutout.cutout_model(str(path))


def test_cutout_cli(product_photo, tmp_path):
    out = tmp_path / "models"
    assert main(["cutout", str(product_photo), "-o", str(out), "--resolution", "60",
                 "--texture-size", "64", "--html"]) == 0
    assert (out / "product.glb").exists() and (out / "product.html").exists()
