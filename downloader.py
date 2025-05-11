# downloader.py
import asyncio
import aiohttp
import aiofiles
import os
from datetime import datetime, timedelta # Essential for dynamic date ranges
import json
import logging


RAW_DATA_DIR = "raw_data" # Fallback if config.py is not found or RAW_DATA_DIR isn't in it

logger = logging.getLogger(__name__) # Use __name__ for module-specific logger

os.makedirs(RAW_DATA_DIR, exist_ok=True)

BASE_API_URL = "https://www.federalregister.gov/api/v1/documents.json"

async def fetch_documents_for_date(session: aiohttp.ClientSession, target_date_str: str, per_page: int = 1000):
    """
    Fetches all documents for a specific publication date.
    Handles pagination within this function for a single date.
    """
    all_results_for_date = []
    current_page = 1
    total_pages = 1 # Assume at least one page

    logger.info(f"Fetching documents for date: {target_date_str}")

    while current_page <= total_pages:
        params = {
            "conditions[publication_date][is]": target_date_str,
            "per_page": per_page,
            "page": current_page
            # You can add other default filters here if desired, e.g., specific document types
            # "conditions[type][]": "Presidential Document", # Example: if you ONLY want these
        }
        try:
            headers = {"User-Agent": "MyDataPipeline/1.0 (DailyUpdater)"}
            async with session.get(BASE_API_URL, params=params, headers=headers, timeout=120) as response: # Increased timeout
                response.raise_for_status()
                data = await response.json()

                if not data:
                    logger.warning(f"Received empty API response for {target_date_str}, page {current_page}.")
                    break

                results_on_page = data.get("results", [])
                all_results_for_date.extend(results_on_page)
                logger.debug(f"Date {target_date_str}: Fetched {len(results_on_page)} docs on page {current_page}. Total for date: {len(all_results_for_date)}.")

                if current_page == 1: # Only update total_pages on the first successful page fetch
                    total_pages = data.get("total_pages", 1)
                    if total_pages == 0 and not results_on_page:
                        logger.info(f"No documents found for date {target_date_str} (total_pages=0).")
                        break # No need to fetch further pages
                    if total_pages > 1:
                        logger.info(f"Date {target_date_str}: Total pages to fetch: {total_pages}.")

                if not results_on_page or current_page >= total_pages:
                    break # No more results on this page or all pages fetched

                current_page += 1
                if total_pages > 1 : await asyncio.sleep(0.2) # Small polite delay if paginating for a date

        except asyncio.TimeoutError:
            logger.error(f"Timeout error fetching data for {target_date_str}, page {current_page}.", exc_info=False) # exc_info=False for cleaner log on timeout
            break # Stop fetching for this date on timeout
        except aiohttp.ClientResponseError as e_http:
            logger.error(f"HTTP error {e_http.status} fetching data for {target_date_str}, page {current_page}: {e_http.message}", exc_info=False)
            break # Stop fetching for this date on HTTP error
        except Exception as e:
            logger.error(f"Generic error fetching data for {target_date_str}, page {current_page}.", exc_info=True)
            break # Stop fetching for this date on other errors

    if all_results_for_date:
        logger.info(f"Finished fetching for date {target_date_str}. Total documents: {len(all_results_for_date)}.")
    # Return even if empty, so save_raw_data can decide to save an empty result file or not
    return {"date": target_date_str, "count": len(all_results_for_date), "results": all_results_for_date}


async def save_raw_data(date_str: str, data_for_date: dict):
    """Saves the fetched data for a specific date to a JSON file."""
    # data_for_date is the dict returned by fetch_documents_for_date
    if not data_for_date or data_for_date.get("count", 0) == 0: # Check count
        logger.info(f"No documents to save for date {date_str} (count is 0).")
        return

    filename = f"{date_str}.json" # File per date
    filepath = os.path.join(RAW_DATA_DIR, filename)
    try:
        async with aiofiles.open(filepath, mode='w', encoding='utf-8') as f:
            await f.write(json.dumps(data_for_date, indent=2)) # Save the whole dict
        logger.info(f"Successfully saved raw data for {date_str} to {filepath}")
    except IOError as e:
        logger.error(f"Error saving data for {date_str} to {filepath}.", exc_info=True)

async def main_downloader(days_to_fetch: int = 7):
    """
    Main function to download data for the last N days.
    Each day's data is saved in a separate file.
    """
    logger.info(f"Starting downloader to fetch data for the last {days_to_fetch} days.")
    # Use a single ClientSession for all requests for efficiency
    async with aiohttp.ClientSession() as session:
        tasks = []
        today = datetime.utcnow().date() # Use UTC for consistency

        for i in range(days_to_fetch): # Fetches today, yesterday, day before, etc.
            target_date_obj = today - timedelta(days=i)
            target_date_str = target_date_obj.strftime("%Y-%m-%d")

            # Create a task for fetching and saving for each day
            async def fetch_and_save_for_day(date_to_process_str: str):
                logger.info(f"Initiating fetch for date: {date_to_process_str}")
                # Set per_page for individual date fetching if desired, e.g., 500 or 1000
                # The Federal Register API seems to cap per_page at 1000.
                daily_data = await fetch_documents_for_date(session, date_to_process_str, per_page=1000)
                if daily_data: # daily_data will always be a dict, check if it's not None
                    await save_raw_data(date_to_process_str, daily_data)
                else:
                    logger.warning(f"No data structure returned from fetch_documents_for_date for {date_to_process_str}")

            tasks.append(fetch_and_save_for_day(target_date_str))

        # Run all date-fetching tasks concurrently
        await asyncio.gather(*tasks, return_exceptions=True) # return_exceptions=True to not stop all on one failure

    logger.info("Downloader finished processing all requested dates.")


if __name__ == "__main__":
    # When running downloader.py directly for testing:
    # 1. Setup basicConfig for logging ONLY for this direct execution.
    # 2. Call main_downloader.
    logging.basicConfig(
        level=logging.INFO, # Set to DEBUG for more verbose output during testing
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    # Example: Fetch data for the last 3 days
    asyncio.run(main_downloader(days_to_fetch=3))