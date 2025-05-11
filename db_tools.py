# db_tools_sync.py (New or modified file)
import mysql.connector
from mysql.connector import Error # Import Error for exception handling
import logging
from typing import List, Dict, Optional, Any
from config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# No global pool needed in the same way for simple synchronous connections.
# Connections are typically opened and closed per function or per request.

def get_db_connection():
    """Establishes a synchronous database connection."""
    try:
        connection = mysql.connector.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        if connection.is_connected():
            logging.debug("MySQL connection successful")
            return connection
    except Error as e:
        logging.error(f"Error connecting to MySQL: {e}")
        return None

def search_federal_documents(
    keywords: Optional[str] = None,
    document_type: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    agency_name: Optional[str] = None,
    limit: int = 5
) -> List[Dict[str, Any]]:
    """
    Searches federal documents (synchronously).
    Returns a list of matching documents or an empty list.
    """
    connection = get_db_connection()
    if not connection:
        return [{"error": "Database connection failed."}]

    # Using dictionary=True with the cursor makes it return rows as dictionaries
    cursor = connection.cursor(dictionary=True)
    results = []

    query_parts = ["SELECT document_number, title, type, abstract, publication_date, html_url, agency_name FROM federal_documents WHERE 1=1"]
    params = []

    if keywords:
        query_parts.append("AND (title LIKE %s OR abstract LIKE %s OR excerpts LIKE %s)")
        keyword_param = f"%{keywords}%"
        params.extend([keyword_param, keyword_param, keyword_param])
    if document_type:
        query_parts.append("AND type = %s")
        params.append(document_type)
    # ... (add other conditions similarly for start_date, end_date, agency_name) ...
    if start_date:
        query_parts.append("AND publication_date >= %s")
        params.append(start_date)
    if end_date:
        query_parts.append("AND publication_date <= %s")
        params.append(end_date)
    if agency_name:
        query_parts.append("AND agency_name LIKE %s")
        params.append(f"%{agency_name}%")


    query_parts.append("ORDER BY publication_date DESC")
    query_parts.append(f"LIMIT %s") # Use %s for limit as well with mysql.connector
    params.append(limit)

    final_query = " ".join(query_parts)
    logging.info(f"Executing SYNC DB query: {final_query} with params: {params}")

    try:
        cursor.execute(final_query, tuple(params))
        db_results = cursor.fetchall() # Fetches all rows
        if not db_results:
            logging.info("No documents found matching criteria (sync).")
            return [{"message": "No documents found matching your criteria."}]

        # Convert date objects to strings for consistency if needed
        for row in db_results:
            if 'publication_date' in row and hasattr(row['publication_date'], 'isoformat'):
                row['publication_date'] = row['publication_date'].isoformat()
        results = db_results

    except Error as e:
        logging.error(f"Error querying database (sync): {e}")
        results = [{"error": f"An error occurred while searching the database (sync): {str(e)}"}]
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()
            logging.debug("MySQL connection closed")
    return results

# Example usage for testing db_tools_sync.py directly
if __name__ == "__main__":
    print("Testing DB search...")
    docs = search_federal_documents(keywords="executive order AI", limit=2)
    for doc in docs:
        print(doc)