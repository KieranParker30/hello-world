"""Command-line interface: `img2mesh relief|carve|scan ...`."""

from __future__ import annotations

import argparse
import sys

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

    p = sub.add_parser("scan", help="handheld photos -> textured 3D model (photogrammetry)")
    p.add_argument("images", nargs="+", help="20-60 overlapping photos of the object")
    p.add_argument("-o", "--output", default="model.glb",
                   help="output .glb/.ply/.obj keep colour, .stl does not (default model.glb)")
    p.add_argument("--resolution", type=int, default=200, help="voxels on longest side")
    p.add_argument("--size", type=float, default=100.0, help="largest dimension in mm")
    p.add_argument("--crop", type=float, default=0.75,
                   help="how much surroundings to keep (bigger = more, default 0.75)")
    p.add_argument("--image-size", type=int, default=1600,
                   help="photo size used for camera solving (default 1600)")
    p.add_argument("--dense-size", type=int, default=1000,
                   help="photo size used for depth maps (default 1000)")
    p.add_argument("--work-dir", help="keep intermediate files (COLMAP database, sparse model)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "relief":
            mesh = image_to_relief(args.image, args.width, args.height, args.base,
                                   args.resolution, args.depth, args.invert, args.smooth)
        elif args.command == "scan":
            from .photogrammetry import reconstruct

            mesh = reconstruct(args.images, args.resolution, args.size, args.image_size,
                               args.dense_size, crop=args.crop, work_dir=args.work_dir)
        else:
            angles = [float(a) for a in args.angles.split(",")] if args.angles else None
            mesh = images_to_model(args.images, angles, args.resolution, args.size,
                                   args.threshold, args.axis, args.reverse, args.smooth,
                                   not args.keep_holes, args.save_masks)
        mesh.save(args.output)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    lo, hi = mesh.bounds()
    dims = " x ".join(f"{d:.1f}" for d in hi - lo)
    print(f"Saved {args.output}: {len(mesh.faces):,} triangles, {dims} mm")
    if args.command == "scan" and args.output.lower().endswith(".stl"):
        print("note: STL has no colour; use .glb, .ply or .obj to keep the photo colours")
    return 0
