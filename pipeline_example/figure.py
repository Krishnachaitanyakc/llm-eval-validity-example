"""Figure: how the headline moves stage by stage, and agreement versus accuracy.

Printed width 117 mm at 600 dpi; grayscale friendly (markers and line styles
carry the series, not colour).
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from .simulation import SYSTEM_NAMES  # noqa: E402

WIDTH_MM = 117
DPI = 600
STYLE = {"Alpha": ("o", "-", "0.0"), "Beta": ("s", "--", "0.35"),
         "Gamma": ("^", ":", "0.55")}
STAGE_KEYS = ("truth", "s1_prompt_bug", "s3_fallback", "s67_drop_undecided",
              "s7_best_run")
STAGE_LABELS = ("Ground\ntruth", "+ prompt\nbug (1)", "+ fallback\n(3)",
                "+ drop\nundecided\n(6, 7)", "+ best\nrun (7)", "Corrected\nbounds,\ntruth")


def draw(res, path):
    plt.rcParams.update({"font.size": 7, "font.family": "DejaVu Sans",
                         "axes.linewidth": 0.6, "svg.hashsalt": "fixed"})
    width_in = WIDTH_MM / 25.4
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(width_in, width_in * 0.62),
                                   gridspec_kw={"height_ratios": [1.15, 1]})
    xs = list(range(len(STAGE_KEYS)))
    counts = res["checks"]["item14"]["counts"]
    for k, name in enumerate(SYSTEM_NAMES):
        marker, ls, color = STYLE[name]
        ys = [res["stages"][name][s] for s in STAGE_KEYS]
        ax1.plot(xs, ys, marker=marker, ls=ls, color=color, lw=1.0, ms=4,
                 label=name)
        xb = len(STAGE_KEYS) + (k - 1) * 0.28 - 0.04
        lo, hi = counts[name]["lower"], counts[name]["upper"]
        ax1.plot([xb, xb], [lo, hi], color=color, lw=1.4, solid_capstyle="butt")
        for y in (lo, hi):
            ax1.plot([xb - 0.06, xb + 0.06], [y, y], color=color, lw=1.0)
        ax1.plot([xb + 0.1], [res["truth"][name]], marker=marker, color=color,
                 ms=3, mfc="white", mew=0.7, ls="none")
    ax1.axvline(len(STAGE_KEYS) - 0.5, color="0.7", lw=0.6)
    ax1.set_xticks(list(range(len(STAGE_LABELS))))
    ax1.set_xticklabels(STAGE_LABELS)
    ax1.set_ylabel("Accuracy")
    ax1.set_ylim(0.15, 0.8)
    ax1.set_title("(a) Headline accuracy as faults accumulate", loc="left",
                  fontsize=7.5)
    ax1.legend(frameon=False, ncol=3, loc="upper center")
    ax1.grid(axis="y", color="0.9", lw=0.5)

    rows = [r for r in res["depth_profile"] if r["system"] == "Alpha"]
    depths = [r["depth"] for r in rows]
    series = (("faulty_accuracy", "Accuracy, faulty", "o", "-", "0.0"),
              ("faulty_agreement_permissive", "Agreement, permissive extractor",
               "s", "--", "0.0"),
              ("faulty_agreement_strict", "Agreement, strict extractor",
               "s", ":", "0.5"),
              ("true_accuracy", "Accuracy, ground truth", "o", "-", "0.6"))
    for key, label, marker, ls, color in series:
        mfc = "white" if "strict" in key or "true" in key else color
        ax2.plot(depths, [r[key] for r in rows], marker=marker, ls=ls,
                 color=color, lw=1.0, ms=4, mfc=mfc, mew=0.8, label=label)
    ax2.set_xticks(depths)
    ax2.set_xlabel("Chain depth (steps)")
    ax2.set_ylabel("Share")
    ax2.set_ylim(0, 1.45)
    ax2.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax2.set_title("(b) System Alpha: agreement rises while accuracy falls",
                  loc="left", fontsize=7.5)
    ax2.legend(frameon=False, fontsize=5.5, loc="upper center", ncol=2, borderaxespad=0.2)
    ax2.grid(axis="y", color="0.9", lw=0.5)
    for ax in (ax1, ax2):
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    fig.tight_layout(pad=0.4, h_pad=0.8)
    fig.savefig(path, dpi=DPI, metadata={"Software": None})
    plt.close(fig)
