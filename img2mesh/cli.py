"""Command-line interface: `img2mesh relief|carve|cutout|scan ...`."""

from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path

from .carve import images_to_model
from .relief import image_to_relief


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="img2mesh", description="Turn images into 3D models (STL / OBJ / PLY / GLB)."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    r = sub.add_parser("relief", help="one image -> relief / heightmap / lithophane")
    r.add_argument("image")
    r.add_argument("-o", "--output", default="model.stl", help="output .stl/.obj/.ply")
    r.add_argument("--width", type=float, default=100.0, help="model width in mm (default 100)")
    r.add_argument("--height", type=float, default=10.0, help="relief depth in mm (default 10)")
    r.add_argument("--base", type=float, default=2.0, help="base thickness in mm (default 2)")
    r.add_argument("--resolution", type=int, default=256, help="grid size on long side")
    r.add_argument("--depth", choices=["brightness", "ai"], default="brightness",
                   help="brightness = light is high; ai = estimate real depth with a neural net")
    r.add_argument("--invert", action="store_true", help="dark is high (use for lithophanes)")
    r.add_argument("--smooth", type=float, default=0.0, help="blur radius in pixels")

    c = sub.add_parser("carve", help="photos around an object -> full 3D model")
    c.add_argument("images", nargs="+", help="photos in order around the object")
    c.add_argument("-o", "--output", default="model.stl", help="output .stl/.obj/.ply")
    c.add_argument("--angles", type=str, help="comma-separated angles in degrees "
                   "(default: evenly spaced over 360)")
    c.add_argument("--resolution", type=int, default=128, help="voxels on longest side")
    c.add_argument("--size", type=float, default=100.0, help="largest dimension in mm")
    c.add_argument("--threshold", type=float, default=40.0,
                   help="colour difference from background counted as object (0-255)")
    c.add_argument("--axis", type=float, default=0.5,
                   help="turntable axis position as fraction of image width (default 0.5)")
    c.add_argument("--reverse", action="store_true", help="photos go the other way round "
                   "(use if the result is mirrored)")
    c.add_argument("--smooth", type=float, default=1.0, help="surface smoothing (voxels)")
    c.add_argument("--keep-holes", action="store_true",
                   help="keep holes in silhouettes (e.g. a mug handle)")
    c.add_argument("--save-masks", metavar="DIR", help="write detected silhouettes for checking")

    k = sub.add_parser("cutout", help="one product photo -> textured 3D cut-out (AI depth)")
    k.add_argument("images", nargs="+", help="product photos (transparent or plain background)")
    k.add_argument("-o", "--output", default=".",
                   help="output .glb for one photo, or a folder for several (default: here)")
    k.add_argument("--width", type=float, default=300.0, help="model width in mm (default 300)")
    k.add_argument("--depth", type=float, default=0.35,
                   help="relief depth as a fraction of the width (default 0.35)")
    k.add_argument("--back", type=float, default=0.6,
                   help="back depth relative to the front (default 0.6)")
    k.add_argument("--resolution", type=int, default=400, help="grid size on the long side")
    k.add_argument("--texture-size", type=int, default=2048, help="texture size in pixels")
    k.add_argument("--html", action="store_true", help="also write <model-viewer> pages")

    p = sub.add_parser("scan", help="handheld photos -> textured 3D model (photogrammetry)")
    p.add_argument("images", nargs="+", help="20-60 overlapping photos of the object")
    p.add_argument("-o", "--output", default="model.glb",
                   help="output file; .glb is best for websites (default model.glb)")
    p.add_argument("--quality", choices=["draft", "high", "ultra"], default="high",
                   help="draft = quick check, high = website quality (default), "
                        "ultra = maximum detail, slower and bigger")
    p.add_argument("--faces", type=int, help="triangle budget for the final model")
    p.add_argument("--texture-size", type=int, help="texture width/height in pixels")
    p.add_argument("--resolution", type=int, help="voxels on the longest side")
    p.add_argument("--size", type=float, default=100.0, help="largest dimension in mm")
    p.add_argument("--crop", type=float, default=0.75,
                   help="how much surroundings to keep (bigger = more, default 0.75)")
    p.add_argument("--remove-ground", action="store_true",
                   help="cut away the table or floor the object stands on")
    p.add_argument("--keep-gaps", action="store_true",
                   help="don't bridge small gaps with Poisson surface reconstruction")
    p.add_argument("--no-draco", action="store_true",
                   help="don't Draco-compress the .glb geometry (for viewers without Draco)")
    p.add_argument("--html", action="store_true",
                   help="also write a web page that shows the model with <model-viewer>")
    p.add_argument("--image-size", type=int, help="photo size used for camera solving")
    p.add_argument("--dense-size", type=int, help="photo size used for depth maps")
    p.add_argument("--work-dir", help="keep intermediate files (COLMAP database, sparse model)")
    return parser


MODEL_VIEWER = "https://cdn.jsdelivr.net/npm/@google/model-viewer@4.0.0/dist/model-viewer.min.js"


def write_preview_html(glb_path: str) -> Path:
    """A page showing the model with <model-viewer>; copy the tag into your site."""
    glb = Path(glb_path)
    name = html.escape(glb.stem)
    page = glb.with_suffix(".html")
    page.write_text(f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{name}</title>
<script type="module" src="{MODEL_VIEWER}"></script>
<style>
  body {{ margin: 0; font-family: system-ui, sans-serif; background: #f4f4f2; }}
  model-viewer {{ width: 100%; height: 100vh; --poster-color: transparent; }}
</style>
</head>
<body>
<!-- Copy this tag into your website. Serve the page over http(s), not file://. -->
<model-viewer src="{html.escape(glb.name)}" alt="3D model of {name}"
  camera-controls touch-action="pan-y" auto-rotate auto-rotate-delay="2000"
  shadow-intensity="1" exposure="1" environment-image="neutral" ar>
</model-viewer>
</body>
</html>
""")
    return page


def _cutout(args) -> int:
    from .cutout import cutout_model

    out = Path(args.output)
    single = len(args.images) == 1 and out.suffix.lower() == ".glb"
    if not single:
        out.mkdir(parents=True, exist_ok=True)
    for image in args.images:
        dst = out if single else out / (Path(image).stem + ".glb")
        try:
            mesh = cutout_model(image, args.width, args.depth, args.back, args.resolution,
                                args.texture_size)
            mesh.save(dst, draco=True)
            if args.html:
                write_preview_html(str(dst))
        except (ValueError, OSError) as exc:
            print(f"error: {image}: {exc}", file=sys.stderr)
            return 1
        print(f"Saved {dst}: {len(mesh.faces):,} triangles, {dst.stat().st_size / 1e6:.1f} MB")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "cutout":
        return _cutout(args)
    try:
        if args.command == "relief":
            mesh = image_to_relief(args.image, args.width, args.height, args.base,
                                   args.resolution, args.depth, args.invert, args.smooth)
        elif args.command == "scan":
            from .photogrammetry import reconstruct

            mesh = reconstruct(
                args.images, quality=args.quality, size=args.size, resolution=args.resolution,
                faces=args.faces, texture_size=args.texture_size,
                max_image_size=args.image_size, dense_size=args.dense_size, crop=args.crop,
                remove_ground=args.remove_ground, fill_gaps=not args.keep_gaps,
                work_dir=args.work_dir)
        else:
            angles = [float(a) for a in args.angles.split(",")] if args.angles else None
            mesh = images_to_model(args.images, angles, args.resolution, args.size,
                                   args.threshold, args.axis, args.reverse, args.smooth,
                                   not args.keep_holes, args.save_masks)
        is_glb = args.output.lower().endswith(".glb")
        draco = args.command == "scan" and is_glb and not args.no_draco
        mesh.save(args.output, draco=draco)
        if getattr(args, "html", False):
            if not is_glb:
                raise ValueError("--html needs a .glb output")
            page = write_preview_html(args.output)
            print(f"Wrote {page}")
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    lo, hi = mesh.bounds()
    dims = " x ".join(f"{d:.1f}" for d in hi - lo)
    size_mb = Path(args.output).stat().st_size / 1e6
    print(f"Saved {args.output}: {len(mesh.faces):,} triangles, {dims} mm, {size_mb:.1f} MB")
    if args.command == "scan" and args.output.lower().endswith((".stl", ".ply")):
        print("note: this format has no texture maps; use .glb (or .obj) for full quality")
    return 0
