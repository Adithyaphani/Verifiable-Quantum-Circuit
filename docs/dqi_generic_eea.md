# DQI decoder v2: generic-schedule EEA

`src/dqi/generic_eea2.py` replaces Google's Proos-Zalka synchronized EEA (222 quantum-controlled iterations) with a fixed schedule of 35 EEA steps that assumes every quotient has degree 1. That holds for ~99.65% of the verifier's shots. The rest decode wrongly and are paid for through the repetition factor R(eps+).

Key ideas:
1. **Generic EEA, in place.** Two arrays of 71 GF(2^12) slots. Array (i mod 2) holds r_i low-aligned and u_i reversed from the top, so each step's two freed top slots of r are exactly where u grows. The even array's first 70 slots are the syndrome registers themselves.
2. **No controlled multiplications.** The quotient coefficients q1, q0 are gated by the "alive" flag once (12 Toffolis each), so the 142 slot updates per step are plain 54-Toffoli multiplications that become no-ops after the decoder halts.
3. **Free clean-up.** q1 and q0 are recomputed from the new state (q1 = lead(u_i)/lead(u_{i-1})) and cleared by measurement-based uncomputation.
4. **Cheaper field arithmetic** (`src/dqi/gf_fast.py`): 2-level Karatsuba multiplication (54 Toffolis vs 63) and tower-field inversion GF(((2^3)^2)^2) (77 vs 315). All products are cleared for free by HMR plus classically conditioned CZ.
5. **Chien/Forney.** sigma = c*u_k and omega = c*r_k share the same scale c, so e_j = omega/sigma' at each root, with no normalisation. Each position costs 11 (zero test) + 77 (inverse) + 12 (AND) Toffolis; the MBUC phase is free.
6. **6-bit step counter** instead of 35 flags, and in-place accumulators (Q 1829 -> 1780).

Official verifier (102,400 shots): PASS, Q = 1780, T = 985,342, 377 phase errors (eps+ -> R = 1.69), score 5.288e12. Reference: 2.444e13, so **4.62x**.

Build: `python tools/build_dqi.py dqi.kmb [--verify 2]`.
