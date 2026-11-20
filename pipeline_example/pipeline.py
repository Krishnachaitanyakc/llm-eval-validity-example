"""The evaluation pipeline under test, with its injected faults.

Stage 1  prompt builder: the faulty builder drops the original question from
         later step messages for the items marked bug_hit.
Stage 3  extractor: the permissive extractor reads 'Answer: N' and otherwise
         falls back to the last number in the reply. The strict extractor is
         an independent implementation that accepts only the two declared
         answer markers and never guesses.
Stage 6  instrumentation: the agent variant loses the final answer event of
         some runs, more often for runs that fail.
Stage 7  aggregation: the faulty report drops runs without a final answer
         event, records grader errors as failures and reports the best of
         the five runs.
"""

import re

from .simulation import (ITEMS, N_RUNS, SYSTEMS, model_reply, draws_for,
                         prompt_text)

# ---------------------------------------------------------------- logs


def generate_log(builder, fmt, systems=SYSTEMS):
    """Run every system on every item N_RUNS times and return log records."""
    records = []
    for system in systems:
        for item in ITEMS:
            visible = not (builder == "faulty" and item.bug_hit)
            for run in range(N_RUNS):
                reply, finish, label = model_reply(system, item, run, fmt,
                                                   visible)
                d = draws_for(system, item, run)
                passed = label == item.reference
                lost = d.u_loss < (system.loss_pass if passed
                                   else system.loss_fail)
                records.append({
                    "system": system.name, "format": fmt, "builder": builder,
                    "item_id": item.item_id, "run": run, "depth": item.depth,
                    "kind": item.kind, "reference": item.reference,
                    "reply": "" if lost else reply,
                    "finish_reason": finish,
                    "trace_has_answer": not lost,
                    "grader_error": d.grader_error,
                    "error_persists": d.error_persists,
                    # Simulated hand label: available to the audit only.
                    "label": label,
                })
    return records


def null_echo_log(fmt):
    """A null control that has no capability: it echoes the prompt."""
    records = []
    for item in ITEMS:
        for run in range(N_RUNS):
            records.append({
                "system": "Null echo", "format": fmt, "builder": "fixed",
                "item_id": item.item_id, "run": run, "depth": item.depth,
                "kind": item.kind, "reference": item.reference,
                "reply": prompt_text(item, fmt), "finish_reason": "stop",
                "trace_has_answer": True, "grader_error": False,
                "error_persists": False, "label": None,
            })
    return records


# ----------------------------------------------------------- extractors

_ANSWER = re.compile(r"Answer:\s*(-?\d+)")
_NUMBER = re.compile(r"-?\d+")


def permissive_extract(text):
    """Return (answer or None, used_fallback). This is the faulty stage 3."""
    m = _ANSWER.search(text)
    if m:
        return int(m.group(1)), False
    numbers = _NUMBER.findall(text)
    if numbers:
        return int(numbers[-1]), True
    return None, False


def strict_extract(text):
    """Independent extractor: declared markers only, no fallback."""
    found = None
    for marker in ("Answer:", "The answer is"):
        start = text.rfind(marker)
        if start < 0:
            continue
        rest = text[start + len(marker):].lstrip()
        digits = ""
        for ch in rest:
            if ch.isdigit() or (ch == "-" and not digits):
                digits += ch
            else:
                break
        if digits.strip("-"):
            if found is None or start > found[0]:
                found = (start, int(digits))
    return None if found is None else found[1]


def oracle_extract(record):
    """The answer a careful human labeler records (simulation only)."""
    return record["label"]


# ---------------------------------------------------------- aggregation


def _mean(values):
    values = list(values)
    return sum(values) / len(values) if values else float("nan")


def by_system(records):
    out = {}
    for r in records:
        out.setdefault(r["system"], []).append(r)
    return out


def accuracy_all(records, extract):
    """Mean correctness over every item run (no dropping)."""
    return _mean(extract(r) == r["reference"] for r in records)


def permissive_value(r):
    return permissive_extract(r["reply"])[0]


def strict_value(r):
    return strict_extract(r["reply"])


def faulty_headline(records):
    """Stage 7 as implemented: drop undecided runs, grader errors count as
    failures, report the best single run. Returns (headline, run scores)."""
    runs = []
    for run in range(N_RUNS):
        kept = [r for r in records if r["run"] == run and r["trace_has_answer"]]
        runs.append(_mean((not r["grader_error"])
                          and permissive_value(r) == r["reference"]
                          for r in kept))
    return max(runs), runs


def dropped_mean(records):
    """Faulty aggregation without the best run step (mean over runs)."""
    kept = [r for r in records if r["trace_has_answer"]]
    return _mean((not r["grader_error"]) and permissive_value(r) == r["reference"]
                 for r in kept)


def agreement(records, extract):
    """Share of items whose runs all return the same parsed answer, right or
    wrong. Runs without a final answer event are skipped; an item needs at
    least two answered runs to count as agreeing."""
    items = {}
    for r in records:
        items.setdefault(r["item_id"], []).append(r)
    agree = 0
    for rs in items.values():
        answers = [extract(r) for r in rs if r["trace_has_answer"]]
        if len(answers) >= 2 and None not in answers and len(set(answers)) == 1:
            agree += 1
    return agree / len(items)


def outcome_counts(records):
    """Pass, fail, undecided and error counts under the corrected rules:
    strict extraction, grader errors rerun once, persistent errors and lost
    final events counted as undecided."""
    p = f = u = e = 0
    for r in records:
        if r["grader_error"]:
            e += 1
        if not r["trace_has_answer"] or r["error_persists"]:
            u += 1
        elif strict_value(r) == r["reference"]:
            p += 1
        else:
            f += 1
    n = p + f + u
    return {"P": p, "F": f, "U": u, "E": e, "N": n,
            "lower": p / n, "upper": (p + u) / n}
