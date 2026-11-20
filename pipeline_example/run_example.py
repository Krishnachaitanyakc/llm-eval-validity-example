"""Entry point: run the worked example, print the report, write results.

Usage (from the supplement folder):
    python3 -m pipeline_example.run_example [--out results] [--no-figure]
"""

import argparse
import csv
import json
import os

from . import __version__, checks
from .pipeline import (accuracy_all, agreement, by_system, dropped_mean,
                       faulty_headline, generate_log, null_echo_log,
                       oracle_extract, outcome_counts, permissive_value,
                       strict_value)
from .simulation import (DEPTHS, FORMATS, ITEMS, MAIN_FORMAT, N_ITEMS, N_RUNS,
                         RERUN_BUDGET, SEED, SYSTEM_NAMES)

STAGES = (
    ("truth", "truth"),
    ("s1_prompt_bug", "+S1 bug"),
    ("s3_fallback", "+S3 fallback"),
    ("s67_drop_undecided", "+S6,7 drop"),
    ("s7_best_run", "+S7 best run"),
)


def rounded(obj):
    """Round floats for stable JSON output."""
    if isinstance(obj, float):
        return round(obj, 6)
    if isinstance(obj, dict):
        return {str(k): rounded(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [rounded(v) for v in obj]
    return obj


def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        for row in rows:
            w.writerow([f"{v:.4f}" if isinstance(v, float) else v for v in row])


def compute():
    """Run every pipeline variant and every check. Returns a results dict."""
    fixed = {f: generate_log("fixed", f) for f in FORMATS}
    faulty = {f: generate_log("faulty", f) for f in FORMATS}
    fixed_main = by_system(fixed[MAIN_FORMAT])
    faulty_main = by_system(faulty[MAIN_FORMAT])

    stages, truth, headline, run_scores = {}, {}, {}, {}
    for name in SYSTEM_NAMES:
        fx, fa = fixed_main[name], faulty_main[name]
        best, runs = faulty_headline(fa)
        stages[name] = {
            "truth": accuracy_all(fx, oracle_extract),
            "s1_prompt_bug": accuracy_all(fa, oracle_extract),
            "s3_fallback": accuracy_all(fa, permissive_value),
            "s67_drop_undecided": dropped_mean(fa),
            "s7_best_run": best,
        }
        truth[name] = stages[name]["truth"]
        headline[name] = best
        run_scores[name] = runs

    agree = {name: {"truth": agreement(fixed_main[name], oracle_extract),
                    "faulty": agreement(faulty_main[name], permissive_value)}
             for name in SYSTEM_NAMES}

    depth = []
    for name in SYSTEM_NAMES:
        for d in DEPTHS:
            fa = [r for r in faulty_main[name] if r["depth"] == d]
            fx = [r for r in fixed_main[name] if r["depth"] == d]
            depth.append({
                "system": name, "depth": d,
                "faulty_accuracy": accuracy_all(fa, permissive_value),
                "faulty_agreement_permissive": agreement(fa, permissive_value),
                "faulty_agreement_strict": agreement(fa, strict_value),
                "true_accuracy": accuracy_all(fx, oracle_extract),
                "true_agreement": agreement(fx, oracle_extract),
            })

    # Item 1 cells: the score of every run, per format and system.
    faulty_cells = {f: {n: faulty_headline(r)[1]
                        for n, r in by_system(faulty[f]).items()}
                    for f in FORMATS}
    corrected_cells = {f: {n: [outcome_counts([x for x in r if x["run"] == k])
                               ["lower"] for k in range(N_RUNS)]
                           for n, r in by_system(fixed[f]).items()}
                       for f in FORMATS}
    faulty_scores = {f: {n: max(v) for n, v in faulty_cells[f].items()}
                     for f in FORMATS}
    corrected_scores = {f: {n: outcome_counts(r)["lower"]
                            for n, r in by_system(fixed[f]).items()}
                        for f in FORMATS}

    item14 = checks.check_item14(fixed[MAIN_FORMAT], faulty[MAIN_FORMAT])
    claimed = {"permissive": headline,
               "strict": {n: item14["counts"][n]["lower"] for n in SYSTEM_NAMES}}
    sample = checks.audit_sample(faulty[MAIN_FORMAT])
    results = {
        "version": __version__,
        "config": {"seed": SEED, "items": N_ITEMS, "runs": N_RUNS,
                   "depths": list(DEPTHS), "formats": list(FORMATS),
                   "main_format": MAIN_FORMAT, "systems": list(SYSTEM_NAMES),
                   "items_hit_by_prompt_bug": sum(i.bug_hit for i in ITEMS),
                   "rerun_budget": RERUN_BUDGET},
        "truth": truth, "headline": headline, "run_scores": run_scores,
        "stages": stages, "agreement": agree, "depth_profile": depth,
        "rank_tau_faulty_vs_truth": checks.kendall_tau(truth, headline,
                                                       SYSTEM_NAMES),
        "format_scores_faulty": faulty_scores,
        "format_scores_corrected": corrected_scores,
        "format_run_scores_faulty": faulty_cells,
        "format_run_scores_corrected": corrected_cells,
        "checks": {
            "item5": checks.check_item5(faulty[MAIN_FORMAT], fixed[MAIN_FORMAT]),
            "item4": checks.check_item4(sample, claimed),
            "item6": checks.check_item6(faulty[MAIN_FORMAT], headline),
            "item1_faulty": checks.check_item1(faulty_cells, MAIN_FORMAT,
                                               "faulty pipeline"),
            "item1_corrected": checks.check_item1(corrected_cells,
                                                  MAIN_FORMAT,
                                                  "corrected pipeline"),
            "item14": item14,
            "item10": checks.check_item10(null_echo_log(MAIN_FORMAT)),
            "item15": checks.check_item15(run_scores),
        },
    }
    return results, faulty[MAIN_FORMAT], sample


# ----------------------------------------------------------------- report

def report(res):
    L = []
    add = L.append
    cfg = res["config"]
    c = res["checks"]
    add("Worked example: error propagation through an evaluation pipeline")
    add(f"Seed {cfg['seed']}; {cfg['items']} items (chain depth 3 to 7); "
        f"{cfg['runs']} runs; systems {', '.join(cfg['systems'])}; "
        f"main format '{cfg['main_format']}'.")
    add(f"Stage 1 fault hits {cfg['items_hit_by_prompt_bug']} of "
        f"{cfg['items']} items.")
    add("")
    add("1. Headline under the faulty pipeline versus ground truth")
    add(f"{'system':<8}{'truth':>8}{'faulty':>8}{'true rank':>11}{'faulty rank':>13}")
    true_rank = checks.ranking(res["truth"])
    faulty_rank = checks.ranking(res["headline"])
    for n in SYSTEM_NAMES:
        add(f"{n:<8}{res['truth'][n]:>8.3f}{res['headline'][n]:>8.3f}"
            f"{true_rank.index(n) + 1:>11}{faulty_rank.index(n) + 1:>13}")
    add(f"Kendall tau, faulty ranking against true ranking: "
        f"{res['rank_tau_faulty_vs_truth']:+.3f}")
    add("")
    add("2. Propagation, stage by stage (accuracy, main format)")
    add(f"{'system':<8}" + "".join(f"{lab:>14}" for _, lab in STAGES))
    for n in SYSTEM_NAMES:
        add(f"{n:<8}" + "".join(f"{res['stages'][n][k]:>14.3f}" for k, _ in STAGES))
    add("")
    add("3. Agreement rises while accuracy falls (faulty pipeline)")
    add(f"{'system':<8}{'agreement truth':>17}{'agreement faulty':>18}"
        f"{'accuracy truth':>16}{'accuracy faulty':>17}")
    for n in SYSTEM_NAMES:
        a = res["agreement"][n]
        s = res["stages"][n]
        add(f"{n:<8}{a['truth']:>17.3f}{a['faulty']:>18.3f}"
            f"{s['truth']:>16.3f}{s['s3_fallback']:>17.3f}")
    add("Alpha by chain depth (faulty: buggy builder, permissive extractor, all runs):")
    add(f"{'depth':>6}{'acc faulty':>12}{'agr permissive':>16}{'agr strict':>12}"
        f"{'acc truth':>11}{'agr truth':>11}")
    for row in res["depth_profile"]:
        if row["system"] == "Alpha":
            add(f"{row['depth']:>6}{row['faulty_accuracy']:>12.3f}"
                f"{row['faulty_agreement_permissive']:>16.3f}"
                f"{row['faulty_agreement_strict']:>12.3f}"
                f"{row['true_accuracy']:>11.3f}{row['true_agreement']:>11.3f}")
    add("")
    add("4. Checks from Table 2 (thresholds set in advance)")
    i5 = c["item5"]
    for key, label in (("faulty", "faulty pipeline (buggy builder)"),
                       ("corrected", "corrected pipeline (fixed builder)")):
        v5 = i5[key]
        add(f"[{v5['verdict']}] Item 5, truncated and unparseable outputs, "
            f"{label}: largest unparseable share {v5['value']:.3f} "
            f"({v5['worst_system']}); threshold {i5['threshold']}; counts "
            f"in report: {'yes' if v5['counts_reported'] else 'no'}")
        for n, v in v5["per_system"].items():
            add(f"       {n:<6} logged {v['logged']}, truncated {v['truncated']}, "
                f"unparseable {v['unparseable']} ({v['unparseable_share']:.3f}), "
                f"scored by fallback {v['scored_by_fallback']} "
                f"({v['fallback_share']:.3f})")
    i4 = c["item4"]
    for ex in ("permissive", "strict"):
        e = i4["extractors"][ex]
        add(f"[{e['verdict']}] Item 4, extractor audit ({ex}), "
            f"{checks.AUDIT_PER_SYSTEM} per system: smallest Wilson lower "
            f"bound {e['min_wilson_low']:.3f} ({e['worst_system']}); error "
            f"gap {e['error_gap']:.3f}, limit {e['error_gap_limit']:.3f} "
            f"(half the smallest claimed gap {e['smallest_claimed_gap']:.3f})")
        for n, v in e["per_system"].items():
            add(f"       {n:<6} {v['correct']}/{v['n']} = {v['accuracy']:.3f}, "
                f"Wilson 95% [{v['wilson_low']:.3f}, {v['wilson_high']:.3f}], "
                f"error rate {v['error_rate']:.3f}")
        add(f"       pooled {e['correct']}/{e['n']} = {e['accuracy']:.3f}, "
            f"Wilson 95% [{e['wilson_low']:.3f}, {e['wilson_high']:.3f}]")
    add(f"       threshold: {i4['threshold']}")
    add("       claimed gaps: permissive from the faulty headlines, strict "
        "from the corrected lower scores")
    for t, k in i4["extractors"]["permissive"]["error_types"].items():
        add(f"       permissive error: {t}: {k}")
    i6 = c["item6"]
    add(f"[{i6['verdict']}] Item 6, rescoring with an independent strict "
        f"extractor: largest distance {i6['value']:.3f} "
        f"({i6['worst_system']}); threshold {i6['threshold']}")
    for n, v in i6["per_system"].items():
        add(f"       {n:<6} headline {v['headline']:.3f}, rescored "
            f"[{v['rescored_lower']:.3f}, {v['rescored_upper']:.3f}] "
            f"(width {v['rescored_width']:.3f}), distance "
            f"{v['distance']:.3f} {v['verdict']}")
    for key in ("item1_faulty", "item1_corrected"):
        i1 = c[key]
        g = i1["g_study"]
        add(f"[{i1['verdict']}] Item 1, {i1['name'].split('(')[1][:-1]}: "
            f"E rho^2 {i1['value']:.3f} for the reported design (n_c = "
            f"{g['n_c']} format, R = {g['R']} runs); threshold {i1['threshold']}")
        add(f"       variance components (systems by "
            f"{g['g_study_conditions']} formats, {g['g_study_reruns']} runs "
            f"as reruns): system {g['var_m']:.6f}, system x format "
            f"{g['var_mc']:.6f}, rerun {g['var_e']:.6f}")
        add(f"       secondary: E rho^2 {g['rho2_all_conditions']:.3f} for a "
            f"score averaged over all {g['g_study_conditions']} formats "
            f"(n_c = {g['g_study_conditions']})")
        add(f"       secondary: smallest Kendall tau {i1['min_tau']:+.3f} "
            "(three systems: tau takes only +-1/3 and +-1)")
        for f in FORMATS:
            add(f"       {f:<9} ranking {' > '.join(i1['rankings'][f])}, "
                f"tau {i1['taus'][f]:+.3f}")
    i14 = c["item14"]
    add(f"[{i14['verdict_faulty_report']}] Item 14, undecided outcomes, faulty "
        f"report: {i14['faulty_report']}; lost share "
        + ", ".join(f"{n} {v:.3f}" for n, v in i14["faulty_lost_share"].items()))
    add(f"[{i14['verdict_corrected_report']}] Item 14, corrected report "
        f"(fixed builder, strict extractor, grader errors rerun at most "
        f"{times(i14['rerun_budget'])}, undecided kept); bounds over runs:")
    add(f"       {'system':<7}{'runs':>6}{'P':>5}{'F':>5}{'U':>5}{'E':>4}"
        f"{'lower':>8}{'upper':>8}{'truth':>8}")
    for n in SYSTEM_NAMES:
        v = i14["counts"][n]
        add(f"       {n:<7}{v['N']:>6}{v['P']:>5}{v['F']:>5}{v['U']:>5}{v['E']:>4}"
            f"{v['lower']:>8.3f}{v['upper']:>8.3f}{res['truth'][n]:>8.3f}")
    for a, b, text in i14["dominance"]:
        add(f"       {a} vs {b}, on these runs: {text}")
    bs = i14["bootstrap"]
    add(f"       paired bootstrap over items ({bs['reps']} resamples of "
        f"{cfg['items']} items, all runs of an item together, fixed seed), "
        f"{bs['level']:.0%} interval:")
    for p in bs["pairs"]:
        add(f"       {p['margin']:<28} observed {p['observed']:+.3f}, "
            f"interval [{p['low']:+.3f}, {p['high']:+.3f}], "
            f"{'resolved' if p['resolved'] else 'not resolved'}")
    i15 = c["item15"]
    add(f"[{i15['verdict']}] Item 15, selection: faulty report gives the best "
        f"of {N_RUNS} runs only; largest best minus mean {i15['value']:.3f}; "
        f"threshold {i15['threshold']}")
    i10 = c["item10"]
    add(f"[{i10['verdict']}] Item 10, null control (echo agent), permissive: "
        f"score {i10['value']:.3f}; threshold {i10['threshold']}")
    add(f"[{i10['verdict_strict']}] Item 10, null control (echo agent), strict: "
        f"score {i10['value_strict']:.3f}; threshold {i10['threshold']}")
    return "\n".join(L) + "\n"


# ----------------------------------------------------------- chapter table

def minus(x):
    """Three decimals with a Unicode minus sign, as in the README."""
    return f"{x:.3f}".replace("-", "\u2212")


def times(n):
    return {1: "once", 2: "twice"}.get(n, f"{n} times")


def _pair(primary, secondary):
    return primary if secondary is None else f"{primary} ({secondary})"


def chapter_table(res):
    """Table 3 of the chapter: short cells, rows in the order of the text.
    Values and verdicts in parentheses are for the corrected pipeline or the
    strict extractor."""
    c = res["checks"]
    s = res["stages"]
    i5, i4, i6 = c["item5"], c["item4"], c["item6"]
    i1, i1c, i14, i10 = c["item1_faulty"], c["item1_corrected"], c["item14"], c["item10"]
    i15 = c["item15"]
    perm, strict = i4["extractors"]["permissive"], i4["extractors"]["strict"]
    lost = i14["faulty_lost_share"]
    others = max(v for n, v in lost.items() if n != "Gamma")
    rise = [i15["per_system"][n]["best_minus_mean"] for n in SYSTEM_NAMES]
    ba = next(p for p in i14["bootstrap"]["pairs"] if p["pair"] == ["Alpha", "Beta"])
    rows = [
        ("Prompt loses question (1)",
         f"Alpha {s['Alpha']['truth']:.3f} to {s['Alpha']['s1_prompt_bug']:.3f}",
         "Unparseable outputs (5)",
         f"Largest share {i5['value']:.3f} ({i5['value_corrected']:.3f})",
         f"At most {checks.MAX_UNPARSEABLE_SHARE}",
         _pair(i5["verdict"], i5["verdict_corrected"])),
        ("Last number fallback (3)",
         f"Beta {s['Beta']['s1_prompt_bug']:.3f} to {s['Beta']['s3_fallback']:.3f}",
         "Extractor audit (4)",
         f"Lowest bound {perm['min_wilson_low']:.3f} ({strict['min_wilson_low']:.3f}); "
         f"error gap {perm['error_gap']:.3f} ({strict['error_gap']:.3f})",
         f"At least {checks.AUDIT_MIN_LOWER_BOUND}; gap under half the smallest gap",
         _pair(perm["verdict"], strict["verdict"])),
        ("Same fault, four formats (3)",
         "Ranking varies by format",
         "Format invariance (1)",
         f"E\u03c1\u00b2 {i1['value']:.3f} ({i1c['value']:.3f}), one format",
         f"At least {checks.MIN_G_COEFFICIENT}",
         _pair(i1["verdict"], i1c["verdict"])),
        ("Same fault, echo agent (3)",
         f"Echo agent scores {i10['value']:.3f}",
         "Null agent (10)",
         f"Score {i10['value']:.3f} ({i10['value_strict']:.3f})",
         f"At most floor {checks.NULL_FLOOR:g} plus {checks.NULL_MARGIN}",
         _pair(i10["verdict"], i10["verdict_strict"])),
        ("Final event lost, runs dropped (6, 7)",
         f"Gamma {s['Gamma']['s3_fallback']:.3f} to {s['Gamma']['s67_drop_undecided']:.3f}",
         "Undecided outcomes (14)",
         f"U not reported; lost share Gamma {lost['Gamma']:.3f}, others {others:.2f}",
         "P, F, U, E and bounds reported",
         _pair(i14["verdict_faulty_report"], i14["verdict_corrected_report"])),
        (f"Best of {res['config']['runs']} runs (7)",
         f"Rise {min(rise):.3f} to {max(rise):.3f}",
         "Selection (15)",
         f"Best minus mean {i15['value']:.3f}",
         "Every run reported",
         i15["verdict"]),
        ("All faults (1 to 7)",
         f"Beta {res['headline']['Beta']:.3f}, true {res['truth']['Beta']:.3f}",
         "Rescoring, strict extractor (6)",
         f"Largest distance {i6['value']:.3f} ({i6['worst_system']})",
         f"At most {checks.RESCORING_TOLERANCE}",
         i6["verdict"]),
    ]
    head = ("| Fault (stage) | Effect on headline | Check (item) | "
            "Statistic | Threshold | Verdict |")
    lines = [head, "| --- | --- | --- | --- | --- | --- |"]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    cfg = res["config"]
    truth_order = " > ".join(checks.ranking(res["truth"]))
    faulty_order = " > ".join(checks.ranking(res["headline"]))
    n_runs_system = cfg["items"] * cfg["runs"]
    caption = (
        f"Table 3. Worked example with three simulated systems, "
        f"{cfg['items']} items and {cfg['runs']} runs per item. The true "
        f"ranking is {truth_order}; the faulty pipeline reports "
        f"{faulty_order}. Each row gives an injected fault and its stage, its "
        "effect on the headline, the check of Table 2 that tests it, the "
        "statistic, the threshold and the verdict on the faulty pipeline; "
        "values and verdicts in parentheses are for the corrected pipeline "
        "or the strict extractor. All thresholds were fixed before the run. "
        f"The audit labels {checks.AUDIT_PER_SYSTEM} outputs per system. "
        f"Bounds are over runs ({n_runs_system:,} per system), with grader "
        f"errors rerun at most {times(cfg['rerun_budget'])}. In the corrected "
        f"report Beta's lower bound exceeds Alpha's upper bound by "
        f"{ba['observed']:.3f}, but the paired bootstrap 95% interval over "
        f"items for this margin, [{minus(ba['low'])}, {minus(ba['high'])}], "
        "includes zero, so the order holds for these runs only.")
    return "\n".join(lines) + "\n\n" + caption + "\n"


# ------------------------------------------------------------------ files

def write_results(res, faulty_log, sample, out):
    os.makedirs(out, exist_ok=True)
    write_csv(os.path.join(out, "stage_effects.csv"),
              ["system"] + [k for k, _ in STAGES],
              [[n] + [res["stages"][n][k] for k, _ in STAGES] for n in SYSTEM_NAMES])
    keys = ["faulty_accuracy", "faulty_agreement_permissive",
            "faulty_agreement_strict", "true_accuracy", "true_agreement"]
    write_csv(os.path.join(out, "depth_profile.csv"), ["system", "depth"] + keys,
              [[r["system"], r["depth"]] + [r[k] for k in keys]
               for r in res["depth_profile"]])
    write_csv(os.path.join(out, "format_scores.csv"),
              ["format", "system", "faulty_headline", "faulty_run_mean",
               "corrected_lower"],
              [[f, n, res["format_scores_faulty"][f][n],
                sum(res["format_run_scores_faulty"][f][n]) / N_RUNS,
                res["format_scores_corrected"][f][n]]
               for f in FORMATS for n in SYSTEM_NAMES])
    counts = res["checks"]["item14"]["counts"]
    write_csv(os.path.join(out, "corrected_outcomes.csv"),
              ["system", "runs", "P", "F", "U", "E", "lower", "upper", "truth"],
              [[n, counts[n]["N"], counts[n]["P"], counts[n]["F"], counts[n]["U"], counts[n]["E"],
                counts[n]["lower"], counts[n]["upper"], res["truth"][n]]
               for n in SYSTEM_NAMES])
    write_csv(os.path.join(out, "faulty_log_plain.csv"),
              ["system", "item_id", "run", "depth", "kind", "reference",
               "finish_reason", "trace_has_answer", "grader_error", "reply"],
              [[r["system"], r["item_id"], r["run"], r["depth"], r["kind"],
                r["reference"], r["finish_reason"], r["trace_has_answer"],
                r["grader_error"], r["reply"]] for r in faulty_log])
    write_csv(os.path.join(out, "audit_sample.csv"),
              ["system", "item_id", "run", "reply", "hand_label",
               "permissive", "strict"],
              [[r["system"], r["item_id"], r["run"], r["reply"],
                "" if r["label"] is None else r["label"],
                "" if permissive_value(r) is None else permissive_value(r),
                "" if strict_value(r) is None else strict_value(r)]
               for r in sample])
    with open(os.path.join(out, "checks.json"), "w", encoding="utf-8") as fh:
        json.dump(rounded(res["checks"]), fh, indent=2, sort_keys=True)
        fh.write("\n")
    summary = {k: res[k] for k in ("version", "config", "truth", "headline",
                                   "run_scores", "stages", "agreement",
                                   "rank_tau_faulty_vs_truth",
                                   "format_scores_faulty",
                                   "format_scores_corrected",
                                   "format_run_scores_faulty",
                                   "format_run_scores_corrected")}
    with open(os.path.join(out, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(rounded(summary), fh, indent=2, sort_keys=True)
        fh.write("\n")
    with open(os.path.join(out, "chapter_table.md"), "w", encoding="utf-8") as fh:
        fh.write(chapter_table(res))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="results",
                        help="folder for tables and the figure (default: results)")
    parser.add_argument("--no-figure", action="store_true",
                        help="skip the matplotlib figure")
    args = parser.parse_args(argv)
    res, faulty_log, sample = compute()
    text = report(res)
    print(text, end="")
    write_results(res, faulty_log, sample, args.out)
    with open(os.path.join(args.out, "run_output.txt"), "w", encoding="utf-8") as fh:
        fh.write(text)
    if not args.no_figure:
        try:
            from .figure import draw
        except ImportError:
            print("matplotlib not available; figure skipped")
        else:
            draw(res, os.path.join(args.out, "figure_propagation.png"))
    return res


if __name__ == "__main__":
    main()
