# Worked example: how evaluation errors propagate and how the checks detect them

Version 1.0.1. Supplementary material for the chapter "Validity and
Reliability of Large Language Model and Agent Evaluation". The example
simulates a small evaluation end to end, injects faults at several pipeline
stages, shows how they change the headline numbers and the ranking of
systems, and runs seven checks from Table 2 of the chapter (items 1, 4, 5, 6,
10, 14 and 15), each with a pass criterion fixed before the run. The compact
results table is Table 3 of the chapter.

No model is called. The computation uses the Python standard library only
(matplotlib is optional and draws the figure). All random draws come from
generators seeded with fixed strings, so every run prints the same numbers
and writes byte identical result files. A full run takes about one second.

## Run it

From this folder (the one that holds this README):

```
python3 -m pipeline_example.run_example
```

This prints the report below and writes every table, the chapter table and
the figure to `results/`. Use `--out DIR` to write elsewhere and
`--no-figure` to skip the figure. To confirm that the printed numbers and
every result file are reproduced exactly:

```
python3 -m unittest discover -s tests -v
```

Tested with Python 3.12 and matplotlib 3.11. Any Python 3.8 or later should
give the same tables; the figure may differ in pixels across matplotlib
versions, so the test does not compare it.

To cite the example, use `CITATION.cff`. The version is in `VERSION` and in
`pipeline_example.__version__`.

## Design

**Items.** 240 arithmetic chains of depth 3 to 7 ("Start with 14. Add 9.
Multiply by 2. ..."). About a third end with a question of the form "Which of
40, 23 or 61 is closest to the result?". Every reference answer is larger than
7, the largest step count, so a step count is never a correct answer.

**Systems.** Three simulated systems, each run five times on every item.
Whether a run is correct is drawn from a probability that falls with chain
depth, and it does not depend on the prompt format. The intended answer of
every reply is known, which gives the ground truth and the simulated hand
labels for the audit. The systems differ in three ways.

| System | True accuracy | Answer style | Final event lost |
| --- | --- | --- | --- |
| Alpha | 0.636 | almost always "Answer: N" | 3 percent of runs |
| Beta | 0.675 | in the main format, mostly "The answer is N, reached in k steps." | 3 percent of runs |
| Gamma | 0.557 | almost always "Answer: N" | 3 percent of passing runs, 40 percent of failing runs |

Both answer styles are declared answer markers. Beta's style depends on the
prompt format: it uses "Answer: N" in 40 percent of replies under the main
format ("plain") and in 93 percent under the "marker" format.

**Injected faults.**

1. Stage 1, prompt builder. For 49 of the 240 items, chosen per item and more
   often for deeper chains, later step messages lose the original question.
   The model then replies "The original question is missing from this
   message, so I cannot finish step 7 of 7." This is a defect of the
   evaluation, not of the model.
2. Stage 3, extractor. The permissive extractor reads "Answer: N" and
   otherwise falls back to the last number in the reply. It turns the non
   answers of fault 1 into the step count, the same wrong number in every
   run, and it reads Beta's step count instead of Beta's answer.
3. Stages 6 and 7, instrumentation and aggregation. The agent variant loses
   the final answer event of some runs, much more often when Gamma fails. The
   aggregation drops these runs instead of counting them as undecided, and
   records grader errors as failures.
4. Stage 7, aggregation. The report gives the best of the five runs.

**Corrected pipeline.** Once the checks fire, the builder is fixed and the
items rerun, the strict extractor (an independent implementation that accepts
only the two declared markers and never guesses) scores every reply, grader
errors are rerun once (a rerun budget of one per error), and runs with a lost
final event or an error that persists after the rerun are counted as
undecided, following Section 4.5 of the chapter. The scored unit is the run:
each system has 240 items times 5 runs, so its P, F, U and E counts and its
lower and upper scores are over 1,200 runs.

## Design choices that are built in

The example demonstrates mechanisms, not prevalence. Its settings were
chosen to make each mechanism visible, and several results follow from those
settings rather than from anything measured.

* **Gamma's differential trace loss is an assumption.** Gamma loses the final
  event in 40 percent of failing runs against 3 percent of passing runs. No
  measured rate supports this; the chapter says none exists. The largest
  single distortion, Gamma rising from 0.427 to 0.549 when undecided runs are
  dropped, comes from this assumption.
* **Beta's format dependent answer style creates the format effect.** Beta
  writes "Answer: N" in 40 percent of replies under the main format and in 93
  percent under the marker format. This is what makes the ranking change
  across formats under the permissive extractor, what makes item 1 fail and
  what moves its Kendall tau.
* **The non answer prints the step count.** A reply hit by the stage 1 fault
  always ends with "step k of k", so the fallback extractor reads the same
  wrong number in every run and agreement rises by construction. The setting
  is anchored to the author's earlier study, in which most fallback
  extractions of such replies returned the step count.
* **The strict extractor and the hand labels are exact by construction.** The
  strict extractor accepts exactly the two answer styles the simulator
  writes, and the simulated hand labels are the simulator's intended answers.
  The perfect strict audit (40 of 40 for every system) and the identical
  corrected scores across formats (no system by format variance) are
  therefore true by design.
* **Item 5 sees the stage 1 fault only because the model reports it.** The
  simulated model says that the question is missing, so the reply has no
  declared answer. A silent prompt fault would pass item 5; item 2 is the
  proper check for stage 1.
* **Items 14 and 15 fail on the faulty report by definition.** The faulty
  report is defined to omit what these items require (the undecided count and
  every run), and the code records this with flags
  (`faulty_report_has_undecided=False`, `every_run_reported=False`). The same
  holds for the "counts reported" part of item 5. These verdicts are
  compliance checks on the report, not detections from the data.

## What the example shows

* **Ranking reversal.** The true ranking is Beta > Alpha > Gamma. The faulty
  pipeline reports Gamma (0.579) > Alpha (0.523) > Beta (0.263); Kendall tau
  between the two rankings is minus 1. Gamma's faulty headline is higher than
  its true accuracy (0.557).
* **Propagation.** Section 2 of the report follows each system through the
  faults in order. The prompt bug lowers every system (Alpha from 0.636 to
  0.512); the fallback rule lowers Beta from 0.553 to 0.222; dropping
  undecided runs raises Gamma from 0.427 to 0.549; the best run adds 0.03 to
  0.04 to every system.
* **Agreement rises while accuracy falls.** For Alpha, from depth 5 to depth 7
  accuracy under the faulty pipeline (buggy builder and permissive extractor
  together) falls from 0.512 to 0.217 while the share of items on which all
  five runs agree rises from 0.229 to 0.479. With the strict extractor,
  agreement falls to 0.021, as it does in the ground truth. Over all items,
  Alpha's agreement rises from 0.179 to 0.346 as its accuracy falls from
  0.636 to 0.486.
* **The ranking does not generalize across formats.** For a headline
  reported under one format, the generalizability coefficient of item 1 is
  0.561 on the faulty pipeline and 0.955 on the corrected one. The system by
  format component is large on the faulty pipeline (0.0048 against 0.0063
  for systems). A score averaged over all four formats would reach 0.837,
  above the threshold, so the coefficient must be computed for the design
  under which the headline is reported.

## Checks and thresholds

All thresholds are constants at the top of `pipeline_example/checks.py`, set
before the run.

| Table 2 item | Statistic | Threshold set in advance | Faulty pipeline | Corrected or strict |
| --- | --- | --- | --- | --- |
| 5, truncated and unparseable outputs | largest share of logged outputs with no answer under the declared markers, with counts reported | at most 0.05 for every system | FAIL (0.226, Beta) | PASS (0.027, Beta) |
| 4, extractor audit on 40 hand labeled outputs per system | smallest Wilson 95 percent lower bound of accuracy over systems, and the largest difference in error rates between systems | lower bound at least 0.90 for every system, and error gap below half the smallest claimed gap (Proposition 2, inequality (7)) | FAIL (bound 0.181, gap 0.525 against 0.028) | PASS (bound 0.912, gap 0.000 against 0.017) |
| 1, invariance across four formats | generalizability coefficient E rho squared, equation (5), for the reported design (one format, the 5 runs the headline averages), with components from systems by formats and the 5 runs as reruns | at least 0.8 | FAIL (0.561) | PASS (0.955) |
| 10, null agent | score of an agent that echoes the prompt | at most the floor 0 plus a margin of 0.01 | FAIL (0.125) | PASS (0.000) |
| 14, undecided outcomes | faulty: whether U is reported, with the lost share per system; corrected: P, F, U and E counts and bounds per system, with a paired bootstrap interval for each dominance margin | counts and bounds reported; systems ordered only when one lower score exceeds the other upper score | FAIL (U not reported; lost share Gamma 0.229, others 0.03) | PASS |
| 15, selection | best run minus mean of runs | every run reported | FAIL (0.039) | |
| 6, rescoring with an independent strict extractor | largest distance of a headline from the rescored lower and upper scores | at most 0.01 | FAIL (0.274, Beta) | |

**Item 1.** The variance components come from the two way random effects
ANOVA with replication (a = 3 systems, b = 4 formats, R = 5 runs per cell),
by expected mean squares: E[MS_e] = s2_e, E[MS_mc] = s2_e + R s2_mc and
E[MS_m] = s2_e + R s2_mc + b R s2_m. Hence s2_e = MS_e,
s2_mc = (MS_mc − MS_e) / R and s2_m = (MS_m − MS_mc) / (b R), each truncated
at zero when negative, and

E rho squared = s2_m / (s2_m + s2_mc / n_c + s2_e / (n_c R)).

The components are estimated from all four formats, but the coefficient is
computed for the design under which the headline is reported, because the
decision study must match the reporting design: a single headline uses one
format and averages five runs, so n_c = 1 and R = 5. The value for n_c = 4,
which describes a score averaged over the four formats (0.837 faulty, 0.988
corrected), is printed as a secondary line and kept in `checks.json`.

The score of a run is the faulty pipeline's run score (permissive extractor,
undecided runs dropped, grader errors as failures) or the corrected lower
score of that run. Kendall tau of each format's ranking against the main
format is printed as a secondary line. With three systems tau takes only the
values plus or minus 1/3 and plus or minus 1, so a threshold of 0.8 means
that the ranking is unchanged under every format; tau is too coarse to carry
a graded threshold.

**Item 4.** The audit sample is stratified: 40 logged outputs per system,
drawn with a fixed seed, so that every system has its own interval. With 40
outputs, a perfect extractor reaches a Wilson lower bound of 0.912, so the
threshold is attainable. The claimed gaps are those of the scores each
extractor feeds: the faulty headlines for the permissive extractor (smallest
gap 0.056, Gamma against Alpha) and the corrected lower scores for the strict
extractor (smallest gap 0.034, Beta against Alpha). The pooled audit
(73 of 120) hides most of the problem; Beta alone is 12 of 40.

**Item 14.** Under the corrected report, interval dominance orders Beta above
Alpha on these runs (Beta's lower score 0.654 exceeds Alpha's upper score
0.646) and refuses to order Gamma against either system, because Gamma's
bounds [0.542, 0.731] overlap both. The true accuracy of every system lies
within its bounds. The margin of 0.008 is far inside sampling error over 240
items: a paired bootstrap (10,000 resamples of the 240 items with a fixed
seed, all runs of an item for every system moving together) gives a 95
percent interval of [−0.027, 0.042] for lower(Beta) minus upper(Alpha). The
order holds for the recorded runs, but the sampling interval does not
resolve it, so a claim about the population of items would leave Beta and
Alpha unordered.

**Item 6.** This is a rescoring with an independent strict extractor and the
corrected aggregation, not a reconstruction of the same rule; a faithful
reconstruction of the faulty rule would reproduce Beta's 0.263 and pass. It
flags only Beta. Gamma passes because its rescored interval [0.440, 0.671]
is 0.231 wide, so its many undecided runs absorb the error. Alpha passes
because its errors partly cancel: the fallback losses and the best run gain
leave its headline 0.523 inside [0.502, 0.527]. Only the extractor audit and
the counts of item 5 reveal what went wrong for them, which is why the
chapter recommends checks on single stages together with at least one end to
end check.

## Files

| Path | Content |
| --- | --- |
| `pipeline_example/simulation.py` | items, systems and simulated replies |
| `pipeline_example/pipeline.py` | prompt builders, extractors, logging and aggregation |
| `pipeline_example/checks.py` | thresholds, Wilson interval, generalizability coefficient, Kendall tau, paired bootstrap and the checks |
| `pipeline_example/figure.py` | the figure |
| `pipeline_example/run_example.py` | entry point and report |
| `tests/test_reproducible.py` | asserts exact reproduction of the output and result files, and checks equation (5) on hand computed designs |
| `results/run_output.txt` | the printed report |
| `results/stage_effects.csv` | accuracy of each system after each fault |
| `results/depth_profile.csv` | accuracy and agreement by chain depth |
| `results/format_scores.csv` | faulty headline, faulty mean of runs and corrected lower score under each format |
| `results/corrected_outcomes.csv` | runs, P, F, U, E counts and bounds under the corrected pipeline |
| `results/faulty_log_plain.csv` | every logged reply of the faulty pipeline, main format |
| `results/audit_sample.csv` | the 120 audited replies (40 per system) with hand labels and both extractions |
| `results/checks.json` | every check with its statistic, threshold and verdict |
| `results/summary.json` | version, configuration, headline, stage and per run numbers |
| `results/chapter_table.md` | Table 3 of the chapter |
| `results/figure_propagation.png` | figure, 117 mm wide at 600 dpi |
| `VERSION`, `CITATION.cff` | version 1.0.1 and citation metadata |

In `corrected_outcomes.csv` and the report, E counts grader errors that were
rerun; errors that persist after the one rerun are included in U, so
P + F + U is the number of runs.

## Expected output

```
Worked example: error propagation through an evaluation pipeline
Seed 2026; 240 items (chain depth 3 to 7); 5 runs; systems Alpha, Beta, Gamma; main format 'plain'.
Stage 1 fault hits 49 of 240 items.

1. Headline under the faulty pipeline versus ground truth
system     truth  faulty  true rank  faulty rank
Alpha      0.636   0.523          2            2
Beta       0.675   0.263          1            3
Gamma      0.557   0.579          3            1
Kendall tau, faulty ranking against true ranking: -1.000

2. Propagation, stage by stage (accuracy, main format)
system           truth       +S1 bug  +S3 fallback    +S6,7 drop  +S7 best run
Alpha            0.636         0.512         0.486         0.495         0.523
Beta             0.675         0.553         0.222         0.224         0.263
Gamma            0.557         0.452         0.427         0.549         0.579

3. Agreement rises while accuracy falls (faulty pipeline)
system    agreement truth  agreement faulty  accuracy truth  accuracy faulty
Alpha               0.179             0.346           0.636            0.486
Beta                0.225             0.258           0.675            0.222
Gamma               0.233             0.338           0.557            0.427
Alpha by chain depth (faulty: buggy builder, permissive extractor, all runs):
 depth  acc faulty  agr permissive  agr strict  acc truth  agr truth
     3       0.725           0.354       0.375      0.754      0.375
     4       0.621           0.292       0.208      0.729      0.250
     5       0.512           0.229       0.167      0.617      0.167
     6       0.354           0.375       0.021      0.604      0.062
     7       0.217           0.479       0.021      0.475      0.042

4. Checks from Table 2 (thresholds set in advance)
[FAIL] Item 5, truncated and unparseable outputs, faulty pipeline (buggy builder): largest unparseable share 0.226 (Beta); threshold <= 0.05 for every system, counts reported; counts in report: no
       Alpha  logged 1169, truncated 12, unparseable 249 (0.213), scored by fallback 286 (0.245)
       Beta   logged 1166, truncated 23, unparseable 263 (0.226), scored by fallback 800 (0.686)
       Gamma  logged 925, truncated 14, unparseable 159 (0.172), scored by fallback 184 (0.199)
[PASS] Item 5, truncated and unparseable outputs, corrected pipeline (fixed builder): largest unparseable share 0.027 (Beta); threshold <= 0.05 for every system, counts reported; counts in report: yes
       Alpha  logged 1169, truncated 13, unparseable 13 (0.011), scored by fallback 56 (0.048)
       Beta   logged 1166, truncated 31, unparseable 31 (0.027), scored by fallback 713 (0.611)
       Gamma  logged 975, truncated 16, unparseable 16 (0.016), scored by fallback 53 (0.054)
[FAIL] Item 4, extractor audit (permissive), 40 per system: smallest Wilson lower bound 0.181 (Beta); error gap 0.525, limit 0.028 (half the smallest claimed gap 0.056)
       Alpha  33/40 = 0.825, Wilson 95% [0.681, 0.913], error rate 0.175
       Beta   12/40 = 0.300, Wilson 95% [0.181, 0.454], error rate 0.700
       Gamma  28/40 = 0.700, Wilson 95% [0.546, 0.819], error rate 0.300
       pooled 73/120 = 0.608, Wilson 95% [0.519, 0.691]
[PASS] Item 4, extractor audit (strict), 40 per system: smallest Wilson lower bound 0.912 (Alpha); error gap 0.000, limit 0.017 (half the smallest claimed gap 0.034)
       Alpha  40/40 = 1.000, Wilson 95% [0.912, 1.000], error rate 0.000
       Beta   40/40 = 1.000, Wilson 95% [0.912, 1.000], error rate 0.000
       Gamma  40/40 = 1.000, Wilson 95% [0.912, 1.000], error rate 0.000
       pooled 120/120 = 1.000, Wilson 95% [0.969, 1.000]
       threshold: lower bound >= 0.9 for every system, and error gap < 0.5 x smallest claimed gap (Proposition 2, (7))
       claimed gaps: permissive from the faulty headlines, strict from the corrected lower scores
       permissive error: fallback missed the declared marker 'The answer is': 23
       permissive error: fallback read a number from a cut off reply: 1
       permissive error: fallback turned a non answer into a number: 23
[FAIL] Item 6, rescoring with an independent strict extractor: largest distance 0.274 (Beta); threshold <= 0.01
       Alpha  headline 0.523, rescored [0.502, 0.527] (width 0.026), distance 0.000 PASS
       Beta   headline 0.263, rescored [0.537, 0.568] (width 0.031), distance 0.274 FAIL
       Gamma  headline 0.579, rescored [0.440, 0.671] (width 0.231), distance 0.000 PASS
[FAIL] Item 1, faulty pipeline: E rho^2 0.561 for the reported design (n_c = 1 format, R = 5 runs); threshold >= 0.8
       variance components (systems by 4 formats, 5 runs as reruns): system 0.006318, system x format 0.004766, rerun 0.000845
       secondary: E rho^2 0.837 for a score averaged over all 4 formats (n_c = 4)
       secondary: smallest Kendall tau +0.333 (three systems: tau takes only +-1/3 and +-1)
       plain     ranking Gamma > Alpha > Beta, tau +1.000
       marker    ranking Gamma > Beta > Alpha, tau +0.333
       brief     ranking Gamma > Alpha > Beta, tau +1.000
       numbered  ranking Gamma > Alpha > Beta, tau +1.000
[PASS] Item 1, corrected pipeline: E rho^2 0.955 for the reported design (n_c = 1 format, R = 5 runs); threshold >= 0.8
       variance components (systems by 4 formats, 5 runs as reruns): system 0.003327, system x format 0.000000, rerun 0.000780
       secondary: E rho^2 0.988 for a score averaged over all 4 formats (n_c = 4)
       secondary: smallest Kendall tau +1.000 (three systems: tau takes only +-1/3 and +-1)
       plain     ranking Beta > Alpha > Gamma, tau +1.000
       marker    ranking Beta > Alpha > Gamma, tau +1.000
       brief     ranking Beta > Alpha > Gamma, tau +1.000
       numbered  ranking Beta > Alpha > Gamma, tau +1.000
[FAIL] Item 14, undecided outcomes, faulty report: U not reported (undecided runs dropped); lost share Alpha 0.026, Beta 0.028, Gamma 0.229
[PASS] Item 14, corrected report (fixed builder, strict extractor, grader errors rerun at most once, undecided kept); bounds over runs:
       system   runs    P    F    U   E   lower   upper   truth
       Alpha    1200  744  425   31  10   0.620   0.646   0.636
       Beta     1200  785  378   37  13   0.654   0.685   0.675
       Gamma    1200  650  323  227  14   0.542   0.731   0.557
       Alpha vs Beta, on these runs: Beta > Alpha
       Alpha vs Gamma, on these runs: not ordered, bounds overlap
       Beta vs Gamma, on these runs: not ordered, bounds overlap
       paired bootstrap over items (10000 resamples of 240 items, all runs of an item together, fixed seed), 95% interval:
       lower(Beta) - upper(Alpha)   observed +0.008, interval [-0.027, +0.042], not resolved
       lower(Alpha) - upper(Gamma)  observed -0.111, interval [-0.145, -0.077], not resolved
       lower(Beta) - upper(Gamma)   observed -0.077, interval [-0.110, -0.043], not resolved
[FAIL] Item 15, selection: faulty report gives the best of 5 runs only; largest best minus mean 0.039; threshold every run reported
[FAIL] Item 10, null control (echo agent), permissive: score 0.125; threshold <= floor 0.0 + margin 0.01, set in advance
[PASS] Item 10, null control (echo agent), strict: score 0.000; threshold <= floor 0.0 + margin 0.01, set in advance
```

## Licence

MIT, see `LICENSE`.
