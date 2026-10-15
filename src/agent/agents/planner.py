"""
GeoAI Swarm - Planner Node.

Graph Flow:
The Planner is the absolute entry point of the swarm. It receives the user question 
exactly once, generates the plan (a list of tools to use), and passes control forward. 
It never receives feedback or loops back (the cyclical loop happens only between 
Worker and Reviewer).
"""
import os
import sys
from typing import List

# Ensure the root project directory is on the path so 'src' can be imported when running directly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from src.agent.tools.spatial_tools import calculate_optimal_logistics_hub, find_geomarketing_gaps
from src.agent.tools.api_tools import get_route_distance_time
from src.agent.tools.rag_tools import semantic_search_tool, knowledge_graph_tool

from src.agent.swarm_state import SwarmState
from src.agent.config import settings
from src.agent.db_engine import DBEngine

load_dotenv()

# Ensure we have the API key available in the environment
if "GOOGLE_API_KEY" not in os.environ:
    os.environ["GOOGLE_API_KEY"] = settings.google_api_key.split("#")[0].strip()

# 2. Pydantic Schema for Structured Output
class PlannerOutput(BaseModel):
    """Output schema for the Planner agent."""
    reasoning: str = Field(
        description="Think step-by-step about what tools are needed and why. Extract necessary entities."
    )
    plan: List[str] = Field(
        description="A list of tool names required to answer the user's question."
    )

# 4. Planner System Prompt
PLANNER_SYSTEM_PROMPT = """You are the Senior GeoAI Planner for an Actor-Critic Swarm.
Your job is to analyze the user's spatial question and break it down into a clear, step-by-step execution plan for the Worker agent.

You have access to the following spatial tools. You MUST specify in your plan which tool(s) should be used:
1. `calculate_optimal_logistics_hub`: Use this for logistics problems, finding optimal distribution centers, or counting POIs within a radius of a road network.
2. `find_geomarketing_gaps`: Use this for geomarketing expansion, finding ZIP codes with high-income tracts and competitor intersections.
3. `get_route_distance_time`: Use this when asked for driving duration or distances between a specific origin and destination.
4. `semantic_search_tool`: Use this for subjective vibe/intent-based searches using vector embeddings.
5. `knowledge_graph_tool`: Use this to filter POIs by exact categories (cuisine, audience, price_level, etc.) via Apache AGE graph traversals.

<few_shot_examples>
[
    {
        "user": "Where is a good spot to open a luxury car dealership targeting high-income professionals with low nearby competition?",
        "output": {"reasoning": "Step 1: Extract the category ('car dealership') and demographic ('high-income'). Step 2: Pass these to find_geomarketing_gaps to execute a spatial anti-join (gaps) against existing competitors in wealthy block groups. Step 3: The tool returns the optimal gap polygons.", "plan": ["find_geomarketing_gaps"]}
    },
    {
        "user": "Calculate the POI density along I-4 within 5 miles to see if it's a good logistics route.",
        "output": {"reasoning": "Step 1: Extract the infrastructure name ('I-4') and radius ('5 miles'). Step 2: Use calculate_optimal_logistics_hub to generate a 5-mile spatial buffer along the highway centerline. Step 3: The tool calculates POI density within that buffer and returns the catchment GeoJSON.", "plan": ["calculate_optimal_logistics_hub"]}
    },
    {
        "user": "Show me a list of expensive restaurants.",
        "output": {"reasoning": "Step 1: Extract categorical entities (place_type='restaurant', price_level='expensive'). Step 2: Use knowledge_graph_tool to traverse the Apache AGE graph for exact semantic matches. Step 3: The tool retrieves the nodes and joins with gmap_places to ensure the payload has map-ready coordinates.", "plan": ["knowledge_graph_tool"]}
    },
    {
        "user": "Find a quiet and romantic place to eat for a date night, and check the driving time from there to the nearest highway.",
        "output": {"reasoning": "Step 1: Extract the vibe ('quiet and romantic') and use semantic_search_tool to perform a vector search on reviews. Step 2: Extract the lat/lng coordinates of the best match from Step 1. Step 3: Pass those exact coordinates to get_route_distance_time to calculate the routing logistics to the highway.", "plan": ["semantic_search_tool", "get_route_distance_time"]}
    },
    {
        "user": "I want to open a new affordable restaurant. Find a neighborhood with a geomarketing gap where there is a high median income but a lack of existing affordable restaurants with great reviews.",
        "output": {"reasoning": "Step 1: Extract the category ('restaurant') and demographic ('high median income'). Step 2: Use find_geomarketing_gaps to identify ZIP codes with high income but few restaurants. Step 3: Use semantic_search_tool to search reviews in those areas for 'great reviews' to validate quality gaps. Step 4: Cross-reference both results to find the optimal neighborhood.", "plan": ["find_geomarketing_gaps", "semantic_search_tool"]}
    },
    {
        "user": "Evaluate the I-275 highway corridor within 5 miles for POI density, and calculate the driving time from that hub to Downtown.",
        "output": {"reasoning": "Step 1: Extract road name ('I-275'), radius ('5'), and unit ('miles'). Step 2: Use calculate_optimal_logistics_hub to generate a spatial buffer and calculate POI density. Step 3: Extract the hub centroid coordinates (hub_lat, hub_lng) from the logistics tool output. Step 4: Pass those coordinates as origin and the user's destination text to get_route_distance_time.", "plan": ["calculate_optimal_logistics_hub", "get_route_distance_time"]}
    }
]
</few_shot_examples>

Your output must be a Pydantic `PlannerOutput` containing your reasoning first, and then the list of strings representing the steps. 
Do NOT execute the tools yourself. Just create the plan.
"""

# ── Schema Context Injection ───────────────────────────────────────────────────
# Load live database schema and business rules once at module boot.
# This gives the Planner full knowledge of what columns and income brackets
# the Worker will operate on, enabling it to correctly route tool selection.
try:
    _db = DBEngine()
    _db_context = _db.load_context_once()
    PLANNER_SYSTEM_PROMPT = f"{PLANNER_SYSTEM_PROMPT}\n\n{_db_context}"
except Exception as _e:
    print(f"[Planner] Warning: Could not load DB schema context at boot: {_e}")

# Instantiate the LLM with structured output
llm = ChatGoogleGenerativeAI(model=settings.llm_model)
planner_llm = llm.with_structured_output(PlannerOutput)

# 3 & 5. Planner Node Definition
def planner_node(state: SwarmState) -> dict:
    """
    Analyzes the question and updates the state with the generated plan.
    """
    question = state.get("question", "")
    
    messages = [
        SystemMessage(content=PLANNER_SYSTEM_PROMPT),
        HumanMessage(content=question)
    ]
    
    # Generate structured output plan
    result: PlannerOutput = planner_llm.invoke(messages)
    
    return {"plan": result.plan}

# 6. Main Execution Block for standalone testing
if __name__ == "__main__":
    print("--- Testing Planner Node ---")
    mock_state: SwarmState = {
        "question": "Find the optimal logistics hub in Florida and also find the shortest path from it to Miami.",
        "plan": [],
        "draft_response": "",
        "review_feedback": "",
        "review_status": "",
        "loop_count": 0
    }
    
    print(f"User Question: {mock_state['question']}")
    print("Invoking Planner...")
    
    new_state = planner_node(mock_state)
    print(f"\nGenerated Plan (Tools to run):")
    for tool in new_state["plan"]:
        print(f" - {tool}")
