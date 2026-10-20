"""Ray-traced test scene with known geometry, for checking photogrammetry.

A textured block with a spherical dent in its front face, standing on a
textured ground plane, photographed from an orbit at varying heights.
Units are metres-ish; the block is 1.2 x 0.8 x 1.0.
"""

import numpy as np

DENT_CENTRE = np.array([0.0, -0.55, 0.55])
DENT_RADIUS = 0.3
_rng = np.random.default_rng(7)
_WAVES = _rng.normal(size=(48, 3)) * np.repeat([3.0, 6.0, 12.0, 24.0], 12)[:, None]
_PHASES = _rng.uniform(0, 2 * np.pi, 48)
_MIX = _rng.uniform(0.3, 1.0, (48, 3)) / np.repeat([1.0, 1.4, 2.0, 2.8], 12)[:, None]


def object_sdf(p):
    """Signed distance to the dented block (negative inside)."""
    q = np.abs(p - [0.0, 0.0, 0.5]) - [0.6, 0.4, 0.5]
    box = np.linalg.norm(np.maximum(q, 0), axis=-1) + np.minimum(q.max(-1), 0)
    dent = np.linalg.norm(p - DENT_CENTRE, axis=-1) - DENT_RADIUS
    return np.maximum(box, -dent)


def scene_sdf(p):
    return np.minimum(object_sdf(p), p[..., 2])


def _texture(p):
    s = np.sin(p @ _WAVES.T + _PHASES)
    rgb = 0.5 + 0.5 * np.tanh((s @ _MIX) * 0.9)
    return rgb * [0.9, 0.75, 0.6] + 0.08


def look_at(centre, target=(0, 0, 0.45)):
    z = np.asarray(target, float) - centre
    z /= np.linalg.norm(z)
    x = np.cross(z, [0, 0, 1.0])
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    R = np.stack([x, y, z])  # world -> camera, camera y points down
    return R, -R @ centre


def render(R, t, size=(640, 480), focal=560.0):
    w, h = size
    u, v = np.meshgrid(np.arange(w) + 0.5, np.arange(h) + 0.5)
    dirs = np.stack([(u - w / 2) / focal, (v - h / 2) / focal, np.ones_like(u)], -1) @ R
    dirs /= np.linalg.norm(dirs, axis=-1, keepdims=True)
    origin = -R.T @ t
    dist = np.zeros(u.shape)
    for _ in range(90):  # sphere-trace the block
        dist += object_sdf(origin + dirs * dist[..., None])
    on_object = np.abs(object_sdf(origin + dirs * dist[..., None])) < 1e-3
    with np.errstate(divide="ignore", invalid="ignore"):
        ground = np.where(dirs[..., 2] < 0, -origin[2] / dirs[..., 2], np.inf)
    use_ground = ~on_object | (ground < dist)
    dist = np.where(use_ground, ground, dist)
    hit = np.isfinite(dist) & (on_object | (dirs[..., 2] < 0))
    dist[~hit] = 0
    p = origin + dirs * dist[..., None]
    e = 1e-4
    n = np.stack([scene_sdf(p + o) - scene_sdf(p - o) for o in np.eye(3) * e], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True) + 1e-12
    light = np.array([0.4, -0.6, 0.7])
    light /= np.linalg.norm(light)
    shade = 0.45 + 0.55 * np.clip(n @ light, 0, 1)
    rgb = _texture(p) * shade[..., None]
    rgb[~hit] = [0.75, 0.82, 0.9]
    return (np.clip(rgb, 0, 1) * 255).astype(np.uint8)


def camera_orbit(n=24, radius=2.4):
    """Camera centres on a wobbly half-orbit in front of the dented face."""
    out = []
    for i in range(n):
        a = np.radians(-160 + 140 * i / (n - 1))  # from left-front to right-front
        height = 1.1 + 0.5 * np.sin(i * 1.3)
        r = radius * (1 + 0.08 * np.cos(i * 0.7))
        out.append(np.array([r * np.cos(a), r * np.sin(a), height]))
    return out
