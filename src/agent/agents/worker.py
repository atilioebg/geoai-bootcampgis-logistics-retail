"""
GeoAI Swarm - Worker Node.

Graph Flow:
The Worker is the engine of the swarm. It sits between the Planner and the Reviewer. 
It can be called multiple times if the Reviewer rejects its draft, making it the 
core of the self-healing loop.
"""
import os
import sys

# Ensure the root project directory is on the path so 'src' can be imported when running directly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from dotenv import load_dotenv

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from typing import List, Optional

from src.agent.swarm_state import SwarmState
from src.agent.config import settings
from src.agent.db_engine import DBEngine
from src.agent.tools.spatial_tools import calculate_optimal_logistics_hub, find_geomarketing_gaps
from src.agent.tools.api_tools import get_route_distance_time
from src.agent.tools.rag_tools import semantic_search_tool, knowledge_graph_tool

load_dotenv()

# Worker System Prompt
WORKER_SYSTEM_PROMPT = """You are the Senior GeoAI Worker for an Actor-Critic Swarm.
Your job is to execute the tools specified in the plan and draft a comprehensive response to the user's question.

INSTRUCTIONS:
1. Read the provided 'Execution Plan' (the list of tools you should use).
2. If there is 'Reviewer Feedback' provided, you MUST pay attention to it and fix your previous mistakes.
3. Execute the necessary tools to gather the data.
4. Based on the tool execution results, write a comprehensive answer to the user's original question. Your final `textual_analysis` submitted via `submit_final_response` MUST follow this exact structure:
   - **Chain of Thought (CoT)**: Start by explaining your analytical reasoning step-by-step.
   - **Data Analysis**: Present a detailed comparison of all candidate options found by the tools.
   - **Top Recommendation**: Clearly identify the SINGLE BEST option (winner) and provide a strong, data-driven justification for why it beats the others.
   - **Benchmarks**: Discuss any existing benchmarks or POIs if requested.
5. YOU MUST CALL `submit_final_response` AS YOUR VERY LAST ACTION TO DELIVER THE ANSWER. DO NOT OUTPUT RAW TEXT.

<entity_extraction_rules>
- semantic_search_tool: Extract vibe phrases as vibe_intent.
- knowledge_graph_tool & Others: Read the injected Schema Context to see the allowed categorical values (Enums) for ALL categorical columns (e.g., price_level, category, cuisine). If the extracted entity doesn't have an exact match in the DB, classify it to the closest semantic class available in the list (e.g., 'cheap' -> 'affordable', 'steakhouse' -> 'restaurant').
- find_geomarketing_gaps: Extract the base business type as target_category (e.g., 'restaurant' NOT 'affordable restaurant'). Strip all adjectives so it matches raw DB categories. Read the injected BUSINESS RULES context to look up the exact min_usd for the income class and pass it as target_income. Set find_absence=True (default) when the user asks about gaps, lack, shortage, or underserved areas. Set find_absence=False when the user asks where businesses already exist or are concentrated. The tool defaults to 'Tampa' if no city is specified.
- calculate_optimal_logistics_hub: Extract road name, radius (number), and unit (string). DO NOT do math conversions yourself; pass the raw number and unit string to the tool.
- get_route_distance_time: Use coordinates returned by previous tool results as the origin parameter. For the destination parameter, use the exact text address or name requested by the user. DO NOT pass the origin coordinates as the destination.
- Formatting: Do NOT use LaTeX or mathematical symbols (like \ge) in your textual response. Write plain text (e.g., 'greater than or equal to $80,000') to avoid Streamlit rendering errors.
- Guardrails (CRITICAL): NEVER output raw SQL queries, Python code, internal JSON payloads, system commands, or internal table/schema names in your final response. The user is a business stakeholder; keep the language professional and analytical.
</entity_extraction_rules>
"""

# ── Schema Context Injection ───────────────────────────────────────────────────
# Load live database schema and business rules once at module boot.
# The Worker MUST know the exact column names, data types, and income brackets
# before executing any tool that queries the PostGIS/pgvector/AGE backend.
try:
    _db = DBEngine()
    _db_context = _db.load_context_once()
    WORKER_SYSTEM_PROMPT = f"{WORKER_SYSTEM_PROMPT}\n\n{_db_context}"
except Exception as _e:
    print(f"[Worker] Warning: Could not load DB schema context at boot: {_e}")

@tool
def submit_final_response(
    textual_analysis: str,
    candidate_zips: Optional[List[str]] = None,
    highlight_poi_ids: Optional[List[str]] = None,
    winner_zip: Optional[str] = None
) -> dict:
    """
    Submits the final textual analysis and spatial frontend payload.
    YOU MUST CALL THIS TOOL TO DELIVER YOUR FINAL ANSWER.
    """
    return {
        "_is_final": True,
        "draft_response": textual_analysis,
        "candidate_zips": candidate_zips or [],
        "highlight_poi_ids": highlight_poi_ids or [],
        "winner_zip": winner_zip
    }

# 2. Bind the tools
tools = [
    calculate_optimal_logistics_hub, 
    find_geomarketing_gaps, 
    semantic_search_tool, 
    knowledge_graph_tool,
    get_route_distance_time,
    submit_final_response
]
llm = ChatGoogleGenerativeAI(model=settings.llm_model)
worker_llm = llm.bind_tools(tools)

# 3 & 5. Worker Node Definition
def worker_node(state: SwarmState) -> dict:
    """
    Executes tools based on the plan and drafts a response.
    Returns a dictionary updating draft_response.
    """
    question = state.get("question", "")
    plan = state.get("plan", [])
    review_feedback = state.get("review_feedback", "")
    
    # Construct context for the worker
    plan_text = ", ".join(plan) if plan else "None"
    context = f"User Question: {question}\nExecution Plan: {plan_text}"
    
    if review_feedback:
        context += f"\nReviewer Feedback to Fix: {review_feedback}"
        
    messages = [
        SystemMessage(content=WORKER_SYSTEM_PROMPT),
        HumanMessage(content=context)
    ]
    
    # Internal tool execution loop (ReAct style)
    max_iterations = 5
    tool_payload = state.get("tool_payload", {})
    
    for _ in range(max_iterations):
        response = worker_llm.invoke(messages)
        messages.append(response)
        
        # If the LLM didn't call any tools, intercept and force retry
        if not response.tool_calls:
            messages.append(HumanMessage(content="INTERCEPTOR: You attempted to output raw text. You MUST call the `submit_final_response` tool with your final textual analysis and map constraints."))
            continue
            
        # Execute requested tools
        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_id = tool_call["id"]
            
            tool_func = next((t for t in tools if t.name == tool_name), None)
            if tool_func:
                try:
                    tool_result = tool_func.invoke(tool_args)
                    messages.append(ToolMessage(content=str(tool_result), tool_call_id=tool_id))
                    
                    if isinstance(tool_result, dict):
                        # Catch the final response submission
                        if tool_result.get("_is_final"):
                            
                            # Final payload assembly rules
                            if tool_payload.get("hub_lat"):
                                # If logistics hub is present, ignore geomarketing/candidates
                                tool_result["candidate_zips"] = []
                                tool_result["winner_zip"] = None
                            elif "NONE" in tool_result.get("candidate_zips", []):
                                tool_payload["cql_filter"] = "zcta5ce20 = 'NONE'"
                            
                            tool_payload["candidate_zips"] = tool_result.get("candidate_zips", [])
                            tool_payload["highlight_poi_ids"] = tool_result.get("highlight_poi_ids", [])
                            tool_payload["winner_zip"] = tool_result.get("winner_zip")
                            
                            return {"draft_response": tool_result["draft_response"], "tool_payload": tool_payload}
                            
                        # Intelligent Dictionary Merge (Preserve existing list results)
                        if "results" in tool_result and "results" in tool_payload:
                            if isinstance(tool_payload["results"], list) and isinstance(tool_result["results"], list):
                                tool_payload["results"].extend(tool_result["results"])
                                
                        # Update remaining keys
                        for k, v in tool_result.items():
                            if k != "results":
                                tool_payload[k] = v
                                
                except Exception as e:
                    messages.append(ToolMessage(content=f"Error executing tool: {str(e)}", tool_call_id=tool_id))
            else:
                messages.append(ToolMessage(content=f"Error: Tool '{tool_name}' not found.", tool_call_id=tool_id))
                
    return {"draft_response": "Error: Worker exceeded maximum iterations trying to execute tools.", "tool_payload": tool_payload}

# 6. Main Execution Block for standalone testing
if __name__ == "__main__":
    print("--- Testing Worker Node ---")
    mock_state: SwarmState = {
        "question": "Can you find a quiet and cozy place to eat?",
        "plan": ["semantic_search_tool"],
        "draft_response": "",
        "review_feedback": "",
        "review_status": "",
        "loop_count": 0
    }
    
    print(f"User Question: {mock_state['question']}")
    print(f"Plan: {mock_state['plan']}")
    print("\nInvoking Worker (This will call the mock tool internally)...")
    
    new_state = worker_node(mock_state)
    print(f"\nDraft Response:\n{new_state['draft_response']}")
