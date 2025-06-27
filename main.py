# main.py

import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import requests
import base64
import logging
from logging.handlers import RotatingFileHandler
import json
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type, retry_if_result
from urllib.parse import urlparse
import mimetypes
from io import BytesIO
from PIL import Image # Pillow library, install with pip install Pillow

from deep_translator import GoogleTranslator # Install with pip install deep-translator

from config import (
    CSV_FILENAME,
    TARGET_LANGUAGES,
    ARTICLES_PER_REQUEST,
    MAX_PAGES_TO_FETCH,
    INITIAL_HISTORY_DAYS,
    WORDPRESS_API_URL,
    WORDPRESS_USERNAME,
    LOG_DIR,
    LOG_FILE,
    LOG_LEVEL,
    MAX_RETRIES,
    RETRY_DELAY_SECONDS,
    WORDPRESS_CATEGORIES,
    WORDPRESS_TAGS,
    DEFAULT_WORDPRESS_CATEGORY_ID
)
from api_utils import fetch_news_from_api
from csv_manager import get_existing_article_ids_and_latest_date, save_articles_to_csv, update_article_in_csv

load_dotenv()
API_KEY = os.getenv("WORLD_NEWS_API_KEY")

# --- Logging Configuration ---
os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger('main_news_bot_logger')
logger.setLevel(LOG_LEVEL)

if not logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    logger.addHandler(console_handler)

    file_handler = RotatingFileHandler(LOG_FILE, maxBytes=10*1024*1024, backupCount=5)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
# --- End Logging Configuration ---

# --- Initialize translator object with deep_translator ---
translator = GoogleTranslator(source='auto', target='tr')

# --- ENHANCED TRANSLATION FUNCTION ---
def translate_text(text, dest_lang='tr'):
    """Translates text to the target language (default: Turkish) and manages length limits."""
    # MAX_TRANSLATION_LENGTH removed. The translation API might have its own limits.
    text_to_translate = str(text) if text is not None else ""

    if not text_to_translate.strip():
        return ""
    
    # Length warning removed, but keep in mind that the translation API has its own limits.
    # This warning might be useful if you encounter translation errors with very long texts due to API limits.
    # original_length = len(text_to_translate)
    # if original_length > MAX_TRANSLATION_LENGTH:
    #     logger.warning(f"Warning: Text to be translated is too long ({original_length} characters). First {MAX_TRANSLATION_LENGTH} characters will be translated. Original: '{text_to_translate[:50]}...'")
    #     text_to_translate = text_to_translate[:MAX_TRANSLATION_LENGTH]

    try:
        translated_text = translator.translate(text_to_translate)
        
        if translated_text:
            return translated_text
        else:
            logger.error(f"Translation error: deep_translator returned empty text. Original text will be used. Original: '{text_to_translate[:50]}...'")
            return text_to_translate
    except Exception as e:
        logger.error(f"Translation error (deep_translator): {e}. Original text will be used. Original: '{text_to_translate[:50]}...'")
        return text_to_translate

# --- UPDATED FUNCTION: Upload Image to WordPress ---
def upload_image_to_wordpress(image_url):
    """
    Downloads an image from the given URL and uploads it to the WordPress media library.
    Attempts to convert all images to JPEG before uploading.
    Returns the media ID of the uploaded image if successful, otherwise None.
    """
    wp_username = WORDPRESS_USERNAME
    wp_app_password = os.getenv("WORDPRESS_APP_PASSWORD")

    if not wp_app_password:
        logger.error("ERROR: WordPress application password not found. Image cannot be uploaded.")
        return None

    credentials = f"{wp_username}:{wp_app_password}"
    token = base64.b64encode(credentials.encode()).decode("utf-8")

    headers = {
        "Authorization": f"Basic {token}"
    }

    try:
        logger.debug(f"  Downloading image: {image_url}")
        image_response = requests.get(image_url, stream=True, timeout=15)
        image_response.raise_for_status()

        original_image_content = image_response.content

        # Guess file name and extension from URL or MIME type
        parsed_url = urlparse(image_url)
        path = parsed_url.path
        extension = os.path.splitext(path)[1].lower() # Convert extension to lowercase
        
        # Determine MIME type via Content-Type header
        content_type_header = image_response.headers.get('Content-Type')
        mime_type = mimetypes.guess_type(image_url)[0] # Guess from URL
        if not mime_type and content_type_header: # If not guessed from URL, get from Content-Type
            mime_type = content_type_header
        # If still no mime_type or after conversion, default to image/jpeg
        if not mime_type:
            mime_type = 'image/jpeg' 
            extension = '.jpg'

        # Attempt to convert image to JPEG (for all images)
        # This can help resolve issues with WordPress servers handling different formats.
        converted_image_content = original_image_content
        converted_mime_type = 'image/jpeg'
        converted_extension = '.jpg'

        try:
            img = Image.open(BytesIO(original_image_content))
            # Convert to RGB if in RGBA mode to avoid incompatibility when saving as JPEG
            if img.mode == 'RGBA':
                img = img.convert('RGB')
            img_byte_arr = BytesIO()
            img.save(img_byte_arr, format='JPEG') # Save as JPEG
            converted_image_content = img_byte_arr.getvalue()
            logger.info(f"  Image successfully converted to JPEG (original MIME: {mime_type}).")
        except Exception as e:
            logger.warning(f"  Error converting image to JPEG: {e}. Attempting to upload with original image format. URL: {image_url}")
            # If conversion fails, continue using the original MIME and content
            converted_image_content = original_image_content
            converted_mime_type = mime_type # Preserve original MIME type
            converted_extension = extension # Preserve original extension

        # Check supported image formats (after conversion)
        # We only support JPEG, PNG, and GIF. WEBP is now converted.
        if converted_mime_type not in ['image/jpeg', 'image/png', 'image/gif', 'image/jpg']: 
            logger.warning(f"  Unsupported or unconverted image format: {converted_mime_type}. Image could not be uploaded. URL: {image_url}")
            return None
        
        # Create a safe file name
        file_name = f"news_image_{datetime.now().strftime('%Y%m%d%H%M%S_%f')}{converted_extension}"
        
        # WordPress media upload endpoint
        media_upload_url = WORDPRESS_API_URL.replace('/posts', '/media') 
        
        # requests.post's 'files' parameter handles multipart/form-data.
        files = {
            'file': (file_name, converted_image_content, converted_mime_type)
        }
        
        # When 'files' is used, Content-Type header is set automatically, so remove it from our headers
        upload_headers = {k:v for k,v in headers.items() if k.lower() != 'content-type'}

        logger.debug(f"  Sending image upload request to WordPress: {file_name}, MIME: {converted_mime_type}")
        upload_response = requests.post(media_upload_url, headers=upload_headers, files=files, timeout=30)
        upload_response.raise_for_status() # For HTTP errors

        media_data = upload_response.json()
        logger.debug(f"  Image upload response: {json.dumps(media_data)[:200]}...")
        
        return media_data.get('id') # Return the ID of the uploaded image

    except requests.exceptions.RequestException as e:
        # More specific logging for image download or WordPress upload errors
        if hasattr(e, 'response') and e.response is not None:
            if e.response.status_code in [401, 403]:
                logger.error(f"  Image download error: Source server returned authorization (401/403) error. Skipping image. URL: {image_url}")
                logger.debug(f"  Source server response: {e.response.text[:500]}...") # Log source server's response
                return None # Return None immediately on authorization error (skip image)
            else:
                logger.error(f"  Image download or WordPress upload error ({e.response.status_code}): {e}. URL: {image_url}")
                logger.error(f"  WordPress/API error response: {e.response.text}")
        else:
            logger.error(f"  Image download or WordPress upload error: {e}. URL: {image_url}")
        return None # Also return None for other request errors

    except Exception as e:
        logger.error(f"  Unexpected image upload error: {e}. URL: {image_url}")
        return None

# --- UPDATED FUNCTION: Check if Post Exists in WordPress ---
def check_if_post_exists_in_wordpress(post_title):
    """
    Checks if a post with the given title already exists in WordPress.
    Uses a partial title for broader search and details logs.
    'status=any' parameter has been removed.
    """
    wp_username = WORDPRESS_USERNAME
    wp_app_password = os.getenv("WORDPRESS_APP_PASSWORD")

    if not wp_app_password:
        logger.error("ERROR: WordPress application password not found. Cannot check for post existence in WordPress.")
        return False

    credentials = f"{wp_username}:{wp_app_password}"
    token = base64.b64encode(credentials.encode()).decode("utf-8")

    headers = {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json"
    }

    # Take the first 50 characters of the title or the whole title (for very long titles)
    search_query = post_title[:50] if len(post_title) > 50 else post_title
    
    # search_url: 'status=any' parameter removed, will only search published posts
    search_url = f"{WORDPRESS_API_URL}?search={requests.utils.quote(search_query)}&per_page=1"
    
    try:
        logger.debug(f"  Searching for post with title '{post_title[:50]}...' in WordPress. Search URL: {search_url}")
        response = requests.get(search_url, headers=headers, timeout=10)
        response.raise_for_status() # Raise an exception for HTTP errors

        data = response.json()
        logger.debug(f"  WordPress search API response (first 200 chars): {json.dumps(data)[:200]}...")

        if isinstance(data, list) and len(data) > 0:
            for post in data:
                # Check for exact title match.
                # WordPress API's search parameter can sometimes return partial matches.
                if post.get('title', {}).get('rendered') == post_title:
                    logger.info(f"  Post with title '{post_title}' already exists in WordPress (ID: {post['id']}).")
                    return True
            logger.debug(f"  Post with title '{post_title}' found in WordPress search results but no exact match.")
            return False
        else:
            logger.debug(f"  Post with title '{post_title}' not found in WordPress.")
            return False

    except requests.exceptions.Timeout:
        logger.warning(f"  WordPress post check timed out: '{post_title}'")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"  Error checking for post in WordPress: '{post_title}' - {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"  WordPress check error response: {e.response.text}")
        return False
    except json.JSONDecodeError as e:
        logger.error(f"  WordPress post check response could not be parsed as JSON: '{post_title}' - {e}")
        return False
    except Exception as e:
        logger.critical(f"  Critical error in WordPress post check: '{post_title}' - {e}", exc_info=True)
        return False

# --- WordPress Integration Function ---
@retry(stop=stop_after_attempt(MAX_RETRIES), wait=wait_fixed(RETRY_DELAY_SECONDS),
       retry=(retry_if_exception_type(requests.exceptions.RequestException) |
              retry_if_exception_type(json.JSONDecodeError) |
              retry_if_result(lambda result: result is False)))
def publish_article_to_wordpress(article_data):
    """
    Publishes a news dictionary (article_data) as a new post to WordPress.
    Automatically assigns categories and tags, and adds the image as a featured image.
    """
    article_title = article_data.get('title') or "Untitled News"
    article_content = article_data.get('text') or "News without content"
    article_url = article_data.get('url') or "#"
    image_url = article_data.get('image', '') # Get the image URL

    wp_username = WORDPRESS_USERNAME
    wp_app_password = os.getenv("WORDPRESS_APP_PASSWORD")

    if not wp_app_password:
        logger.error("ERROR: WordPress application password not found. Please ensure 'WORDPRESS_APP_PASSWORD' is defined in the '.env' file.")
        raise ValueError("WordPress application password not found.")

    credentials = f"{wp_username}:{wp_app_password}"
    token = base64.b64encode(credentials.encode()).decode("utf-8")
    
    headers = {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json"
    }

    # Content length restriction removed. WordPress's own limits or server performance might be affected.
    # if len(article_content) > 100000:
    #     logger.warning(f"Warning: Content of news titled '{article_title}' is too long ({len(article_content)} characters). Truncating...")
    #     article_content = article_content[:99000] + "..."

    post_content = f"{article_content}<p>Original source: <a href='{article_url}'>{article_url}</a></p>"

    assigned_categories = []
    assigned_tags = []

    if DEFAULT_WORDPRESS_CATEGORY_ID is not None and DEFAULT_WORDPRESS_CATEGORY_ID not in assigned_categories:
        assigned_categories.append(DEFAULT_WORDPRESS_CATEGORY_ID)

    title_lower = article_title.lower()
    content_lower = article_content.lower() # Convert news content to lowercase as well
    
    # Assign categories based on both title and content
    for keyword, category_id in WORDPRESS_CATEGORIES.items():
        if keyword.replace("_", " ") in title_lower or keyword.replace("_", " ") in content_lower: # Check both title and content
            if category_id not in assigned_categories:
                assigned_categories.append(category_id)
    assigned_categories = list(set(assigned_categories))

    # Assign tags based on both title and content
    for keyword, tag_id in WORDPRESS_TAGS.items():
        if keyword.replace("_", " ") in title_lower or keyword.replace("_", " ") in content_lower: # Check both title and content
            if tag_id not in assigned_tags:
                assigned_tags.append(tag_id)
    assigned_tags = list(set(assigned_tags))

    # --- NEWLY ADDED SECTION: Image upload and assignment as featured image ---
    featured_media_id = None
    if image_url:
        logger.debug(f"  Image URL found: {image_url}")
        try:
            featured_media_id = upload_image_to_wordpress(image_url)
            if featured_media_id:
                logger.info(f"  Image uploaded to WordPress, media ID: {featured_media_id}")
            else:
                logger.warning(f"  Image could not be uploaded to WordPress: {image_url}")
                # If image could not be uploaded, try using the default image
                # Assuming DEFAULT_FEATURED_IMAGE_ID is imported from config
                # If not imported, it needs to be added here.
                # For now, I'm assuming DEFAULT_FEATURED_IMAGE_ID is defined and imported in config.
                if hasattr(__import__('config'), 'DEFAULT_FEATURED_IMAGE_ID') and __import__('config').DEFAULT_FEATURED_IMAGE_ID is not None:
                    featured_media_id = __import__('config').DEFAULT_FEATURED_IMAGE_ID
                    logger.info(f"  Since image could not be uploaded, default featured image ({featured_media_id}) will be assigned.")

        except Exception as e:
            logger.error(f"  Unexpected error occurred while uploading image: {e}")
            # If an error occurred during image upload, try using the default image
            if hasattr(__import__('config'), 'DEFAULT_FEATURED_IMAGE_ID') and __import__('config').DEFAULT_FEATURED_IMAGE_ID is not None:
                featured_media_id = __import__('config').DEFAULT_FEATURED_IMAGE_ID
                logger.info(f"  Since an error occurred while uploading image, default featured image ({featured_media_id}) will be assigned.")

    post_data = {
        "title": article_title,
        "content": post_content,
        "status": "publish",
        "categories": assigned_categories,
        "tags": assigned_tags
    }

    if featured_media_id: # If image was successfully uploaded OR default was assigned
        post_data['featured_media'] = featured_media_id
        logger.debug(f"  featured_media added to post data: {featured_media_id}")

    try:
        logger.debug(f"  Sending to WordPress API: Title='{article_title[:50]}...'")
        logger.debug(f"  Assigned Categories: {assigned_categories}, Assigned Tags: {assigned_tags}")
        response = requests.post(WORDPRESS_API_URL, headers=headers, json=post_data, timeout=20)
        
        logger.debug(f"  WordPress API response code: {response.status_code}")
        logger.debug(f"  WordPress API response text: {response.text[:500]}...")
        
        if response.status_code in [201, 200]: 
            logger.info(f"  Successfully posted to WordPress: '{article_title}'")
            return response.json().get('id')
        else:
            logger.error(f"  Unexpected status occurred while posting to WordPress: Status={response.status_code} - Response={response.text}")
            return False
            
    except requests.exceptions.Timeout:
        logger.error(f"  WordPress API request timed out: '{article_title}'")
        raise
    except requests.exceptions.RequestException as e:
        logger.error(f"  Error connecting to WordPress API: '{article_title}' - {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"  WordPress error response: {e.response.text}")
        raise
    except Exception as e:
        logger.critical(f"  Critical error while posting to WordPress: '{article_title}' - {e}", exc_info=True)
        raise


def run_news_scraper():
    """
    Manages the main workflow of the bot.
    Fetches news from World News API, saves to CSV, and publishes to WordPress.
    """
    load_dotenv()
    API_KEY = os.getenv("WORLD_NEWS_API_KEY")

    if not API_KEY:
        logger.error("ERROR: API key not found. Please ensure 'WORLD_NEWS_API_KEY' is defined in the '.env' file.")
        return

    logger.info(f"Checking existing news and latest date in '{CSV_FILENAME}'...")
    existing_ids, latest_date_in_csv, article_publish_status = get_existing_article_ids_and_latest_date(CSV_FILENAME)
    
    if latest_date_in_csv:
        start_date_for_api = latest_date_in_csv.strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"Latest date in CSV is '{start_date_for_api}'. News after this date will be fetched.")
    else:
        start_date_for_api = (datetime.now() - timedelta(days=INITIAL_HISTORY_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"CSV is empty. News will be fetched from API starting from '{start_date_for_api}' (last {INITIAL_HISTORY_DAYS} days).")
            
    total_new_articles_fetched_and_saved = 0
    
    for lang_code in TARGET_LANGUAGES:
        logger.info(f"\n--- Fetching news in {lang_code.upper()} ---")
        current_offset = 0
        
        for page_num in range(MAX_PAGES_TO_FETCH):
            logger.info(f"  Sending request for page {page_num + 1} with Offset {current_offset} in {lang_code.upper()}...")
            
            fetched_articles = []
            try:
                fetched_articles = fetch_news_from_api(API_KEY, lang_code, start_date_for_api, current_offset)
            except Exception as e:
                logger.error(f"  Failed to fetch news from API or retry limit reached: {e}")
                break

            if not fetched_articles:
                logger.info(f"  No more new news found in {lang_code.upper()}.")
                break

            articles_to_add_to_csv = [
                article for article in fetched_articles
                if str(article.get('id')) not in existing_ids
            ]

            if articles_to_add_to_csv:
                newly_saved_count = save_articles_to_csv(articles_to_add_to_csv, CSV_FILENAME, existing_ids)
                total_new_articles_fetched_and_saved += newly_saved_count
                
                logger.info(f"  {len(fetched_articles)} news fetched in {lang_code.upper()}, {newly_saved_count} of them are new and saved to '{CSV_FILENAME}'.")
            else:
                logger.info(f"  No new news to add to CSV in {lang_code.upper()}.")
            
            articles_to_publish_to_wp = []
            for article in fetched_articles:
                article_id_str = str(article.get('id'))
                if article_id_str in article_publish_status and not article_publish_status[article_id_str]['is_published_to_wp']:
                    articles_to_publish_to_wp.append(article)
                elif article_id_str not in article_publish_status:
                     articles_to_publish_to_wp.append(article)

            if articles_to_publish_to_wp:
                logger.info(f"  There are {len(articles_to_publish_to_wp)} news to send to WordPress...")
                for article in articles_to_publish_to_wp:
                    article_title = article.get('title', 'Unknown News')
                    article_world_news_id = str(article.get('id'))

                    # Check if it already exists in WordPress (secondary, title-based check)
                    if check_if_post_exists_in_wordpress(article_title):
                        logger.info(f"  Post with title '{article_title}' already exists in WordPress (secondary check). Updating CSV.")
                        if not article_publish_status.get(article_world_news_id, {}).get('is_published_to_wp', False):
                            update_article_in_csv(CSV_FILENAME, article_world_news_id, "EXISTING_IN_WP")
                            article_publish_status[article_world_news_id] = {'is_published_to_wp': True, 'wordpress_post_id': "EXISTING_IN_WP"}
                        continue

                    try:
                        wordpress_post_id = publish_article_to_wordpress(article)
                        if wordpress_post_id:
                            update_article_in_csv(CSV_FILENAME, article_world_news_id, wordpress_post_id)
                            article_publish_status[article_world_news_id] = {'is_published_to_wp': True, 'wordpress_post_id': wordpress_post_id}
                        else:
                            logger.error(f"  Failed to post to WordPress or could not retrieve post ID: '{article_title}'")
                    except Exception as e:
                        logger.error(f"  Persistent error occurred while posting news to WordPress: '{article_title}' - {e}")
            else:
                logger.info(f"  No new news to post to WordPress in {lang_code.upper()}.")


            current_offset += ARTICLES_PER_REQUEST

    logger.info(f"\n--- Data Fetching Completed ---")
    final_existing_ids, _, final_article_status = get_existing_article_ids_and_latest_date(CSV_FILENAME)
    logger.info(f"A total of {total_new_articles_fetched_and_saved} new articles were saved to '{CSV_FILENAME}'.")
    logger.info(f"There are a total of {len(final_existing_ids)} unique articles in the CSV file.")
    published_count = sum(1 for status in final_article_status.values() if status['is_published_to_wp'])
    logger.info(f"Out of a total of {len(final_existing_ids)} articles in the CSV, {published_count} are marked as published to WordPress.")

if __name__ == "__main__":
    run_news_scraper()