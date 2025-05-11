import asyncio
import aiomysql
import aiofiles
import os
import json
import logging

# Assuming your config.py provides these
from config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, RAW_DATA_DIR

logger = logging.getLogger(__name__)

TABLE_NAME = "latest_federal_documents"

# Updated CREATE TABLE statement
CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    document_number VARCHAR(255) PRIMARY KEY,
    title TEXT,
    type VARCHAR(100),
    abstract TEXT,
    publication_date DATE,
    html_url VARCHAR(1024),
    pdf_url VARCHAR(1024),
    public_inspection_pdf_url VARCHAR(1024),
    agency_name VARCHAR(512),
    excerpts TEXT
);
"""

async def get_db_pool():
    """Creates an aiomysql connection pool."""
    try:
        pool = await aiomysql.create_pool(
            host=DB_HOST, port=DB_PORT,
            user=DB_USER, password=DB_PASSWORD,
            db=DB_NAME, autocommit=True
        )
        return pool
    except Exception as e:
        logging.error(f"Error creating database connection pool: {e}")
        raise

async def create_table_if_not_exists(pool: aiomysql.Pool):
    """Creates the table in the database if it doesn't exist."""
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            try:
                await cur.execute(CREATE_TABLE_SQL)
                logging.info(f"Table '{TABLE_NAME}' ensured to exist.")
            except Exception as e:
                logging.error(f"Error creating table '{TABLE_NAME}': {e}")
                raise

async def process_file_and_insert(pool: aiomysql.Pool, filepath: str):
    """Reads a JSON file, extracts data, and inserts/updates it into the database."""
    try:
        async with aiofiles.open(filepath, mode='r', encoding='utf-8') as f:
            content = await f.read()
            # The downloader now saves a structure like {"count": N, "results": [...]}
            # So we need to access the 'results' list from the loaded JSON.
            file_data_structure = json.loads(content)
            documents_data = file_data_structure.get("results", [])
    except Exception as e:
        logging.error(f"Error reading or parsing JSON file {filepath}: {e}")
        return 0

    if not documents_data:
        logging.info(f"No 'results' array found or it's empty in file {filepath}. Skipping.")
        return 0

    documents_to_insert = []
    for doc in documents_data:
        # Safely get values, providing None if key is missing
        # Extract agency name (first agency's raw_name)
        first_agency_name = None
        agencies_list = doc.get("agencies")
        if agencies_list and isinstance(agencies_list, list) and len(agencies_list) > 0:
            first_agency = agencies_list[0]
            if isinstance(first_agency, dict):
                first_agency_name = first_agency.get("raw_name")

        documents_to_insert.append((
            doc.get("document_number"),          # 1
            doc.get("title"),                    # 2
            doc.get("type"),                     # 3
            doc.get("abstract"),                 # 4
            doc.get("publication_date"),         # 5
            doc.get("html_url"),                 # 6
            doc.get("pdf_url"),                  # 7
            doc.get("public_inspection_pdf_url"),# 8
            first_agency_name,                   # 9
            doc.get("excerpts")                  # 10
        ))

    if not documents_to_insert:
        logging.info(f"No valid documents to insert from {filepath} after parsing.")
        return 0

    # Update INSERT SQL to include new columns
    # Make sure the number of %s matches the number of columns
    # and the order in VALUES matches the tuple order above.
    insert_sql = f"""
    INSERT INTO {TABLE_NAME} (
        document_number, title, type, abstract, publication_date,
        html_url, pdf_url, public_inspection_pdf_url, agency_name, excerpts
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) -- 10 placeholders for 10 columns
    ON DUPLICATE KEY UPDATE
        title = VALUES(title),
        type = VALUES(type),
        abstract = VALUES(abstract),
        publication_date = VALUES(publication_date),
        html_url = VALUES(html_url),
        pdf_url = VALUES(pdf_url),
        public_inspection_pdf_url = VALUES(public_inspection_pdf_url),
        agency_name = VALUES(agency_name),
        excerpts = VALUES(excerpts);
    """

    inserted_count = 0
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            try:
                await cur.executemany(insert_sql, documents_to_insert)
                # For executemany with ON DUPLICATE KEY UPDATE, rowcount can be tricky.
                # It's 1 for each new row inserted, 2 for each existing row updated.
                # For simplicity, we'll just log that the operation was attempted.
                logging.info(f"Attempted to insert/update {len(documents_to_insert)} records from {filepath}. DB affected rows: {cur.rowcount}.")
                # The actual number of "processed" items is len(documents_to_insert)
                inserted_count = len(documents_to_insert)
            except Exception as e:
                logging.error(f"Error inserting data from {filepath}: {e}")
    return inserted_count

async def main_processor():
    """Main function to process all raw data files and insert into DB."""
    pool = await get_db_pool()
    if not pool:
        return

    await create_table_if_not_exists(pool)

    total_docs_processed = 0
    files_processed_count = 0

    raw_files = [f for f in os.listdir(RAW_DATA_DIR) if f.endswith('.json')]
    if not raw_files:
        logging.info("No raw data files found to process.")
    else:
        logging.info(f"Found {len(raw_files)} raw data files to process.")

    # Process files one by one to make logging clearer if one fails
    for filename in raw_files:
        filepath = os.path.join(RAW_DATA_DIR, filename)
        logging.info(f"Processing file: {filepath}")
        try:
            num_docs_in_file = await process_file_and_insert(pool, filepath)
            if num_docs_in_file > 0:
                total_docs_processed += num_docs_in_file
                files_processed_count +=1 # Count file if it had processable docs
        except Exception as e:
            logging.error(f"Critical error processing file {filename}: {e}")


    logging.info(f"Processor finished. Successfully processed data for {total_docs_processed} documents from {files_processed_count} files.")
    pool.close()
    await pool.wait_closed()

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    asyncio.run(main_processor())