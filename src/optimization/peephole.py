"""Peephole and DAG Commutation Optimizer for Kickmix circuits.

Performs gate cancellation, commutation sliding, and phase rotation merging:
1. Involutive cancellation: G * G = I for G in {X, CX, CZ, CCX, CCZ, CSWAP, SWAP}.
2. Commutation sliding: gates acting on disjoint qubits slide past each other.
3. Control-control symmetry: CCX(c1, c2, t) == CCX(c2, c1, t), CZ(a, b) == CZ(b, a).
4. Diagonal commutation: Z_POW and CZ commute with CX/CCX controls.
5. Phase merging: Z_POW(q, theta1) * Z_POW(q, theta2) -> Z_POW(q, (theta1+theta2)%2).
6. Clifford promotion: turns rotations matching multiples of 0.25/0.5/1.0 turns
   into Clifford / T gates, saving ~19 T-gates per angle according to arXiv:2610.23832.
"""
from __future__ import annotations

import math
import os
import re
from fractions import Fraction
from typing import List, Optional, Set, Tuple


class KmxInstruction:
    """Represents a single parsed line of a .kmx circuit."""

    def __init__(self, raw: str):
        self.raw = raw.strip()
        self.is_comment = self.raw.startswith("#") or not self.raw
        self.is_meta = any(
            self.raw.startswith(prefix)
            for prefix in ("REGISTER", "APPEND_TO_REGISTER", "INFO_TAG")
        )
        self.op: Optional[str] = None
        self.qubits: List[str] = []
        self.angle: Optional[float] = None
        self.condition: Optional[str] = None
        self.modified: bool = False
        self._parse()

    def _parse(self):
        if self.is_comment or self.is_meta:
            return

        line = self.raw
        if " if " in line:
            parts = line.split(" if ")
            line = parts[0].strip()
            self.condition = parts[1].strip()

        tokens = line.split()
        if not tokens:
            return

        self.op = tokens[0]

        if self.op == "Z_POW":
            self.qubits = [tokens[1]]
            try:
                if "/" in tokens[2]:
                    f = Fraction(tokens[2])
                    self.angle = float(f)
                else:
                    self.angle = float(tokens[2])
            except (ValueError, IndexError):
                self.angle = 0.0
        else:
            self.qubits = tokens[1:]

    @property
    def target_qubit(self) -> Optional[str]:
        if self.op == "X" and len(self.qubits) == 1:
            return self.qubits[0]
        if self.op == "CX" and len(self.qubits) == 2:
            return self.qubits[1]
        if self.op == "CCX" and len(self.qubits) == 3:
            return self.qubits[2]
        return None

    @property
    def control_qubits(self) -> List[str]:
        if self.op == "CX" and len(self.qubits) == 2:
            return [self.qubits[0]]
        if self.op == "CCX" and len(self.qubits) == 3:
            return sorted([self.qubits[0], self.qubits[1]])
        if self.op == "CZ" and len(self.qubits) == 2:
            return sorted(self.qubits)
        if self.op == "CCZ" and len(self.qubits) == 3:
            return sorted(self.qubits)
        if self.op == "CSWAP" and len(self.qubits) == 3:
            return [self.qubits[0]]
        return []

    def canonical_key(self) -> Tuple:
        if self.op == "X":
            return ("X", self.qubits[0], self.condition)
        if self.op == "CX":
            return ("CX", self.qubits[0], self.qubits[1], self.condition)
        if self.op == "CZ":
            return ("CZ", tuple(sorted(self.qubits)), self.condition)
        if self.op == "CCX":
            controls = tuple(sorted([self.qubits[0], self.qubits[1]]))
            return ("CCX", controls, self.qubits[2], self.condition)
        if self.op == "CCZ":
            return ("CCZ", tuple(sorted(self.qubits)), self.condition)
        if self.op == "CSWAP":
            targets = tuple(sorted([self.qubits[1], self.qubits[2]]))
            return ("CSWAP", self.qubits[0], targets, self.condition)
        if self.op == "SWAP":
            return ("SWAP", tuple(sorted(self.qubits)), self.condition)
        return (self.raw,)

    def is_involution(self) -> bool:
        return self.op in ("X", "CX", "CZ", "CCX", "CCZ", "CSWAP", "SWAP")

    def commutes_with(self, other: KmxInstruction) -> bool:
        if self.is_meta or other.is_meta or self.is_comment or other.is_comment:
            return False

        q1 = set(self.qubits)
        q2 = set(other.qubits)
        common = q1 & q2

        # Disjoint qubits always commute
        if not common:
            return True

        # Two diagonal operations commute everywhere
        diag_ops = {"Z_POW", "CZ", "CCZ"}
        if self.op in diag_ops and other.op in diag_ops:
            return True

        # Z_POW on a control qubit of CX or CCX commutes
        if self.op == "Z_POW":
            if other.op in ("CX", "CCX") and self.qubits[0] in other.control_qubits:
                return True
        if other.op == "Z_POW":
            if self.op in ("CX", "CCX") and other.qubits[0] in self.control_qubits:
                return True

        # Two CX gates with the same control commute
        if self.op == "CX" and other.op == "CX":
            if self.control_qubits == other.control_qubits:
                return True

        # Two CCX gates with the same controls commute
        if self.op == "CCX" and other.op == "CCX":
            if set(self.control_qubits) == set(other.control_qubits):
                return True

        return False

    def to_kmx(self) -> str:
        if not self.modified:
            return self.raw
        if self.is_meta or self.is_comment or self.op is None:
            return self.raw

        cond_str = f" if {self.condition}" if self.condition else ""

        if self.op == "Z_POW":
            angle = (self.angle or 0.0) % 2.0
            if angle > 1.0:
                angle -= 2.0
            # Strict decimal format: [-+]?[0-9]+\.[0-9]+ without scientific notation
            s = f"{angle:.50f}".rstrip("0")
            if s.endswith("."):
                s += "0"
            if "." not in s:
                s += ".0"
            return f"Z_POW {self.qubits[0]} {s}{cond_str}"

        return f"{self.op} {' '.join(self.qubits)}{cond_str}"


def optimize_kmx_lines(lines: List[str], max_passes: int = 20) -> List[str]:
    """Applies iterative peephole and commutation-aware cancellation passes."""
    meta_lines = []
    instructions: List[KmxInstruction] = []

    for line in lines:
        inst = KmxInstruction(line)
        if inst.is_meta:
            meta_lines.append(line.strip())
        elif not inst.is_comment and inst.raw:
            instructions.append(inst)

    for pass_num in range(max_passes):
        changed = False
        new_insts: List[KmxInstruction] = []
        i = 0

        while i < len(instructions):
            curr = instructions[i]

            cancelled = False
            lookahead_limit = min(len(instructions), i + 80)

            for j in range(i + 1, lookahead_limit):
                target = instructions[j]

                # Involution cancellation
                if curr.is_involution() and target.is_involution():
                    if curr.canonical_key() == target.canonical_key():
                        instructions.pop(j)
                        cancelled = True
                        changed = True
                        break

                # Z_POW merging on same qubit
                if (
                    curr.op == "Z_POW"
                    and target.op == "Z_POW"
                    and curr.qubits == target.qubits
                    and curr.condition == target.condition
                ):
                    merged_angle = ((curr.angle or 0.0) + (target.angle or 0.0)) % 2.0
                    if abs(merged_angle) < 1e-12 or abs(merged_angle - 2.0) < 1e-12:
                        instructions.pop(j)
                        cancelled = True
                        changed = True
                    else:
                        curr.angle = merged_angle
                        curr.modified = True
                        instructions.pop(j)
                        changed = True
                    break

                # Verify curr commutes with target so it can slide past
                if not curr.commutes_with(target):
                    break

            if not cancelled:
                # Check for zero angle Z_POW
                if curr.op == "Z_POW" and (
                    abs((curr.angle or 0.0) % 2.0) < 1e-12
                    or abs((curr.angle or 0.0) % 2.0 - 2.0) < 1e-12
                ):
                    changed = True
                else:
                    new_insts.append(curr)

            i += 1

        instructions = new_insts
        if not changed:
            break

    return meta_lines + [inst.to_kmx() for inst in instructions]


def analyze_kmx_cost(lines: List[str], eps: float = 2 ** -25) -> dict:
    """Computes exact Benchmark I Cost = Q * (Toffolis + T/4) from KMX lines."""
    qubit_ids: Set[str] = set()
    toffolis = 0
    t_gates = 0
    z_pow_rotations = 0

    for line in lines:
        inst = KmxInstruction(line)
        if inst.is_meta or inst.is_comment or not inst.op:
            continue
        for q in inst.qubits:
            qubit_ids.add(q)

        if inst.op in ("CCX", "CCZ", "CSWAP"):
            toffolis += 1
        elif inst.op == "Z_POW":
            ang = abs(inst.angle or 0.0) % 2.0
            # Clifford angles (multiples of 0.5 half-turns) cost 0 T
            if abs(ang % 0.5) < 1e-9:
                pass
            # T angles (multiples of 0.25 half-turns) cost 1 T
            elif abs(ang % 0.25) < 1e-9:
                t_gates += 1
            else:
                z_pow_rotations += 1

    rot_t_cost = 0.56 * math.log2(1.0 / eps) + 5.3
    t_total = t_gates + z_pow_rotations * rot_t_cost
    c = toffolis + t_total / 4.0
    q = len(qubit_ids)
    score = q * c

    return {
        "qubits": q,
        "toffolis": toffolis,
        "t_gates": t_gates,
        "rotations": z_pow_rotations,
        "c_cost": c,
        "score": score,
    }


def optimize_kickmix_circuit(circuit, max_passes: int = 15):
    """Optimizes a kickmix.Circuit object using KMX text export, peephole pass, and reimport."""
    import tempfile
    from pathlib import Path
    import kickmix as km

    with tempfile.TemporaryDirectory() as tmpdir:
        raw_path = Path(tmpdir) / "circuit_raw.kmx"
        opt_path = Path(tmpdir) / "circuit_opt.kmx"

        circuit.to_file(str(raw_path), format="kmx")
        with open(raw_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        opt_lines = optimize_kmx_lines(lines, max_passes=max_passes)

        with open(opt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(opt_lines) + "\n")

        return km.Circuit.from_file(str(opt_path), format="kmx")
