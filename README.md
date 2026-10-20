# img2mesh

Turn images into 3D models you can view, edit or 3D-print (`.stl`, `.obj`, `.ply`, `.glb`).

Three ways to build a model:

| Mode | Input | Output |
|------|-------|--------|
| `scan` | **20–60 handheld photos** of an object or scene | Full photogrammetry: a coloured 3D surface with real detail, including dents, holes and hollows. |
| `relief` | **one** image | A solid slab whose surface follows the picture: a bas-relief, embossed logo, terrain or lithophane. With `--depth ai`, a neural network estimates real depth from a photo. |
| `carve` | **several** photos taken around an object | A full 360° model, built by carving away everything outside the object's outline in each photo (the "visual hull"). |

`relief` and `carve` models are closed (watertight), so they're ready for slicers like Cura or PrusaSlicer.

## Install

```bash
pip install .            # core: only needs numpy + Pillow
pip install ".[photo]"   # optional: photogrammetry (COLMAP via pycolmap, OpenCV, SciPy)
pip install ".[ai]"      # optional: AI depth estimation (PyTorch + transformers)
```

## Handheld photos → textured 3D model (photogrammetry)

```bash
img2mesh scan photos/*.jpg -o statue.glb
```

Open the `.glb` in Windows 3D Viewer, macOS Preview/Quick Look, Blender, or any online glTF viewer. It also works on phones.

How it works:

1. **Camera solving** ([COLMAP](https://colmap.github.io/)): matches features between photos to find where each one was taken from and what lens was used.
2. **Depth maps**: each photo is paired with its 4 best neighbours and run through OpenCV's semi-global stereo matcher. A depth is kept only where at least two of the pairs agree.
3. **Fusion**: all depth maps are merged into a voxel grid (a TSDF), which averages out noise and records colour.
4. **Meshing**: the surface is extracted and coloured from the photos. Parts no camera saw are left open, not guessed.

Tips for good photos:

1. Walk around the object and take a photo every 10–15°, so each spot appears in **at least 3 photos**. Go round at two heights if you can.
2. The object should fill most of the frame. Keep everything sharp: no motion blur and no zooming between shots.
3. Use soft, even light (overcast outdoors is ideal). Avoid flash.
4. Matte, textured surfaces work best. Shiny, transparent and plain single-colour surfaces give the matcher nothing to lock onto. A light dusting of powder or some masking tape helps.
5. Don't move the object between shots. Moving the camera is fine.

| Option | Default | Meaning |
|--------|---------|---------|
| `-o` | `model.glb` | `.glb`, `.ply` and `.obj` keep the colours; `.stl` is shape only |
| `--resolution` | 200 | Voxels on the longest side. Higher means more detail, more time and more memory. |
| `--size` | 100 | Largest dimension in mm. Photos have no real-world scale, so set this yourself. |
| `--crop` | 0.75 | How much of the surroundings to keep around the object (raise it if parts get cut off) |
| `--image-size` | 1600 | Photo size used for camera solving |
| `--dense-size` | 1000 | Photo size used for depth maps |
| `--work-dir` | temp | Keep the intermediate files (the COLMAP project can be opened in the COLMAP GUI) |

It runs on a normal CPU, no graphics card needed: 41 phone photos take about 3–4 minutes. The output is a surface rather than a solid. To 3D-print it, close it first, for example with *Make Manifold* in PrusaSlicer or *Solidify* in Blender.

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

**Limitations:** carving can only recover what shows up in outlines, so concave areas (the inside of a bowl, a dent) get filled in. Use `scan` for those. A plain `front, side` pair (`--angles 0,90`) also works, for simple blocky shapes.

## Use from Python

```python
import glob

from img2mesh import image_to_relief, images_to_model
from img2mesh.photogrammetry import reconstruct

image_to_relief("logo.png", width=80, max_height=4).save("logo.stl")
images_to_model(["a.jpg", "b.jpg", "c.jpg", "d.jpg"], size=50).save("model.obj")
reconstruct(sorted(glob.glob("photos/*.jpg"))).save("scan.glb")
```

## Tests

```bash
pip install ".[test,photo]" && pytest
```

The tests ray-trace synthetic photos of known objects, rebuild them, and measure the result against the true geometry. For `scan`, that means checking the error is under 2% and that a dent invisible to outlines is recovered. The photogrammetry tests are skipped if the `photo` extras aren't installed.
