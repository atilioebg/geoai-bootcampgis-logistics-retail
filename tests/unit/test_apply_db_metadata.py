"""
Unit tests for the GeoAI Cognitive Blueprint — load_context_once() and apply_db_metadata.

Tests verify:
    (a) load_context_once() returns a non-empty string.
    (b) The returned context contains at least one known column from each of the
        3 core tables (demographics_acs, spatial_tiger, gmap_reviews_enriched).
    (c) The returned context contains the 'us_income_brackets' business rules key.

All tests mock the database engine to avoid requiring a live PostGIS connection.
The module-level _context_cache is reset before each test to guarantee isolation.
"""

import json
import pytest
from unittest.mock import MagicMock, patch

import src.agent.db_engine as db_engine_module
from src.agent.db_engine import DBEngine, load_context_once


# ── Fixtures & Helpers ─────────────────────────────────────────────────────────

def _make_col_row(column_name: str, data_type: str = "numeric", description: str = "Test column."):
    """Build a mock SQLAlchemy result row for a table column query."""
    row = MagicMock()
    row.column_name = column_name
    row.data_type   = data_type
    row.description = description
    return row


def _make_rule_row(rule_key: str, rule_value: dict):
    """Build a mock SQLAlchemy result row for a business_rules query."""
    row = MagicMock()
    row.rule_key          = rule_key
    row.rule_value_json   = rule_value   # simulate psycopg2 already returning a dict
    return row


def _build_mock_engine(col_rows: list, rule_rows: list) -> MagicMock:
    """Build a fully mocked SQLAlchemy engine with controlled query results.

    The engine's connect() context manager returns a mock connection whose
    execute() method uses side_effect to return different results for the
    4 expected queries (3 table columns + 1 business_rules).

    Args:
        col_rows:  Rows to return for each table column query (same list reused).
        rule_rows: Rows to return for the business_rules query.

    Returns:
        MagicMock engine configured for use with load_context_once().
    """
    mock_engine = MagicMock()
    mock_conn   = MagicMock()

    col_result  = MagicMock()
    col_result.fetchall.return_value = col_rows

    rule_result = MagicMock()
    rule_result.fetchall.return_value = rule_rows

    # 4 execute() calls: demographics_acs, spatial_tiger, gmap_reviews_enriched, business_rules
    mock_conn.execute.side_effect = [
        col_result,   # demographics_acs columns
        col_result,   # spatial_tiger columns
        col_result,   # gmap_reviews_enriched columns
        rule_result,  # business_rules
    ]

    # Wire the context manager
    mock_engine.connect.return_value.__enter__.return_value = mock_conn
    mock_engine.connect.return_value.__exit__.return_value = False

    return mock_engine


@pytest.fixture(autouse=True)
def reset_context_cache():
    """Reset the module-level cache before every test for complete isolation."""
    db_engine_module._context_cache = None
    yield
    db_engine_module._context_cache = None


# ── Test (a): load_context_once() returns a non-empty string ──────────────────

def test_load_context_once_returns_non_empty_string():
    """load_context_once() must return a non-empty string under any DB state."""
    col_rows  = [_make_col_row("median_household_income")]
    rule_rows = [_make_rule_row("us_income_brackets", {"low_income": {"max_usd": 29999}})]
    mock_engine = _build_mock_engine(col_rows, rule_rows)

    db = DBEngine.__new__(DBEngine)  # Bypass __init__ to avoid real DB connection
    db.engine = mock_engine

    with patch.object(db, "get_engine", return_value=mock_engine):
        result = load_context_once(db)

    assert isinstance(result, str), "load_context_once() must return a string."
    assert len(result.strip()) > 0, "load_context_once() must not return an empty string."
    assert "=== GeoAI DATABASE SCHEMA CONTEXT ===" in result


# ── Test (b): Context contains columns from all 3 core tables ─────────────────

def test_load_context_once_contains_core_table_columns():
    """Context string must contain at least one known column from each of the 3 core tables."""
    # We return different rows per table by varying side_effect
    mock_engine = MagicMock()
    mock_conn   = MagicMock()

    acs_rows = [_make_col_row("median_household_income", "numeric",
                               "[ACS B19013_001E] Median household income.")]
    tiger_rows = [_make_col_row("state_fips", "text",
                                 "State FIPS code — 2-digit numeric code.")]
    gmap_rows = [_make_col_row("avg_rating", "numeric",
                                "Average star rating of the business (1.0-5.0 scale).")]
    rule_rows = [_make_rule_row("us_income_brackets",
                                {"low_income": {"max_usd": 29999}})]

    col_results  = [MagicMock(), MagicMock(), MagicMock()]
    col_results[0].fetchall.return_value = acs_rows
    col_results[1].fetchall.return_value = tiger_rows
    col_results[2].fetchall.return_value = gmap_rows
    rule_result = MagicMock()
    rule_result.fetchall.return_value = rule_rows

    mock_conn.execute.side_effect = [
        col_results[0],  # demographics_acs
        col_results[1],  # spatial_tiger
        col_results[2],  # gmap_reviews_enriched
        rule_result,     # business_rules
    ]
    mock_engine.connect.return_value.__enter__.return_value = mock_conn
    mock_engine.connect.return_value.__exit__.return_value = False

    db = DBEngine.__new__(DBEngine)
    db.engine = mock_engine

    with patch.object(db, "get_engine", return_value=mock_engine):
        context = load_context_once(db)

    # (b1) demographics_acs
    assert "median_household_income" in context, (
        "Context must contain 'median_household_income' from demographics_acs."
    )
    # (b2) spatial_tiger
    assert "state_fips" in context, (
        "Context must contain 'state_fips' from spatial_tiger."
    )
    # (b3) gmap_reviews_enriched
    assert "avg_rating" in context, (
        "Context must contain 'avg_rating' from gmap_reviews_enriched."
    )


# ── Test (c): Context contains the us_income_brackets business rules key ──────

def test_load_context_once_contains_business_rules_key():
    """Context string must contain the 'us_income_brackets' business rules key."""
    income_brackets = {
        "low_income":    {"label": "Low Income",    "min_usd": 0,     "max_usd": 29999},
        "middle_class":  {"label": "Middle Class",  "min_usd": 30000, "max_usd": 80000},
        "upper_class":   {"label": "Upper Class",   "min_usd": 80001, "max_usd": None},
    }

    col_rows  = [_make_col_row("geoid")]
    rule_rows = [_make_rule_row("us_income_brackets", income_brackets)]
    mock_engine = _build_mock_engine(col_rows, rule_rows)

    db = DBEngine.__new__(DBEngine)
    db.engine = mock_engine

    with patch.object(db, "get_engine", return_value=mock_engine):
        context = load_context_once(db)

    assert "us_income_brackets" in context, (
        "Context must contain the 'us_income_brackets' business rules key."
    )
    # Also validate that the income bracket labels are present
    assert "Low Income" in context,   "Context must contain 'Low Income' bracket label."
    assert "Middle Class" in context, "Context must contain 'Middle Class' bracket label."
    assert "Upper Class" in context,  "Context must contain 'Upper Class' bracket label."


# ── Test (bonus): Cache is populated after first call ─────────────────────────

def test_load_context_once_is_cached_after_first_call():
    """The module-level cache must be populated after the first call so subsequent
    calls don't hit the database again."""
    col_rows  = [_make_col_row("median_household_income")]
    rule_rows = [_make_rule_row("us_income_brackets", {})]
    mock_engine = _build_mock_engine(col_rows, rule_rows)

    db = DBEngine.__new__(DBEngine)
    db.engine = mock_engine

    with patch.object(db, "get_engine", return_value=mock_engine):
        result_first  = load_context_once(db)
        result_second = load_context_once(db)  # Should return from cache

    assert result_first is result_second, (
        "Subsequent calls to load_context_once() must return the exact same cached object."
    )
    # engine.connect() should have been called only once
    assert mock_engine.connect.call_count == 1, (
        "Database connect() must only be called once regardless of how many times "
        "load_context_once() is invoked."
    )
