import os
from streamlit.testing.v1 import AppTest

def test_session_restart():
    """
    Test that the 'Restart Session' button properly clears the chat memory 
    and the frontend payload from Streamlit's session state.
    """
    app_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src/frontend/app.py"))
    at = AppTest.from_file(app_path, default_timeout=30)
    at.run(timeout=30)
    
    # Verify initial state is empty
    assert len(at.session_state.messages) == 0
    assert len(at.session_state.frontend_payload) == 0
    
    # Inject fake state
    at.session_state.messages = [{"role": "user", "content": "Fake message"}]
    at.session_state.frontend_payload = {"layer": "fake_layer", "color": "FFFFFF"}
    
    assert len(at.session_state.messages) == 1
    assert len(at.session_state.frontend_payload) == 2
    
    # Find and click the 'Restart Session' button (it's in the sidebar)
    # the sidebar is a block, let's find the button directly
    assert len(at.sidebar.button) > 0
    restart_button = at.sidebar.button[0]
    assert restart_button.label == "Restart Session"
    
    # Click it and run
    restart_button.click().run(timeout=10)
    
    # Assert session is wiped
    assert len(at.session_state.messages) == 0, "Messages list was not cleared!"
    assert len(at.session_state.frontend_payload) == 0, "Frontend payload was not cleared!"
