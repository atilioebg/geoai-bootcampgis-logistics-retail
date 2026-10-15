"""
GeoAI Tools for Semantic Search and Graph Traversals.
"""
import json
import sys
import os

# Ensure the root project directory is on the path so 'src' can be imported when running directly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from langchain_core.tools import tool
from sqlalchemy import text
from src.agent.db_engine import DBEngine
from sentence_transformers import SentenceTransformer

db = DBEngine()
# Initialize local embedding model for semantic search
model_name = os.getenv("EMBEDDING_MODEL", "BAAI/bge-large-en-v1.5")
model = SentenceTransformer(model_name)

@tool
def semantic_search_tool(vibe_intent: str, limit: int = 5, city_name: str = "Tampa") -> dict:
    """
    Handles Semantic Search, NLP, vibes, and similarity matching.
    Searches for locations that match a specific customer 'vibe' intent using vector embeddings.
    """
    embedding = model.encode(vibe_intent).tolist()
    
    # Query pgvector using cosine distance (<=>) with dynamic spatial boundary
    sql_query = text("""
        WITH city_boundary AS (
            SELECT geometry FROM spatial_tiger_71000_place WHERE feature_name = :city_name LIMIT 1
        ),
        bounded_places AS (
            SELECT p.gmap_id, p.geom 
            FROM gmap_places p, city_boundary cb
            WHERE ST_Intersects(p.geom, cb.geometry)
        )
        SELECT r.name_x, r.text_normalized, 
               ST_Y(ST_Transform(bp.geom, 4326)) AS lat,
               ST_X(ST_Transform(bp.geom, 4326)) AS lng,
               r.gmap_id,
               (r.embedding <=> CAST(:embedding AS vector)) AS distance
        FROM gmap_reviews_enriched r
        JOIN bounded_places bp ON r.gmap_id = bp.gmap_id
        ORDER BY distance ASC
        LIMIT :limit;
    """)
    
    bind_params = {"limit": limit, "embedding": str(embedding), "city_name": city_name}
    
    try:
        with db.get_engine().connect() as conn:
            result = conn.execute(sql_query, bind_params)
            rows = [dict(row._mapping) for row in result.fetchall()]
            
            # Map-ready payload constraints
            poi_ids = [row['gmap_id'] for row in rows]
            return {
                "status": "success", 
                "highlight_poi_ids": poi_ids,
                "results": rows
            }
    except Exception as e:
        return {"status": "error", "error": str(e)}

@tool
def knowledge_graph_tool(
    cuisine: str = None, 
    audience: str = None, 
    price_level: str = None, 
    place_type: str = None, 
    accessibility: str = None, 
    waterfront: str = None,
    city_name: str = "Tampa"
) -> dict:
    """
    Traverses the Apache AGE knowledge graph to filter Places based on exact categories.
    Do NOT write raw Cypher. Pass the extracted categories to this parameterized tool.
    """
    # Constructing a parameterized Cypher query with dynamic MATCH clauses
    # Using raw strings r"" and escaping colons \: to prevent SQLAlchemy parsing errors
    match_clauses = [r"MATCH (p\:Place)"]
    
    if price_level:
        match_clauses.append(fr"MATCH (p\:Place {{price_level: {json.dumps(price_level)}}})")
    if accessibility:
        match_clauses.append(fr"MATCH (p\:Place {{accessibility: {json.dumps(accessibility)}}})")
    if waterfront:
        match_clauses.append(fr"MATCH (p\:Place {{waterfront: {json.dumps(waterfront)}}})")
        
    if cuisine:
        match_clauses.append(fr"MATCH (p)-[\:SERVES]->(c\:Cuisine {{name: {json.dumps(cuisine)}}})")
    if audience:
        match_clauses.append(fr"MATCH (p)-[\:TARGETS]->(a\:Audience {{name: {json.dumps(audience)}}})")
    if place_type:
        match_clauses.append(fr"MATCH (p)-[\:IS_TYPE]->(t\:PlaceType {{name: {json.dumps(place_type)}}})")
        
    cypher_match = " ".join(match_clauses)
    
    # Cypher wrapped inside SQL to enrich spatial coordinates
    cypher_query = text(f"""
        WITH city_boundary AS (
            SELECT geometry FROM spatial_tiger_71000_place WHERE feature_name = :city_name LIMIT 1
        ),
        graph_results AS (
            SELECT TRIM(BOTH '"' FROM gmap_id::text) AS clean_id 
            FROM cypher('geoai_graph', $cypher$
                {cypher_match}
                RETURN p.gmap_id LIMIT 50
            $cypher$) AS (gmap_id agtype)
        )
        SELECT gr.clean_id AS gmap_id, r.name_x, r.category,
               ST_Y(ST_Transform(p.geom, 4326)) AS lat,
               ST_X(ST_Transform(p.geom, 4326)) AS lng
        FROM graph_results gr
        JOIN gmap_places p ON gr.clean_id = p.gmap_id
        JOIN gmap_reviews_enriched r ON gr.clean_id = r.gmap_id
        JOIN city_boundary cb ON ST_Intersects(p.geom, cb.geometry)
    """)
    
    bind_params = {"city_name": city_name}
    
    try:
        with db.get_engine().connect() as conn:
            # Must load Apache AGE extension for Cypher to work
            conn.execute(text("LOAD 'age';"))
            conn.execute(text("SET search_path = ag_catalog, \"$user\", public;"))
            
            result = conn.execute(cypher_query, bind_params)
            rows = [dict(row._mapping) for row in result.fetchall()]
            
            poi_ids = [row['gmap_id'] for row in rows]
            return {
                "status": "success", 
                "highlight_poi_ids": poi_ids,
                "results": rows
            }
    except Exception as e:
        return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    print("Testing RAG Tools Execution...")
    
    # Test Semantic Search
    print("\n--- Test: semantic_search_tool ---")
    semantic_result = semantic_search_tool.invoke({"vibe_intent": "A quiet and cozy cafe", "limit": 2})
    print(json.dumps(semantic_result, indent=2))
    
    # Test Knowledge Graph (Empty Result Expected due to ETL strings)
    print("\n--- Test: knowledge_graph_tool (Empty) ---")
    kg_result = knowledge_graph_tool.invoke({
        "cuisine": "Italian",
        "price_level": "$$"
    })
    print(json.dumps(kg_result, indent=2))
    
    # Test Knowledge Graph (Data Expected)
    print("\n--- Test: knowledge_graph_tool (Match) ---")
    kg_result_match = knowledge_graph_tool.invoke({
        "price_level": "affordable"
    })
    print(json.dumps(kg_result_match, indent=2))
