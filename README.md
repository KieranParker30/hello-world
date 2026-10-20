# img2mesh

Turn images into 3D models you can view, edit or 3D-print (`.stl`, `.obj`, `.ply`, `.glb`).

Three ways to build a model:

| Mode | Input | Output |
|------|-------|--------|
| `scan` | **20–60 handheld photos** of an object or scene | Full photogrammetry: a website-ready textured 3D model (`.glb`) with real detail, including dents, holes and hollows. |
| `relief` | **one** image | A solid slab whose surface follows the picture: a bas-relief, embossed logo, terrain or lithophane. With `--depth ai`, a neural network estimates real depth from a photo. |
| `carve` | **several** photos taken around an object | A full 360° model, built by carving away everything outside the object's outline in each photo (the "visual hull"). |

`relief` and `carve` models are closed (watertight), so they're ready for slicers like Cura or PrusaSlicer.

## Install

```bash
pip install .            # core: only needs numpy + Pillow
pip install ".[photo]"   # optional: photogrammetry (COLMAP via pycolmap, OpenCV, SciPy)
pip install ".[ai]"      # optional: AI depth estimation (PyTorch + transformers)
```

## Handheld photos → textured 3D model for the web (photogrammetry)

```bash
img2mesh scan photos/*.jpg -o statue.glb --html
```

This produces a website-ready `statue.glb` and a `statue.html` showing it with [`<model-viewer>`](https://modelviewer.dev). Copy the `<model-viewer>` tag from that page into your site, next to the `.glb` file.

The model is built the way professional scanning tools build theirs:

- **Texture map.** Colour comes from your full-resolution photos. Each texel uses the photos that see that spot best (facing it, close up, not blocked by anything else) and blends gently between neighbouring photos, so you don't see seams.
- **Normal map.** Fine surface detail (bark, grain, scratches) is baked from the high-resolution scan, so a lighter mesh still catches the light like the detailed one.
- **Clean surface.** Small gaps are bridged with screened Poisson surface reconstruction, frayed borders are trimmed and pinholes are filled. Large areas no camera saw stay open rather than invented. Use `--keep-gaps` to skip the Poisson step.
- **Web-sized mesh.** The detailed surface is reduced to a sensible triangle budget with quadric decimation and UV-unwrapped with [xatlas](https://github.com/jpcy/xatlas).
- **Draco compression.** Geometry is compressed with Draco, which `<model-viewer>`, three.js and Babylon.js all support. Use `--no-draco` for tools that don't.
- **glTF conventions.** Metres, Y up, centred, with the photographed side facing the default camera.

### Putting it on your website

The simplest way is Google's [`<model-viewer>`](https://modelviewer.dev) web component. It handles Draco, lighting, touch controls and AR on phones:

```html
<script type="module" src="https://cdn.jsdelivr.net/npm/@google/model-viewer@4.0.0/dist/model-viewer.min.js"></script>

<model-viewer src="statue.glb" alt="3D model of the statue"
  camera-controls touch-action="pan-y" auto-rotate
  shadow-intensity="1" environment-image="neutral" ar
  style="width: 100%; height: 500px">
</model-viewer>
```

With [three.js](https://threejs.org), give `GLTFLoader` a `DRACOLoader`:

```js
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';

const draco = new DRACOLoader();
draco.setDecoderPath('https://www.gstatic.com/draco/versioned/decoders/1.5.7/');
const loader = new GLTFLoader();
loader.setDRACOLoader(draco);
loader.load('statue.glb', (gltf) => scene.add(gltf.scene));
```

Serve the page over `http(s)://`. Browsers won't load models from `file://` pages.

### Quality presets

| `--quality` | Use it for | Triangles | Textures |
|-------------|-----------|-----------|----------|
| `draft` | Quick check that your photos work | 50,000 | 2048 × 2048 |
| `high` (default) | Websites: sharp on desktop and phones | 150,000 | 4096 × 4096 |
| `ultra` | Hero pieces, zoomed-in viewing, archiving | 400,000 | 8192 × 8192 |

`ultra` textures are larger than some phones can display (many cap at 4096 px), so use `high` for pages that need to work everywhere. Override any part with `--faces` and `--texture-size`.

For even smaller downloads, you can re-compress the textures to KTX2 or WebP with [glTF-Transform](https://gltf-transform.dev): `npx @gltf-transform/cli optimize statue.glb statue-small.glb --texture-compress webp`.

### Taking the photos

1. Walk around the object and take a photo every 10–15°, so each spot appears in **at least 3 photos**. Go round at two or three heights, and take a few close-ups of detailed areas.
2. The object should fill most of the frame. Keep everything sharp: no motion blur and no zooming between shots. Use the highest resolution your camera has.
3. Use soft, even light (overcast outdoors or a light tent is ideal). Avoid flash and harsh shadows, because the lighting ends up baked into the texture.
4. Matte, textured surfaces work best. Shiny, transparent and plain single-colour surfaces give the matcher nothing to lock onto. A light dusting of powder or some masking tape helps.
5. Don't move the object between shots; move the camera. For objects on a table, add `--remove-ground` to cut the table away.

### All options

| Option | Default | Meaning |
|--------|---------|---------|
| `-o` | `model.glb` | `.glb` for websites. `.obj` writes the texture and normal map as JPEGs next to it. `.ply`/`.stl` have no texture maps. |
| `--quality` | `high` | Preset, see above |
| `--faces` | from preset | Triangle budget for the final model |
| `--texture-size` | from preset | Texture width and height in pixels |
| `--resolution` | from preset | Voxels on the longest side of the detailed scan |
| `--size` | 100 | Largest dimension in mm. Photos have no real-world scale, so set this to the real object size if it matters. |
| `--remove-ground` | off | Cut away the table or floor the object stands on |
| `--crop` | 0.75 | How much of the surroundings to keep around the object (raise it if parts get cut off) |
| `--keep-gaps` | off | Don't bridge small gaps (keeps only directly measured surface) |
| `--html` | off | Also write a `<model-viewer>` web page for the model |
| `--no-draco` | off | Store the geometry uncompressed |
| `--work-dir` | temp | Keep the intermediate files (the COLMAP project can be opened in the COLMAP GUI) |

It runs on a normal CPU, no graphics card needed. The underside of an object on a table is never photographed, so it stays open.

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
reconstruct(sorted(glob.glob("photos/*.jpg")), quality="high").save("scan.glb", draco=True)
```

## Tests

```bash
pip install ".[test,photo]" && pytest
```

The tests ray-trace synthetic photos of known objects, rebuild them, and measure the result against the true geometry. For `scan`, that means checking the error is under 2% and that a dent invisible to outlines is recovered. The photogrammetry tests are skipped if the `photo` extras aren't installed.
