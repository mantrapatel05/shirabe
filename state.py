from __future__ import annotations

from operator import add
from typing import Annotated

from typing_extensions import TypedDict

from evidence import CitationCheck, EvidenceRecord


class AgentState(TypedDict):
    repo_url: str
    repo_path: str
    question: str
    plan: list[str]
    evidence: Annotated[list[str], add]
    evidence_records: Annotated[list[EvidenceRecord], add]
    analysis: str
    answer: str
    citation_report: list[CitationCheck]
    abstained: bool
    iteration: int
    max_iterations: int
    needs_more_evidence: bool
