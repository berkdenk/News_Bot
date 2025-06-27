# api_utils.py

import requests # Library for HTTP requests
import json     # Library for processing JSON data
import time     # Library for pausing execution
import logging  # Library for logging
# tenacity: Library used for automatic retries in case of errors
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

# Importing necessary settings from config.py
from config import (
    SEARCH_KEYWORDS,             # Keywords for searching
    ARTICLES_PER_REQUEST,        # Number of articles to fetch per request
    SLEEP_TIME_BETWEEN_REQUESTS, # Sleep duration between requests
    MAX_RETRIES,                 # Maximum number of retries
    RETRY_DELAY_SECONDS          # Delay duration between retries
)

# Using the same logger as in main.py, so all logs are collected in one file
logger = logging.getLogger('main_news_bot_logger')

# --- Retry Decorator ---
# This decorator ensures that when the 'fetch_news_from_api' function raises an error (Exception),
# it will retry a specified number of times (MAX_RETRIES) with a defined interval (RETRY_DELAY_SECONDS).
# requests.exceptions.RequestException: Handles HTTP request errors such as network issues or timeouts.
# json.JSONDecodeError: Handles cases where the API response is not valid JSON.
@retry(stop=stop_after_attempt(MAX_RETRIES), wait=wait_fixed(RETRY_DELAY_SECONDS),
       retry=(retry_if_exception_type(requests.exceptions.RequestException) |
              retry_if_exception_type(json.JSONDecodeError)))
def fetch_news_from_api(api_key, lang, earliest_publish_date, offset):
    """
    Fetches news from the World News API based on specified parameters.
    Includes a retry mechanism.

    Parameters:
    api_key (str): World News API key.
    lang (str): Language code for fetching news (e.g., "pl", "en").
    earliest_publish_date (str): The earliest publish date for news (in YYYY-MM-DD HH:MM:SS format).
    offset (int): Offset to start fetching news from the API (for pagination).

    Returns:
    list: A list of fetched news articles (each article as a dictionary).
    """
    url = "https://api.worldnewsapi.com/search-news" # Base search URL of the API
    params = {
        "api-key": api_key,
        "language": lang,
        "earliest-publish-date": earliest_publish_date,
        "text": SEARCH_KEYWORDS, # Keywords from config.py
        "offset": offset,
        "number": ARTICLES_PER_REQUEST # Number of news articles to fetch per request
    }

    try:
        logger.debug(f"  Sending API request (language: {lang.upper()}, Offset: {offset}).")
        # Send an HTTP GET request. timeout: specifies the maximum time the request should wait.
        response = requests.get(url, params=params, timeout=10)
        # The response.raise_for_status() method raises an HTTPError exception
        # if a 4xx (Client Error) or 5xx (Server Error) response code is received.
        # This allows 'tenacity' to catch the error.
        response.raise_for_status()

        data = response.json() # Parse the response in JSON format.
        logger.info(f"Fetched {len(data.get('news', []))} news articles from API in {lang.upper()} (Offset: {offset}).")

        # Pause after each successful request to avoid hitting API rate limits
        time.sleep(SLEEP_TIME_BETWEEN_REQUESTS)

        # Check if 'news' key exists, return an empty list otherwise
        return data.get("news", [])

    except requests.exceptions.Timeout:
        # Error caught when the request times out
        logger.error(f"API request timed out (language: {lang.upper()}, Offset: {offset}).")
        # Re-raise the exception so 'tenacity' can catch it and retry
        raise

    except requests.exceptions.RequestException as e:
        # General HTTP request errors (connection error, invalid URL, etc.)
        logger.error(f"An error occurred during the API request (language: {lang.upper()}, Offset: {offset}): {e}")
        # If there's an error message in the response, log that too
        if hasattr(e, 'response') and e.response is not None:
            logger.debug(f"API response: {e.response.text[:500]}") # Log the first 500 characters of the response text
        raise # Re-raise the exception

    except json.JSONDecodeError as e:
        # Case where the API response is not in JSON format
        logger.error(f"API response could not be parsed as JSON (language: {lang.upper()}, Offset: {offset}): {e}")
        if response is not None:
            logger.debug(f"API response text: {response.text[:500]}")
        raise # Re-raise the exception

    except Exception as e:
        # All other unexpected errors not covered by the specific exceptions above
        logger.critical(f"Critical error occurred while fetching news from API (language: {lang.upper()}, Offset: {offset}): {e}", exc_info=True)
        raise # Re-raise the exception