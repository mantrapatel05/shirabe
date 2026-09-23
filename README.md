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

LangSmith tracing is optional. The current `.env.example` enables it; add a LangSmith key to use it, or set `LANGSMITH_TRACING=false` to disable tracing. Traces may contain your question and repository excerpts.

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

The repository must be public and hosted on GitHub. Each run clones it into a temporary directory, then plans searches, gathers evidence, and prints an answer.

## How the current implementation works

1. **Planner:** asks the model for 3–5 plain-keyword search queries.
2. **Investigator:** searches supported text files. All query terms must occur on the same line. Each search returns up to 8 snippets, with up to 2 surrounding lines.
3. **Analyzer:** reviews the gathered evidence and can request another search pass. The graph allows at most 3 investigation passes.
4. **Explainer:** writes the final answer and is prompted to cite repository paths and line ranges, while separating evidence from inference.

Repository cloning is shallow and has a 120-second timeout. Search skips configured directories and files larger than 500 KB. The analyzer receives at most 30,000 characters of evidence.

## Project files

| File | Purpose |
|---|---|
| `main.py` | CLI setup, repository clone, graph invocation, and output |
| `graph.py` | LangGraph nodes and investigation loop |
| `nodes.py` | Planner, investigator, analyzer, and explainer |
| `state.py` | Shared graph state and evidence reducer |
| `tools.py` | GitHub cloning, text search, and bounded file reads |
| `evaluate.py` | Early evaluation scaffold |

## Configuration

| Variable | Purpose |
|---|---|
| `GROQ_API_KEY` | Required API key for model calls |
| `GROQ_MODEL` | Optional model name; defaults to `openai/gpt-oss-120b` |
| `LANGSMITH_TRACING` | Enables/disables LangSmith tracing |
| `LANGSMITH_API_KEY` | Required only when using LangSmith tracing |
| `LANGSMITH_PROJECT` | Optional LangSmith project name |
