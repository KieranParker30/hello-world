"""Handheld photos -> textured, web-ready 3D model (full photogrammetry).

Pipeline:
1. Structure from Motion with COLMAP (pycolmap): find each photo's camera
   position, orientation and lens from matched SIFT features.
2. Dense stereo: for each photo pick the best neighbouring photos, rectify each
   pair and run OpenCV semi-global matching to get a depth map. A depth is kept
   only where at least two pairs agree, which removes most bad matches.
3. Fusion: integrate all depth maps into a truncated signed distance field
   (TSDF) voxel grid, averaging out noise.
4. Meshing: extract the detailed surface with surface nets, keeping only parts
   that cameras actually observed.
5. Texturing (texture.py): decimate, UV-unwrap, bake a colour texture from the
   full-resolution photos and a normal map from the detailed surface.

Needs: pip install 'img2mesh[photo]'.
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
        import fast_simplification  # noqa: F401
        import pycolmap
        import scipy  # noqa: F401
        import xatlas  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "Photogrammetry needs extra packages:  pip install 'img2mesh[photo]'\n"
            "(or: pip install pycolmap opencv-python-headless scipy xatlas "
            "fast-simplification DracoPy)"
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
    photo: Path | None = None  # full-resolution undistorted photo
    K_photo: np.ndarray | None = None  # intrinsics for `photo`

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
    log(f"[1/5] Finding features in {len(paths)} photos...")
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
        K_photo = np.array([[fx, 0, cx - 0.5], [0, fy, cy - 0.5], [0, 0, 1]])
        m = img.cam_from_world().matrix()
        ids = {p.point3D_id for p in img.points2D if p.has_point3D()}
        views.append(View(img.name, K, m[:, :3].copy(), m[:, 3].copy(), rgb, ids,
                          photo=image_dir / img.name, K_photo=K_photo))
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


def aim_point(views: list[View]) -> np.ndarray:
    """Least-squares point closest to every camera's line of sight."""
    A = np.zeros((3, 3))
    b = np.zeros(3)
    for v in views:
        P = np.eye(3) - np.outer(v.direction, v.direction)
        A += P
        b += P @ v.centre
    return np.linalg.lstsq(A, b, rcond=None)[0]


def fusion_bounds(views: list[View], points: np.ndarray, crop: float = 0.75, margin: float = 0.05):
    """Region to reconstruct: around the spot all the cameras are aimed at.

    `crop` is the radius kept around that spot, as a fraction of the typical
    camera distance; raise it to include more surroundings.
    """
    centres = np.array([v.centre for v in views])
    focus = aim_point(views)
    radius = crop * np.median(np.linalg.norm(centres - focus, axis=1))
    near = points[np.linalg.norm(points - focus, axis=1) < radius]
    if len(near) < 20:
        near = points
    lo, hi = np.percentile(near, 1, axis=0), np.percentile(near, 99, axis=0)
    pad = (hi - lo) * margin
    return lo - pad, hi + pad


def find_ground(points: np.ndarray, up: np.ndarray, focus_height: float,
                iterations: int = 500, seed: int = 0):
    """Dominant roughly horizontal plane below the object: returns (normal, offset)
    with normal . x = offset on the plane and the normal pointing up, or None."""
    if len(points) < 50:
        return None
    rng = np.random.default_rng(seed)
    heights = points @ up
    tol = 0.01 * (np.percentile(heights, 99) - np.percentile(heights, 1))
    best, best_count = None, 0
    for _ in range(iterations):
        a, b, c = points[rng.choice(len(points), 3, replace=False)]
        n = np.cross(b - a, c - a)
        if np.linalg.norm(n) < 1e-12:
            continue
        n /= np.linalg.norm(n)
        if n @ up < 0:
            n = -n
        if n @ up < np.cos(np.radians(20)):  # must be roughly level
            continue
        d = n @ a
        count = int((np.abs(points @ n - d) < tol).sum())
        if count > best_count:
            best, best_count = (n, d), count
    if best is None or best_count < 0.08 * len(points):
        return None
    n, d = best
    if d >= focus_height:  # a plane above the object's middle is not the ground
        return None
    inliers = points[np.abs(points @ n - d) < tol]
    centre = inliers.mean(0)
    _, _, vt = np.linalg.svd(inliers - centre)  # refine with least squares
    n = vt[2] if vt[2] @ up > 0 else -vt[2]
    return n, float(n @ centre) + 2 * tol


def fuse(views: list[View], lo: np.ndarray, hi: np.ndarray, resolution: int,
         trunc_voxels: float = 4.0):
    """Integrate depth maps into a TSDF; returns (tsdf, weight, voxel size)."""
    voxel = (hi - lo).max() / resolution
    dims = np.maximum(np.ceil((hi - lo) / voxel).astype(int), 2)
    trunc = trunc_voxels * voxel
    tsdf = np.ones(dims, np.float32)
    weight = np.zeros(dims, np.float32)

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
    return tsdf, weight, voxel


def smooth_tsdf(tsdf: np.ndarray, valid: np.ndarray, sigma: float) -> np.ndarray:
    """Gaussian-smooth the distance field using observed voxels only."""
    if sigma <= 0:
        return tsdf
    from scipy.ndimage import gaussian_filter

    m = valid.astype(np.float32)
    num = gaussian_filter(tsdf * m, sigma)
    den = gaussian_filter(m, sigma)
    return np.where(den > 1e-3, num / np.maximum(den, 1e-3), tsdf).astype(np.float32)


def field_normals(tsdf: np.ndarray, valid: np.ndarray, lo: np.ndarray, voxel: float):
    """Function giving the detailed surface's outward normal at world points."""
    dims = np.array(tsdf.shape)

    def sample(g: np.ndarray) -> np.ndarray:  # trilinear, g in voxel-index units
        i0 = np.clip(np.floor(g).astype(int), 0, dims - 2)
        f = np.clip(g - i0, 0, 1)
        out = np.zeros(len(g), np.float32)
        for dx, dy, dz in np.ndindex(2, 2, 2):
            wgt = ((f[:, 0] if dx else 1 - f[:, 0]) * (f[:, 1] if dy else 1 - f[:, 1])
                   * (f[:, 2] if dz else 1 - f[:, 2]))
            out += wgt * tsdf[i0[:, 0] + dx, i0[:, 1] + dy, i0[:, 2] + dz]
        return out

    def normals(points: np.ndarray):
        out_n = np.zeros_like(points)
        ok = np.zeros(len(points), bool)
        for start in range(0, len(points), 2_000_000):
            sl = slice(start, start + 2_000_000)
            g = (points[sl] - lo) / voxel - 0.5
            grad = np.stack([sample(g + e) - sample(g - e) for e in np.eye(3)], axis=1)
            length = np.linalg.norm(grad, axis=1)
            out_n[sl] = grad / np.maximum(length, 1e-12)[:, None]
            gi = np.clip(np.round(g).astype(int), 0, dims - 1)
            ok[sl] = valid[gi[:, 0], gi[:, 1], gi[:, 2]] & (length > 1e-6)
        return out_n, ok

    return normals


# ----------------------------------------------------------------------- 4. Meshing


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


def _facing_rotation(mesh: Mesh, views: list[View], R_up: np.ndarray) -> np.ndarray:
    """Turn about +Z so the photographed side faces -Y (the viewer's side in glTF)."""
    centre = mesh.vertices.mean(axis=0)
    d = np.mean([v.centre @ R_up.T - centre for v in views], axis=0)
    angle = -np.pi / 2 - np.arctan2(d[1], d[0])
    c, s = np.cos(angle), np.sin(angle)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


QUALITY = {  # image size, depth-map size, voxels, triangles, texture size
    "draft": dict(max_image_size=1600, dense_size=1000, resolution=200, faces=50_000, texture_size=2048),
    "high": dict(max_image_size=2000, dense_size=1600, resolution=360, faces=150_000, texture_size=4096),
    "ultra": dict(max_image_size=3000, dense_size=2000, resolution=480, faces=400_000, texture_size=8192),
}


def reconstruct(
    paths: list[str],
    quality: str = "high",
    size: float = 100.0,
    resolution: int | None = None,
    faces: int | None = None,
    texture_size: int | None = None,
    max_image_size: int | None = None,
    dense_size: int | None = None,
    neighbours: int = 4,
    min_views: int = 2,
    crop: float = 0.75,
    smooth: float = 0.7,
    remove_ground: bool = False,
    work_dir: str | None = None,
    log=print,
) -> Mesh:
    """Photos -> UV-textured mesh with a normal map, sized `size` mm, facing -Y, Z up."""
    if len(paths) < 3:
        raise ValueError("Photogrammetry needs at least 3 photos (20-60 works best)")
    preset = dict(QUALITY[quality])
    for key, val in dict(resolution=resolution, faces=faces, texture_size=texture_size,
                         max_image_size=max_image_size, dense_size=dense_size).items():
        if val is not None:
            preset[key] = val
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
        rec, image_dir = run_sfm(paths, work, preset["max_image_size"], log)
        views, sparse = load_views(rec, image_dir, preset["dense_size"])
        point_map = {pid: p.xyz for pid, p in rec.points3D.items()}

        log(f"[2/5] Computing depth maps for {len(views)} photos...")
        nbrs = pick_neighbours(views, point_map, neighbours)
        for i, view in enumerate(views):
            view.depth = compute_depth(view, [views[j] for j in nbrs[i]], point_map)
        if not any(v.depth is not None and (v.depth > 0).any() for v in views):
            raise ValueError("Dense matching found no depth; the photos may be too far "
                             "apart or the surface too plain")

        log("[3/5] Fusing depth maps...")
        lo, hi = fusion_bounds(views, sparse, crop)
        tsdf, weight, voxel = fuse(views, lo, hi, preset["resolution"])
        for v in views:
            v.depth = v.image = None  # free memory before texturing
        valid = weight >= min_views
        del weight
        R_up = _up_rotation(views)
        if remove_ground:
            up = R_up[2]  # world direction that becomes +Z
            nearby = sparse[(sparse >= lo).all(1) & (sparse <= hi).all(1)]
            plane = find_ground(nearby, up, float(aim_point(views) @ up))
            if plane is None:
                log("      No ground plane found; keeping everything")
            else:
                n, d = plane
                axes = [lo[k] + (np.arange(tsdf.shape[k]) + 0.5) * voxel for k in range(3)]
                height = (axes[0][:, None, None] * n[0] + axes[1][None, :, None] * n[1]
                          + axes[2][None, None, :] * n[2])
                valid &= height > d
                log("      Removed the ground plane")
        tsdf = smooth_tsdf(tsdf, valid, smooth)

        log("[4/5] Building the mesh...")
        dense = surface_nets(-tsdf, 0.0, valid=valid)  # inside = behind the surface
        if len(dense.faces) == 0:
            raise ValueError("No surface found; try more photos or a lower quality setting")
        dense = _largest_component(Mesh(lo + (dense.vertices + 0.5) * voxel, dense.faces))
        log(f"      Detailed surface: {len(dense.faces):,} triangles")

        log(f"[5/5] Texturing ({preset['faces']:,} triangles, "
            f"{preset['texture_size']}px textures)...")
        from .texture import Camera, bake, decimate, unwrap

        low = unwrap(decimate(dense, preset["faces"]), preset["texture_size"])
        cameras = []
        for v in views:
            with Image.open(v.photo) as im:
                cameras.append(Camera(v.K_photo, v.R, v.t, np.asarray(im.convert("RGB"))))
        texture, normal_map, normals = bake(
            low, cameras, preset["texture_size"], field_normals(tsdf, valid, lo, voxel), log=log)
        model = Mesh(low.vertices, low.faces, uvs=low.uvs, normals=normals,
                     texture=texture, normal_map=normal_map)
        model = model.rotated(R_up)
        model = model.rotated(_facing_rotation(model, views, R_up))
        return model.scaled_to(size)
    finally:
        if temp is not None:
            shutil.rmtree(temp, ignore_errors=True)
