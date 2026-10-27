import random

import numpy as np
import pytest

km = pytest.importorskip("kickmix")
from src.dqi.gf_fast import Arith  # noqa: E402

GF = km.GF2Field(12)
AR = Arith(GF)


def _run(build, regs_in, shots=256, seed=1):
    b = km.CircuitBuilder()
    regs = {name: b.create_quantum_register(12, name=name) for name in regs_in}
    outs = build(b, regs)
    c = b.finish_circuit()
    sim = km.Simulator(batch_size=shots, seed=seed)
    sim.use_same_registers_as(c)
    sim.clear_for_shot()
    vals = {k: [random.randrange(4096) for _ in range(shots)] for k in regs_in}
    for k, v in vals.items():
        for s in range(shots):
            sim.write_within_shot(k, s, v[s])
    sim.do(c)
    return c, sim, vals, regs, outs


def _toffolis(c):
    return c.operation_statistics().num_toffoli_like


def test_ixor_mul_and_controlled():
    def build(b, r):
        AR.ixor_mul(b, r["x"], r["y"], r["t"])
        AR.ixor_mul(b, r["x"], r["y"], r["u"], control=r["c"][0])
    c, sim, vals, regs, _ = _run(build, ["x", "y", "t", "u", "c"])
    for s in range(256):
        x, y = vals["x"][s], vals["y"][s]
        assert sim.read_within_shot("t", s, out=int) == vals["t"][s] ^ GF.mul(x, y)
        exp_u = vals["u"][s] ^ (GF.mul(x, y) if vals["c"][s] & 1 else 0)
        assert sim.read_within_shot("u", s, out=int) == exp_u
        assert sim.read_shot_phase(s) == 0
    assert _toffolis(c) == 54 + 66


def test_inverse_and_div_roundtrip():
    def build(b, r):
        inv, rec = AR.init_inverse(b, r["z"])
        b.cx(inv, r["t"])                       # copy z^-1 out
        AR.del_inverse(b, rec)
        ratio, rec2 = AR.init_div(b, r["x"], r["z"])
        b.cx(ratio, r["u"])
        AR.del_div(b, rec2)
    c, sim, vals, regs, _ = _run(build, ["z", "t", "x", "u"])
    for s in range(256):
        z, x = vals["z"][s], vals["x"][s]
        zi = GF.pow(z, 4094) if z else 0
        assert sim.read_within_shot("t", s, out=int) == vals["t"][s] ^ zi
        assert sim.read_within_shot("u", s, out=int) == vals["u"][s] ^ GF.mul(x, zi)
        assert sim.read_shot_phase(s) == 0, "MBU left a phase"
    regs_all = {q for v in c.register_data.values() for q in v}
    sim_scratch = [km.q(i) for i in range(c.num_qubits) if km.q(i) not in regs_all]
    assert not sim.read_across_shots(km.array(sim_scratch)).any()
    assert _toffolis(c) <= 78 + 132
