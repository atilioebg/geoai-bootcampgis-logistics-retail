"""
Database Connection Manager using SQLAlchemy.

This module provides:
  - DBEngine: Connection pool manager with PostGIS/pgvector/AGE extension init.
  - load_context_once: One-shot live schema + business_rules loader for LLM injection.
"""
import json
from typing import Optional

from sqlalchemy import create_engine, inspect, text, Column, Integer, String
from sqlalchemy.orm import Session, declarative_base
from sqlalchemy.exc import SQLAlchemyError
from geoalchemy2 import Geometry
from src.agent.config import settings

Base = declarative_base()

class CoffeeShop(Base):
    __tablename__ = 'coffee_shops'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    geom = Column(Geometry('POINT', srid=4326))

class DBEngine:
    """Manages robust connection pooling to PostgreSQL/PostGIS."""
    
    def __init__(self):
        """Initializes the database engine with connection pooling."""
        try:
            self.engine = create_engine(
                settings.database_url,
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,
                pool_recycle=3600
            )
        except Exception as e:
            print(f"Error initializing DB Engine: {e}")
            raise
            
    def init_extensions(self):
        """
        Activates all required extensions (postgis, vector, age).
        Crucially uses AUTOCOMMIT isolation level for Apache AGE compatibility.
        """
        queries = [
            "CREATE EXTENSION IF NOT EXISTS postgis;",
            "CREATE EXTENSION IF NOT EXISTS vector;",
            "CREATE EXTENSION IF NOT EXISTS age;",
            "LOAD 'age';",
            "SET search_path = ag_catalog, public;"
        ]
        
        try:
            with self.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                for query in queries:
                    conn.execute(text(query))
        except SQLAlchemyError as e:
            print(f"Failed to initialize extensions: {e}")
            raise
            
    def get_engine(self):
        return self.engine

    def load_context_once(self) -> str:
        """Load and cache the live database schema + business rules for LLM injection.

        Uses the PostgreSQL system catalog (pg_description) to extract column
        names, data types, and official descriptions for all 3 core tables.
        Also queries the business_rules table for domain configuration rules.

        The result is formatted into a structured string and cached at the class
        level. Subsequent calls across any DBEngine instance return the cached
        value without hitting the database, ensuring agent boot is fast.

        Returns:
            str: Formatted context string containing table schemas and business
                 rules, ready to be injected into agent system prompts.
        """
        return load_context_once(self)


# ── Module-level cache ─────────────────────────────────────────────────────────
# Shared across all DBEngine instances. The database is queried exactly once
# per process lifetime. Reset to None in tests via direct assignment.
_context_cache: Optional[str] = None

# Core tables that form the GeoAI knowledge base
_CORE_TABLES: dict[str, str] = {
    "demographics_acs_tract_tampa_2023": "ACS 5-Year Estimates — Hillsborough County / Tampa, FL (2023)",
    "gmap_reviews_enriched":             "Google Maps POI Reviews — NLP + Llama 3.2 semantic enrichment (FL, 2020+)",
    "gmap_places":                       "Google Maps Places — Spatial Dimension (Points, EPSG:4326)",
}

_COLUMN_QUERY = text("""
    SELECT
        a.attname                                   AS column_name,
        format_type(a.atttypid, a.atttypmod)        AS data_type,
        COALESCE(d.description, '[No description]') AS description
    FROM pg_class c
    JOIN pg_attribute a
        ON  a.attrelid = c.oid
        AND a.attnum   > 0
        AND NOT a.attisdropped
    LEFT JOIN pg_description d
        ON  d.objoid   = c.oid
        AND d.objsubid = a.attnum
    WHERE c.relname = :table_name
      AND c.relkind = 'r'
    ORDER BY a.attnum;
""")


def load_context_once(db_instance: "DBEngine") -> str:
    """Load and cache the live database schema + business rules for LLM injection.

    Queries pg_description and the business_rules table to build a structured
    context string. The result is cached in the module-level _context_cache so
    the database is only hit once per process, regardless of how many agents
    or DBEngine instances are active.

    This function is exposed both as a standalone callable and via the
    DBEngine.load_context_once() instance method (which delegates here).

    Args:
        db_instance: An initialized DBEngine whose get_engine() provides the pool.

    Returns:
        str: Formatted context string with table schemas (column names, types,
             and pg_description comments) and all business_rules records.
             Returns a graceful message if the database is unreachable.
    """
    global _context_cache
    if _context_cache is not None:
        return _context_cache

    engine = db_instance.get_engine()
    lines: list[str] = [
        "=== GeoAI DATABASE SCHEMA CONTEXT ===",
        "Source: Live pg_description + business_rules table (PostgreSQL/PostGIS)\n",
    ]

    try:
        with engine.connect() as conn:
            # Dynamically discover all spatial_tiger tables
            try:
                tiger_tables = conn.execute(
                    text("SELECT tablename FROM pg_tables WHERE tablename LIKE 'spatial_tiger_%' ORDER BY tablename;")
                ).scalars().all()
            except Exception:
                tiger_tables = []
                
            all_tables = list(_CORE_TABLES.keys()) + tiger_tables

            # ── Table schemas ──────────────────────────────────────────────────
            for table_name in all_tables:
                if table_name in _CORE_TABLES:
                    table_desc = _CORE_TABLES[table_name]
                else:
                    layer_name = table_name.replace("spatial_tiger_71000_", "").upper()
                    table_desc = f"TIGER/Line Shapefile Layer: {layer_name} (clipped to Tampa city limits)"
                    
                lines.append(f"--- TABLE: {table_name} ---")
                lines.append(f"({table_desc})")
                try:
                    result = conn.execute(_COLUMN_QUERY, {"table_name": table_name})
                    rows = result.fetchall()
                    if not rows:
                        lines.append("  [Table not yet created — populate via the ETL pipeline]\n")
                        continue
                    for row in rows:
                        lines.append(
                            f"  • {row.column_name:<38} [{row.data_type}]:"
                            f" {row.description}"
                        )
                except Exception:
                    lines.append("  [Table not yet created — populate via the ETL pipeline]\n")
                lines.append("")

            # ── Business rules ─────────────────────────────────────────────────
            lines.append("--- BUSINESS RULES (business_rules) ---")
            try:
                rules = conn.execute(
                    text("SELECT rule_key, rule_value_json FROM business_rules ORDER BY rule_key;")
                ).fetchall()
                if not rules:
                    lines.append("  [No business rules seeded yet — run apply_db_metadata.py]\n")
                else:
                    for rule in rules:
                        lines.append(f"  Rule Key: {rule.rule_key}")
                        value = (
                            rule.rule_value_json
                            if isinstance(rule.rule_value_json, dict)
                            else json.loads(rule.rule_value_json)
                        )
                        lines.append(f"  Value: {json.dumps(value, indent=4)}")
                        lines.append("")
            except Exception:
                lines.append("  [business_rules table not yet created — run apply_db_metadata.py]\n")

            # ── Dynamic Enum Extraction ────────────────────────────────────────
            lines.append("--- CATEGORICAL ENUMS (gmap_reviews_enriched) ---")
            lines.append("Valid Enums (Use EXACTLY as written below):")
            try:
                # Extract Price Levels
                price_levels = conn.execute(text(
                    "SELECT DISTINCT price_level FROM gmap_reviews_enriched WHERE price_level IS NOT NULL ORDER BY price_level;"
                )).scalars().all()
                if price_levels:
                    lines.append(f"  • price_level: {price_levels}")
                
                # Extract Categories (Top 100 for token efficiency)
                categories = conn.execute(text(
                    "SELECT category, COUNT(*) as cnt FROM gmap_reviews_enriched WHERE category IS NOT NULL GROUP BY category ORDER BY cnt DESC LIMIT 100;"
                )).fetchall()
                if categories:
                    cat_list = [row.category for row in categories]
                    lines.append(f"  • category: {cat_list}")
            except Exception as e:
                lines.append(f"  [Failed to load dynamic enums: {e}]\n")
            lines.append("")

    except Exception as exc:
        lines.append(f"[WARNING] Could not load schema context from database: {exc}")
        lines.append("[WARNING] Agents will operate without live schema context.")

    lines.append("=== END SCHEMA CONTEXT ===")

    _context_cache = "\n".join(lines)
    return _context_cache


if __name__ == "__main__":

    db = DBEngine()
    print("Connection Pool successfully initialized!")
    
    # 1. Initialize extensions before using spatial types
    db.init_extensions()
    print("Extensions initialized successfully.")
    
    # 2. Create tables
    engine = db.get_engine()
    Base.metadata.create_all(engine)
    print("Table 'coffee_shops' ensured in database.")
    
    with Session(engine) as session:
        # Step 1: Insert
        print("\n--- Step 1: Insert ---")
        new_shop = CoffeeShop(name='GeoCafe', geom='SRID=4326;POINT(-82.4572 27.9506)')
        session.add(new_shop)
        session.commit()
        print(f"Inserted: {new_shop.name}")
        
        # Step 2: Update
        print("\n--- Step 2: Update ---")
        shop = session.query(CoffeeShop).filter_by(name='GeoCafe').first()
        if shop:
            shop.name = 'GeoCafe Premium'
            session.commit()
            print(f"Updated name to: {shop.name}")
            
        # Step 3: Delete
        print("\n--- Step 3: Delete ---")
        shop_to_delete = session.query(CoffeeShop).filter_by(name='GeoCafe Premium').first()
        if shop_to_delete:
            # Get raw WKT geometry using ST_AsText
            wkt_geom = session.scalar(shop_to_delete.geom.ST_AsText())
            print(f"Deleting Shop ID: {shop_to_delete.id}, Geometry: {wkt_geom}")
            session.delete(shop_to_delete)
            session.commit()
            print("Shop successfully deleted.")
