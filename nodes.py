from __future__ import annotations

import json

from langchain_groq import ChatGroq

from config import load_settings
from errors import ProviderError
from state import AgentState
from tools import search_repository


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
    model = ChatGroq(model=settings.groq_model, temperature=0)
    try:
        response = model.invoke(prompt)
    except Exception as exc:
        message = str(exc)
        if settings.groq_api_key:
            message = message.replace(settings.groq_api_key, "[REDACTED]")
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
    evidence = []
    for query in state["plan"]:
        for match in search_repository(state["repo_path"], query):
            evidence.append(f"QUERY: {query}\n{match}")
    return {"evidence": evidence, "iteration": state["iteration"] + 1}


def analyze_node(state: AgentState):
    evidence_text = "\n\n---\n\n".join(state["evidence"])
    analysis = _invoke(
        "You are analyzing evidence from a software repository.\n"
        f'Question:\n{state["question"]}\n'
        f"Repository evidence:\n{evidence_text[:30000]}\n"
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
    evidence_text = "\n\n---\n\n".join(state["evidence"])
    answer = _invoke(
        "You are an engineering explainer.\n"
        f'Question:\n{state["question"]}\n'
        f'Analysis:\n{state["analysis"]}\n'
        f"Evidence:\n{evidence_text[:30000]}\n"
        "Write a concise, technically precise answer. Cite repository-relative file paths and "
        "line ranges when available. Distinguish observed evidence from inference. Do not make "
        "unsupported claims. Prefer concrete execution/data-flow explanations."
    )
    return {"answer": answer}
