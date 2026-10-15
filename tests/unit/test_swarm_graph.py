import pytest
from src.agent.swarm_state import SwarmState
from src.agent.swarm_graph import route_from_reviewer, emergency_brake_node

def test_route_from_reviewer_retries():
    state = SwarmState(review_status="rejected", loop_count=1)
    next_node = route_from_reviewer(state)
    assert next_node == "worker"

def test_route_from_reviewer_emergency_brake():
    state = SwarmState(review_status="rejected", loop_count=3)
    next_node = route_from_reviewer(state)
    assert next_node == "emergency_brake"
    
def test_route_from_reviewer_approved():
    state = SwarmState(review_status="approved", loop_count=1)
    next_node = route_from_reviewer(state)
    from langgraph.graph import END
    assert next_node == END

def test_emergency_brake_node():
    state = SwarmState()
    result = emergency_brake_node(state)
    assert "SYSTEM ERROR" in result["draft_response"]
    assert "Emergency brake engaged" in result["draft_response"]
