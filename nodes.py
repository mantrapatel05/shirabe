from __future__ import annotations
import json, os
from langchain_groq import ChatGroq
from state import AgentState
from tools import search_repository

def get_model():
    return ChatGroq(model=os.getenv("GROQ_MODEL","openai/gpt-oss-120b"),temperature=0)

def _text(response): return response.content if isinstance(response.content,str) else str(response.content)

def _parse_plan(text: str) -> list[str]:
    cleaned=text.strip()
    if cleaned.startswith("```"):
        cleaned="\n".join(line for line in cleaned.splitlines() if not line.strip().startswith("```"))
    start=cleaned.find("{"); end=cleaned.rfind("}")
    if start!=-1 and end!=-1 and end>start:
        cleaned=cleaned[start:end+1]
    return json.loads(cleaned)["queries"]

def plan_node(state: AgentState):
    response=get_model().invoke(f'''You are planning an investigation of a software repository.\nEngineering question:\n{state["question"]}\nCreate 3 to 5 concrete repository search queries targeting likely files, functions/classes, configuration, control flow, and data flow.\nEach query must be 1-3 simple keywords such as file names, function names, or code terms (example: "search_repository", "clone_repository tools", "StateGraph planner").\nDo NOT use search operators like filename:, path:, extension:, language:, class:, TODO, *, or quotes. Use plain words only.\nReturn ONLY valid JSON: {{"queries": ["...", "..."]}}''')
    return {"plan":_parse_plan(_text(response))}

def investigate_node(state: AgentState):
    evidence=[]
    for query in state["plan"]:
        for match in search_repository(state["repo_path"],query): evidence.append(f"QUERY: {query}\n{match}")
    return {"evidence":evidence,"iteration":state["iteration"]+1}

def analyze_node(state: AgentState):
    evidence_text="\n\n---\n\n".join(state["evidence"])
    response=get_model().invoke(f'''You are analyzing evidence from a software repository.\nQuestion:\n{state["question"]}\nRepository evidence:\n{evidence_text[:30000]}\nProduce a technical analysis. Identify concrete files/symbols, explain control/data flow, separate direct evidence from inference, never invent behavior, and say what is missing if evidence is insufficient. End with exactly one line: NEEDS_MORE_EVIDENCE: true or NEEDS_MORE_EVIDENCE: false''')
    analysis=_text(response)
    return {"analysis":analysis,"needs_more_evidence":"needs_more_evidence: true" in analysis.lower()}

def route_after_analysis(state: AgentState):
    return "investigate" if state["needs_more_evidence"] and state["iteration"]<state["max_iterations"] else "explain"

def explain_node(state: AgentState):
    evidence_text="\n\n---\n\n".join(state["evidence"])
    response=get_model().invoke(f'''You are an engineering explainer.\nQuestion:\n{state["question"]}\nAnalysis:\n{state["analysis"]}\nEvidence:\n{evidence_text[:30000]}\nWrite a concise, technically precise answer. Cite repository-relative file paths and line ranges when available. Distinguish observed evidence from inference. Do not make unsupported claims. Prefer concrete execution/data-flow explanations.''')
    return {"answer":_text(response)}
