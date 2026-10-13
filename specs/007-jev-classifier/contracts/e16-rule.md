# Contract: experiment E16, jev for the category

**Status: approved by Luis on 2026-10-12, before any E16 run.** He asked for it in the
conversation, to decide with real measurements which classifier spends less and gives the better
results in a test environment with low traffic. The registration below therefore carries
`approved_by: Luis`; `eval/experiments/run_dev.py` still refuses to run without it (FR-021). The
text is written on 2026-10-12, before any E16 run, and after the demonstrative jev-1.13 run of
2026-10-11, whose numbers are known. That run decides nothing; E16 calls jev again.

## Registration text (to append under `iteration_2:` in `explorations/research/experiments_plan.yaml`)

```yaml
  - id: E16
    factor: item classifier, a decision model for the category
    registered_at: "<UTC timestamp when the implementation session writes this entry>"
    variants: [jev-1.13, jev-hybrid]
    reference: gpt-oss-120b   # its committed E14 answers on this set; no new call
    held_fixed: >-
      Frozen dev set (all 130 items decide). Decision prompt dec-v1 (the E13 payload, moved into
      the package unchanged); cls-v2 for gpt-oss-120b, whose answers are the committed E14 cache
      (explorations/results/iter2/cache/gpt-oss-120b.jsonl), so the hybrid's detail side makes no
      new call. OpenRouter routing; serving provider recorded. Input: item text, merchant, MCC;
      never the declared expense type or attendee count.
    why: >-
      On 2026-10-11 jev-1.13 classified 130/130 categories (gpt-oss-120b 123/130, McNemar b=7 c=0
      p=0.0156) but returns no subtype or recipient (A6/A9 wrong 23/29). That run was not
      registered. The hybrid takes jev's category and confidence and gpt-oss-120b's subtype and
      recipient.
    metrics: >-
      Category accuracy (primary) with Wilson intervals; restricted F1; A6/A9 items wrong (subtype
      or recipient kind) out of those that exercise A6/A9; schema-violation rate; McNemar exact b/c;
      paired bootstrap of the accuracy difference (10,000 resamples, seed 20261012); cost per
      1,000 items (both calls for the hybrid); median and p95 latency per item (both calls for the
      hybrid); Brier and ECE of each confidence source.
    decision_rule: >-
      Applied in this order, per challenger. (1) Exclusion: schema violations on more than 2 % of
      items. (2) A6/A9 guard: more than 2 more A6/A9 items wrong than the reference fails the
      challenger, whatever its accuracy ("fails_a6a9_guard"). (3) Restricted guard: restricted F1
      below the reference's minus 0.01 fails it ("fails_restricted_guard"). (4) Superiority:
      McNemar exact p < 0.05 in the challenger's favour AND the bootstrap lower bound of its
      accuracy difference > 0. (5) Non-inferiority: bootstrap lower bound > -0.02. Winner: if any
      challenger is superior, the cheapest superior challenger wins (the reference is not
      eligible). Otherwise, the cheapest among the reference and the non-inferior challengers;
      ties go to the lower median latency, then the name. If nothing qualifies, keep the
      reference.
    threshold_rule: >-
      If a jev variant wins, its EXC-03 confidence source and threshold are chosen with E7's
      registered procedure on the winner's answers (lowest Brier among the sources
      top_probability and reported confidence, reported only if at least three bins hold 10 or
      more items; threshold: among every distinct confidence plus 0, keep those that send at most
      10 % of correct items to review, pick the highest accuracy on the kept items, ties to the
      lower threshold). A threshold of 0 is a valid outcome and is reported with the dev items it
      would send to review (k/N).
    repeatability: >-
      Before scoring, the 130 jev answers are requested once and cached; a second uncached pass on
      a random 20-item subset (seed 20261012) measures how often the category changes between
      calls (k/20). It is reported, it decides nothing, and its calls count in the budget.
    budget: USD 0.10 for the whole experiment (jev about USD 0.006 per pass of 130 items).
    data: "5f34f08ec59f487c9483378cfe3e0a4904f9985086d677b7c619ce210fe000a7"
    approved_by: Luis   # approved in conversation on 2026-10-12, before any E16 run
```

## How the rule differs from E14, and why

| E14 as coded (`eval/experiments/decide.py`) | E16 | Reason |
|---|---|---|
| Superiority checked before the A6/A9 guard (lines 137–146) | Guards first | A model that cannot do A6/A9 cannot replace one that can, however accurate its category |
| Winner = cheapest of the reference plus all qualifying models (line 153) | A superior challenger wins outright; cost picks only among several superior ones, or among non-inferior ones | E14's registered text says a superior challenger "becomes the reference". The code let a costlier superior model lose to the old reference |
| Restricted F1 checked only for non-inferiority | Restricted guard applies to every challenger | The engine depends on the restricted flag in both cases |
| One confidence source per model | Two for jev (top probability, reported confidence) | jev returns both. Calibration on 2026-10-11: Brier 0.0109 and 0.0120 (N = 130) |

The two code fixes apply to E14 as well (FR-018, FR-019). They do not change E14's committed
outcome, because no E14 challenger was superior or failed only the A6/A9 guard. A test proves
this (SC-003).

## Reported for E16 (each with its N)

Per variant:

- accuracy as k/130 with a Wilson interval;
- restricted F1;
- A6/A9 wrong as k/29;
- schema violations as k/130;
- McNemar b, c and p against the reference;
- the bootstrap difference and its interval;
- cost per 1,000 items;
- median and p95 latency;
- Brier and ECE per confidence source, with the bin counts;
- the status (`excluded`, `fails_a6a9_guard`, `fails_restricted_guard`, `superior`,
  `non_inferior` or `worse`).

For the experiment as a whole:

- the winner and why each other variant lost;
- the chosen confidence source and threshold, with the dev items it sends to review (k/N);
- the repeatability measure (k/20);
- the billed spend.

## Expected, stated before running

This section is not part of the rule.

- jev-1.13 alone should fail the A6/A9 guard (23/29 wrong against the reference's 2/29).
- The hybrid's A6/A9 errors should be close to the reference's, because its detail side *is* the
  reference's cached answers. They can differ only where jev says `other` and gpt-oss did not,
  or the reverse (merge table).

With N = 130, a 7-item advantage gives p = 0.0156, so superiority is detectable. A smaller
advantage may only show non-inferiority. At about USD 0.10 per 1,000 items the hybrid would cost
more than the reference's USD 0.06, and it would then lose to the reference.
