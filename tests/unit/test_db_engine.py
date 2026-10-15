"""
Unit and Security Tests for DBEngine and SQLAlchemy Integrations.
"""
import pytest
from sqlalchemy import text
from src.agent.db_engine import DBEngine

@pytest.fixture
def db():
    """Fixture to provide a DBEngine instance."""
    return DBEngine()

def test_db_engine_initialization(db):
    """Test that the DB engine initializes and exposes connection pooling."""
    engine = db.get_engine()
    assert engine is not None
    # Verify pool size configuration matches our robust settings
    assert engine.pool.size() == 10

def test_sql_injection_prevention(db):
    """
    SECURITY TEST: Validate that using SQLAlchemy text() with bind parameters 
    successfully prevents SQL injection attacks.
    We pass a malicious string (a classic DROP TABLE attack) and ensure 
    it is treated purely as a string literal value by the database engine,
    rather than executable SQL commands.
    """
    malicious_input = "'; DROP TABLE users;--"
    
    # Simple query to echo back the input
    query = text("""
        SELECT :user_input AS safe_output
    """)
    
    # If injection was possible, this would attempt to execute DROP TABLE
    with db.get_engine().connect() as conn:
        result = conn.execute(query, {"user_input": malicious_input}).fetchone()
        
    # The database simply echoes back the exact malicious string as a safe value.
    # This proves parameter binding is functioning correctly.
    assert result is not None
    assert result[0] == malicious_input
