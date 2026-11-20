"""Simulated items, systems and model replies.

Nothing here calls a model. Every random draw comes from a generator seeded
with a string built from SEED and the identifiers of the draw, so results do
not depend on the order in which items or systems are processed, and string
seeds are hashed with SHA-512 by the standard library, so they do not depend
on PYTHONHASHSEED either.

The ground truth is the answer each simulated system intends to give under a
correctly built prompt. Whether a run is correct does not depend on the
prompt format, so any change of ranking across formats comes from the
pipeline, not from the systems.
"""

import random
from dataclasses import dataclass

SEED = 2026
N_ITEMS = 240
DEPTHS = (3, 4, 5, 6, 7)
N_RUNS = 5
FORMATS = ("plain", "marker", "brief", "numbered")
MAIN_FORMAT = "plain"
CLOSEST_SHARE = 0.35

# Stage 1 fault: share of items, by chain depth, whose later step messages
# lose the original question. Which items are hit is fixed per item, as it
# would be for a builder that trims history above a length budget.
BUG_RATE = {3: 0.0, 4: 0.05, 5: 0.15, 6: 0.30, 7: 0.45}

# Grader errors (a fault of the evaluation system), the rerun budget of the
# corrected pipeline (one rerun per error) and the share that a rerun resolves.
ERROR_RATE = 0.01
RERUN_BUDGET = 1
RERUN_RESOLVES = 0.8

# Format instructions. None contains a digit, so a reply that echoes the
# prompt ends with the last number of the question.
INSTRUCTIONS = {
    "plain": "Solve the problem step by step and state the final answer.",
    "marker": "Solve the problem step by step. End your reply with 'Answer: <number>'.",
    "brief": "Work out the result and give the final answer.",
    "numbered": "Show each step on its own line, then give the final answer.",
}


def rng_for(*parts):
    """Return a generator seeded by SEED and the given identifiers."""
    return random.Random(":".join(str(p) for p in (SEED,) + parts))


@dataclass(frozen=True)
class Item:
    item_id: int
    depth: int
    kind: str          # "compute" or "closest"
    question: str
    reference: int
    first_step: tuple  # (a, symbol, b, result) of the first operation
    candidates: tuple  # the three options of a "closest" item, else ()
    difficulty: float  # shift of the solve probability, shared by systems
    bug_hit: bool      # the faulty builder drops the question for this item


def _make_item(item_id):
    r = rng_for("item", item_id)
    depth = DEPTHS[item_id % len(DEPTHS)]
    while True:
        value = r.randint(10, 30)
        text = [f"Start with {value}."]
        first = None
        last_operand = None
        for _ in range(depth):
            ops = ["add", "subtract"] + (["multiply"] if value <= 40 else [])
            op = r.choice(ops)
            if op == "subtract" and value < 14:
                op = "add"
            if op == "add":
                b = r.randint(2, 19)
                new, sym, phrase = value + b, "+", f"Add {b}."
            elif op == "subtract":
                b = r.randint(2, min(19, value - 10))
                new, sym, phrase = value - b, "-", f"Subtract {b}."
            else:
                b = r.choice((2, 3))
                new, sym, phrase = value * b, "x", f"Multiply by {b}."
            if first is None:
                first = (value, sym, b, new)
            text.append(phrase)
            last_operand = b
            value = new
        if value != last_operand and value >= 10:
            break
    total = value
    kind = "closest" if r.random() < CLOSEST_SHARE else "compute"
    candidates = ()
    if kind == "closest":
        near = total + r.choice((-3, -2, -1, 1, 2, 3))
        far_low = total - r.randint(15, 40)
        if far_low < 1:
            far_low = total + r.randint(85, 120)
        far_high = total + r.randint(45, 80)
        options = [near, far_low, far_high]
        r.shuffle(options)
        candidates = tuple(options)
        text.append(f"Which of {options[0]}, {options[1]} or {options[2]} "
                    "is closest to the result?")
        reference = near
    else:
        text.append("What is the result?")
        reference = total
    difficulty = r.uniform(-0.2, 0.2)
    bug_hit = r.random() < BUG_RATE[depth]
    return Item(item_id, depth, kind, " ".join(text), reference, first,
                candidates, difficulty, bug_hit)


ITEMS = tuple(_make_item(i) for i in range(N_ITEMS))


@dataclass(frozen=True)
class System:
    name: str
    skill: float        # solve probability at depth 3 for an average item
    marker_rate: dict   # by format: share of replies using "Answer: N"
    trunc_rate: float   # replies cut off by the token limit (model failure)
    loss_pass: float    # share of passing runs whose final event is lost
    loss_fail: float    # share of failing runs whose final event is lost


SYSTEMS = (
    System("Alpha", 0.79,
           {"plain": 0.97, "marker": 0.99, "brief": 0.96, "numbered": 0.98},
           0.01, 0.03, 0.03),
    System("Beta", 0.84,
           {"plain": 0.40, "marker": 0.93, "brief": 0.62, "numbered": 0.80},
           0.03, 0.03, 0.03),
    System("Gamma", 0.72,
           {"plain": 0.95, "marker": 0.98, "brief": 0.94, "numbered": 0.96},
           0.02, 0.03, 0.40),
)
SYSTEM_NAMES = tuple(s.name for s in SYSTEMS)


@dataclass(frozen=True)
class RunDraws:
    """Random draws for one system, item and run, shared by every pipeline."""
    solves: bool
    wrong_answer: int
    truncated: bool
    u_loss: float
    grader_error: bool
    error_persists: bool


def draws_for(system, item, run):
    r = rng_for("run", system.name, item.item_id, run)
    p = system.skill - 0.07 * (item.depth - 3) + item.difficulty
    p = min(0.97, max(0.03, p))
    solves = r.random() < p
    if item.kind == "closest" and r.random() < 0.6:
        wrong = r.choice([c for c in item.candidates if c != item.reference])
    else:
        offset = r.choice([d for d in range(-12, 13) if d != 0])
        wrong = item.reference + offset
        if wrong < 1:
            wrong = item.reference + abs(offset)
    truncated = r.random() < system.trunc_rate
    u_loss = r.random()
    grader_error = r.random() < ERROR_RATE
    error_persists = grader_error and r.random() >= RERUN_RESOLVES
    return RunDraws(solves, wrong, truncated, u_loss, grader_error,
                    error_persists)


def uses_marker(system, item, run, fmt):
    """Whether this reply ends with 'Answer: N' (else 'The answer is N, ...')."""
    r = rng_for("style", system.name, item.item_id, run, fmt)
    return r.random() < system.marker_rate[fmt]


def prompt_text(item, fmt):
    return f"{INSTRUCTIONS[fmt]} {item.question}"


def model_reply(system, item, run, fmt, question_visible):
    """Return (reply text, finish reason, intended answer or None).

    The intended answer is what a careful human labeler would record as the
    answer stated in the reply; it is None for non answers and cut off replies.
    """
    d = draws_for(system, item, run)
    a, sym, b, v1 = item.first_step
    working = f"First, {a} {sym} {b} = {v1}."
    if not question_visible:
        text = ("The original question is missing from this message, so I "
                f"cannot finish step {item.depth} of {item.depth}.")
        return text, "stop", None
    if d.truncated:
        return f"{working} Next, we", "length", None
    answer = item.reference if d.solves else d.wrong_answer
    if uses_marker(system, item, run, fmt):
        text = f"{working} Answer: {answer}"
    else:
        text = f"{working} The answer is {answer}, reached in {item.depth} steps."
    return text, "stop", answer
