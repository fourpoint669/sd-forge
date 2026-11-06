"""Numerically check the behavior claims made in library/archetypes.md.

Usage:  python -I engine/verify_archetypes.py
Prints PASS/FAIL per check and exits non-zero on any failure. Pure numpy/stdlib;
integration is fixed-step Euler (what Vensim/PySD default to) with a small dt.
"""
import math
import sys

import numpy as np

results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")


def euler(f, y0, t_end, dt):
    n = int(round(t_end / dt))
    ys = np.empty((n + 1, len(y0)))
    ys[0] = y0
    for i in range(n):
        ys[i + 1] = ys[i] + dt * np.asarray(f(i * dt, ys[i]))
    return np.arange(n + 1) * dt, ys


# 1. Reinforcing loop: exponential growth, dS/dt = g S -> S(t)=S0 e^{gt}
t, y = euler(lambda t, s: [0.1 * s[0]], [1.0], 20, 0.001)
check("R-loop exponential growth", abs(y[-1, 0] - math.exp(2)) / math.exp(2) < 1e-2,
      f"S(20)={y[-1,0]:.4f} vs {math.exp(2):.4f}")

# 2. Balancing loop: goal seeking, dS/dt=(G-S)/tau -> S(t)=G-(G-S0)e^{-t/tau}
G, tau = 100.0, 5.0
t, y = euler(lambda t, s: [(G - s[0]) / tau], [0.0], 25, 0.001)
exact = G - G * math.exp(-25 / tau)
check("B-loop goal seeking", abs(y[-1, 0] - exact) / G < 1e-3, f"S(25)={y[-1,0]:.3f} vs {exact:.3f}")

# 3. Limits to growth / logistic S-curve: dS/dt = g S (1 - S/K); inflection at K/2
g, K = 0.5, 1000.0
t, y = euler(lambda t, s: [g * s[0] * (1 - s[0] / K)], [10.0], 30, 0.001)
rate = np.gradient(y[:, 0], t)
S_at_peak = y[np.argmax(rate), 0]
check("Logistic: converges to K", abs(y[-1, 0] - K) / K < 1e-3, f"S(30)={y[-1,0]:.2f}")
check("Logistic: max growth rate at S=K/2", abs(S_at_peak - K / 2) / K < 0.02, f"S*={S_at_peak:.1f}")

# 4. Bass diffusion: dA/dt=(p+q A/N)(N-A); peak adoption rate at t*=ln(q/p)/(p+q), A*=N(q-p)/(2q)
p, q, N = 0.03, 0.38, 1000.0
t, y = euler(lambda t, s: [(p + q * s[0] / N) * (N - s[0])], [0.0], 30, 0.001)
rate = np.gradient(y[:, 0], t)
t_star = math.log(q / p) / (p + q)
check("Bass: peak time = ln(q/p)/(p+q)", abs(t[np.argmax(rate)] - t_star) < 0.05,
      f"t*={t[np.argmax(rate)]:.2f} vs {t_star:.2f}")
check("Bass: adopters at peak = N(q-p)/(2q)", abs(y[np.argmax(rate), 0] - N * (q - p) / (2 * q)) / N < 0.01)
check("Bass: saturates at N", abs(y[-1, 0] - N) / N < 1e-3)

# 5. SIR: S+I+R conserved; peak infectious when S = N/R0; final size from implicit relation
beta, gam, Npop = 0.4, 0.1, 1000.0
R0 = beta / gam
def sir(t, s):
    S, I, R = s
    inf = beta * S * I / Npop
    return [-inf, inf - gam * I, gam * I]
t, y = euler(sir, [Npop - 1, 1, 0], 200, 0.01)
check("SIR: population conserved (rel drift < 1e-6)", np.max(np.abs(y.sum(axis=1) - Npop)) / Npop < 1e-6)
check("SIR: infection peak at S=N/R0", abs(y[np.argmax(y[:, 1]), 0] - Npop / R0) / Npop < 0.02,
      f"S*={y[np.argmax(y[:,1]),0]:.1f} vs {Npop/R0:.1f}")
# final-size: R_inf/N = 1 - exp(-R0 * R_inf/N) (solved by fixed point)
z = 0.5
for _ in range(200):
    z = 1 - math.exp(-R0 * z)
check("SIR: final size matches implicit relation", abs(y[-1, 2] / Npop - z) < 0.01,
      f"{y[-1,2]/Npop:.3f} vs {z:.3f}")

# 6. Stock management with delay (inventory oscillation): ds/dt = in - out, orders adjust with lag
#    Balanced loop with delay: S' = (G-S)/tau_a with second-order delay in perception -> overshoot
G, tau_a, tau_d = 100.0, 2.0, 4.0
def delayed(t, s):
    S, P = s  # P = perceived stock (first-order smoothing)
    return [(G - P) / tau_a, (S - P) / tau_d]
t, y = euler(delayed, [0.0, 0.0], 60, 0.001)
check("B-loop with delay: overshoot > 1% above goal", y[:, 0].max() > 1.01 * G, f"max={y[:,0].max():.1f}")
check("B-loop with delay: eventually settles", abs(y[-1, 0] - G) / G < 0.02, f"S(60)={y[-1,0]:.2f}")

# 7. Shifting the burden: symptomatic fix (fast, decays) vs fundamental solution (slow);
#    reliance on the fix erodes fundamental capability, so the problem gap re-opens.
def burden(t, s):
    gap, cap = s
    fix = 0.5 * gap                      # symptomatic fix effort proportional to gap
    fund = 0.05 * gap * cap              # fundamental solution effectiveness depends on capability
    d_gap = 0.1 - fix - fund             # constant pressure creating the gap
    d_cap = 0.02 * (1 - cap) - 0.2 * fix * cap  # capability erodes with reliance on the fix
    return [d_gap, d_cap]
t, y = euler(burden, [1.0, 1.0], 100, 0.01)
check("Shifting burden: capability ends >25% below its initial value", y[-1, 1] < 0.75, f"cap(100)={y[-1,1]:.3f}")
check("Shifting burden: gap settles above a no-erosion case", y[-1, 0] > 0.1 / (0.5 + 0.05 * 1.0),
      f"gap={y[-1,0]:.3f} vs {0.1/0.55:.3f}")

# 8. Resource depletion: renewable resource with harvest; overshoot-and-collapse when capital grows on a finite nonrenewable stock
def deplete(t, s):
    R, K = s
    extract = 0.05 * K * R / (R + 100.0)   # extraction ~ capital, tapering as resource depletes
    return [-extract, 1.0 * extract - 0.03 * K]  # capital reinvests extraction output, depreciates
t, y = euler(deplete, [1000.0, 10.0], 400, 0.01)
extract = 0.05 * y[:, 1] * y[:, 0] / (y[:, 0] + 100.0)
check("Resource depletion: extraction rises then falls (peaks mid-run)", 0 < np.argmax(extract) < len(t) - 1 and extract[-1] < 0.5 * extract.max(),
      f"peak at t={t[np.argmax(extract)]:.0f}, final/peak={extract[-1]/extract.max():.2f}")

# 9. Integration-error scaling: halving dt halves the Euler error (first order)
def run(dt):
    t, y = euler(lambda t, s: [-0.5 * s[0]], [1.0], 10, dt)
    return abs(y[-1, 0] - math.exp(-5))
e1, e2 = run(0.1), run(0.05)
check("Euler error ~ O(dt): halving dt halves error (ratio 1.8-2.2)", 1.8 < e1 / e2 < 2.2, f"ratio={e1/e2:.2f}")

sys.exit(0 if all(results) else 1)
