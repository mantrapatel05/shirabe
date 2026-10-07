from __future__ import annotations

import json

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from config import load_settings
from errors import ProviderError
from evidence import (
    EVIDENCE_ID_PREFIX,
    EVIDENCE_PREAMBLE,
    MAX_EVIDENCE_RECORDS,
    AnswerClaim,
    Citation,
    EvidenceRecord,
    build_abstention,
    format_evidence,
    parse_claims,
    render_claims,
    validate_claim,
)
from state import AgentState
from tools import get_repo_revision, load_text_lines, read_range, search_hits


def _text(response) -> str:
    return response.content if isinstance(response.content, str) else str(response.content)


def _invoke(prompt: str) -> str:
    """Call the configured model and return its text, or raise ProviderError.

    Any exception from the provider client is caught here. The configured
    API key (if it happens to appear in the exception's message, which some
    HTTP client errors do when echoing request details) is redacted before
    the message is ever shown to the user.
    """
    settings = load_settings()
    model = ChatOpenAI(
        model=settings.openrouter_model,
        temperature=0,
        api_key=SecretStr(settings.openrouter_api_key),
        base_url="https://openrouter.ai/api/v1",
    )
    try:
        response = model.invoke(prompt)
    except Exception as exc:
        message = str(exc)
        if settings.openrouter_api_key:
            message = message.replace(settings.openrouter_api_key, "[REDACTED]")
        raise ProviderError(f"Model provider call failed: {message}") from None
    return _text(response)


def _parse_plan(text: str) -> list[str]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = "\n".join(line for line in cleaned.splitlines() if not line.strip().startswith("```"))
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start:end + 1]

    try:
        queries = json.loads(cleaned)["queries"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ProviderError(f"Planner returned invalid output ({exc}).") from None

    is_list_of_nonempty_strings = isinstance(queries, list) and queries and all(
        isinstance(q, str) and q.strip() for q in queries
    )
    if not is_list_of_nonempty_strings:
        raise ProviderError("Planner returned a 'queries' field that is not a non-empty list of strings.")

    return queries


def plan_node(state: AgentState):
    text = _invoke(
        "You are planning an investigation of a software repository.\n"
        f'Engineering question:\n{state["question"]}\n'
        "Create 3 to 5 concrete repository search queries targeting likely files, "
        "functions/classes, configuration, control flow, and data flow.\n"
        'Each query must be 1-3 simple keywords such as file names, function names, or '
        'code terms (example: "search_repository", "clone_repository tools", "StateGraph planner").\n'
        "Do NOT use search operators like filename:, path:, extension:, language:, class:, TODO, *, "
        "or quotes. Use plain words only.\n"
        'Return ONLY valid JSON: {"queries": ["...", "..."]}'
    )
    return {"plan": _parse_plan(text)}


def investigate_node(state: AgentState):
    """Search the checkout and expand hits into validated evidence records.

    Every hit is re-read through the repository-root-confined reader, so the
    stored excerpt is exactly the range the citation validator will check.
    IDs are stable across investigation passes; already-seen ranges are not
    recorded twice.
    """
    existing = state.get("evidence_records", [])
    seen = {(record.path, record.start_line, record.end_line) for record in existing}
    budget = MAX_EVIDENCE_RECORDS - len(existing)
    snapshot_id = get_repo_revision(state["repo_path"])
    lines_cache = load_text_lines(state["repo_path"])

    records: list[EvidenceRecord] = []
    next_id = len(existing) + 1
    for query in state["plan"]:
        if len(records) >= budget:
            break
        for hit in search_hits(state["repo_path"], query, lines_cache=lines_cache):
            if len(records) >= budget:
                break
            if (hit.path, hit.start_line, hit.end_line) in seen:
                continue
            try:
                lines = read_range(state["repo_path"], hit.path, hit.start_line, hit.end_line)
            except (OSError, ValueError):
                continue
            excerpt = "\n".join(
                f"{hit.start_line + offset}: {line}" for offset, line in enumerate(lines)
            )
            record = EvidenceRecord(
                evidence_id=f"{EVIDENCE_ID_PREFIX}{next_id}",
                path=hit.path,
                start_line=hit.start_line,
                end_line=hit.end_line,
                reason=f"query: {query}",
                excerpt=excerpt,
                snapshot_id=snapshot_id,
            )
            records.append(record)
            seen.add((record.path, record.start_line, record.end_line))
            next_id += 1
    evidence = [format_evidence(record) for record in records]
    return {"evidence": evidence, "evidence_records": records, "iteration": state["iteration"] + 1}


def analyze_node(state: AgentState):
    evidence_text = "\n\n---\n\n".join(state["evidence"])
    analysis = _invoke(
        "You are analyzing evidence from a software repository.\n"
        f'Question:\n{state["question"]}\n'
        f"Repository evidence:\n{EVIDENCE_PREAMBLE}\n{evidence_text[: state['max_evidence_chars']]}\n"
        "Produce a technical analysis. Identify concrete files/symbols, explain control/data "
        "flow, separate direct evidence from inference, never invent behavior, and say what is "
        "missing if evidence is insufficient. End with exactly one line: "
        "NEEDS_MORE_EVIDENCE: true or NEEDS_MORE_EVIDENCE: false"
    )
    return {"analysis": analysis, "needs_more_evidence": "needs_more_evidence: true" in analysis.lower()}


def route_after_analysis(state: AgentState):
    if state["needs_more_evidence"] and state["iteration"] < state["max_iterations"]:
        return "investigate"
    return "explain"


def explain_node(state: AgentState):
    """Build the final answer from validated evidence only.

    Claims cite evidence IDs; every ID, path, and range is checked against
    the records actually sent to the model. Claims without a valid citation
    are dropped, and the run abstains when nothing citable remains. An empty
    evidence ledger abstains without calling the model at all.
    """
    records = state.get("evidence_records", [])
    if not records:
        checked = f"queries {state['plan']} against {state['repo_url']} (no matching source ranges)"
        return {
            "answer": build_abstention(state["question"], checked),
            "answer_claims": [],
            "citation_report": [],
            "abstained": True,
        }

    evidence_text = "\n\n---\n\n".join(state["evidence"])
    response = _invoke(
        "You are an engineering explainer.\n"
        f'Question:\n{state["question"]}\n'
        f'Analysis:\n{state["analysis"]}\n'
        f"Evidence:\n{EVIDENCE_PREAMBLE}\n{evidence_text[: state['max_evidence_chars']]}\n"
        "Write a concise, technically precise answer as JSON with this exact shape: "
        '{"claims": [{"text": "...", "evidence": ["E1", {"id": "E2", '
        '"start_line": 3, "end_line": 5}]}]}. '
        "Every claim must cite at least one evidence ID shown above; cite only IDs shown above. "
        "Use an explicit id/start_line/end_line object only to narrow a range, keeping it "
        "inside the cited record's range. Distinguish observed evidence from inference. "
        "Do not make unsupported claims."
    )
    try:
        claims = parse_claims(response)
    except ValueError as exc:
        raise ProviderError(f"Explainer returned invalid output ({exc}).") from None

    records_by_id = {record.evidence_id: record for record in records}
    rendered: list[tuple[AnswerClaim, list[Citation]]] = []
    checks = []
    for claim in claims:
        accepted, claim_checks = validate_claim(claim, records_by_id)
        checks.extend(claim_checks)
        if accepted:
            rendered.append((claim, accepted))
    if not rendered:
        checked = f"{len(records)} evidence ranges, none supporting a cited claim"
        return {
            "answer": build_abstention(state["question"], checked),
            "answer_claims": [],
            "citation_report": checks,
            "abstained": True,
        }
    claim_dicts = [
        {
            "text": claim.text,
            "citations": [
                {
                    "evidence_id": citation.evidence_id,
                    "path": citation.path,
                    "start_line": citation.start_line,
                    "end_line": citation.end_line,
                }
                for citation in accepted
            ],
        }
        for claim, accepted in rendered
    ]
    return {
        "answer": render_claims(rendered),
        "answer_claims": claim_dicts,
        "citation_report": checks,
        "abstained": False,
    }
