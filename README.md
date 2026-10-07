# Shirabe (調べ)

**Shirabe** (調べ, *shirabe*) is a Japanese word for an investigation or inquiry. This project uses LangGraph to investigate public GitHub repositories and answer engineering questions with repository evidence. ([Dictionary reference](https://kanji.jepang.org/en/vocabulary/%E8%AA%BF%E3%81%B9))

## What it does

Give Shirabe a public GitHub repository URL and a question. It clones the repository, searches text files for relevant lines, and asks an LLM to explain what the evidence shows.

```text
Repository URL + question
        ↓
Plan search queries
        ↓
Search repository ──┐
        ↓            │ request more evidence (up to 3 search passes)
Analyze evidence ────┘
        ↓
Explain with file and line references
```

Shirabe uses **Python**, **LangGraph**, **ChatOpenAI**, and optionally **LangSmith** for tracing.

## Quickstart

You need Python 3.11 or newer, Git, and a OpenRouter API key.

Create and activate a virtual environment, then install the dependencies:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

On macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Add your key to `.env`:

```env
OPENROUTER_API_KEY=your_openrouter_api_key
OPENROUTER_MODEL=nvidia/nemotron-3.5-lightning:free
```

LangSmith tracing is optional and disabled by default. To enable it, set `LANGSMITH_TRACING=true` in `.env` and add your LangSmith key. Traces may contain your question and repository excerpts.

The repository's `.gitignore` excludes `.env`, but never commit API keys or paste them into issue reports.

## Run

Pass a repository URL and question as arguments:

```bash
python main.py "https://github.com/psf/requests" "How is an HTTP request constructed and sent?"
```

Or start interactive mode:

```bash
python main.py
```

The repository must be public and hosted on GitHub. Each run clones it into a temporary directory, then plans searches, gathers evidence, and prints an answer. Temporary clones are always cleaned up, even on failure.

## Demo (no key required)

```bash
python demo.py
python demo.py --save-report demo-report.json
```

The demo runs a multi-file investigation and an abstention case against the
miniature fixtures with canned model claims, so it works with no OpenRouter key,
no network, and no tracing credentials. It prints the evidence trail,
citation-integrity findings, and the release's known retrieval limitation.

## Investigation reports

Reports are versioned JSON (`report_version: v1`) with the question,
repository label and snapshot, answer, structured claims, bounded evidence
excerpts, citation-check outcomes, run limits, and run provenance. Saving is
always explicit and reports never contain secrets, full repository contents,
raw prompts, or tracing data:

```bash
python main.py "https://github.com/psf/requests" "How is X built?" --save-report report.json
python main.py --inspect-report report.json
python main.py --attach-review report.json --labels 1,1,0
python main.py --delete-report report.json
```

Human claim-support labels are opt-in (one boolean per saved claim),
inspectable, and deletable with the same file. Promoting a reviewed example
into the benchmark requires provenance, licensing, and privacy checks first.

## How the current implementation works

1. **Planner:** asks the model for 3–5 plain-keyword search queries.
2. **Investigator:** searches supported text files. All query terms must occur on the same line. Each search returns up to 8 snippets, with up to 2 surrounding lines. Hits are expanded through a root-confined reader into typed evidence records with stable IDs, bounded excerpts, and the checkout's commit SHA when available.
3. **Analyzer:** reviews the gathered evidence and can request another search pass. The graph allows at most 3 investigation passes (configurable).
4. **Explainer:** returns structured claims that cite evidence IDs. Every ID, path, and line range is validated against the evidence actually sent to the model; claims without a valid citation are dropped, and runs with no supporting evidence abstain explicitly instead of guessing. The CLI prints citation-integrity findings after the answer.

Repository cloning is shallow and has a configurable timeout (default 120 s). Repositories exceeding file-count or byte-size budgets are rejected before search begins. Search skips configured directories and files larger than 500 KB. Each investigation pass reads every searchable file once and scans matches in sorted path order. The analyzer and explainer receive at most `SHIRABE_MAX_EVIDENCE_CHARS` characters of evidence (default 30,000).

## Project files

| File | Purpose |
|---|---|
| `main.py` | CLI setup, config validation, clone, budget check, graph invocation, cleanup |
| `graph.py` | LangGraph nodes and investigation loop |
| `nodes.py` | Planner, investigator, analyzer, and explainer with error handling |
| `state.py` | Shared graph state and evidence reducer |
| `tools.py` | GitHub cloning, text search, budget enforcement, and bounded file reads |
| `config.py` | Centralized environment configuration loading and validation |
| `errors.py` | Exception hierarchy for user-facing errors |
| `evidence.py` | Typed evidence records, claim parsing, and citation-integrity checks |
| `evaluate.py` | Reproducible benchmark runner (fixture and live modes) |
| `eval_cases.py` | Versioned benchmark cases over miniature fixtures (dataset v1) |
| `eval_metrics.py` | Metric definitions with explicit denominators |
| `tests/` | Deterministic tests; they need no network, model key, or tracing credentials |
| `demo.py` | No-key fixture demo: evidence trail, citation checks, abstention case |
| `report.py` | Versioned report export with opt-in review labels |

## Architecture

```text
main.py / demo.py ──→ graph.py ──→ nodes.py ──→ tools.py (read-only checkout)
                         │              ├── evidence.py (records, claim parsing, citation checks)
                         │              └── report.py (versioned export, opt-in review labels)
                         └── state.py (shared investigation state)
config.py + errors.py bound and sanitize every layer; evaluate.py +
eval_cases.py + eval_metrics.py measure retrieval and answer quality.
```

Shirabe only reads source: it clones (shallow), searches, and reads bounded
ranges. It never executes repository code, never opens shells against the
checkout, and never mutates anything outside its own temp directory.
Repository text is treated as untrusted data in every prompt, and source
text that reads like instructions cannot change the tool set.

## Configuration

| Variable | Purpose | Default |
|---|---|---|
| `OPENROUTER_API_KEY` | Required API key for model calls | — |
| `OPENROUTER_MODEL` | Model name | `nvidia/nemotron-3.5-lightning:free` |
| `LANGSMITH_TRACING` | Enable LangSmith tracing | `false` |
| `LANGSMITH_API_KEY` | Required only when tracing is enabled | — |
| `LANGSMITH_PROJECT` | LangSmith project name | `shirabe` |
| `SHIRABE_MAX_ITERATIONS` | Max investigation passes | `3` |
| `SHIRABE_CLONE_TIMEOUT_SECONDS` | Clone timeout | `120` |
| `SHIRABE_MAX_REPO_FILES` | Max files in cloned repo | `4000` |
| `SHIRABE_MAX_REPO_TOTAL_BYTES` | Max total bytes in cloned repo | `200000000` |
| `SHIRABE_MAX_FILE_BYTES` | Max size of a single file to search | `500000` |
| `SHIRABE_MAX_EVIDENCE_CHARS` | Max evidence chars sent to analyzer | `30000` |

## Evaluation

`python evaluate.py --mode fixture` runs 6 versioned cases (dataset v1) over
original miniature fixtures in `tests/fixtures/` — single-file and
cross-file behavior, configuration, a failure path, and one unanswerable
question. It uses real retrieval with pinned queries and mocked model
outputs, so it reproduces without credentials and runs in CI. Live-model
evaluation is opt-in: `python evaluate.py --mode live` needs `OPENROUTER_API_KEY`
and records dataset revision, model/provider, settings, and timestamp.

Each metric reports its numerator and denominator; claim support needs human
labels and is reported as unlabeled (never zero) until reviewed. Latest
fixture run:

| Metric | Result |
|---|---|
| Retrieval file recall@5 | 8/9 |
| Retrieval range recall | 9/11 |
| Citation integrity | 18/18 |
| Abstention precision / recall | 1/1, 1/1 |
| Claim support | unlabeled |

Known gaps (`calc-single`, `flow-control`; analysis in
`tests/fixtures/README.md`): relevant code reachable only through a
same-file symbol or an import edge is missed by lexical retrieval. Retrieval
stays lexical for this release; a narrow symbol/import expansion is the
candidate to judge on this dataset next. Fixture numbers are regression
signals, not general accuracy claims.

## Safety & Error Handling

These are expected limitations and safety boundaries handled gracefully by the system:

- Malformed model output (bad planner JSON, non-claim explainer JSON) fails
  the run with a short provider error instead of a guessed answer.
- Model citations that do not resolve to supplied evidence are rejected and
  reported; answers keep only validated citations.
- Empty evidence abstains explicitly; the unanswerable benchmark case guards
  this path in CI.
- Oversized repositories, clone timeouts, and non-GitHub URLs fail fast
  with actionable messages; temp clones are always cleaned up.
- Supported languages are lexical-only: retrieval matches plain keywords in
  configured text extensions and never implies complete static analysis.
- Tracing enabled without a key fails fast at startup instead of silently
  running untraced.

## Tracing privacy

LangSmith tracing is optional and disabled by default
(`LANGSMITH_TRACING=false`). When enabled, traces may contain your question,
planned queries, and repository excerpts sent to the model. Saved
investigation reports never include traces, prompts, secrets, or full
repository contents — only bounded evidence excerpts, validation outcomes,
and run metadata. The fixture demo, benchmark, and test suite force tracing
off even when the surrounding environment enables it, so keyless runs never
emit traces. The fixture demo and benchmark never enable tracing.

## Development

Install dev dependencies and run the full check suite:

```bash
pip install -r requirements-dev.txt
pytest
ruff check .
mypy config.py errors.py tools.py nodes.py main.py graph.py state.py evaluate.py evidence.py eval_cases.py eval_metrics.py report.py demo.py
pip-audit -r requirements.txt
```

These checks need no `OPENROUTER_API_KEY` or LangSmith credentials: tests mock the
model client, the temp clone, and the graph invocation, and the deterministic
benchmark (`python evaluate.py --mode fixture`) runs without a model key.
The same steps run in CI (`.github/workflows/ci.yml`) on every push and
pull request.

## License

MIT — see `LICENSE`. Evaluation fixtures under `tests/fixtures/` are
original miniature examples released under the same license.
