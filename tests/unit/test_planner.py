"""
Unit tests for the Planner Node.
"""
import pytest
from unittest.mock import patch
from src.agent.swarm_state import SwarmState
from src.agent.agents.planner import planner_node, PlannerOutput

@patch("src.agent.agents.planner.planner_llm")
def test_planner_node_single_intent(mock_planner_llm):
    """Test that the planner correctly extracts a single logistics tool intent."""
    mock_planner_llm.invoke.return_value = PlannerOutput(plan=["calculate_optimal_logistics_hub"])
    
    state: SwarmState = {
        "question": "Where should we place our distribution center in Texas?",
        "plan": [], "draft_response": "", "review_feedback": "", "review_status": "", "loop_count": 0
    }
    
    result = planner_node(state)
    
    assert "plan" in result
    assert isinstance(result["plan"], list)
    assert len(result["plan"]) == 1
    assert result["plan"][0] == "calculate_optimal_logistics_hub"

@patch("src.agent.agents.planner.planner_llm")
def test_planner_node_multi_intent(mock_planner_llm):
    """Test that the planner correctly extracts multiple tool intents for complex questions."""
    mock_planner_llm.invoke.return_value = PlannerOutput(
        plan=["find_geomarketing_gaps", "search_semantic_reviews"]
    )
    
    state: SwarmState = {
        "question": "Find a blue ocean territory and also search for cozy cafes nearby.",
        "plan": [], "draft_response": "", "review_feedback": "", "review_status": "", "loop_count": 0
    }
    
    result = planner_node(state)
    
    assert "plan" in result
    assert len(result["plan"]) == 2
    assert "find_geomarketing_gaps" in result["plan"]
    assert "search_semantic_reviews" in result["plan"]
