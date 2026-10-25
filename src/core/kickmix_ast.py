"""
Kickmix Circuit Abstract Syntax Tree (AST) & Serializer.

Defines the core data structures for building, simulating, optimizing,
and serializing Kickmix verifiable quantum circuits (.kmx / .kmb).
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple, Dict, Any, Union
import math


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
    RZ = "RZ"
    MEASURE_UNCOMPUTE = "MEASURE_UNCOMPUTE"


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
    angle: Optional[float] = None  # In radians, for RZ gates

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
            # An n-controlled NOT requires roughly 2(n-2) Toffolis with clean ancillae
            num_ctrl = len(self.controls)
            return max(1, 2 * (num_ctrl - 2)) if num_ctrl >= 2 else 0
        return 0

    def to_kmx_line(self, qubit_index_map: Dict[Qubit, int]) -> str:
        """Serializes the gate operation to a standard .kmx text format line."""
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
        elif self.op_type == OpType.RZ:
            # Space-separated opcode, target qubit, and phase angle
            return f"RZ {tgt_indices[0]} {self.angle:.12f}"

        elif self.op_type == OpType.MEASURE_UNCOMPUTE:
            return f"UNCOMPUTE {tgt_indices[0]}"
        else:
            raise ValueError(f"Unknown operation type: {self.op_type}")


class KickmixCircuit:
    """
    Kickmix verifiable quantum circuit builder and optimizer.
    Maintains registers, instructions, and resource metrics.
    """

    def __init__(self, name: str = "kickmix_circuit"):
        self.name = name
        self.registers: Dict[str, int] = {}  # Register name -> size
        self.instructions: List[GateOp] = []
        self._qubit_index_map: Dict[Qubit, int] = {}
        self._next_qubit_id = 0

    def add_register(self, name: str, size: int) -> List[Qubit]:
        """Allocates a register of qubits."""
        if name in self.registers:
            raise ValueError(f"Register '{name}' already exists.")
        self.registers[name] = size
        qubits = []
        for i in range(size):
            q = Qubit(register=name, index=i)
            self._qubit_index_map[q] = self._next_qubit_id
            self._next_qubit_id += 1
            qubits.append(q)
        return qubits

    @property
    def num_qubits(self) -> int:
        """Total number of qubits allocated."""
        return self._next_qubit_id

    @property
    def toffoli_count(self) -> int:
        """Total Toffoli gate cost."""
        return sum(op.toffoli_cost for op in self.instructions)

    @property
    def cx_count(self) -> int:
        """Total CNOT gate count."""
        return sum(1 for op in self.instructions if op.op_type == OpType.CX)

    @property
    def phase_count(self) -> int:
        """Total diagonal phase operations (Z, S, T, RZ)."""
        return sum(1 for op in self.instructions if op.op_type in (OpType.Z, OpType.S, OpType.T, OpType.RZ))

    @property
    def benchmark_1_cost(self) -> float:
        """Cost metric for Benchmark I (Fusion 1/√x phasing): Q^2 * T."""
        q = self.num_qubits
        t = self.toffoli_count
        return float(q * q * t)

    # --- Gate Application Helpers ---

    def x(self, target: Qubit):
        self.instructions.append(GateOp(op_type=OpType.X, targets=[target]))

    def cx(self, control: Qubit, target: Qubit):
        self.instructions.append(GateOp(op_type=OpType.CX, targets=[target], controls=[control]))

    def ccx(self, control1: Qubit, control2: Qubit, target: Qubit):
        self.instructions.append(GateOp(op_type=OpType.CCX, targets=[target], controls=[control1, control2]))

    def mcx(self, controls: List[Qubit], target: Qubit):
        self.instructions.append(GateOp(op_type=OpType.MCX, targets=[target], controls=controls))

    def swap(self, q1: Qubit, q2: Qubit):
        self.instructions.append(GateOp(op_type=OpType.SWAP, targets=[q1, q2]))

    def z(self, target: Qubit):
        self.instructions.append(GateOp(op_type=OpType.Z, targets=[target]))

    def s(self, target: Qubit):
        self.instructions.append(GateOp(op_type=OpType.S, targets=[target]))

    def t(self, target: Qubit):
        self.instructions.append(GateOp(op_type=OpType.T, targets=[target]))

    def rz(self, target: Qubit, angle: float):
        self.instructions.append(GateOp(op_type=OpType.RZ, targets=[target], angle=angle))

    def uncompute(self, target: Qubit):
        self.instructions.append(GateOp(op_type=OpType.MEASURE_UNCOMPUTE, targets=[target]))

    # --- Serialization ---

    def to_kmx(self) -> str:
        """Serializes the circuit into the human-readable Kickmix (.kmx) text format."""
        lines = [
            f"# Kickmix Circuit: {self.name}",
            f"# Total Qubits: {self.num_qubits}",
            f"# Total Gates: {len(self.instructions)}",
            f"# Toffoli Count: {self.toffoli_count}",
            f"# Registers: " + ", ".join(f"{name}[{size}]" for name, size in self.registers.items()),
            ""
        ]
        for op in self.instructions:
            lines.append(op.to_kmx_line(self._qubit_index_map))
        return "\n".join(lines) + "\n"

    def save_kmx(self, filepath: str):
        """Saves circuit to a .kmx file."""
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(self.to_kmx())

    def to_cirq(self):
        """Converts the Kickmix circuit into a Cirq Circuit object for visualization and simulation."""
        import cirq
        qubits = [cirq.LineQubit(i) for i in range(self.num_qubits)]
        circuit = cirq.Circuit()

        for op in self.instructions:
            tgt_idx = [self._qubit_index_map[t] for t in op.targets]
            ctrl_idx = [self._qubit_index_map[c] for c in op.controls]

            if op.op_type == OpType.X:
                circuit.append(cirq.X(qubits[tgt_idx[0]]))
            elif op.op_type == OpType.CX:
                circuit.append(cirq.CNOT(qubits[ctrl_idx[0]], qubits[tgt_idx[0]]))
            elif op.op_type == OpType.CCX:
                circuit.append(cirq.TOFFOLI(qubits[ctrl_idx[0]], qubits[ctrl_idx[1]], qubits[tgt_idx[0]]))
            elif op.op_type == OpType.SWAP:
                circuit.append(cirq.SWAP(qubits[tgt_idx[0]], qubits[tgt_idx[1]]))
            elif op.op_type == OpType.Z:
                circuit.append(cirq.Z(qubits[tgt_idx[0]]))
            elif op.op_type == OpType.S:
                circuit.append(cirq.S(qubits[tgt_idx[0]]))
            elif op.op_type == OpType.T:
                circuit.append(cirq.T(qubits[tgt_idx[0]]))
            elif op.op_type == OpType.RZ:
                circuit.append(cirq.rz(op.angle)(qubits[tgt_idx[0]]))
            elif op.op_type == OpType.MEASURE_UNCOMPUTE:
                # In cirq simulation, represented as reset or identity projection
                circuit.append(cirq.reset(qubits[tgt_idx[0]]))

        return circuit

    def __repr__(self) -> str:
        return (f"<KickmixCircuit '{self.name}': {self.num_qubits} qubits, "
                f"{len(self.instructions)} gates, {self.toffoli_count} Toffolis, "
                f"B1 Cost={self.benchmark_1_cost:.1f}>")
