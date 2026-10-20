# img2mesh

Turn images into 3D models you can view, edit or 3D-print (`.stl`, `.obj`, `.ply`).

Two ways to build a model:

| Mode | Input | Output |
|------|-------|--------|
| `relief` | **one** image | A solid slab whose surface follows the picture: a bas-relief, embossed logo, terrain or lithophane. With `--depth ai`, a neural network estimates real depth from a photo. |
| `carve` | **several** photos taken around an object | A full 360° model, built by carving away everything outside the object's outline in each photo (the "visual hull"). |

Every model is closed (watertight), so it's ready for slicers like Cura or PrusaSlicer.

## Install

```bash
pip install .            # core: only needs numpy + Pillow
pip install ".[ai]"      # optional: AI depth estimation (PyTorch + transformers)
```

## One image → relief

```bash
img2mesh relief logo.png -o logo.stl --width 80 --height 4
img2mesh relief photo.jpg -o photo.stl --depth ai --smooth 1     # AI depth from a photo
img2mesh relief portrait.jpg -o litho.stl --invert --height 3 --base 0.6   # lithophane
```

| Option | Default | Meaning |
|--------|---------|---------|
| `--width` | 100 | Model width in mm |
| `--height` | 10 | Depth of the relief in mm |
| `--base` | 2 | Thickness of the flat base in mm |
| `--resolution` | 256 | Grid points along the long side (more = finer, bigger file) |
| `--depth` | `brightness` | `brightness`: light areas are high. `ai`: estimate depth with [Depth Anything V2](https://huggingface.co/depth-anything/Depth-Anything-V2-Small-hf). The model downloads (~100 MB) on first use. |
| `--invert` | off | Make dark areas high (use this for lithophanes) |
| `--smooth` | 0 | Blur radius in pixels, to reduce noise |

## Several photos → full 3D model

```bash
img2mesh carve photos/*.jpg -o figurine.stl --size 60
```

Tips for good photos:

1. Put the object on a turntable (or a lazy Susan) in front of a **plain background** that contrasts with it.
2. Keep the camera **fixed** at the same height and distance, and aim it at the turntable axis.
3. Take 12–36 photos, turning the object by the same amount each time. Name them so they sort in order (`img_01.jpg`, `img_02.jpg`, …).
4. Shoot from farther away and zoom in. The method assumes little perspective distortion.
5. You can also pass PNGs with a transparent background (for example from a background-removal tool). The tool then uses the transparency directly.

| Option | Default | Meaning |
|--------|---------|---------|
| `--size` | 100 | Largest dimension in mm |
| `--resolution` | 128 | Voxels along the longest side |
| `--angles` | evenly over 360° | Custom angles, e.g. `--angles 0,90,180,270` |
| `--threshold` | 40 | How different from the background a pixel must be to count as object (0–255) |
| `--axis` | 0.5 | Turntable axis position as a fraction of image width |
| `--reverse` | off | Photos go the other way round (use it if the model comes out mirrored) |
| `--smooth` | 1.0 | Surface smoothing |
| `--keep-holes` | off | Keep holes in outlines (e.g. a mug handle) instead of filling them |
| `--save-masks DIR` | – | Save the detected outlines so you can check them |

**Limitations:** carving can only recover what shows up in outlines, so concave areas (the inside of a bowl, a dent) get filled in. A plain `front, side` pair (`--angles 0,90`) also works, for simple blocky shapes.

## Use from Python

```python
from img2mesh import image_to_relief, images_to_model

image_to_relief("logo.png", width=80, max_height=4).save("logo.stl")
images_to_model(["a.jpg", "b.jpg", "c.jpg", "d.jpg"], size=50).save("model.obj")
```

## Tests

```bash
pip install ".[test]" && pytest
```

The tests render synthetic turntable photos of a known object, rebuild it, and check the mesh's volume, watertightness and orientation.
