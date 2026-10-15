"""
GeoAI Swarm - Reviewer Node.

Graph Flow:
The Reviewer is the critic of the swarm. It evaluates the Worker's draft response 
against the user's original question. It forms a self-healing loop with the Worker, 
acting as a strict manager to guarantee correction within a maximum of 3 retries.
"""
import sys
import os
from enum import Enum
from pydantic import BaseModel, Field

# Ensure the root project directory is on the path so 'src' can be imported when running directly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

from src.agent.swarm_state import SwarmState
from src.agent.config import settings
from src.agent.db_engine import DBEngine

class ReviewStatus(str, Enum):
    approved = "approved"
    rejected = "rejected"

class ReviewerOutput(BaseModel):
    """Output schema for the Reviewer agent."""
    review_status: ReviewStatus = Field(description="The status of the review: 'approved' or 'rejected'.")
    review_feedback: str = Field(description="Highly specific feedback or instructions for the worker to fix the draft. Leave empty if approved.")

REVIEWER_SYSTEM_PROMPT = """You are the Senior GeoAI Manager and Reviewer for an Actor-Critic Swarm.
Your sole responsibility is to evaluate if the Worker's draft response successfully answers the user's original question.

You are part of a self-healing loop with a MAXIMUM of 3 retries. You must be a strict manager. 
If the draft response is inadequate, inaccurate, or missing key information, you MUST reject it and provide HIGHLY SPECIFIC feedback to guarantee correction on the next iteration.
If the draft response is excellent and fully answers the user's question, you must approve it.

<reviewer_guardrails>
- REJECT if the Worker failed to return coordinates AND the user explicitly asked for a specific place (do not reject aggregate queries).
- REJECT if the Worker hallucinates non-existent tables or tools.
- DO NOT demand that the Worker output or execute raw SQL queries. The Worker uses internal Python tools to interact with the database. If the Worker's draft logically answers the question and cites reasonable metrics, approve it.
</reviewer_guardrails>
"""

llm = ChatGoogleGenerativeAI(model=settings.llm_model)
reviewer_llm = llm.with_structured_output(ReviewerOutput)

def _validate_gis_agent(tool_output: dict) -> list[str]:
    """
    Deterministic Python sensor for validating spatial tool payloads.
    Guarantees predictable safety harness behavior without LLM hallucination.
    """
    errors = []
    if not tool_output:
        errors.append("Validation Error: No spatial tool was executed (tool_payload is empty).")
        return errors
        
    # Check for execution failure
    status = tool_output.get("status")
    if status != "success":
        errors.append(f"Validation Error: Tool execution failed with status '{status}'.")
        
    if "lat" in tool_output and tool_output["lat"] is None:
        errors.append("Validation Error: Missing coordinates in spatial result.")
        
    return errors

def reviewer_node(state: SwarmState) -> dict:
    """
    Evaluates the tool payload (deterministic sensor) and draft response (LLM).
    Increments the loop_count by 1.
    """
    tool_payload = state.get("tool_payload", {})
    current_loops = state.get("loop_count", 0)
    plan = state.get("plan", [])
    
    # 1. Deterministic Pre-Check (Safety Harness)
    # Only trigger the strict spatial sensor if the Planner actually assigned tools.
    if plan:
        validation_errors = _validate_gis_agent(tool_payload)
        if validation_errors:
            return {
                "review_status": "rejected",
                "review_feedback": "\n".join(validation_errors),
                "loop_count": current_loops + 1
            }
        
    # 2. Non-Deterministic Semantic Review (LLM Critique)
    question = state.get("question", "")
    draft = state.get("draft_response", "")
    context = f"User Question: {question}\nWorker's Draft Response: {draft}"
    
    messages = [
        SystemMessage(content=REVIEWER_SYSTEM_PROMPT),
        HumanMessage(content=context)
    ]
    
    result: ReviewerOutput = reviewer_llm.invoke(messages)
    
    output = {
        "review_status": result.review_status.value,
        "review_feedback": result.review_feedback,
        "loop_count": current_loops + 1
    }
    
    # Overwrite frontend payload ONLY on complete success
    if result.review_status.value == "approved":
        output["frontend_payload"] = tool_payload
        
    return output
