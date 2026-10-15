"""
High-Performance Graph Ingestion Pipeline using Server-Side Cursors and Cypher UNWIND.
"""
import sys
import os
import json
import subprocess
from tqdm import tqdm
from dotenv import load_dotenv

# Add project root to path for src.agent imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
from src.agent.db_engine import DBEngine

def dict_to_cypher_map(d):
    """Converts a Python dictionary to a Cypher-compatible map string (keys unquoted)."""
    parts = []
    for k, v in d.items():
        # json.dumps safely escapes strings and handles nulls
        val = json.dumps(v)
        parts.append(f"{k}: {val}")
    return "{" + ", ".join(parts) + "}"

def list_to_cypher_array(lst):
    """Converts a list of Python dictionaries to a Cypher array string."""
    return "[" + ", ".join(dict_to_cypher_map(d) for d in lst) + "]"

def main():
    load_dotenv()
    db = DBEngine()
    
    raw_conn = db.get_engine().raw_connection()
    
    try:
        with raw_conn.cursor() as count_cur:
            count_cur.execute("SELECT COUNT(*) FROM gmap_reviews_enriched;")
            total_rows = count_cur.fetchone()[0]
            
        print(f"Total rows to process: {total_rows}")
        
        batch_size = 5000
        output_sql_file = os.path.join(os.path.dirname(__file__), "05_bulk_load.sql")
        
        with open(output_sql_file, "w", encoding="utf-8") as sql_file:
            sql_file.write("LOAD 'age';\n")
            sql_file.write("SET search_path = ag_catalog, public;\n\n")
            
            # Named cursor allows server-side fetching
            with raw_conn.cursor(name='fetch_cursor') as extract_cur:
                extract_cur.itersize = batch_size
                extract_cur.execute("SELECT gmap_id, semantic_json FROM gmap_reviews_enriched;")
                
                with tqdm(total=total_rows, desc="Generating Bulk SQL") as pbar:
                    while True:
                        rows = extract_cur.fetchmany(batch_size)
                        if not rows:
                            break
                            
                        batch_data = []
                        for gmap_id, semantic_json in rows:
                            try:
                                # Handle string json or dict
                                if isinstance(semantic_json, str):
                                    clean_json = semantic_json.replace("'", '"') if semantic_json.startswith("{'") else semantic_json
                                    data = json.loads(clean_json)
                                elif isinstance(semantic_json, dict):
                                    data = semantic_json
                                else:
                                    continue
                                    
                                batch_data.append({
                                    "gmap_id": str(gmap_id),
                                    "price_level": str(data.get("price_level", "")),
                                    "accessibility": str(data.get("accessibility", "")),
                                    "waterfront": str(data.get("waterfront", "")),
                                    "cuisine": str(data.get("cuisine", "")),
                                    "audience": str(data.get("audience", "")),
                                    "place_type": str(data.get("place_type", ""))
                                })
                            except Exception:
                                # Skip invalid json rows
                                pass
                                
                        if batch_data:
                            cypher_array = list_to_cypher_array(batch_data)
                            
                            cypher_query = f"""
SELECT * FROM cypher('geoai_graph', $$
    UNWIND {cypher_array} AS row
    MERGE (p:Place {{gmap_id: row.gmap_id}})
    SET p.price_level = row.price_level, 
        p.accessibility = row.accessibility, 
        p.waterfront = row.waterfront
    
    MERGE (c:Cuisine {{name: row.cuisine}})
    MERGE (a:Audience {{name: row.audience}})
    MERGE (t:PlaceType {{name: row.place_type}})
    
    MERGE (p)-[:SERVES]->(c)
    MERGE (p)-[:TARGETS]->(a)
    MERGE (p)-[:IS_TYPE]->(t)
    RETURN count(p)
$$) AS (v agtype);
"""
                            sql_file.write(cypher_query + "\n")
                                
                        pbar.update(len(rows))
        
        raw_conn.commit()
        print(f"SQL file generated at: {output_sql_file}")
        
        print("Executing bulk load via psql...")
        
        # We need to copy the file to the container first
        subprocess.run(["docker", "cp", output_sql_file, "geostack-db-1:/tmp/05_bulk_load.sql"])
        
        result = subprocess.run([
            "docker", "exec", "geostack-db-1", "psql", "-U", "postgres", "-d", "bootcampgis",
            "-f", "/tmp/05_bulk_load.sql"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("Ingestion complete.")
        else:
            print(f"Error during ingestion execution: {result.stderr}")
            
    except Exception as e:
        raw_conn.rollback()
        print(f"Error during ingestion: {e}")
    finally:
        raw_conn.close()

if __name__ == "__main__":
    main()
