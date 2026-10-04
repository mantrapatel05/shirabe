from dataclasses import dataclass
@dataclass
class EvalCase:
    question:str
    expected_terms:list[str]
CASES=[EvalCase("How does this repository handle HTTP requests?",["request"]),EvalCase("Where is configuration loaded?",["config"])]
def score(answer:str,expected_terms:list[str])->float:
    text=answer.lower(); hits=sum(term.lower() in text for term in expected_terms); return hits/len(expected_terms) if expected_terms else 1.0
if __name__=="__main__": 
    print("Shirabe evaluation scaffold. Connect CASES to a fixed repository + graph invocation to run them.")
