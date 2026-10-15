"""
Unit tests for RAG tools (Semantic Search & Knowledge Graph).
"""
import pytest
from unittest.mock import patch, MagicMock
from src.agent.tools.rag_tools import semantic_search_tool, knowledge_graph_tool, find_infrastructure_shortest_path
import json

@patch("src.agent.tools.rag_tools.db.get_engine")
@patch("src.agent.tools.rag_tools.model.encode")
def test_semantic_search_tool(mock_encode, mock_get_engine):
    """Test semantic search tool logic and query format."""
    mock_encode.return_value.tolist.return_value = [0.1, 0.2, 0.3]
    
    # Mocking SQLAlchemy connection and execution
    mock_conn = MagicMock()
    mock_get_engine.return_value.connect.return_value.__enter__.return_value = mock_conn
    mock_result = MagicMock()
    
    class RowMock:
        def __init__(self, mapping):
            self._mapping = mapping
            
    mock_result.fetchall.return_value = [
        RowMock({"name_x": "Cafe A", "text_normalized": "great cafe", "distance": 0.1}),
        RowMock({"name_x": "Cafe B", "text_normalized": "cozy place", "distance": 0.2})
    ]
    mock_conn.execute.return_value = mock_result
    
    result = semantic_search_tool.invoke({"vibe_intent": "cozy", "limit": 2})
    
    assert result["status"] == "success"
    assert len(result["results"]) == 2
    assert result["results"][0]["name_x"] == "Cafe A"
    
    mock_encode.assert_called_once_with("cozy")
    mock_conn.execute.assert_called_once()


@patch("src.agent.tools.rag_tools.db.get_engine")
def test_knowledge_graph_tool(mock_get_engine):
    """Test Knowledge Graph parameterized cypher query generation."""
    mock_conn = MagicMock()
    mock_get_engine.return_value.connect.return_value.__enter__.return_value = mock_conn
    mock_result = MagicMock()
    
    class RowMock:
        def __init__(self, mapping):
            self._mapping = mapping
            
    mock_result.fetchall.return_value = [
        RowMock({"gmap_id": "12345"}),
        RowMock({"gmap_id": "67890"})
    ]
    mock_conn.execute.return_value = mock_result
    
    result = knowledge_graph_tool.invoke({
        "cuisine": "Mexican",
        "price_level": "$$"
    })
    
    assert result["status"] == "success"
    assert len(result["results"]) == 2
    
    mock_conn.execute.assert_called_once()
    args, kwargs = mock_conn.execute.call_args
    query_str = str(args[0])
    
    assert "MATCH (p:Place {price_level: $price_level})" in query_str
    assert "MATCH (p)-[:SERVES]->(c:Cuisine {name: $cuisine})" in query_str
    assert args[1]["ag_params"] == json.dumps({
        "cuisine": "Mexican",
        "audience": None,
        "price_level": "$$",
        "place_type": None,
        "accessibility": None,
        "waterfront": None
    })
