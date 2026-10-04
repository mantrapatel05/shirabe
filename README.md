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

Shirabe uses **Python**, **LangGraph**, **ChatGroq**, and optionally **LangSmith** for tracing.

## Quickstart

You need Python 3.11 or newer, Git, and a Groq API key.

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
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=openai/gpt-oss-120b
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

## How the current implementation works

1. **Planner:** asks the model for 3–5 plain-keyword search queries.
2. **Investigator:** searches supported text files. All query terms must occur on the same line. Each search returns up to 8 snippets, with up to 2 surrounding lines. Hits are expanded through a root-confined reader into typed evidence records with stable IDs, bounded excerpts, and the checkout's commit SHA when available.
3. **Analyzer:** reviews the gathered evidence and can request another search pass. The graph allows at most 3 investigation passes (configurable).
4. **Explainer:** returns structured claims that cite evidence IDs. Every ID, path, and line range is validated against the evidence actually sent to the model; claims without a valid citation are dropped, and runs with no supporting evidence abstain explicitly instead of guessing. The CLI prints citation-integrity findings after the answer.

Repository cloning is shallow and has a configurable timeout (default 120 s). Repositories exceeding file-count or byte-size budgets are rejected before search begins. Search skips configured directories and files larger than 500 KB. The analyzer receives at most 30,000 characters of evidence.

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
| `evaluate.py` | Early evaluation scaffold (v0.3) |
| `tests/` | Deterministic tests; they need no network, model key, or tracing credentials |

## Configuration

| Variable | Purpose | Default |
|---|---|---|
| `GROQ_API_KEY` | Required API key for model calls | — |
| `GROQ_MODEL` | Model name | `openai/gpt-oss-120b` |
| `LANGSMITH_TRACING` | Enable LangSmith tracing | `false` |
| `LANGSMITH_API_KEY` | Required only when tracing is enabled | — |
| `LANGSMITH_PROJECT` | LangSmith project name | `shirabe` |
| `SHIRABE_MAX_ITERATIONS` | Max investigation passes | `3` |
| `SHIRABE_CLONE_TIMEOUT_SECONDS` | Clone timeout | `120` |
| `SHIRABE_MAX_REPO_FILES` | Max files in cloned repo | `4000` |
| `SHIRABE_MAX_REPO_TOTAL_BYTES` | Max total bytes in cloned repo | `200000000` |
| `SHIRABE_MAX_FILE_BYTES` | Max size of a single file to search | `500000` |
| `SHIRABE_MAX_EVIDENCE_CHARS` | Max evidence chars sent to analyzer | `30000` |

## Development

Install dev dependencies and run the full check suite:

```bash
pip install -r requirements-dev.txt
pytest
ruff check .
mypy config.py errors.py tools.py nodes.py main.py graph.py state.py evaluate.py
pip-audit -r requirements.txt
```

These checks need no `GROQ_API_KEY` or LangSmith credentials: tests mock the
model client, the temp clone, and the graph invocation. The same steps run in
CI (`.github/workflows/ci.yml`) on every push and pull request.
