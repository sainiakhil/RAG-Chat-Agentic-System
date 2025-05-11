# RAG-Chat-Agentic-System

## Core Components

1.  **Data Pipeline (`downloader.py`, `processor.py`, `run_pipeline.py`):**
    *   `downloader.py`: Fetches documents daily for a configurable number of recent days from the official Federal Register API. Handles pagination and saves raw data as JSON files (one per day). This part is `async`.
    *   `processor.py`: Reads the raw JSON files, processes the document data, and inserts/updates records into a MySQL database table (`federal_documents`). Uses `INSERT ... ON DUPLICATE KEY UPDATE` to handle new and existing records. This part is also `async`.
    *   `run_pipeline.py`: An `async` script that orchestrates the execution of the downloader and then the processor. This should be run daily (e.g., via a cron job or scheduler in a production environment).

2.  **Database Tools (`db_tools_sync.py`):**
    *   Provides a synchronous function `search_federal_documents_sync` that constructs and executes raw SQL queries against the `federal_documents` table in MySQL.
    *   This function is designed to be called as a "tool" by the LLM agent.

3.  **LLM Agent (`agent_gemini_sync.py`):**
    *   Uses the Google Gemini API (e.g., `gemini-1.5-flash-latest`).
    *   Implements the core RAG logic:
        *   Takes a user query and conversation history.
        *   Uses a system prompt to guide its behavior, including when and how to use the `search_federal_documents` tool.
        *   If it decides to use the tool, it generates the appropriate arguments (keywords, dates, document type, etc.).
        *   Calls the `search_federal_documents_sync` function.
        *   Receives the database results and formulates a comprehensive, summarized answer for the user, including details of relevant documents.

4.  **User Interface (`app_streamlit_sync.py`):**
    *   A web application built with Streamlit.
    *   Provides a chat interface for users to ask questions.
    *   Manages conversation history for display.
    *   Calls the `get_gemini_response_with_tool_use_sync` function from `agent_gemini_sync.py` to get responses.

5.  **Configuration (`config.py`, `.env`):**
    *   `config.py`: Loads configuration values from environment variables.
    *   `.env`: Stores sensitive information like database credentials and the `GOOGLE_API_KEY`. **This file should be listed in your `.gitignore` and not committed to the repository.**

## Setup and Installation

1.  **Prerequisites:**
    *   Python 3.8+
    *   MySQL Server installed and running.
    *   A Google Cloud Project with the "Generative Language API" (or Vertex AI API for Gemini) enabled and an API key.

2.  **Clone the Repository:**
    ```bash
    git clone <your-repository-url>
    cd <repository-name>
    ```

3.  **Create a Virtual Environment (Recommended):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

4.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    A `requirements.txt` file should be created with contents like:
    ```txt
    streamlit
    google-generativeai
    python-dotenv
    mysql-connector-python # For synchronous DB access
    # For the async data pipeline:
    aiohttp
    aiofiles
    aiomysql
    # Pillow (often a streamlit sub-dependency but good to list)
    Pillow
    ```

5.  **Set Up MySQL Database:**
    *   Connect to your MySQL server.
    *   Create a database (e.g., `federal_data`):
        ```sql
        CREATE DATABASE federal_data;
        ```
    *   The `federal_documents` table will be created automatically by `processor.py` when the pipeline runs for the first time.

6.  **Configure Environment Variables:**
    *   Create a `.env` file in the root of the project:
        ```env
        # MySQL Configuration
        DB_HOST=localhost
        DB_PORT=3306
        DB_USER=your_mysql_username
        DB_PASSWORD=your_mysql_password
        DB_NAME=federal_data # Should match the database you created

        # Google Gemini API Key
        GOOGLE_API_KEY=YOUR_GOOGLE_API_KEY_HERE
        ```
    *   Replace placeholders with your actual credentials and API key.
    *   **IMPORTANT:** Add `.env` to your `.gitignore` file to prevent committing secrets.

## Running the System

1.  **Run the Data Pipeline (Daily or as needed):**
    *   This step populates/updates your MySQL database with recent Federal Register documents.
    *   Open your terminal, activate the virtual environment, and run:
        ```bash
        python run_pipeline.py
        ```
    *   Monitor the console output for logs from the downloader and processor. This can take some time, especially on the first run.

2.  **Run the Streamlit Application (User Interface):**
    *   Once the pipeline has run at least once and populated some data:
        ```bash
        streamlit run app_streamlit_sync.py
        ```
    *   Streamlit will provide a URL (usually `http://localhost:8501`) to open in your web browser.
    *   You can now interact with the chat agent.

## How It Works (Flow)

1.  **User Query:** User types a question into the Streamlit chat interface.
2.  **Agent Processing (`app_streamlit_sync.py` -> `agent_gemini_sync.py`):**
    *   The query (and conversation history) is sent to `get_gemini_response_with_tool_use_sync`.
    *   The Gemini LLM analyzes the query and conversation history based on its system prompt.
3.  **Tool Call Decision:**
    *   If the LLM determines it needs data from the database, it decides to use the `search_federal_documents` tool.
    *   It generates arguments for the tool (keywords, dates, document_type, etc.).
4.  **Database Query (`agent_gemini_sync.py` -> `db_tools_sync.py`):**
    *   The agent calls `search_federal_documents_sync` with the generated arguments.
    *   `db_tools_sync.py` connects to MySQL and executes a raw SQL query.
5.  **Results to LLM:** The search results (list of documents) are returned to `agent_gemini_sync.py`.
6.  **Response Formulation:**
    *   The agent sends the tool results back to the Gemini LLM.
    *   The LLM, guided by the system prompt, processes these results and formulates a final textual answer, including summaries and details of the documents.
7.  **Display to User:** The final answer is sent back to `app_streamlit_sync.py` and displayed in the chat UI.

## Customization and Future Improvements

*   **Asynchronous Agent/UI:** Convert `agent_gemini_sync.py` and `app_streamlit_sync.py` to use `async` and `await` for non-blocking UI performance, especially if LLM or DB calls are slow. This would involve re-introducing proper `asyncio` event loop management in Streamlit.
*   **More Sophisticated Search:**
    *   Implement MySQL Full-Text Search in `db_tools_sync.py` for better keyword relevance.
    *   Integrate semantic search using vector embeddings (e.g., with a vector database or Faiss) for finding conceptually similar documents, not just keyword matches.
*   **Advanced Agent Capabilities:**
    *   Enable the agent to make multiple tool calls if needed.
    *   Implement more robust conversational memory.
    *   Allow the agent to ask clarifying questions more effectively.
*   **Error Handling:** Enhance error handling and provide more user-friendly error messages.
*   **Streaming Responses:** Implement streaming for LLM responses in Streamlit for a more interactive feel.
*   **Configuration Management:** Use a more structured configuration approach if the project grows (e.g., Pydantic for settings).
*   **Deployment:** Package the application for deployment (e.g., using Docker).

## Troubleshooting

*   **"Attached to a different loop" errors (if using async versions):** Ensure `nest_asyncio.apply()` is used at the top of your Streamlit script if you revert to async operations.
*   **DB Connection Issues:** Verify MySQL credentials in `.env` and that the MySQL server is running and accessible. Check `config.py` loads them correctly.
*   **`GOOGLE_API_KEY` not found:** Ensure the environment variable is set correctly and accessible to your Python process.
*   **LLM Not Using Tool Correctly:** This is often a prompt engineering issue. Refine the `system_instruction` in `agent_gemini_sync.py` and the tool description. Check the logs to see what arguments the LLM is trying to use.
*   **Pipeline Failures:** Check logs from `run_pipeline.py`, `downloader.py`, and `processor.py` for errors related to API access, data parsing, or database inserts.

---
