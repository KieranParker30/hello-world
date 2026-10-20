"""Handheld photos -> textured 3D model (full photogrammetry).

Pipeline:
1. Structure from Motion with COLMAP (pycolmap): find each photo's camera
   position, orientation and lens from matched SIFT features.
2. Dense stereo: for each photo pick the best neighbouring photos, rectify each
   pair and run OpenCV semi-global matching to get a depth map. Depths from two
   neighbours must agree, which removes most bad matches.
3. Fusion: integrate all depth maps into a truncated signed distance field
   (TSDF) voxel grid, averaging out noise and recording colour.
4. Meshing: extract the surface with surface nets, keeping only parts that
   cameras actually observed, and colour each vertex.

Needs: pip install 'img2mesh[photo]'  (pycolmap, opencv-python-headless, scipy).
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from .mesh import Mesh
from .surface import surface_nets


def _require():
    try:
        import cv2
        import pycolmap
        import scipy  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "Photogrammetry needs extra packages:  pip install 'img2mesh[photo]'\n"
            "(or: pip install pycolmap opencv-python-headless scipy)"
        ) from exc
    return cv2, pycolmap


@dataclass
class View:
    name: str
    K: np.ndarray  # 3x3 intrinsics at dense resolution
    R: np.ndarray  # world -> camera rotation
    t: np.ndarray  # world -> camera translation
    image: np.ndarray  # (h, w, 3) uint8 RGB at dense resolution
    point_ids: set = field(default_factory=set)
    depth: np.ndarray | None = None

    @property
    def centre(self) -> np.ndarray:
        return -self.R.T @ self.t

    @property
    def direction(self) -> np.ndarray:
        return self.R[2]  # optical axis in world coordinates


# --------------------------------------------------------------------------- 1. SfM


def run_sfm(paths: list[str], work: Path, max_size: int = 1600, log=print):
    """Return a reconstruction with undistorted pinhole cameras plus its image dir."""
    _, pycolmap = _require()
    images = work / "images"
    images.mkdir(parents=True, exist_ok=True)
    for i, p in enumerate(paths):
        with Image.open(p) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            im.thumbnail((max_size, max_size), Image.LANCZOS)
            im.save(images / f"{i:04d}_{Path(p).stem}.jpg", quality=95)

    db = work / "database.db"
    log(f"[1/4] Finding features in {len(paths)} photos...")
    pycolmap.extract_features(db, images)
    log("      Matching photos against each other...")
    pycolmap.match_exhaustive(db)
    log("      Solving camera positions (structure from motion)...")
    recs = pycolmap.incremental_mapping(db, images, work / "sparse")
    if not recs:
        raise ValueError(
            "Could not work out where the photos were taken from. Use more photos "
            "with more overlap (each part of the object in 3+ photos) and avoid "
            "plain, shiny or transparent surfaces."
        )
    best = max(recs.values(), key=lambda r: r.num_reg_images())
    log(f"      Placed {best.num_reg_images()}/{len(paths)} photos, "
        f"{best.num_points3D():,} sparse points")
    if best.num_reg_images() < 3:
        raise ValueError("Fewer than 3 photos could be placed; take more overlapping photos")

    best_dir = work / "sparse_best"
    best_dir.mkdir(exist_ok=True)
    best.write(best_dir)
    undist = work / "undistorted"
    pycolmap.undistort_images(undist, best_dir, images)
    return pycolmap.Reconstruction(undist / "sparse"), undist / "images"


def load_views(rec, image_dir: Path, dense_size: int) -> tuple[list[View], np.ndarray]:
    """Views scaled to `dense_size` plus the sparse point cloud (N, 3)."""
    views = []
    for img in sorted(rec.images.values(), key=lambda im: im.name):
        if not img.has_pose:
            continue
        cam = rec.cameras[img.camera_id]
        fx, fy, cx, cy = cam.params  # PINHOLE after undistortion
        with Image.open(image_dir / img.name) as im:
            scale = min(1.0, dense_size / max(im.size))
            size = (round(im.width * scale), round(im.height * scale))
            rgb = np.asarray(im.convert("RGB").resize(size, Image.LANCZOS))
        sx, sy = size[0] / cam.width, size[1] / cam.height
        # COLMAP puts pixel centres at +0.5; ours are at integer indices.
        K = np.array([[fx * sx, 0, cx * sx - 0.5],
                      [0, fy * sy, cy * sy - 0.5],
                      [0, 0, 1]])
        pose = img.cam_from_world()
        m = pose.matrix()
        ids = {p.point3D_id for p in img.points2D if p.has_point3D()}
        views.append(View(img.name, K, m[:, :3].copy(), m[:, 3].copy(), rgb, ids))
    points = np.array([p.xyz for p in rec.points3D.values()])
    return views, points


# ------------------------------------------------------------------ 2. Dense stereo


def pick_neighbours(views: list[View], points: dict, count: int = 4) -> list[list[int]]:
    """For each view, the neighbours with most shared points at a useful angle."""
    result = []
    for i, ref in enumerate(views):
        scores = []
        for j, src in enumerate(views):
            if i == j:
                continue
            shared = ref.point_ids & src.point_ids
            if len(shared) < 30:
                continue
            xyz = np.array([points[k] for k in list(shared)[:300]])
            a = xyz - ref.centre
            b = xyz - src.centre
            cos = np.einsum("ij,ij->i", a, b) / (
                np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1))
            angle = np.degrees(np.median(np.arccos(np.clip(cos, -1, 1))))
            # Prefer a 5-30 degree baseline: enough parallax, still similar views.
            if angle < 2 or angle > 45:
                continue
            weight = min(1.0, angle / 5) * min(1.0, 30 / angle)
            scores.append((len(shared) * weight, j))
        result.append([j for _, j in sorted(scores, reverse=True)[:count]])
    return result


def _rectify_pair(ref: View, src: View):
    """Rotate both cameras to share an orientation with the baseline along +x."""
    baseline = src.centre - ref.centre
    B = np.linalg.norm(baseline)
    x = baseline / B
    z = ref.direction + src.direction
    y = np.cross(z, x)
    y /= np.linalg.norm(y)
    z = np.cross(x, y)
    R_rect = np.stack([x, y, z])  # world -> rectified
    f = ref.K[0, 0]

    h, w = ref.image.shape[:2]
    H_ref0 = R_rect @ ref.R.T @ np.linalg.inv(ref.K)
    corners = np.array([[0, 0, 1], [w, 0, 1], [0, h, 1], [w, h, 1]], dtype=float).T
    proj = H_ref0 @ corners
    if (proj[2] <= 0).any():
        return None  # too much rotation between the views
    xy = f * proj[:2] / proj[2]
    lo, hi = xy.min(axis=1), xy.max(axis=1)
    size = np.ceil(hi - lo).astype(int) + 1
    if (size > 2.5 * max(w, h)).any():
        return None
    K_rect = np.array([[f, 0, -lo[0]], [0, f, -lo[1]], [0, 0, 1]])
    H_ref = K_rect @ H_ref0
    H_src = K_rect @ R_rect @ src.R.T @ np.linalg.inv(src.K)
    return R_rect, K_rect, H_ref, H_src, B, (int(size[0]), int(size[1]))


def pair_depth(ref: View, src: View, zmin: float, zmax: float) -> np.ndarray | None:
    """Depth map (in ref's image, 0 = unknown) from rectified semi-global matching."""
    cv2, _ = _require()
    rect = _rectify_pair(ref, src)
    if rect is None:
        return None
    R_rect, K_rect, H_ref, H_src, B, size = rect
    f = K_rect[0, 0]

    def warp(img, H):
        return cv2.warpPerspective(img, H, size, flags=cv2.INTER_LINEAR,
                                   borderMode=cv2.BORDER_CONSTANT, borderValue=0)

    left = warp(cv2.cvtColor(ref.image, cv2.COLOR_RGB2GRAY), H_ref)
    right = warp(cv2.cvtColor(src.image, cv2.COLOR_RGB2GRAY), H_src)
    left_ok = warp(np.full(ref.image.shape[:2], 255, np.uint8), H_ref) > 250
    right_ok = warp(np.full(src.image.shape[:2], 255, np.uint8), H_src) > 250

    d_lo, d_hi = f * B / zmax, f * B / zmin
    min_disp = max(0, int(np.floor(d_lo)) - 2)
    num_disp = int(np.ceil((d_hi - min_disp + 2) / 16)) * 16
    num_disp = int(np.clip(num_disp, 16, 384))
    block = 5
    sgbm = cv2.StereoSGBM_create(
        minDisparity=min_disp, numDisparities=num_disp, blockSize=block,
        P1=8 * block * block, P2=32 * block * block, disp12MaxDiff=1,
        uniquenessRatio=10, speckleWindowSize=100, speckleRange=2,
        mode=cv2.STEREO_SGBM_MODE_SGBM_3WAY,
    )
    disp = sgbm.compute(left, right).astype(np.float32) / 16.0
    xs = np.arange(size[0])[None, :] - disp
    xi = np.clip(np.round(xs).astype(int), 0, size[0] - 1)
    rows = np.arange(size[1])[:, None].repeat(size[0], 1)
    good = (disp > min_disp) & left_ok & right_ok[rows, xi] & (xs >= 0)
    disp[~good] = 0

    # Look up each ref pixel's disparity, then turn it into depth along the ref ray.
    h, w = ref.image.shape[:2]
    u, v = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    pts = H_ref @ np.stack([u.ravel(), v.ravel(), np.ones(u.size, np.float32)])
    mx = (pts[0] / pts[2]).reshape(h, w).astype(np.float32)
    my = (pts[1] / pts[2]).reshape(h, w).astype(np.float32)
    d = cv2.remap(disp, mx, my, cv2.INTER_NEAREST, borderValue=0)
    z_rect = np.where(d > 0, f * B / np.maximum(d, 1e-6), 0)
    # A ref pixel's ray in rectified coords is (mx-cx, my-cy, f) * z_rect / f;
    # its depth in the ref camera is the z component after rotating back.
    ray = np.stack([(mx - K_rect[0, 2]) / f, (my - K_rect[1, 2]) / f, np.ones_like(mx)], -1)
    z_ref = (ray @ (ref.R @ R_rect.T)[2]) * z_rect
    z_ref[(d <= 0) | (z_ref < zmin) | (z_ref > zmax)] = 0
    return z_ref.astype(np.float32)


def compute_depth(ref: View, srcs: list[View], points: dict, tolerance: float = 0.02):
    """Depth map for `ref`, keeping depths that at least two neighbours agree on."""
    xyz = np.array([points[k] for k in ref.point_ids]) if ref.point_ids else None
    if xyz is None or len(xyz) < 20:
        return None
    z = (xyz - ref.centre) @ ref.direction
    zmin, zmax = np.percentile(z, 1) * 0.75, np.percentile(z, 99) * 1.33
    zmin = max(zmin, 1e-6)
    maps = [m for m in (pair_depth(ref, s, zmin, zmax) for s in srcs) if m is not None]
    if not maps:
        return None
    if len(maps) == 1:
        return maps[0]
    # Each candidate depth is supported by the maps that agree with it; keep
    # the best-supported candidate if at least two maps back it.
    stack = np.stack(maps)
    best_depth = np.zeros_like(stack[0])
    best_support = np.zeros(stack[0].shape, dtype=int)
    for cand in stack:
        agree = (stack > 0) & (cand > 0) & (np.abs(stack - cand) < tolerance * cand)
        support = agree.sum(0)
        mean = (stack * agree).sum(0) / np.maximum(support, 1)
        better = support > best_support
        best_depth[better], best_support[better] = mean[better], support[better]
    depth = np.where(best_support >= 2, best_depth, 0)
    return depth.astype(np.float32)


# ------------------------------------------------------------------------ 3. Fusion


def fusion_bounds(views: list[View], points: np.ndarray, crop: float = 0.75, margin: float = 0.05):
    """Region to reconstruct: around the spot all the cameras are aimed at.

    `crop` is the radius kept around that spot, as a fraction of the typical
    camera distance; raise it to include more surroundings.
    """
    centres = np.array([v.centre for v in views])
    dirs = np.array([v.direction for v in views])
    # Least-squares point closest to every camera's line of sight.
    A = np.zeros((3, 3))
    b = np.zeros(3)
    for c, d in zip(centres, dirs):
        P = np.eye(3) - np.outer(d, d)
        A += P
        b += P @ c
    focus = np.linalg.lstsq(A, b, rcond=None)[0]
    radius = crop * np.median(np.linalg.norm(centres - focus, axis=1))
    near = points[np.linalg.norm(points - focus, axis=1) < radius]
    if len(near) < 20:
        near = points
    lo, hi = np.percentile(near, 1, axis=0), np.percentile(near, 99, axis=0)
    pad = (hi - lo) * margin
    return lo - pad, hi + pad


def fuse(views: list[View], lo: np.ndarray, hi: np.ndarray, resolution: int,
         trunc_voxels: float = 4.0):
    """Integrate depth maps into a TSDF; returns (tsdf, weight, colour, voxel size)."""
    voxel = (hi - lo).max() / resolution
    dims = np.maximum(np.ceil((hi - lo) / voxel).astype(int), 2)
    trunc = trunc_voxels * voxel
    tsdf = np.ones(dims, np.float32)
    weight = np.zeros(dims, np.float32)
    colour = np.zeros(tuple(dims) + (3,), np.float32)
    cweight = np.zeros(dims, np.float32)

    gx, gy = np.meshgrid(lo[0] + (np.arange(dims[0]) + 0.5) * voxel,
                         lo[1] + (np.arange(dims[1]) + 0.5) * voxel, indexing="ij")
    for view in views:
        if view.depth is None:
            continue
        h, w = view.depth.shape
        for k in range(dims[2]):  # one z-slice at a time keeps memory small
            pts = np.stack([gx, gy, np.full_like(gx, lo[2] + (k + 0.5) * voxel)], -1)
            cam = pts @ view.R.T + view.t
            zc = cam[..., 2]
            front = zc > 1e-6
            u = np.round(view.K[0, 0] * cam[..., 0] / np.where(front, zc, 1) + view.K[0, 2])
            v = np.round(view.K[1, 1] * cam[..., 1] / np.where(front, zc, 1) + view.K[1, 2])
            inside = front & (u >= 0) & (u < w) & (v >= 0) & (v < h)
            ui, vi = u[inside].astype(int), v[inside].astype(int)
            depth = view.depth[vi, ui]
            sdf = depth - zc[inside]
            use = (depth > 0) & (sdf > -trunc)
            if not use.any():
                continue
            ix, iy = np.nonzero(inside)
            ix, iy = ix[use], iy[use]
            val = np.minimum(1.0, sdf[use] / trunc)
            wt = weight[ix, iy, k]
            tsdf[ix, iy, k] = (tsdf[ix, iy, k] * wt + val) / (wt + 1)
            weight[ix, iy, k] = wt + 1
            near = np.abs(val) < 1
            if near.any():
                cx_, cy_ = ix[near], iy[near]
                colour[cx_, cy_, k] += view.image[vi[use][near], ui[use][near]]
                cweight[cx_, cy_, k] += 1
    colour /= np.maximum(cweight, 1)[..., None]
    return tsdf, weight, colour, cweight, voxel


# ----------------------------------------------------------------------- 4. Meshing


def _vertex_colours(verts_grid: np.ndarray, colour: np.ndarray, cweight: np.ndarray):
    """Colour each vertex from the nearest voxels that recorded a colour."""
    acc = np.zeros((len(verts_grid), 3))
    tot = np.zeros(len(verts_grid))
    base = np.floor(verts_grid).astype(int)
    for offset in np.ndindex(2, 2, 2):
        idx = np.clip(base + offset, 0, np.array(cweight.shape) - 1)
        wt = cweight[idx[:, 0], idx[:, 1], idx[:, 2]] > 0
        acc += colour[idx[:, 0], idx[:, 1], idx[:, 2]] * wt[:, None]
        tot += wt
    return np.clip(acc / np.maximum(tot, 1)[:, None], 0, 255).astype(np.uint8)


def _largest_component(mesh: Mesh, keep_fraction: float = 0.02) -> Mesh:
    """Drop small floating fragments (stereo noise)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components

    n = len(mesh.vertices)
    e = np.concatenate([mesh.faces[:, [0, 1]], mesh.faces[:, [1, 2]]])
    graph = coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n, n))
    _, labels = connected_components(graph, directed=False)
    face_label = labels[mesh.faces[:, 0]]
    ids, counts = np.unique(face_label, return_counts=True)
    keep = np.isin(face_label, ids[counts >= keep_fraction * counts.max()])
    faces = mesh.faces[keep]
    used = np.unique(faces)
    remap = np.full(n, -1)
    remap[used] = np.arange(len(used))
    colours = None if mesh.colors is None else mesh.colors[used]
    return Mesh(mesh.vertices[used], remap[faces], colours)


def _up_rotation(views: list[View]) -> np.ndarray:
    """Rotation taking the photographer's average 'up' direction to +Z."""
    up = -np.mean([v.R[1] for v in views], axis=0)  # camera +y points down in images
    up /= np.linalg.norm(up)
    axis = np.cross(up, [0, 0, 1])
    s, c = np.linalg.norm(axis), up[2]
    if s < 1e-8:
        return np.eye(3) if c > 0 else np.diag([1, -1, -1])
    k = axis / s
    Kx = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + s * Kx + (1 - c) * Kx @ Kx


def reconstruct(
    paths: list[str],
    resolution: int = 200,
    size: float = 100.0,
    max_image_size: int = 1600,
    dense_size: int = 1000,
    neighbours: int = 4,
    min_views: int = 2,
    crop: float = 0.75,
    work_dir: str | None = None,
    log=print,
) -> Mesh:
    if len(paths) < 3:
        raise ValueError("Photogrammetry needs at least 3 photos (20-60 works best)")
    temp = None
    if work_dir is None:
        temp = tempfile.mkdtemp(prefix="img2mesh_")
        work = Path(temp)
    else:
        work = Path(work_dir)
        if (work / "database.db").exists():
            raise ValueError(f"Work folder {work} already has a reconstruction; "
                             "use an empty folder")
    try:
        rec, image_dir = run_sfm(paths, work, max_image_size, log)
        views, sparse = load_views(rec, image_dir, dense_size)
        point_map = {pid: p.xyz for pid, p in rec.points3D.items()}

        log(f"[2/4] Computing depth maps for {len(views)} photos...")
        nbrs = pick_neighbours(views, point_map, neighbours)
        for i, view in enumerate(views):
            view.depth = compute_depth(view, [views[j] for j in nbrs[i]], point_map)
        if not any(v.depth is not None and (v.depth > 0).any() for v in views):
            raise ValueError("Dense matching found no depth; the photos may be too far "
                             "apart or the surface too plain")

        log("[3/4] Fusing depth maps...")
        lo, hi = fusion_bounds(views, sparse, crop)
        tsdf, weight, colour, cweight, voxel = fuse(views, lo, hi, resolution)

        log("[4/4] Building the mesh...")
        valid = weight >= min_views
        mesh = surface_nets(-tsdf, 0.0, valid=valid)  # inside = behind the surface
        if len(mesh.faces) == 0:
            raise ValueError("No surface found; try more photos or a lower --resolution")
        colours = _vertex_colours(mesh.vertices, colour, cweight)
        world = lo + (mesh.vertices + 0.5) * voxel
        mesh = _largest_component(Mesh(world @ _up_rotation(views).T, mesh.faces, colours))
        return mesh.scaled_to(size)
    finally:
        if temp is not None:
            shutil.rmtree(temp, ignore_errors=True)
