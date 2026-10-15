import pytest
import os
from streamlit.testing.v1 import AppTest

def test_app_initialization_and_layout():
    """
    Test that the Streamlit application initializes session state variables 
    correctly and renders the basic layout without exceptions.
    """
    app_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src/frontend/app.py"))
    at = AppTest.from_file(app_path, default_timeout=30)
    at.run(timeout=30)
    
    assert not at.exception, f"App raised an exception: {at.exception}"
    
    # Verify session state initialization
    assert "messages" in at.session_state
    assert isinstance(at.session_state.messages, list)
    assert len(at.session_state.messages) == 0
    
    assert "frontend_payload" in at.session_state
    assert isinstance(at.session_state.frontend_payload, dict)
    
    # Verify layout components exist
    assert len(at.sidebar.button) > 0
    assert at.sidebar.button[0].label == "Restart Session"
    
    assert len(at.info) > 0
    assert "Map will be rendered here" in at.info[0].value
    
    assert len(at.chat_input) > 0
