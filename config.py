# config.py

import os
import logging  # Required to define logging levels

# --- World News API Basic Settings ---
# Base URL used to fetch news from the API
BASE_URL = "https://api.worldnewsapi.com/search-news"

# --- File Names ---
# Name of the CSV file where fetched news articles will be saved
CSV_FILENAME = "polonya_turk_haberleri.csv"

# --- News Filtering and Search Parameters ---
# ISO 3166 country code for filtering news related to Poland
POLAND_COUNTRY_CODE = "PL"

# Keywords to search for in the API. Use 'OR' operator to search for multiple terms.
# The 'text' parameter in World News API has a 100-character limit.
SEARCH_KEYWORDS = "Poland AND (Türkiye OR Turkish OR student OR Visa)"
#SEARCH_KEYWORDS = "Polska AND (Turcja OR turecki OR migracja OR ambasada OR student OR wiza OR ekonomia)"
#SEARCH_KEYWORDS = "Poland AND (Türkiye OR migration OR student OR visa OR economy)"

# ISO 639-1 language codes for news fetching
# Fetching news in 'pl' (Polish) and 'en' (English)
TARGET_LANGUAGES = ["en", "pl"]

# --- Pagination and Limit Settings ---
# Number of articles to fetch per API request
ARTICLES_PER_REQUEST = 2
# Maximum number of pages to fetch from the API per language.
# This limit helps avoid exceeding the API usage quota.
MAX_PAGES_TO_FETCH = 2
# If the CSV file is empty or a fresh start is desired, how many days back to fetch news from
INITIAL_HISTORY_DAYS = 30

# --- Delay Between API Requests (in seconds) ---
# To avoid hitting API rate limits, a delay is required between requests
SLEEP_TIME_BETWEEN_REQUESTS = 1

# --- Error Handling and Retry Settings (for Tenacity Library) ---
# Maximum number of retries when connecting to API or WordPress
MAX_RETRIES = 5
# Delay between retries (in seconds)
RETRY_DELAY_SECONDS = 10

# --- Logging Settings ---
# Directory where log files will be saved
LOG_DIR = "logs"
# Full path to the log file
LOG_FILE = os.path.join(LOG_DIR, "news_bot.log")
# Logging level.
# DEBUG: Most detailed logs (useful during development)
# INFO: General info messages
# WARNING: Potential issues
# ERROR: Error situations
# CRITICAL: Critical errors (may cause the application to stop)
LOG_LEVEL = logging.DEBUG

# --- WordPress Integration Settings ---
# URL of the WordPress REST API endpoint for posting content
WORDPRESS_API_URL = "http://localhost/haberlerim/wp-json/wp/v2/posts"
# Username used to publish posts on WordPress.
# The application password for this user should be defined in the .env file (not stored here for security).
WORDPRESS_USERNAME = "aliyigitogun"

# --- WordPress Category and Tag IDs ---
# IMPORTANT: The IDs in these dictionaries must match the actual category and tag IDs on YOUR WordPress site.
# You can find them in the WordPress admin panel (Posts > Categories/Tags, from the edit screen URL).

# WordPress category names and their IDs where news should be assigned
WORDPRESS_CATEGORIES = {
    "general": 1,
    "politics": 3,     # Examples: "politics", "government", "election", "parliament"
    "poland": 7,       # Examples: "poland", "polska", "warsaw", "varşova"
    "economy": 5,      # Examples: "economy", "gospodarka", "inflation", "trade"
    "ukraine": 8,      # Examples: "ukraine", "ukraina", "kyiv", "kiev"
    "student": 9,      # Examples: "student", "education", "university", "scholarship"
    "turkish": 10,     # Examples: "turkish", "turkey", "ankara", "istanbul"
    "visa": 11,        # Examples: "visa", "schengen", "passport", "migration", "refugee"
    "russia": 12,      # Examples: "russia", "rosja", "moscow", "moskova"
    "war": 13,         # Examples: "war", "conflict", "operation"
    # Additional categories...
}

WORDPRESS_TAGS = {
    "ukraine": 14,
    "russia": 15,
    "poland": 16,
    "war": 17,
    "economy": 18,
    "politics": 19,
    "turkish": 20,
    "student": 21,
    "visa": 22,
    "schengen": 23,
    "usa": 24,         # Examples: "usa", "america", "united states"
    "europe": 25,      # Examples: "europe", "european union", "eu"
    # Additional tags...
}

# If no specific category can be determined for a news article, the default category ID to assign
DEFAULT_WORDPRESS_CATEGORY_ID = 1
