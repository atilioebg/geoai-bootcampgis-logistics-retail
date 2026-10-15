import pytest
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../")))

from src.agent.agents.planner import planner_node, PlannerOutput
from src.agent.agents.worker import worker_node
from src.agent.swarm_state import SwarmState

@pytest.fixture
def base_state() -> SwarmState:
    return {
        "question": "",
        "plan": [],
        "draft_response": "",
        "review_feedback": "",
        "review_status": "",
        "loop_count": 0,
        "tool_payload": {},
        "frontend_payload": {}
    }

def test_planner_tool_selection_geomarketing(base_state):
    base_state["question"] = "Find a geomarketing gap for an affordable restaurant."
    new_state = planner_node(base_state)
    
    assert "plan" in new_state
    assert isinstance(new_state["plan"], list)
    assert len(new_state["plan"]) > 0
    assert "find_geomarketing_gaps" in new_state["plan"]

def test_planner_tool_selection_logistics(base_state):
    base_state["question"] = "Calculate the POI density along I-4 within 5 miles."
    new_state = planner_node(base_state)
    
    assert "plan" in new_state
    assert isinstance(new_state["plan"], list)
    assert len(new_state["plan"]) > 0
    assert "calculate_optimal_logistics_hub" in new_state["plan"]

def test_worker_draft_generation(base_state, monkeypatch):
    base_state["question"] = "Can you find a quiet and cozy place to eat?"
    base_state["plan"] = ["semantic_search_tool"]
    
    try:
        new_state = worker_node(base_state)
        assert "draft_response" in new_state
        assert "tool_payload" in new_state
    except Exception as e:
        pytest.fail(f"Worker node failed to execute: {e}")
