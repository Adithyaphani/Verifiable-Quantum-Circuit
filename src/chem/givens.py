"""Givens-tree angle words for unit vectors (dfthcsos verifier convention).

Rows are decoded by the verifier as: v = e_0; for t, (p, c) in enumerate(tree): rotate (v_p, v_c)
by theta_t = pi * word_t / 2**(brot - 1). On the path tree (t, t+1) that is hyperspherical
coordinates, so angles follow from tail norms.
"""
from __future__ import annotations

import numpy as np

N = 76
PATH = np.array([[t, t + 1] for t in range(N - 1)], dtype=np.int64)


def angles_path(u: np.ndarray) -> np.ndarray:
    """theta/pi in [0, 2) of a vector on the path tree (u is normalised first)."""
    u = np.asarray(u, dtype=np.float64)
    u = u / np.linalg.norm(u)
    n = len(u)
    tail = np.sqrt(np.cumsum(u[::-1] ** 2)[::-1])
    th = np.zeros(n - 1)
    for t in range(n - 1):
        if t < n - 2:
            th[t] = np.arctan2(tail[t + 1], u[t])
        else:
            th[t] = np.arctan2(u[t + 1], u[t])
    return np.mod(th / np.pi, 2.0)


def reconstruct(theta_over_pi: np.ndarray, edges: np.ndarray = PATH) -> np.ndarray:
    a = np.atleast_2d(np.asarray(theta_over_pi, dtype=np.float64))
    v = np.zeros((a.shape[0], a.shape[1] + 1))
    v[:, 0] = 1.0
    for i, (p, c) in enumerate(edges):
        th = np.pi * a[:, i]
        cs, sn = np.cos(th), np.sin(th)
        vp, vc = v[:, p].copy(), v[:, c].copy()
        v[:, p] = cs * vp - sn * vc
        v[:, c] = sn * vp + cs * vc
    return v


def quantize(theta_over_pi: np.ndarray, brot: int) -> np.ndarray:
    return (np.round(np.asarray(theta_over_pi) * (1 << (brot - 1))).astype(np.int64)) % (1 << brot)


def words_to_vectors(words: np.ndarray, brot: int, edges: np.ndarray = PATH) -> np.ndarray:
    return reconstruct(np.asarray(words, dtype=np.float64) / (1 << (brot - 1)), edges)
