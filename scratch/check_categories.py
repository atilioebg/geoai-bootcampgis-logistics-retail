from src.agent.db_engine import DBEngine
from sqlalchemy import text

db = DBEngine()
with db.get_engine().connect() as conn:
    res = conn.execute(text("SELECT category, COUNT(*) FROM gmap_reviews_enriched WHERE category ILIKE '%fine dining%' OR category ILIKE '%steak%' OR category ILIKE '%wine%' GROUP BY category ORDER BY COUNT(*) DESC LIMIT 20;"))
    for row in res:
        print(row)
