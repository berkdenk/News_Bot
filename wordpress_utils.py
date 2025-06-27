# wordpress_utils.py
import requests
import json
import base64
import time
from config import WORDPRESS_API_URL, WORDPRESS_USERNAME, WORDPRESS_APP_PASSWORD, MAX_RETRIES, RETRY_DELAY_SECONDS
import logging

logger = logging.getLogger(__name__)

def send_news_to_wordpress(news_item):
    """
    Sends a news item to WordPress as a new post.
    Handles authentication, category/tag assignment, and retries on failure.

    Parameters:
    news_item (dict): A dictionary containing the news article data,
                      expected to have 'title' and 'text' keys.

    Returns:
    bool: True if the news item was successfully sent to WordPress, False otherwise.
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Basic " + base64.b64encode(f"{WORDPRESS_USERNAME}:{WORDPRESS_APP_PASSWORD}".encode()).decode("utf-8")
    }

    # Example category and tag assignment. Logic can be added later to make this dynamic,
    # e.g., by searching for specific keywords in the news title or content.
    # For now, we'll use fixed IDs.

    category_ids = []
    tag_ids = []

    # Example: If the news title contains 'Ukraine', assign a specific category/tag
    title_lower = news_item['title'].lower()
    if "ukraine" in title_lower or "ukrayna" in title_lower:
        # Replace these IDs with the actual IDs of your WordPress categories/tags
        # CATEGORY IDs HERE (e.g., 5)
        if 5 not in category_ids: category_ids.append(5) # 'War News' or relevant category ID
        # TAG IDs HERE (e.g., 10)
        if 10 not in tag_ids: tag_ids.append(10) # 'Ukraine' or relevant tag ID

    if "poland" in title_lower or "polonya" in title_lower:
        # CATEGORY IDs HERE (e.g., 6)
        if 6 not in category_ids: category_ids.append(6) # 'Poland News' or relevant category ID
        # TAG IDs HERE (e.g., 11)
        if 11 not in tag_ids: tag_ids.append(11) # 'Poland' or relevant tag ID

    # If no categories are determined, we can assign a default category (e.g., "General" category ID 1)
    if not category_ids:
        category_ids.append(1) # The ID for the "Uncategorized" category in WordPress is usually 1. Please verify.


    data = {
        "title": news_item['title'],
        "content": news_item['text'],
        "status": "publish",
        "categories": category_ids, # List of category IDs
        "tags": tag_ids # List of tag IDs
    }

    json_data = json.dumps(data)

    response = None # Initialize response to None
    for attempt in range(MAX_RETRIES):
        try:
            logger.debug(f"  Sending to WordPress API: Title='{news_item['title'][:50]}...'")
            response = requests.post(WORDPRESS_API_URL, headers=headers, data=json_data, timeout=20) # Added timeout
            response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
            logger.debug(f"  WordPress API response code: {response.status_code}")
            logger.debug(f"  WordPress API response text: {response.text[:100]}...")
            logger.info(f"  Successfully sent to WordPress: '{news_item['title']}'")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"  Error connecting to WordPress API (Attempt {attempt + 1}/{MAX_RETRIES}): '{news_item['title']}' - {e}")
            if response is not None:
                logger.debug(f"  WordPress API response code: {response.status_code}")
                logger.debug(f"  WordPress API response text: {response.text}")
            if attempt < MAX_RETRIES - 1:
                logger.info(f"  Retrying after {RETRY_DELAY_SECONDS} seconds...")
                time.sleep(RETRY_DELAY_SECONDS)
            else:
                logger.error(f"  Maximum number of retries reached. News could not be sent: '{news_item['title']}'")
                return False
        except json.JSONDecodeError as e:
            logger.error(f"  WordPress API response could not be parsed as JSON (Attempt {attempt + 1}/{MAX_RETRIES}): '{news_item['title']}' - {e}")
            if response is not None:
                logger.debug(f"  WordPress API response code: {response.status_code}")
                logger.debug(f"  WordPress API response text: {response.text}")
            if attempt < MAX_RETRIES - 1:
                logger.info(f"  Retrying after {RETRY_DELAY_SECONDS} seconds...")
                time.sleep(RETRY_DELAY_SECONDS)
            else:
                logger.error(f"  Maximum number of retries reached. News could not be sent: '{news_item['title']}'")
                return False
        except Exception as e:
            logger.error(f"  An unexpected error occurred while sending to WordPress (Attempt {attempt + 1}/{MAX_RETRIES}): '{news_item['title']}' - {e}")
            if attempt < MAX_RETRIES - 1:
                logger.info(f"  Retrying after {RETRY_DELAY_SECONDS} seconds...")
                time.sleep(RETRY_DELAY_SECONDS)
            else:
                logger.error(f"  Maximum number of retries reached. News could not be sent: '{news_item['title']}'")
                return False