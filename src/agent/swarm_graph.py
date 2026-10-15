"""
GeoAI Swarm - Main LangGraph Compilation.
"""
import os
import sys

# Ensure the root project directory is on the path so 'src' can be imported when running directly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from langgraph.graph import StateGraph, START, END
from langchain_core.messages import HumanMessage

from src.agent.swarm_state import SwarmState
from src.agent.agents.planner import planner_node
from src.agent.agents.worker import worker_node
from src.agent.agents.reviewer import reviewer_node

def emergency_brake_node(state: SwarmState) -> dict:
    """
    Graceful fallback node executed when loop_count reaches the maximum.
    Prevents infinite cycles in the self-healing loop.
    """
    return {
        "draft_response": "SYSTEM ERROR: The Swarm was unable to successfully execute and validate the spatial query after 3 attempts. Emergency brake engaged to prevent infinite looping."
    }

def route_from_reviewer(state: SwarmState) -> str:
    """
    Conditional edge routing logic.
    If rejected and loops < 3, return 'worker' to retry.
    If rejected and loops >= 3, return 'emergency_brake'.
    Otherwise, return END.
    """
    status = state.get("review_status", "approved")
    loops = state.get("loop_count", 0)
    
    if status.lower() == "rejected":
        if loops < 3:
            return "worker"
        else:
            return "emergency_brake"
    return END

# Build Graph
builder = StateGraph(SwarmState)
builder.add_node("planner", planner_node)
builder.add_node("worker", worker_node)
builder.add_node("reviewer", reviewer_node)
builder.add_node("emergency_brake", emergency_brake_node)

builder.add_edge(START, "planner")
builder.add_edge("planner", "worker")
builder.add_edge("worker", "reviewer")
builder.add_edge("emergency_brake", END)

# Add conditional edge from reviewer
builder.add_conditional_edges(
    "reviewer",
    route_from_reviewer,
    {
        "worker": "worker",
        "emergency_brake": "emergency_brake",
        END: END
    }
)

swarm_graph = builder.compile()

def run_test(test_name: str, test_question: str):
    print(f"\n{'='*50}")
    print(f"RUNNING {test_name}")
    print(f"Question: '{test_question}'")
    print(f"{'='*50}")
    
    current_state: SwarmState = {
        "question": test_question,
        "plan": [],
        "draft_response": "",
        "review_feedback": "",
        "review_status": "",
        "loop_count": 0,
        "tool_payload": {},
        "frontend_payload": {}
    }
    
    print("\nSwarm Thinking Process:")
    for event in swarm_graph.stream(current_state):
        for node_name, node_state in event.items():
            current_state.update(node_state)
            print(f"\n--- [{node_name.upper()} NODE FIRED] ---")
            if node_name == "planner":
                print(f"Generated Plan: {node_state.get('plan')}")
            elif node_name == "worker":
                draft = str(node_state.get('draft_response', ''))
                snippet = draft[:150] + ("..." if len(draft) > 150 else "")
                print(f"Draft Response Snippet: {snippet}")
                print(f"Captured Tool Payload: {node_state.get('tool_payload')}")
            elif node_name == "reviewer":
                print(f"Review Status: {node_state.get('review_status')}")
                if node_state.get("review_status") == "rejected":
                    print(f"Feedback:\n{node_state.get('review_feedback')}")
                print(f"Loop Count: {node_state.get('loop_count')}")
            elif node_name == "emergency_brake":
                print(f"Emergency Brake Activated!")
                
    print("\n================ FINAL OUTPUT ================")
    print(current_state.get("draft_response", "No response generated."))
    print(f"Final Frontend Payload: {current_state.get('frontend_payload')}")
    print("==============================================\n")

if __name__ == "__main__":
    # Test A: Pre-Execution Guardrail (Pydantic Field Block)
    # The LLM will try to use find_geomarketing_gaps with radius_km=50000. 
    # Pydantic will block it (max 100), the tool will return an error string,
    # the LLM will generate an error draft, the Reviewer's Python sensor will see tool_payload={},
    # reject it, and loop it until Emergency Brake.
    run_test(
        "TEST A (Pre-Execution Guardrail)", 
        "Find geomarketing gaps with target income 75000 and radius of 50,000km."
    )
    
    # Test B: Post-Execution Sensor & Emergency Brake
    # The LLM will pass valid parameters (e.g. radius_km=10), but target_income is so high 
    # (or location so weird) that the mocked DB returns an empty viable_tracts array.
    # The sensor catches it, rejects, loops 3 times, triggers brake.
    run_test(
        "TEST B (Emergency Brake Loop)", 
        "Find geomarketing gaps with an absurd target income of 999999999."
    )
