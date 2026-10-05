# Shirabe evaluation fixtures (dataset revision v1)

## License and provenance

Every file directly under this directory is an **original miniature example
written for Shirabe evaluation** and is released under the **MIT license**.
They are not copied from any third-party repository. Fixtures are
deliberately tiny (one to three files) so a reviewer can read each one in
full and check every label by hand.

## What is covered

| Fixture | Case(s) | Question class |
|---|---|---|
| `calc/` | `calc-single` | Single-file behavior |
| `flow/` | `flow-control`, `flow-data` | Cross-file control flow, cross-file data flow |
| `shop/` | `shop-config` | Configuration entry and consumers |
| `guarded/` | `guarded-failure` | Failure path and its selecting condition |
| `auth/` | `auth-unanswerable` | Unanswerable (no retry logic exists anywhere) |

Labeled relevant ranges live in `eval_cases.py`. Labels were checked by
reading each fixture; `tests/test_eval.py` additionally asserts that every
labeled file exists and every labeled range falls inside the file, so stale
labels fail CI instead of silently rotting.

## Edge cases in the labels

- `flow-control` labels `models.py:12-16`, which shares **no keyword** with
  the case queries. It is reachable only through the `service.py` import.
  Lexical retrieval is expected to miss it (see gap analysis below).
- `flow-data` targets the same file through different keywords and is
  expected to pass: the pair shows retrieval succeeding or failing on
  wording, not on fixture size.
- `shop-config` labels a single line (`config.py:5`); range-overlap scoring
  treats any retrieved range covering line 5 as a hit.
- `auth-unanswerable` has no relevant ranges by construction. Any retrieved
  range or any answered claim for it is a benchmark failure.
- Fixture mode bypasses the planner: case queries stand in for planner
  output. Planner quality is therefore **not** measured in fixture mode;
  use live mode for end-to-end runs.

## Retrieval gap analysis (measured, dataset v1)

Full fixture run: file recall 8/9, range recall 9/11 at k=5. Two cases miss:

- `flow-control` scores file recall 2/3 and range recall 2/3: `handler.py`
  and `service.py` are retrieved, `models.py` is not, because nothing in the
  queries lexically reaches it. The missing file is exactly one deterministic
  import edge away (`service.py` imports `models.py`).
- `calc-single` scores range recall 1/2: the `total()` definition and body
  are retrieved, but the `add()` helper definition (`calc.py:5-7`) is not.
  The queries match the call site (`result = add(result, value)`), never the
  `def add` lines in the same file.

Both gaps have the same shape: relevant code reachable through a
deterministic code edge (same-file symbol definition, cross-file import)
that pure lexical matching cannot follow. Decision: keep retrieval lexical
for this release and treat one narrow deterministic symbol/import expansion
as the v0.4 candidate, to be judged on this same dataset without regressing
citation integrity. These gaps are fixture findings, not claims about
general repository performance.

## Human claim-support rubric

Deterministic fixture mode cannot judge whether true lines actually prove a
claim, so claim support is always reported as unlabeled there. When labeling
live-model answers by hand, mark each material claim:

- **supported:** the cited ranges, read together, show the claimed behavior.
- **unsupported:** the ranges are real but do not show it, or no usable
  citation exists.

Record the labels as a plain list of true/false values (one per material
claim, in answer order) alongside the dataset revision, model, and settings.
`eval_metrics.claim_support_score` turns a label list into a fraction with
an explicit denominator; an empty label list reports no score, never zero.
