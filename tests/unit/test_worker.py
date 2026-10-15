"""
Unit tests for the Worker Node.
"""
import pytest
from unittest.mock import patch
from langchain_core.messages import AIMessage
from src.agent.swarm_state import SwarmState
from src.agent.agents.worker import worker_node

@patch("src.agent.agents.worker.worker_llm")
def test_worker_node_drafts_response(mock_worker_llm):
    """Test that the worker correctly outputs a draft response."""
    # Mock LLM responding directly with text (no tool calls)
    mock_worker_llm.invoke.return_value = AIMessage(content="This is the draft response.")
    
    state: SwarmState = {
        "question": "Where is the gap?",
        "plan": ["find_geomarketing_gaps"], 
        "draft_response": "", 
        "review_feedback": "", 
        "review_status": "", 
        "loop_count": 0
    }
    
    result = worker_node(state)
    
    assert "draft_response" in result
    assert result["draft_response"] == "This is the draft response."

@patch("src.agent.agents.worker.worker_llm")
def test_worker_node_with_feedback(mock_worker_llm):
    """Test that the worker handles reviewer feedback correctly."""
    mock_worker_llm.invoke.return_value = AIMessage(content="This is the updated draft response.")
    
    state: SwarmState = {
        "question": "Where is the gap?",
        "plan": ["find_geomarketing_gaps"], 
        "draft_response": "Old draft", 
        "review_feedback": "Please add more details about the income.", 
        "review_status": "REJECTED", 
        "loop_count": 1
    }
    
    result = worker_node(state)
    
    assert "draft_response" in result
    assert result["draft_response"] == "This is the updated draft response."
    
    # Verify feedback was included in the LLM call context
    call_args = mock_worker_llm.invoke.call_args[0][0]
    human_msg = call_args[1].content
    assert "Reviewer Feedback to Fix: Please add more details about the income." in human_msg
