"""Build, save and sanity-check circuits with the OFFICIAL kickmix library.

Install kickmix first (not on PyPI):
    git clone --depth 1 https://github.com/quantumlib/Qualtran && pip install ./Qualtran/kickmix
Do not use src/core/kickmix_ast.py for submissions: its text format is rejected by the official parser.
"""
import random
import kickmix as km


def save_and_reload(circuit: "km.Circuit", path: str) -> "km.Circuit":
    """Write the circuit and load it back with the official parser (fails loudly if invalid)."""
    circuit.to_file(path)
    return km.Circuit.from_file(path)


def stats(circuit: "km.Circuit") -> dict:
    st = circuit.operation_statistics()
    return {"qubits": circuit.num_qubits, "toffoli": st.num_toffoli_like,
            "t": st.num_t_like, "instructions": st.num_instructions}


def fuzz_registers(circuit: "km.Circuit", reference, shots: int = 64, ignore_phase: bool = True) -> None:
    """Run random inputs through the official simulator and compare with reference(inputs)->outputs.

    reference takes a dict {register_name: int} and returns the expected dict. Scratch qubits
    (those in no named register) must come back as 0.
    """
    regs = circuit.register_data
    used = {q for v in regs.values() for q in v}
    unused = km.array(sorted(set(km.q(i) for i in range(circuit.num_qubits)) - used))
    sim = km.Simulator(batch_size=shots)
    sim.use_same_registers_as(circuit)
    sim.clear_for_shot()
    inputs = []
    for s in range(shots):
        inp = {k: random.randrange(1 << len(v)) for k, v in regs.items()}
        inputs.append(inp)
        for k, val in inp.items():
            sim.write_within_shot(k, s, val)
    sim.do(circuit)
    for s, inp in enumerate(inputs):
        want = reference(dict(inp))
        for k in regs:
            got = sim.read_within_shot(k, s, out=int)
            assert got == want[k], f"register {k}: {inp} -> {got}, expected {want[k]}"
        assert sim.read_within_shot(unused, s, out=int) == 0, "scratch qubits not clean"
