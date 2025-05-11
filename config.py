import os
from dotenv import load_dotenv

load_dotenv() # Load variables from .env file

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")


# Directory for raw data
RAW_DATA_DIR = "raw_data"