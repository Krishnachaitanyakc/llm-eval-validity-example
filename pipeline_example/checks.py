"""The chapter's checks (Table 2 items 1, 4, 5, 6, 10, 14 and 15).

Thresholds are module constants, fixed before the example was run, as Table 2
asks. Each check returns a dict with its statistic, threshold and verdict.

Item 1 uses the generalizability coefficient of equation (5) of the chapter
for systems crossed with conditions (here prompt formats), with the runs as
reruns within each cell:

    E rho^2 = s2_m / (s2_m + s2_mc / n_c + s2_e / (n_c * R))

The variance components come from the two way random effects ANOVA with
replication (a systems, b formats, R reruns per cell), by expected mean
squares:

    E[MS_e]  = s2_e
    E[MS_mc] = s2_e + R s2_mc
    E[MS_m]  = s2_e + R s2_mc + b R s2_m

so s2_e = MS_e, s2_mc = (MS_mc - MS_e) / R and s2_m = (MS_m - MS_mc) / (b R),
each truncated at zero when the estimate is negative.

The G study uses the b = 4 formats tested; the decision study must match the
reporting design. The headline is reported under one format and averages the
R = 5 runs, so the primary coefficient uses n_c = 1 and R = 5. The value for
n_c = 4 (a score averaged over the four formats) is kept as a secondary line.
"""

import math

from .pipeline import (by_system, outcome_counts, permissive_extract,
                       permissive_value, strict_value, faulty_headline)
from .simulation import RERUN_BUDGET, SYSTEM_NAMES, rng_for

# Thresholds set in advance.
AUDIT_PER_SYSTEM = 40            # item 4: stratified sample, 40 per system
AUDIT_SAMPLE_SIZE = 120
AUDIT_MIN_LOWER_BOUND = 0.90      # item 4: Wilson lower bound, every system
AUDIT_GAP_FRACTION = 0.5          # item 4: error gap below half smallest gap (7)
MAX_UNPARSEABLE_SHARE = 0.05      # item 5: outputs with no parseable answer
RESCORING_TOLERANCE = 0.01        # item 6: headline vs strict rescoring
MIN_G_COEFFICIENT = 0.8           # item 1: E rho^2, equation (5)
REPORTED_FORMATS = 1              # item 1: the headline uses one format (n_c = 1)
NULL_FLOOR = 0.0                  # item 10: score of a system with no capability
NULL_MARGIN = 0.01                # item 10: margin above the floor
BOOTSTRAP_REPS = 10000            # item 14: paired bootstrap over items
BOOTSTRAP_LEVEL = 0.95


def wilson(successes, n, z=1.959964):
    """Wilson score interval for a binomial proportion."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (centre - half, centre + half)


def kendall_tau(scores_a, scores_b, names):
    """Kendall tau a between two score dicts over the same systems."""
    concordant = discordant = 0
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            da = scores_a[names[i]] - scores_a[names[j]]
            db = scores_b[names[i]] - scores_b[names[j]]
            if da * db > 0:
                concordant += 1
            elif da * db < 0:
                discordant += 1
    pairs = len(names) * (len(names) - 1) // 2
    return (concordant - discordant) / pairs


def ranking(scores):
    return sorted(scores, key=lambda s: (-scores[s], s))


def verdict(ok):
    return "PASS" if ok else "FAIL"


def smallest_gap(scores):
    """Smallest absolute difference between the scores of two systems."""
    names = sorted(scores)
    return min(abs(scores[a] - scores[b])
               for i, a in enumerate(names) for b in names[i + 1:])


def g_coefficient(cells, names, conditions, d_conditions=None, d_reruns=None):
    """Generalizability coefficient E rho^2 of equation (5) for systems
    crossed with conditions, R reruns per cell.

    The variance components are estimated from the G study (all conditions
    in cells); the coefficient is for a decision study with d_conditions
    conditions and d_reruns reruns (by default those of the G study).

    cells[condition][system] is the list of R rerun scores. Variance
    components come from the two way random effects ANOVA with replication by
    expected mean squares, each truncated at zero (see the module docstring).
    """
    a, b = len(names), len(conditions)
    reps = len(cells[conditions[0]][names[0]])
    cell = {(m, c): sum(cells[c][m]) / reps for m in names for c in conditions}
    row = {m: sum(cell[m, c] for c in conditions) / b for m in names}
    col = {c: sum(cell[m, c] for m in names) / a for c in conditions}
    grand = sum(row.values()) / a
    ss_m = b * reps * sum((row[m] - grand) ** 2 for m in names)
    ss_mc = reps * sum((cell[m, c] - row[m] - col[c] + grand) ** 2
                       for m in names for c in conditions)
    ss_e = sum((y - cell[m, c]) ** 2
               for m in names for c in conditions for y in cells[c][m])
    ms_m = ss_m / (a - 1)
    ms_mc = ss_mc / ((a - 1) * (b - 1))
    ms_e = ss_e / (a * b * (reps - 1))
    var_e = max(ms_e, 0.0)
    var_mc = max((ms_mc - ms_e) / reps, 0.0)
    var_m = max((ms_m - ms_mc) / (b * reps), 0.0)
    def coefficient(n_c, r):
        denom = var_m + var_mc / n_c + var_e / (n_c * r)
        return var_m / denom if denom > 0 else float("nan")

    d_nc = b if d_conditions is None else d_conditions
    d_r = reps if d_reruns is None else d_reruns
    return {"ms_m": ms_m, "ms_mc": ms_mc, "ms_e": ms_e, "var_m": var_m,
            "var_mc": var_mc, "var_e": var_e,
            "g_study_conditions": b, "g_study_reruns": reps,
            "n_c": d_nc, "R": d_r, "rho2": coefficient(d_nc, d_r),
            "rho2_all_conditions": coefficient(b, reps)}


# ------------------------------------------------------------- item 5

def _item5_rows(log):
    rows = {}
    for name, recs in by_system(log).items():
        logged = [r for r in recs if r["trace_has_answer"]]
        truncated = sum(r["finish_reason"] == "length" for r in logged)
        unparseable = sum(strict_value(r) is None for r in logged)
        fallback = sum(permissive_extract(r["reply"])[1] for r in logged)
        rows[name] = {"logged": len(logged), "truncated": truncated,
                      "unparseable": unparseable,
                      "unparseable_share": unparseable / len(logged),
                      "scored_by_fallback": fallback,
                      "fallback_share": fallback / len(logged)}
    return rows


def check_item5(faulty_log, fixed_log, faulty_counts_reported=False,
                corrected_counts_reported=True):
    """Unparseable share on the faulty log (buggy builder) and on the
    corrected log (fixed builder). The counts_reported flags record whether
    each report gives the counts; the faulty report is defined to omit them."""
    out = {"item": 5, "name": "Truncated and unparseable outputs",
           "statistic": "largest share of logged outputs with no answer "
                        "under the declared markers",
           "threshold": f"<= {MAX_UNPARSEABLE_SHARE} for every system, "
                        "counts reported"}
    for key, log, reported in (("faulty", faulty_log, faulty_counts_reported),
                               ("corrected", fixed_log,
                                corrected_counts_reported)):
        rows = _item5_rows(log)
        worst = max(rows, key=lambda n: rows[n]["unparseable_share"])
        ok = all(v["unparseable_share"] <= MAX_UNPARSEABLE_SHARE
                 for v in rows.values())
        out[key] = {"value": rows[worst]["unparseable_share"],
                    "worst_system": worst, "share_ok": ok,
                    "counts_reported": reported,
                    "verdict": verdict(ok and reported), "per_system": rows}
    out["value"] = out["faulty"]["value"]
    out["value_corrected"] = out["corrected"]["value"]
    out["verdict"] = out["faulty"]["verdict"]
    out["verdict_corrected"] = out["corrected"]["verdict"]
    return out


# ------------------------------------------------------------- item 4

def audit_sample(faulty_log):
    """Seeded random sample of logged outputs for hand labeling, stratified
    by system (AUDIT_PER_SYSTEM each), so that every system has its own
    interval."""
    sample = []
    for name in SYSTEM_NAMES:
        logged = [r for r in faulty_log
                  if r["system"] == name and r["trace_has_answer"]]
        sample.extend(rng_for("audit", name).sample(logged, AUDIT_PER_SYSTEM))
    return sample


def _error_type(r):
    value, fallback = permissive_extract(r["reply"])
    if value == r["label"]:
        return "correct"
    if r["label"] is None and r["finish_reason"] == "length":
        return "fallback read a number from a cut off reply"
    if r["label"] is None:
        return "fallback turned a non answer into a number"
    return "fallback missed the declared marker 'The answer is'"


def check_item4(sample, claimed):
    """claimed[extractor] holds the scores the pipeline using that extractor
    reports; its smallest gap sets the limit on the error gap (7)."""
    out = {}
    for label, extract in (("permissive", permissive_value),
                           ("strict", strict_value)):
        hits = sum(extract(r) == r["label"] for r in sample)
        lo, hi = wilson(hits, len(sample))
        per_system = {}
        for name in SYSTEM_NAMES:
            rs = [r for r in sample if r["system"] == name]
            h = sum(extract(r) == r["label"] for r in rs)
            plo, phi = wilson(h, len(rs))
            per_system[name] = {"n": len(rs), "correct": h,
                                "accuracy": h / len(rs),
                                "error_rate": 1 - h / len(rs),
                                "wilson_low": plo, "wilson_high": phi,
                                "bound_ok": plo >= AUDIT_MIN_LOWER_BOUND}
        errors = [v["error_rate"] for v in per_system.values()]
        error_gap = max(errors) - min(errors)
        gap = smallest_gap(claimed[label])
        limit = AUDIT_GAP_FRACTION * gap
        min_low = min(v["wilson_low"] for v in per_system.values())
        worst = min(per_system, key=lambda n: per_system[n]["wilson_low"])
        ok = all(v["bound_ok"] for v in per_system.values()) and error_gap < limit
        out[label] = {"correct": hits, "n": len(sample),
                      "accuracy": hits / len(sample),
                      "wilson_low": lo, "wilson_high": hi,
                      "min_wilson_low": min_low, "worst_system": worst,
                      "error_gap": error_gap, "smallest_claimed_gap": gap,
                      "error_gap_limit": limit,
                      "claimed_scores": claimed[label],
                      "verdict": verdict(ok), "per_system": per_system}
    errors = {}
    for r in sample:
        t = _error_type(r)
        if t != "correct":
            errors[t] = errors.get(t, 0) + 1
    out["permissive"]["error_types"] = dict(sorted(errors.items()))
    return {"item": 4, "name": "Extractor audit on a hand labeled sample",
            "statistic": "smallest Wilson 95% lower bound of extractor "
                         "accuracy over systems, and the largest difference "
                         "in error rates between systems",
            "value": out["permissive"]["min_wilson_low"],
            "threshold": f"lower bound >= {AUDIT_MIN_LOWER_BOUND} for every "
                         f"system, and error gap < {AUDIT_GAP_FRACTION} x "
                         "smallest claimed gap (Proposition 2, (7))",
            "verdict": out["permissive"]["verdict"], "extractors": out}


# ------------------------------------------------------------- item 6

def check_item6(faulty_log, headlines):
    """Rescoring with an independent strict extractor. This is not a
    reconstruction of the same rule: it rescores the logged replies with
    another extractor and the corrected aggregation (lower and upper scores),
    and asks whether the headline lies within the rescored bounds."""
    rows = {}
    for name, recs in by_system(faulty_log).items():
        c = outcome_counts(recs)
        h = headlines[name]
        gap = max(c["lower"] - h, h - c["upper"], 0.0)
        rows[name] = {"headline": h, "rescored_lower": c["lower"],
                      "rescored_upper": c["upper"],
                      "rescored_width": c["upper"] - c["lower"],
                      "distance": gap,
                      "verdict": verdict(gap <= RESCORING_TOLERANCE)}
    worst_system = max(rows, key=lambda n: rows[n]["distance"])
    worst = rows[worst_system]["distance"]
    return {"item": 6, "name": "Rescoring with an independent strict extractor",
            "statistic": "largest distance of a headline from the rescored "
                         "[lower, upper] interval",
            "value": worst, "worst_system": worst_system,
            "threshold": f"<= {RESCORING_TOLERANCE}",
            "verdict": verdict(worst <= RESCORING_TOLERANCE),
            "per_system": rows}


# ------------------------------------------------------------- item 1

def check_item1(cells, main_format, pipeline_label):
    """cells[format][system]: the score of each of the R runs.

    Primary statistic: E rho^2 of equation (5) for the reported design, one
    format (n_c = REPORTED_FORMATS) and the R runs the headline averages,
    with variance components from all formats tested. Secondary: E rho^2 for
    a score averaged over every format tested (n_c = 4). Secondary: Kendall tau of each format's ranking of run
    means against the main format; with three systems tau takes only the
    values plus or minus 1/3 and plus or minus 1, so it cannot carry a
    graded threshold."""
    formats = tuple(cells)
    means = {f: {n: sum(v) / len(v) for n, v in cells[f].items()}
             for f in formats}
    reruns = len(cells[main_format][SYSTEM_NAMES[0]])
    g = g_coefficient(cells, SYSTEM_NAMES, formats,
                      d_conditions=REPORTED_FORMATS, d_reruns=reruns)
    taus = {f: kendall_tau(means[main_format], means[f], SYSTEM_NAMES)
            for f in formats}
    return {"item": 1, "name": f"Invariance across formats ({pipeline_label})",
            "statistic": "generalizability coefficient E rho^2, equation (5), "
                         "for the reported design (one format, the runs the "
                         "headline averages); components from systems by "
                         "formats with runs as reruns",
            "value_all_formats": g["rho2_all_conditions"],
            "value": g["rho2"], "threshold": f">= {MIN_G_COEFFICIENT}",
            "verdict": verdict(g["rho2"] >= MIN_G_COEFFICIENT),
            "g_study": g,
            "secondary": "Kendall tau against the main format (three "
                         "systems: values +-1/3 and +-1 only)",
            "min_tau": min(taus.values()),
            "rankings": {f: ranking(s) for f, s in means.items()},
            "mean_scores": means, "taus": taus}


# ------------------------------------------------------------- item 14

def _percentile_interval(values, level):
    v = sorted(values)
    b = len(v)
    tail = (1 - level) / 2
    return (v[int(math.floor(tail * b))], v[int(math.ceil((1 - tail) * b)) - 1])


def paired_bootstrap(records, reps=BOOTSTRAP_REPS, level=BOOTSTRAP_LEVEL):
    """Paired bootstrap over items for every pair of systems.

    Resamples the items with replacement (all runs of an item, for every
    system, move together) and recomputes the margin lower(X) - upper(Y),
    where X is the system with the larger observed lower score. Returns a
    percentile interval for each margin."""
    item_ids = sorted({r["item_id"] for r in records})
    index = {i: k for k, i in enumerate(item_ids)}
    pas, pus, ns = {}, {}, {}
    for name, recs in by_system(records).items():
        p = [0] * len(item_ids)
        pu = [0] * len(item_ids)
        n = [0] * len(item_ids)
        for r in recs:
            k = index[r["item_id"]]
            n[k] += 1
            if not r["trace_has_answer"] or r["error_persists"]:
                pu[k] += 1
            elif strict_value(r) == r["reference"]:
                p[k] += 1
                pu[k] += 1
        pas[name], pus[name], ns[name] = p, pu, n
    pairs = []
    for i, a in enumerate(SYSTEM_NAMES):
        for b in SYSTEM_NAMES[i + 1:]:
            low_a = sum(pas[a]) / sum(ns[a])
            low_b = sum(pas[b]) / sum(ns[b])
            x, y = (a, b) if low_a >= low_b else (b, a)
            pairs.append((a, b, x, y))
    margins = {(a, b): [] for a, b, _, _ in pairs}
    rng = rng_for("bootstrap")
    population = range(len(item_ids))
    for _ in range(reps):
        idx = rng.choices(population, k=len(item_ids))
        tot = {}
        for name in SYSTEM_NAMES:
            tot[name] = (sum(map(pas[name].__getitem__, idx)),
                         sum(map(pus[name].__getitem__, idx)),
                         sum(map(ns[name].__getitem__, idx)))
        for a, b, x, y in pairs:
            margins[a, b].append(tot[x][0] / tot[x][2] - tot[y][1] / tot[y][2])
    out = []
    for a, b, x, y in pairs:
        observed = (sum(pas[x]) / sum(ns[x])) - (sum(pus[y]) / sum(ns[y]))
        lo, hi = _percentile_interval(margins[a, b], level)
        out.append({"pair": [a, b], "margin": f"lower({x}) - upper({y})",
                    "observed": observed, "low": lo, "high": hi,
                    "resolved": lo > 0})
    return out


def check_item14(corrected_log, faulty_log, faulty_report_has_undecided=False):
    """faulty_report_has_undecided records whether the faulty report gives U;
    it is defined to omit it, so the faulty verdict is a compliance check."""
    counts = {n: outcome_counts(r) for n, r in by_system(corrected_log).items()}
    lost = {n: sum(not r["trace_has_answer"] for r in rs) / len(rs)
            for n, rs in by_system(faulty_log).items()}
    order = []
    for a in SYSTEM_NAMES:
        for b in SYSTEM_NAMES:
            if a < b:
                ca, cb = counts[a], counts[b]
                if ca["lower"] > cb["upper"]:
                    order.append((a, b, f"{a} > {b}"))
                elif cb["lower"] > ca["upper"]:
                    order.append((a, b, f"{b} > {a}"))
                else:
                    order.append((a, b, "not ordered, bounds overlap"))
    boot = paired_bootstrap(corrected_log)
    return {"item": 14, "name": "Undecided outcomes",
            "statistic": "faulty report: whether U is reported, and the lost "
                         "share per system; corrected report: P, F, U, E "
                         "counts, lower and upper scores over runs, and a "
                         "paired bootstrap interval for each dominance margin",
            "faulty_report": "U not reported (undecided runs dropped)",
            "faulty_lost_share": lost,
            "verdict_faulty_report": verdict(faulty_report_has_undecided),
            "verdict_corrected_report": verdict(all(
                {"P", "F", "U", "E", "lower", "upper"} <= set(c)
                for c in counts.values())),
            "verdict": verdict(faulty_report_has_undecided),
            "threshold": "P, F, U, E and bounds reported for every system; "
                         "order only when lower(A) > upper(B), and claim it "
                         "beyond these items only when the paired interval "
                         "of the margin excludes zero",
            "unit": "runs (bounds are over all runs of a system)",
            "rerun_budget": RERUN_BUDGET,
            "bootstrap": {"reps": BOOTSTRAP_REPS, "level": BOOTSTRAP_LEVEL,
                          "seed": "rng_for('bootstrap')",
                          "resampled_unit": "item, all runs together",
                          "pairs": boot},
            "counts": counts, "dominance": order}


# ------------------------------------------------------------- item 10

def check_item10(null_log):
    perm = sum(permissive_value(r) == r["reference"] for r in null_log) / len(null_log)
    strict = sum(strict_value(r) == r["reference"] for r in null_log) / len(null_log)
    limit = NULL_FLOOR + NULL_MARGIN
    return {"item": 10, "name": "Null control (echo agent)",
            "statistic": "score of an agent that only echoes the prompt",
            "value": perm, "value_strict": strict,
            "threshold": f"<= floor {NULL_FLOOR} + margin {NULL_MARGIN}, "
                         "set in advance",
            "verdict": verdict(perm <= limit),
            "verdict_strict": verdict(strict <= limit)}


# ------------------------------------------------------------- item 15

def check_item15(run_scores, every_run_reported=False):
    """Selection: the faulty report gives only the best of the runs. The flag
    records that the faulty report is defined to omit the other runs."""
    rows = {}
    for name, runs in run_scores.items():
        mean = sum(runs) / len(runs)
        rows[name] = {"best": max(runs), "mean": mean,
                      "best_minus_mean": max(runs) - mean}
    worst = max(v["best_minus_mean"] for v in rows.values())
    return {"item": 15, "name": "Uncertainty and selection",
            "statistic": "best run minus mean of runs",
            "value": worst, "threshold": "every run reported",
            "every_run_reported": every_run_reported,
            "verdict": verdict(every_run_reported), "per_system": rows}
