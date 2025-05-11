import google.generativeai as genai
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import calendar # For month name to number mapping
import re # For simple parsing


from db_tools import search_federal_documents 
from config import GOOGLE_API_KEY

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY not set.")
genai.configure(api_key=GOOGLE_API_KEY)

GEMINI_MODEL_NAME = "gemini-2.0-flash-001" # or "gemini-1.0-pro"

# --- Tool Definition (largely the same, but ensure descriptions are clear) ---
search_tool_declaration = genai.protos.Tool(
    function_declarations=[
        genai.protos.FunctionDeclaration(
            name="search_federal_documents",
            description=(
                "Searches a database of U.S. Federal Register documents. Use this to find proposed rule, rules, notices, presidential documents (like executive orders), etc. "
                "You should try to fill as many parameters as possible from the user's conversation. "
                "If the user provides information over multiple turns, combine it for the tool call. "
                "For example, if they first mention 'AI' and then later specify 'Notice' and then '2025-02-06', use all these for one tool call. "
                "If a user asks for recent documents (e.g., 'this month'), calculate the appropriate start_date and end_date. "
                "If only keywords are provided, that's okay for an initial search. "

            ),
            parameters=genai.protos.Schema(
                type=genai.protos.Type.OBJECT,
                properties={
                    "keywords": genai.protos.Schema(type=genai.protos.Type.STRING, description="Specific keywords. E.g., 'artificial intelligence', 'executive order climate change'. Can be combined from conversation."),
                    "document_type": genai.protos.Schema(type=genai.protos.Type.STRING, description="Document type like 'Rule', 'Proposed Rule', 'Notice', 'Presidential Document'. Infer from conversation."),
                    "start_date": genai.protos.Schema(type=genai.protos.Type.STRING, description="Start date (YYYY-MM-DD)."),
                    "end_date": genai.protos.Schema(type=genai.protos.Type.STRING, description="End date (YYYY-MM-DD)."),
                    "agency_name": genai.protos.Schema(type=genai.protos.Type.STRING, description="Agency name. E.g., 'Environmental Protection Agency'. Infer from conversation."),
                    "limit": genai.protos.Schema(type=genai.protos.Type.INTEGER, description="Max documents. Default 5.")
                },
            )
        )
    ]
)

available_tools = {
    "search_federal_documents": search_federal_documents 
}

def get_date_range_for_month(year_str: str, month_str: str) -> tuple[Optional[str], Optional[str]]:
    # ... (same helper function as before) ...
    try:
        year = int(year_str)
        month_map = {name.lower(): num for num, name in enumerate(calendar.month_name) if num}
        month_map.update({str(num): num for num in range(1, 13)})
        month_map.update({f"{num:02d}": num for num in range(1, 13)})
        month = None
        if month_str.lower() in month_map: month = month_map[month_str.lower()]
        elif month_str.isdigit() and 1 <= int(month_str) <= 12: month = int(month_str)
        else:
            for m_name, m_num in month_map.items():
                if m_name in month_str.lower(): month = m_num; break
        if month is None: return None, None
        start_date = datetime(year, month, 1)
        if month == 12: end_date = datetime(year, month, 31)
        else: end_date = datetime(year, month + 1, 1) - timedelta(days=1)
        today = datetime.now()
        if year == today.year and month == today.month: end_date = min(end_date, today)
        return start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")
    except ValueError: return None, None


def get_gemini_response_with_tool_use(
    user_query: str,
    # Pass the existing conversation history for context
    conversation_history: Optional[List[genai.protos.Content]] = None,
    max_iterations: int = 3
) -> str:
    # --- System Instructions ---
    system_instruction = (
        "You are an AI assistant expert at searching and explaining U.S. Federal Register documents using the 'search_federal_documents' tool. "
        "Your goal is to understand the user's cumulative request over the conversation, make an informed tool call, and then present the findings clearly. "
        "1. **Aggregate Information:** Combine information from the entire conversation for tool calls. "
        "2. **Proactive Tool Use:** Use the tool if you have enough information (e.g., keywords). Not all parameters need to be filled. "
        "3. **Date Calculation:** If relative dates ('this month', 'April 2025') are mentioned, calculate 'start_date' and 'end_date' (YYYY-MM-DD). Today's date is " + datetime.now().strftime("%Y-%m-%d") + ". "
        "4. **Document Type Logic (IMPORTANT REVISION):** "
        "    a. If the user *explicitly asks for 'executive orders'*, then you MUST use 'Presidential Document' as the 'document_type' for the tool and can mention this. "
        "    b. If the user asks for 'presidential documents' generally, also use 'Presidential Document' as the 'document_type'. "
        "    c. If the user asks for 'executive documents' (more general than 'executive orders' or 'presidential documents'), or if they just provide keywords (e.g., 'documents on security') without specifying a clear type like 'rule' or 'notice', it's often best to **NOT specify a 'document_type' parameter at all** in your first tool call. This will allow the search to be broader across all document types. You can then suggest filtering by type if too many results are found. "
        "    d. If the user specifies a different type like 'Rule', 'Notice', etc., use that exact type. "
        "5. **Information Presentation and Explanation:** After the tool returns documents: "
        "    a. Provide an overall summary. "
        "    b. For key documents: list Title, Publication Date, Agency, a brief explanation of relevance from its abstract, and the HTML URL. "
        "    c. Use clear formatting (e.g., bullet points). "
        "6. **Handling No Results/Errors:** If no documents are found, clearly inform the user what search parameters you used (e.g., 'I searched for documents with keywords X and type Y but found nothing.'). Suggest broadening the search (e.g., removing a type filter, changing keywords, or adjusting dates). "
        "7. **Clarification (If Truly Necessary):** Only if the request is extremely vague after several turns, ask for specific clarification. "
        "8. **Default Search with Keywords:** If only keywords are provided (e.g., 'artificial intelligence and security'), use those keywords for the tool call without necessarily needing a document_type or date. "
    )
    model = genai.GenerativeModel(
        model_name=GEMINI_MODEL_NAME,
        tools=[search_tool_declaration],
        system_instruction=system_instruction
    )

    # Initialize or use provided conversation history
    # The history should contain both 'user' and 'model' (and 'function') turns
    if conversation_history is None:
        current_messages_for_gemini = []
    else:
        current_messages_for_gemini = list(conversation_history) # Make a copy

    # Add the current user query to the history
    current_messages_for_gemini.append(
        genai.protos.Content(role="user", parts=[genai.protos.Part(text=user_query)])
    )

    logging.info(f"User query to Gemini (sync): {user_query}")
    logging.info(f"Starting conversation with history length: {len(current_messages_for_gemini)}")


    for iteration in range(max_iterations):
        logging.info(f"Gemini Iteration (sync) {iteration + 1}.")
        # Log the full history being sent to Gemini for this turn
        # for i, msg_content in enumerate(current_messages_for_gemini):
        #    logging.debug(f"History msg {i} to Gemini: Role='{msg_content.role}', Parts='{[p.text if hasattr(p, 'text') else str(p) for p in msg_content.parts]}'")

        try:
            response = model.generate_content(
                current_messages_for_gemini, # Send the full conversation history
            )
            if not response.candidates:
                logging.warning("Gemini response had no candidates.")
                return "I'm sorry, I didn't receive a valid response from the model."
            candidate_content = response.candidates[0].content
            # Add model's response (tool call or text) to history for the *next* iteration or final output
            current_messages_for_gemini.append(candidate_content)

        except Exception as e:
            logging.error(f"Error calling Gemini API (sync): {e}", exc_info=True)
            # Remove the last user message if API call failed, so it's not duplicated on retry by user
            if current_messages_for_gemini and current_messages_for_gemini[-1].role == "user":
                 current_messages_for_gemini.pop()
            return f"Sorry, an error occurred while communicating with the AI model: {str(e)}"

        if candidate_content.parts:
            function_call_part = next((part for part in candidate_content.parts if hasattr(part, 'function_call') and part.function_call.name), None)

            if function_call_part:
                fc = function_call_part.function_call
                function_name = fc.name
                function_args = dict(fc.args)
                logging.info(f"Tool call (sync): {function_name} with args: {function_args}")

                # Fallback date logic (keep it, but improved prompt should reduce need)
                if function_name == "search_federal_documents":
                    if ("start_date" not in function_args or not function_args.get("start_date")) and user_query: # Check if value is empty too
                        # (Your existing date parsing logic based on user_query)
                        # ...
                        pass # For brevity, assume your date logic is here


                if function_name not in available_tools:
                    tool_response_content_for_llm = {"error": f"Tool '{function_name}' not found."}
                else:
                    try:
                        tool_function = available_tools[function_name]
                        tool_response_data = tool_function(**function_args)
                        logging.info(f"Tool '{function_name}' response (sync): {str(tool_response_data)[:500]}...")
                        tool_response_content_for_llm = {"result": tool_response_data}
                    except Exception as te:
                        logging.error(f"Error executing tool {function_name} (sync): {te}", exc_info=True)
                        tool_response_content_for_llm = {"error": f"Error executing tool '{function_name}': {str(te)}"}

                # Append the function response to the history
                current_messages_for_gemini.append(
                    genai.protos.Content(
                        role="function",
                        parts=[genai.protos.Part(
                            function_response=genai.protos.FunctionResponse(
                                name=function_name,
                                response=tool_response_content_for_llm
                            )
                        )]
                    )
                )
                continue # Next iteration for LLM to process tool result

            else: # No function call, should be a text response
                final_text_response = "".join(part.text for part in candidate_content.parts if hasattr(part, 'text'))
                if final_text_response:
                    logging.info(f"Gemini final text response (sync): {final_text_response}")
                    return final_text_response
                else:
                    logging.warning("Gemini returned parts but no text and no tool call. Previous turn likely resulted in an error or confusion.")
                    return "I seem to have gotten a bit confused. Could you please try rephrasing your request or start over?"
        else:
            logging.warning("Gemini response had no parts (sync).")
            return "I'm sorry, I received an empty response from the AI model."

    logging.warning("Max iterations reached without a final text answer from Gemini (sync).")
    return "I'm having trouble finalizing an answer. Please try rephrasing your request."

