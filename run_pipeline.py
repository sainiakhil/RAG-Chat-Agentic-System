# run_pipeline.py
import asyncio
import logging # Keep this
from downloader import main_downloader
from processor import main_processor

# THIS IS THE ONLY basicConfig CALL when running the pipeline
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Get a logger for this main script (optional, but good practice)
logger = logging.getLogger(__name__)


async def run_full_pipeline():
    logger.info("Starting data pipeline...") # Use logger instance

    logger.info("Running downloader...")
    try:
        await main_downloader()
        logger.info("Downloader completed.")
    except Exception as e:
        logger.error(f"Downloader failed: {e}", exc_info=True) # Add exc_info for traceback
        return

    logger.info("Running processor...")
    try:
        await main_processor()
        logger.info("Processor completed.")
    except Exception as e:
        logger.error(f"Processor failed: {e}", exc_info=True) # Add exc_info
        return

    logger.info("Data pipeline finished successfully.")

if __name__ == "__main__":
    asyncio.run(run_full_pipeline())