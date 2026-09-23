from langgraph.graph import END, START, StateGraph
from nodes import analyze_node, explain_node, investigate_node, plan_node, route_after_analysis
from state import AgentState

def build_graph():
    workflow=StateGraph(AgentState)
    workflow.add_node("planner",plan_node); workflow.add_node("investigator",investigate_node); workflow.add_node("analyzer",analyze_node); workflow.add_node("explainer",explain_node)
    workflow.add_edge(START,"planner"); workflow.add_edge("planner","investigator"); workflow.add_edge("investigator","analyzer")
    workflow.add_conditional_edges("analyzer",route_after_analysis,{"investigate":"investigator","explain":"explainer"})
    workflow.add_edge("explainer",END)
    return workflow.compile()
app=build_graph()
