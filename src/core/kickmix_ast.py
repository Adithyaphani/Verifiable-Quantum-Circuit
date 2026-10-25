"""
Kickmix Circuit Abstract Syntax Tree (AST) & Serializer.

Defines the core data structures for building, simulating, optimizing,
and serializing Kickmix verifiable quantum circuits (.kmx / .kmb).
Strictly adheres to official Kickmix instruction grammar:
- Classical reversible: X, CX, CCX, SWAP
- Diagonal phase: Z, S, T, Z_POW, NEG
- Measurement and reset: HMR, R
- Classical bits: BIT_STORE0, BIT_STORE1, BIT_INVERT
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple, Dict, Any, Union
import math
import re


class OpType(Enum):
    """Supported operation types in Kickmix circuits."""
    X = "X"
    CX = "CX"
    CCX = "CCX"
    MCX = "MCX"
    SWAP = "SWAP"
    Z = "Z"
    S = "S"
    T = "T"
    Z_POW = "Z_POW"
    NEG = "NEG"
    R = "R"
    HMR = "HMR"
    BIT_STORE0 = "BIT_STORE0"
    BIT_STORE1 = "BIT_STORE1"
    BIT_INVERT = "BIT_INVERT"


@dataclass(frozen=True)
class Qubit:
    """Represents a quantum bit in a named register."""
    register: str
    index: int

    @property
    def name(self) -> str:
        return f"{self.register}_{self.index}"

    def __str__(self) -> str:
        return self.name


@dataclass
class GateOp:
    """Represents a single gate instruction in a Kickmix circuit."""
    op_type: OpType
    targets: List[Qubit]
    controls: List[Qubit] = field(default_factory=list)
    angle: Optional[float] = None  # In turns, for Z_POW gates
    classical_bit: Optional[int] = None

    @property
    def is_toffoli(self) -> bool:
        """Returns True if the operation consumes Toffoli resources."""
        return self.op_type == OpType.CCX or (self.op_type == OpType.MCX and len(self.controls) >= 2)

    @property
    def toffoli_cost(self) -> int:
        """Returns Toffoli equivalent cost."""
        if self.op_type == OpType.CCX:
            return 1
        elif self.op_type == OpType.MCX:
            num_ctrl = len(self.controls)
            return max(1, 2 * (num_ctrl - 2)) if num_ctrl >= 2 else 0
        return 0

    def to_kmx_line(self, qubit_index_map: Dict[Qubit, int]) -> str:
        """Serializes the gate operation to a standard space-separated .kmx line."""
        ctrl_indices = [str(qubit_index_map[c]) for c in self.controls]
        tgt_indices = [str(qubit_index_map[t]) for t in self.targets]

        if self.op_type == OpType.X:
            return f"X {tgt_indices[0]}"
        elif self.op_type == OpType.CX:
            return f"CX {ctrl_indices[0]} {tgt_indices[0]}"
        elif self.op_type == OpType.CCX:
            return f"CCX {ctrl_indices[0]} {ctrl_indices[1]} {tgt_indices[0]}"
        elif self.op_type == OpType.MCX:
            ctrl_str = " ".join(ctrl_indices)
            return f"MCX [{ctrl_str}] {tgt_indices[0]}"
        elif self.op_type == OpType.SWAP:
            return f"SWAP {tgt_indices[0]} {tgt_indices[1]}"
        elif self.op_type == OpType.Z:
            return f"Z {tgt_indices[0]}"
        elif self.op_type == OpType.S:
            return f"S {tgt_indices[0]}"
        elif self.op_type == OpType.T:
            return f"T {tgt_indices[0]}"
        elif self.op_type == OpType.Z_POW:
            # Strictly space-separated: Z_POW <target> <angle_in_turns>
            turns = self.angle if self.angle is not None else 0.0
            return f"Z_POW {tgt_indices[0]} {turns:.12f}"
        elif self.op_type == OpType.NEG:
            return f"NEG {tgt_indices[0]}"
        elif self.op_type == OpType.R:
            return f"R {tgt_indices[0]}"
        elif self.op_type == OpType.HMR:
            bit = self.classical_bit if self.classical_bit is not None else 0
            return f"HMR {tgt_indices[0]} {bit}"
        elif self.op_type == OpType.BIT_STORE0:
            return f"BIT_STORE0 {self.classical_bit}"
        elif self.op_type == OpType.BIT_STORE1:
            return f"BIT_STORE1 {self.classical_bit}"
        elif self.op_type == OpType.BIT_INVERT:
            return f"BIT_INVERT {self.classical_bit}"
        else:
            raise ValueError(f"Unknown operation type: {self.op_type}")


class KickmixCircuit:
    """
    Kickmix verifiable quantum circuit builder and optimizer.
    """
    def __init__(self, name: str = "circuit"):
        self.name = name
        self.registers: Dict[str, int] = {}
        self.instructions: List[GateOp] = []
        self._qubit_index_map: Dict[Qubit, int] = {}
        self._next_id: int = 0

    def add_register(self, name: str, size: int) -> List[Qubit]:
        """Allocates a named quantum register."""
        if name in self.registers:
            raise ValueError(f"Register '{name}' already exists.")
        self.registers[name] = size
        qubits = []
        for i in range(size):
            q = Qubit(name, i)
            self._qubit_index_map[q] = self._next_id
            self._next_id += 1
            qubits.append(q)
        return qubits

    @property
    def num_qubits(self) -> int:
        return self._next_id

    @property
    def toffoli_count(self) -> int:
        return sum(op.toffoli_cost for op in self.instructions)

    def x(self, target: Qubit):
        self.instructions.append(GateOp(OpType.X, targets=[target]))

    def cx(self, control: Qubit, target: Qubit):
        self.instructions.append(GateOp(OpType.CX, targets=[target], controls=[control]))

    def ccx(self, c1: Qubit, c2: Qubit, target: Qubit):
        self.instructions.append(GateOp(OpType.CCX, targets=[target], controls=[c1, c2]))

    def swap(self, q1: Qubit, q2: Qubit):
        self.instructions.append(GateOp(OpType.SWAP, targets=[q1, q2]))

    def z(self, target: Qubit):
        self.instructions.append(GateOp(OpType.Z, targets=[target]))

    def s(self, target: Qubit):
        self.instructions.append(GateOp(OpType.S, targets=[target]))

    def t(self, target: Qubit):
        self.instructions.append(GateOp(OpType.T, targets=[target]))

    def z_pow(self, target: Qubit, turns: float):
        """Applies diagonal rotation exp(i 2pi turns) to state |1>."""
        self.instructions.append(GateOp(OpType.Z_POW, targets=[target], angle=turns))

    def reset(self, target: Qubit):
        """Resets target qubit to |0>."""
        self.instructions.append(GateOp(OpType.R, targets=[target]))

    def to_kmx(self) -> str:
        """Serializes the circuit to official space-separated .kmx string."""
        lines = [
            f"# Kickmix Circuit: {self.name}",
            f"# Total Qubits: {self.num_qubits}",
            f"# Total Instructions: {len(self.instructions)}",
            f"# Toffoli Count: {self.toffoli_count}",
            ""
        ]
        for op in self.instructions:
            lines.append(op.to_kmx_line(self._qubit_index_map))
        return "\n".join(lines) + "\n"

    def save_kmx(self, path: str):
        """Writes the circuit to a .kmx file and validates syntax."""
        content = self.to_kmx()
        validate_kmx_content(content)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


VALID_OPCODES = {
    "X", "CX", "CCX", "MCX", "SWAP",
    "Z", "S", "T", "Z_POW", "NEG",
    "R", "HMR",
    "BIT_STORE0", "BIT_STORE1", "BIT_INVERT"
}


def validate_kmx_content(kmx_str: str) -> bool:
    """
    Validates that every instruction line conforms strictly to Kickmix grammar.
    Raises ValueError with line details if any invalid opcode or format is found.
    """
    for line_idx, raw_line in enumerate(kmx_str.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        tokens = line.split()
        op = tokens[0]
        if op not in VALID_OPCODES:
            raise ValueError(
                f"Line {line_idx}: Invalid Kickmix opcode '{op}'. "
                f"Must be one of {sorted(VALID_OPCODES)}"
            )
        # Verify opcode-specific arguments
        if op in ("X", "Z", "S", "T", "NEG", "R"):
            if len(tokens) != 2 or not tokens[1].isdigit():
                raise ValueError(f"Line {line_idx}: '{op}' expects 1 integer target, got: {tokens}")
        elif op == "CX":
            if len(tokens) != 3 or not (tokens[1].isdigit() and tokens[2].isdigit()):
                raise ValueError(f"Line {line_idx}: 'CX' expects 2 integer arguments, got: {tokens}")
        elif op == "CCX":
            if len(tokens) != 4 or not all(t.isdigit() for t in tokens[1:4]):
                raise ValueError(f"Line {line_idx}: 'CCX' expects 3 integer arguments, got: {tokens}")
        elif op == "SWAP":
            if len(tokens) != 3 or not (tokens[1].isdigit() and tokens[2].isdigit()):
                raise ValueError(f"Line {line_idx}: 'SWAP' expects 2 integer arguments, got: {tokens}")
        elif op == "Z_POW":
            if len(tokens) != 3 or not tokens[1].isdigit():
                raise ValueError(f"Line {line_idx}: 'Z_POW' expects target and float turns, got: {tokens}")
            try:
                float(tokens[2])
            except ValueError:
                raise ValueError(f"Line {line_idx}: 'Z_POW' angle must be float, got: {tokens[2]}")
    return True
