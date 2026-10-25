"""Local scorer implementing the official formulas from arXiv:2610.23832v2.

Benchmark I  : S = Q * C,  C = Toffolis + T/4 (+ Z_POW priced at 0.56*log2(1/eps)+5.3 T each)
Benchmark II : S = R(eps_plus) * Q^2 * T,  R = ln2 / -ln(1/2 + 2*sqrt(eps_plus)); needs eps_plus < 1/16
Benchmark III: S = lambda_eff * T_tot * Q_tot, lambda_eff = sqrt(E_gap * (2*Lambda - E_gap))
Lower is better. Verify against Kaggle's Evaluation tab before relying on it.
"""
import math


def zpow_t_cost(eps: float) -> float:
    return 0.56 * math.log2(1.0 / eps) + 5.3


def bench1_score(qubits: int, toffolis: float, t_gates: float = 0, zpow_eps=()) -> float:
    t_total = t_gates + sum(zpow_t_cost(e) for e in zpow_eps)
    return qubits * (toffolis + t_total / 4.0)


def failure_upper_bound(shots: int, failures: int = 0, confidence_bits: int = 128) -> float:
    if failures:
        raise NotImplementedError("only the zero-failure bound is implemented")
    return confidence_bits * math.log(2) / shots


def repetition_factor(eps_plus: float) -> float:
    if eps_plus >= 1 / 16:
        return math.inf
    return math.log(2) / -math.log(0.5 + 2 * math.sqrt(eps_plus))


def bench2_score(qubits: int, t_count: float, eps_plus: float) -> float:
    return repetition_factor(eps_plus) * qubits ** 2 * t_count


def bench3_score(lam: float, e_gap: float, t_tot: float, q_tot: float) -> float:
    if lam <= 49.0 or e_gap <= 3.914898:
        return math.inf
    return math.sqrt(e_gap * (2 * lam - e_gap)) * t_tot * q_tot
