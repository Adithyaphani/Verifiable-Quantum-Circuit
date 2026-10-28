"""Benchmark III (dfthcsos): re-quantize a DF-THC factorization at fewer angle bits.

The score is lambda_eff * T * Q, and the ANGLE_k circuits are most of T:
2 * ceil(75 / J) * (76 + R*B) Toffolis, where J * brot plus the selection and
unary-iteration ancillas must fit in 128 qubits. At brot = 12 that gives J = 8
(10 circuits); at brot = 10 it gives J = 10 (8 circuits).

With nearest rounding the baseline's two-body error error_2 goes from 0.0186
(brot 12) to 0.040 (brot 10), which fails the 0.02 limit. This module:

  1. jointly refits vectors and weights (`joint_fit`, optional; small gain);
  2. picks every angle word to minimise the real two-body residual instead of
     rounding it (`QOpt`: greedy +-1 word moves per vector, scored with a rank-3
     update of the packed residual), alternating with exact weight refits (`WFit`);
  3. re-optimises the SOS offsets W for lambda_eff (`opt_offsets`);
  4. writes the one-body rows (eigenvectors of h1'), submission.npz and ANGLE_k circuits.

Packed pair space: P = N(N+1)/2 pairs, off-diagonal pairs scaled by sqrt(2), so the
Frobenius norm over all N^4 entries equals the packed one.
"""
from __future__ import annotations

import time

import numpy as np
from scipy.linalg.blas import dger
from scipy.optimize import minimize

N = 76
IU = np.triu_indices(N)
I0, I1 = IU
C_PQ = np.where(I0 == I1, 1.0, np.sqrt(2.0))


# ----------------------------------------------------------------------------- basics
def packed_target(tei, S):
    """T = (pq|rs) + (S x I + I x S)/2 in packed pair space (error_2's target)."""
    T = np.array(tei, dtype=np.float64)
    d = np.arange(N)
    T[:, :, d, d] += 0.5 * S[:, :, None]
    T[d, d, :, :] += 0.5 * S[None, :, :]
    return T[I0, I1][:, I0, I1] * C_PQ[:, None] * C_PQ[None, :]


def khat(U):
    """A[pq, b] = c_pq U[b, p] U[b, q] for U of shape (B, N)."""
    return (U[:, I0] * U[:, I1] * C_PQ[None, :].astype(U.dtype)).T


def angles_tree(u, edges):
    """theta/pi per tree edge such that the verifier's decoding of e_0 gives +-u."""
    v = np.array(u, dtype=np.float64)
    v /= np.linalg.norm(v)
    th = np.zeros(len(edges))
    for t in range(len(edges) - 1, -1, -1):
        p, c = edges[t]
        a = np.arctan2(v[c], v[p])
        th[t] = a
        v[p] = np.cos(a) * v[p] + np.sin(a) * v[c]
        v[c] = 0.0
    return np.mod(th / np.pi, 2.0)


def words_of(U, edges, brot):
    th = np.array([angles_tree(u, edges) for u in U])
    return (np.round(th * (1 << (brot - 1))).astype(np.int64)) % (1 << brot)


def decode(words, edges, brot):
    """The verifier's row decoding (dfthc_math.reconstruct_u_vectors), batched."""
    a = np.atleast_2d(words) / (1 << (brot - 1))
    v = np.zeros((a.shape[0], a.shape[1] + 1))
    v[:, 0] = 1.0
    for i, (p, c) in enumerate(edges):
        th = np.pi * a[:, i]
        cs, sn = np.cos(th), np.sin(th)
        vp, vc = v[:, p].copy(), v[:, c].copy()
        v[:, p] = cs * vp - sn * vc
        v[:, c] = sn * vp + cs * vc
    return v


# ----------------------------------------------------------------------------- weight refit
class WFit:
    """min_w ||sum_r A_r w_r w_r^T A_r^T - T|| for fixed vectors U (R, B, N)."""

    def __init__(self, U, Ts):
        self.R, self.B, _ = U.shape
        Uf = U.reshape(-1, N)
        self.H = (Uf @ Uf.T) ** 2
        A = khat(Uf)
        TA = Ts @ A
        B = self.B
        self.F = [A[:, r * B:(r + 1) * B].T @ TA[:, r * B:(r + 1) * B] for r in range(self.R)]
        self.Tn2 = float(np.sum(Ts * Ts))

    def lg(self, w):
        R, B = self.R, self.B
        G = [w[r] @ w[r].T for r in range(R)]
        M = np.empty_like(self.H)
        for s in range(R):
            M[:, s * B:(s + 1) * B] = self.H[:, s * B:(s + 1) * B] @ G[s]
        loss, gw = self.Tn2, np.empty_like(w)
        for r in range(R):
            HGH = M[r * B:(r + 1) * B] @ self.H[:, r * B:(r + 1) * B]
            loss += np.sum(G[r] * HGH) - 2 * np.sum(G[r] * self.F[r])
            gw[r] = 4 * (HGH - self.F[r]) @ w[r]
        return loss, gw

    def fit(self, w0, iters=200):
        shp = w0.shape

        def f(x):
            l, g = self.lg(x.reshape(shp))
            return l, g.ravel()
        r = minimize(f, w0.ravel(), jac=True, method="L-BFGS-B",
                     options={"maxiter": iters, "maxcor": 30, "ftol": 1e-16, "gtol": 1e-14})
        w = r.x.reshape(shp)
        return w, float(np.sqrt(max(self.lg(w)[0], 0.0)))


# ----------------------------------------------------------------------------- joint refit
def joint_loss_grad(Uraw, w, Ts, dt=np.float32):
    R, B, _ = Uraw.shape
    nrm = np.linalg.norm(Uraw, axis=2, keepdims=True)
    U = Uraw / nrm
    Us, ws = U.astype(dt), w.astype(dt)
    Xs = [khat(Us[r]) @ ws[r] for r in range(R)]
    Res = -Ts.astype(dt)
    for X in Xs:
        Res += X @ X.T
    loss = float(np.sum(Res.astype(np.float64) ** 2))
    gU, gw = np.empty_like(U), np.empty_like(w)
    for r in range(R):
        GX = 4.0 * (Res @ Xs[r])
        gw[r] = khat(Us[r]).T @ GX
        Y = (GX @ ws[r].T).astype(np.float64)
        Z = np.zeros((B, N, N))
        Z[:, I0, I1] = (Y * C_PQ[:, None]).T
        Z = Z + np.transpose(Z, (0, 2, 1))
        g = np.einsum("bkq,bq->bk", Z, U[r])
        gU[r] = (g - np.sum(g * U[r], 1, keepdims=True) * U[r]) / nrm[r]
    return loss, gU, gw


def joint_fit(U, w, Ts, iters=140):
    nu, su, sw = U.size, U.shape, w.shape

    def f(x):
        l, gU, gw = joint_loss_grad(x[:nu].reshape(su), x[nu:].reshape(sw), Ts)
        return l, np.concatenate([gU.ravel(), gw.ravel()])
    r = minimize(f, np.concatenate([U.ravel(), w.ravel()]), jac=True, method="L-BFGS-B",
                 options={"maxiter": iters, "maxcor": 30, "ftol": 1e-16, "gtol": 1e-14})
    U = r.x[:nu].reshape(su)
    return U / np.linalg.norm(U, axis=2, keepdims=True), r.x[nu:].reshape(sw)


# ----------------------------------------------------------------------------- word selection
class QOpt:
    """Quantization-aware angle words for the two-body vectors."""

    def __init__(self, U, w, Ts, edges, brot):
        self.R, self.B, _ = U.shape
        self.w, self.Ts, self.edges, self.brot = w, Ts, edges, brot
        self.words = words_of(U.reshape(-1, N), edges, brot).reshape(self.R, self.B, -1)
        self.Uq = decode(self.words.reshape(-1, N - 1), edges, brot).reshape(U.shape)
        self.rebuild()

    def rebuild(self):
        self.X = [khat(self.Uq[r]) @ self.w[r] for r in range(self.R)]
        self.Res = -self.Ts.copy()
        for X in self.X:
            self.Res += X @ X.T

    def err(self):
        return float(np.linalg.norm(self.Res))

    def opt_vector(self, r, b, maxit=30):
        """Greedy +-1 word moves, each candidate scored against the start state
        (the small 2 s d^T Res d term is dropped); exact rank-3 residual update at the end."""
        wb = self.w[r, b]
        s = wb @ wb
        y = self.X[r] @ wb
        g = self.Res @ y
        yy = y @ y
        cur = self.words[r, b].copy()
        a0 = khat(self.Uq[r, b][None])[:, 0]
        mod, T = 1 << self.brot, len(cur)
        idx = np.arange(T)
        best, dbest = 0.0, None
        for _ in range(maxit):
            cand = np.repeat(cur[None], 2 * T, 0)
            cand[idx, idx] = (cur - 1) % mod
            cand[T + idx, idx] = (cur + 1) % mod
            dA = khat(decode(cand, self.edges, self.brot)) - a0[:, None]
            yd = y @ dA
            dd = np.sum(dA * dA, 0)
            dL = 4 * (g @ dA) + 2 * yy * dd + 2 * yd ** 2 + 4 * s * yd * dd + s * s * dd * dd
            k = int(np.argmin(dL))
            if dL[k] >= best - 1e-15:
                break
            best, cur, dbest = dL[k], cand[k], dA[:, k].copy()
        if dbest is None:
            return 0.0
        Rf = self.Res.T                     # symmetric: update through the Fortran view
        dger(1.0, y, dbest, a=Rf, overwrite_a=1)
        dger(1.0, dbest, y, a=Rf, overwrite_a=1)
        dger(s, dbest, dbest, a=Rf, overwrite_a=1)
        self.X[r] += np.outer(dbest, wb)
        self.words[r, b] = cur
        self.Uq[r, b] = decode(cur, self.edges, self.brot)[0]
        return best

    def sweep(self):
        for r in range(self.R):
            for b in range(self.B):
                self.opt_vector(r, b)

    def run(self, rounds=3, log=print):
        log(f"nearest rounding: error_2 = {self.err():.6f}")
        for rd in range(rounds):
            t = time.time()
            self.w, e = WFit(self.Uq, self.Ts).fit(self.w, iters=150)
            self.rebuild()
            self.sweep()
            log(f"round {rd}: weight refit {e:.6f} -> word sweep {self.err():.6f} ({time.time() - t:.0f}s)")
        self.w, e = WFit(self.Uq, self.Ts).fit(self.w, iters=200)
        self.rebuild()
        log(f"final weight refit: error_2 = {e:.6f}")
        return self.words, self.w


# ----------------------------------------------------------------------------- SOS offsets
E_GAP_FLOOR = 3.914898


def sos_metrics(Wv, Xs, h1p0, c0, a, s, smooth=0.0):
    """E_gap, Lambda and their gradients in the offsets W (see dfthc_math)."""
    lam, V = np.linalg.eigh(h1p0 - np.tensordot(Wv, Xs, axes=1))
    if smooth > 0:
        absl = np.sqrt(lam * lam + smooth * smooth)
        dabs = lam / absl
    else:
        absl, dabs = np.abs(lam), np.sign(lam)
    egap = c0 + np.sum(absl - lam) + 0.5 * np.sum(Wv * Wv)
    m = Wv + s
    am = np.sqrt(m * m + smooth * smooth) if smooth > 0 else np.abs(m)
    dam = m / am if smooth > 0 else np.sign(m)
    Lam = np.sum(absl) + 0.25 * np.sum((a + am) ** 2)
    proj = np.einsum("pj,kpq,qj->kj", V, Xs, V, optimize=True)
    return egap, Lam, -(proj @ (dabs - 1.0)) + Wv, -(proj @ dabs) + 0.5 * (a + am) * dam


def opt_offsets(Xs, h1p0, c0, a, s, W0, margin=2e-3, iters=150):
    floor = E_GAP_FLOOR + margin

    def f(x, sm, mu):
        eg, La, deg, dla = sos_metrics(x, Xs, h1p0, c0, a, s, sm)
        le = np.sqrt(max(eg * (2 * La - eg), 1e-12))
        g = (deg * (2 * La - eg) + eg * (2 * dla - deg)) / (2 * le)
        if eg < floor:
            le += mu * (floor - eg) ** 2
            g = g - 2 * mu * (floor - eg) * deg
        return le, g
    W = W0.copy()
    for sm, mu in ((1e-3, 1e6), (1e-5, 1e8)):
        W = minimize(f, W, args=(sm, mu), jac=True, method="L-BFGS-B",
                     options={"maxiter": iters, "maxcor": 30}).x
    return W
