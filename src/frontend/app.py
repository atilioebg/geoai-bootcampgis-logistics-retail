"""
GeoAI Swarm - Streamlit Frontend.

To run this application, use the following command in your terminal:
    streamlit run src/frontend/app.py
"""
import sys
import os

# Add the project root to sys.path so 'src' module can be found
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

import streamlit as st
from streamlit_folium import st_folium
from src.agent.swarm_graph import swarm_graph
from src.agent.swarm_state import SwarmState
from src.frontend.map_utils import render_dynamic_map

# 1. Master Layout configuration
st.set_page_config(page_title="GeoAI Swarm", layout="wide")

# Custom CSS for UX Polish
st.markdown("""
    <style>
        /* Make the map container flush and adjust main padding */
        .block-container {
            padding-top: 2rem !important;
            padding-bottom: 2rem !important;
            padding-left: 1rem !important;
            padding-right: 1rem !important;
        }
        /* Style the chat container */
        .stChatInputContainer {
            padding-bottom: 20px;
        }
    </style>
""", unsafe_allow_html=True)

# 2. Session Memory Initialization
if "messages" not in st.session_state:
    st.session_state.messages = []
if "frontend_payload" not in st.session_state:
    st.session_state.frontend_payload = {}

# Sidebar Configuration
with st.sidebar:
    st.title("GeoAI Control Panel")
    st.write("Configure swarm options and manage session state.")
    
    if st.button("Restart Session", use_container_width=True):
        st.session_state.messages = []
        st.session_state.frontend_payload = {}
        st.toast("Session Restarted Successfully!", icon="🔄")
        st.rerun()

# Split the main screen into a 75/25 layout
col_map, col_chat = st.columns([3, 1])

# 4. Render Dynamic Map
with col_map:
    # Render the folium map based on the active payload
    dynamic_map = render_dynamic_map(st.session_state.frontend_payload)
    
    # Display it in Streamlit (Disable component returns to stop rendering loops)
    st_folium(dynamic_map, width=1200, height=800, returned_objects=[])
    
    # Display the current validated payload for debugging
    if st.session_state.frontend_payload:
        st.success("Valid Spatial Payload Ready for Render:")
        st.json(st.session_state.frontend_payload)

# 3 & 5 & 6. Chat Interface and LangGraph Integration
with col_chat:
    st.subheader("Swarm Chat")
    
    # Render chat history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            
    # Chat Input
    if prompt := st.chat_input("Ask the GeoAI Swarm..."):
        # Append user message to history and render it
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
            
        # Initialize LangGraph State
        current_state: SwarmState = {
            "question": prompt,
            "plan": [],
            "draft_response": "",
            "review_feedback": "",
            "review_status": "",
            "loop_count": 0,
            "tool_payload": {},
            "frontend_payload": st.session_state.frontend_payload  # Pass previous validated state
        }
        
        # Swarm Execution with Glass-Box Streaming
        with st.chat_message("assistant"):
            with st.status("Agents Working...", expanded=True) as status:
                for event in swarm_graph.stream(current_state):
                    for node_name, node_state in event.items():
                        current_state.update(node_state)
                        
                        if node_name == "planner":
                            st.write(f"🧠 **Planner**: Generated plan -> {node_state.get('plan')}")
                        elif node_name == "worker":
                            st.write(f"🛠️ **Worker**: Executed spatial tools and drafted response.")
                            if node_state.get('tool_payload'):
                                st.write(f"📦 **Worker payload**: Captured {node_state.get('tool_payload').get('status')} response.")
                        elif node_name == "reviewer":
                            status_val = node_state.get('review_status')
                            if status_val == "rejected":
                                st.error(f"❌ **Reviewer**: Draft rejected. Feedback:\n\n{node_state.get('review_feedback')}")
                            else:
                                st.success(f"✅ **Reviewer**: Draft approved!")
                            st.write(f"🔄 **Loop Count**: {node_state.get('loop_count')}")
                        elif node_name == "emergency_brake":
                            st.error(f"🚨 **Emergency Brake Activated!**")
                
                status.update(label="Processing Complete!", state="complete", expanded=False)
                
            # Extract final response and payload
            final_response = current_state.get("draft_response", "No response generated.")
            st.markdown(final_response)
            
            # Save assistant response to memory
            st.session_state.messages.append({"role": "assistant", "content": final_response})
            
            # STATE RESILIENCE: Update the global frontend payload ONLY if the 
            # Swarm successfully approved a new one. If an intermediate tool failed 
            # and the agent is looping to self-heal, the map remains stable!
            if current_state.get("frontend_payload"):
                st.session_state.frontend_payload = current_state.get("frontend_payload")
                st.rerun()  # Rerun to force the left map column to update with new data

if __name__ == "__main__":
    from streamlit.testing.v1 import AppTest
    from streamlit.runtime import exists
    
    # Prevent infinite recursion when AppTest imports this file
    if not exists():
        print("Testing Streamlit UI Programmatically...")
        
        # Initialize the app with a 30 second timeout for LangGraph loading
        at = AppTest.from_file(__file__, default_timeout=30)
        at.run(timeout=30)
        
        # Inject fake state
        at.session_state.messages = [{"role": "user", "content": "fake"}]
        at.session_state.frontend_payload = {"layer": "fake"}
        
        # Simulate a click on the 'Restart Session' button
        restart_button = at.sidebar.button[0]
        restart_button.click().run(timeout=10)
        
        # Assert session is wiped
        if len(at.session_state.messages) == 0 and len(at.session_state.frontend_payload) == 0:
            print("Terminal Test: Session Reset UI PASSED")
        else:
            print("Terminal Test: Session Reset UI FAILED")
