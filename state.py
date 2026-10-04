from operator import add
from typing import Annotated

from typing_extensions import TypedDict


class AgentState(TypedDict):
    repo_url: str
    repo_path: str
    question: str
    plan: list[str]
    evidence: Annotated[list[str], add]
    analysis: str
    answer: str
    iteration: int
    max_iterations: int
    needs_more_evidence: bool
