# app_streamlit_sync.py
import streamlit as st
import logging
import google.generativeai as genai # Needed for Content objects in history

from agent_gemini import get_gemini_response_with_tool_use
from config import GOOGLE_API_KEY

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(app_streamlit)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

st.set_page_config(page_title="Federal Document Agent", layout="centered")
st.title("Federal Document Search Agent📜")

if not GOOGLE_API_KEY:
    st.error("🔴 GOOGLE_API_KEY is not set. Please set it and restart.")
    st.stop()

# Initialize chat history for display (simple list of dicts)
if "display_messages" not in st.session_state:
    st.session_state.display_messages = [{"role": "assistant", "content": "How can I help you find federal documents today?"}]

# Initialize conversation history for Gemini (list of genai.protos.Content objects)
if "gemini_conversation_history" not in st.session_state:
    st.session_state.gemini_conversation_history = []

# Display chat messages
for message in st.session_state.display_messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if user_query := st.chat_input("Ask about federal documents..."):
    # Add user message to UI display history
    st.session_state.display_messages.append({"role": "user", "content": user_query})
    with st.chat_message("user"):
        st.markdown(user_query)

    # Add user message to Gemini's actual conversation history
    st.session_state.gemini_conversation_history.append(
        genai.protos.Content(role="user", parts=[genai.protos.Part(text=user_query)])
    )

    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        message_placeholder.markdown("Thinking...")
        try:
            # Pass the current Gemini conversation history to the agent
            assistant_response_text = get_gemini_response_with_tool_use(
                user_query, # Current query (agent also appends this internally to its working copy of history)
                conversation_history=st.session_state.gemini_conversation_history[:-1] # Pass history *before* current user query
            )
            message_placeholder.markdown(assistant_response_text)

            # Add assistant's final text response to UI display history
            st.session_state.display_messages.append({"role": "assistant", "content": assistant_response_text})
            # Add assistant's final text response to Gemini's actual conversation history
            # Note: If the agent had tool calls, the `gemini_conversation_history`
            # inside the agent function was updated with tool_call and tool_response parts.
            # For the Streamlit history, we only care about the final textual response from the model.
            # However, the agent function needs the *full* history including tool interactions.
            # This part is tricky. The agent's internal message list (`current_messages_for_gemini`)
            # is what matters most for its own context.
            # We need to decide if `st.session_state.gemini_conversation_history` should store the *full* interaction
            # or just user/model text turns. For proper multi-turn tool use, it needs the full interaction.

            # Let's simplify: the agent function now manages its own history internally for a given call
            # based on what's passed to it. For a new user query, we pass the *accumulated* history.
            # The agent function appends its own model responses (text or tool calls) and tool results
            # to the copy of the history it works with. We need to get that *updated full history* back
            # if we want true multi-turn context.

            # ---- For now, the agent is designed to take the user_query and the history *up to that point*
            # and then it builds its own internal message list for the current interaction.
            # Let's add the model's final textual response to the gemini_conversation_history
            st.session_state.gemini_conversation_history.append(
                genai.protos.Content(role="model", parts=[genai.protos.Part(text=assistant_response_text)])
            )

        except Exception as e:
            logger.error(f"Error during agent interaction (sync): {e}", exc_info=True)
            error_msg = f"Sorry, an error occurred: {str(e)}"
            message_placeholder.error(error_msg)
            st.session_state.display_messages.append({"role": "assistant", "content": error_msg})
            # Also add error to gemini history so model knows it failed.
            st.session_state.gemini_conversation_history.append(
                genai.protos.Content(role="model", parts=[genai.protos.Part(text=f"Error occurred: {error_msg}")]) # Model "said" this
            )