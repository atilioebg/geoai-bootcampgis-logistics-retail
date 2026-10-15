"""
Integration tests for the ORM Spatial CRUD Workflow.
"""
import pytest
from sqlalchemy.orm import Session
from sqlalchemy import text
from geoalchemy2.elements import WKBElement
from src.agent.db_engine import DBEngine, CoffeeShop, Base

@pytest.fixture(scope="module")
def db_engine():
    """Module-level fixture to initialize engine and tables."""
    db = DBEngine()
    db.init_extensions()
    engine = db.get_engine()
    # Ensure a clean state
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    return engine

@pytest.fixture
def session(db_engine):
    """Provides a fresh session for each test."""
    with Session(db_engine) as session:
        yield session
        # Rollback after each test to keep DB clean
        session.rollback()

def test_insert_coffee_shop(session):
    """Test inserting a new spatial record."""
    new_shop = CoffeeShop(name='TestCafe', geom='SRID=4326;POINT(-82.0 27.0)')
    session.add(new_shop)
    session.commit()
    
    # Query back
    shop = session.query(CoffeeShop).filter_by(name='TestCafe').first()
    assert shop is not None
    assert shop.id is not None
    assert isinstance(shop.geom, WKBElement)

def test_update_coffee_shop(session):
    """Test updating an existing spatial record."""
    # Setup
    shop = CoffeeShop(name='OldName', geom='SRID=4326;POINT(0 0)')
    session.add(shop)
    session.commit()
    
    # Update
    shop_to_update = session.query(CoffeeShop).filter_by(name='OldName').first()
    shop_to_update.name = 'NewName'
    session.commit()
    
    # Verify
    updated_shop = session.query(CoffeeShop).filter_by(name='NewName').first()
    assert updated_shop is not None
    assert updated_shop.name == 'NewName'

def test_delete_coffee_shop(session):
    """Test deleting a spatial record."""
    # Setup
    shop = CoffeeShop(name='DeleteMe', geom='SRID=4326;POINT(0 0)')
    session.add(shop)
    session.commit()
    
    # Delete
    shop_to_delete = session.query(CoffeeShop).filter_by(name='DeleteMe').first()
    session.delete(shop_to_delete)
    session.commit()
    
    # Verify
    deleted_shop = session.query(CoffeeShop).filter_by(name='DeleteMe').first()
    assert deleted_shop is None

def test_orm_sql_injection_prevention(session):
    """
    Test that SQLAlchemy ORM safely binds parameters, preventing SQL injection 
    even if malicious strings are used in fields.
    """
    malicious_name = "'; DROP TABLE coffee_shops;--"
    
    # Attempt to insert a malicious name
    hacker_shop = CoffeeShop(name=malicious_name, geom='SRID=4326;POINT(0 0)')
    session.add(hacker_shop)
    session.commit()
    
    # Query it back
    safe_shop = session.query(CoffeeShop).filter_by(name=malicious_name).first()
    
    # The record should exist with the literal malicious string, 
    # and the table should NOT be dropped.
    assert safe_shop is not None
    assert safe_shop.name == malicious_name
    
    # Prove the table still exists by counting records
    count = session.query(CoffeeShop).count()
    assert count >= 1
