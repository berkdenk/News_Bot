# csv_manager.py

import csv      # Library for reading/writing CSV files
import os       # Library for file system operations
from datetime import datetime # Library for working with date and time objects
import logging  # Library for logging

# Using the same logger as in main.py
logger = logging.getLogger('main_news_bot_logger')

def get_existing_article_ids_and_latest_date(csv_filename):
    """
    Reads existing news IDs and the latest news date from the specified CSV file.
    Also tracks the IDs of news articles that have been posted to WordPress.

    Parameters:
    csv_filename (str): The name of the CSV file to read.

    Returns:
    tuple: (set<str>, datetime, dict<str, dict>) -
           A set of existing news IDs,
           the publish date of the latest news,
           and a dictionary containing WordPress publication statuses and IDs of articles.
           Returns an empty set, None, and an empty dictionary if the file doesn't exist or is empty.
    """
    existing_ids = set() # News IDs from World News API
    latest_date = None   # Date of the latest news
    # Dictionary to hold the publication status and WordPress ID of each article
    # Key: World News API article ID, Value: {'is_published_to_wp': bool, 'wordpress_post_id': int/None}
    article_status = {}

    if not os.path.exists(csv_filename):
        logger.info(f"'{csv_filename}' file does not exist yet.")
        return existing_ids, latest_date, article_status

    try:
        with open(csv_filename, mode='r', newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            
            # Check if all required columns are present
            required_fieldnames = ['id', 'title', 'publish_date', 'is_published_to_wp', 'wordpress_post_id']
            if not all(field in reader.fieldnames for field in required_fieldnames):
                logger.warning(f"Missing columns found in '{csv_filename}'. File will be recreated.")
                return set(), None, {} # Return empty on invalid file format

            for row in reader:
                article_id = row.get('id')
                publish_date_str = row.get('publish_date')
                is_published_to_wp_str = row.get('is_published_to_wp', 'False') # Default to 'False'
                wordpress_post_id_str = row.get('wordpress_post_id')

                if article_id:
                    existing_ids.add(article_id)
                    article_status[article_id] = {
                        'is_published_to_wp': is_published_to_wp_str.lower() == 'true',
                        'wordpress_post_id': int(wordpress_post_id_str) if wordpress_post_id_str and wordpress_post_id_str.isdigit() else None
                    }

                if publish_date_str:
                    try:
                        current_date = datetime.strptime(publish_date_str, '%Y-%m-%d %H:%M:%S')
                        if latest_date is None or current_date > latest_date:
                            latest_date = current_date
                    except ValueError:
                        logger.warning(f"Invalid date format '{publish_date_str}', skipping.")

        logger.info(f"Found {len(existing_ids)} existing articles in '{csv_filename}'. Latest date: {latest_date}")
    except Exception as e:
        logger.error(f"Error reading '{csv_filename}': {e}. Returning empty.")
        return set(), None, {} # Return empty in case of an error

    return existing_ids, latest_date, article_status

def save_articles_to_csv(articles, csv_filename, existing_ids):
    """
    Saves newly fetched articles to the CSV file.
    Does not overwrite existing articles, only appends new ones.
    Adds 'is_published_to_wp' and 'wordpress_post_id' fields.

    Parameters:
    articles (list): List of articles to be saved (each article as a dictionary).
    csv_filename (str): The name of the CSV file to save to.
    existing_ids (set): A set of article IDs already present in the CSV file.

    Returns:
    int: The number of new articles saved to the CSV file.
    """
    newly_saved_count = 0
    # Fields (column headers) where articles will be saved
    # NEW COLUMNS ADDED: 'is_published_to_wp', 'wordpress_post_id'
    fieldnames = ['id', 'title', 'text', 'url', 'publish_date', 'language', 'author', 'image', 'is_published_to_wp', 'wordpress_post_id']

    file_exists = os.path.exists(csv_filename)
    
    # Using a temporary list to write all rows from memory
    rows_to_write = []
    
    # Read existing file content (if it exists and is not empty)
    current_rows = []
    if file_exists and os.stat(csv_filename).st_size > 0:
        try:
            with open(csv_filename, mode='r', newline='', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                # Read if it has valid column headers
                if all(field in reader.fieldnames for field in fieldnames[:8]): # First 8 columns are sufficient for check
                     current_rows = list(reader)
                else:
                    logger.warning(f"Column headers of '{csv_filename}' are old or missing. File will be recreated.")
        except Exception as e:
            logger.error(f"Error reading existing '{csv_filename}': {e}. File will be written from scratch.")
            current_rows = [] # Clear existing rows in case of an error

    # Add existing rows (for rewriting) to the rows_to_write list
    rows_to_write.extend(current_rows)

    for article in articles:
        article_id = str(article.get('id'))

        if article_id not in existing_ids: # Only add new ones
            row_data = {
                'id': article.get('id', ''),
                'title': article.get('title', ''),
                'text': article.get('text', ''),
                'url': article.get('url', ''),
                'publish_date': article.get('publish_date', ''),
                'language': article.get('language', ''),
                'author': article.get('author', ''),
                'image': article.get('image', ''),
                'is_published_to_wp': 'False', # Default: not yet published
                'wordpress_post_id': ''       # WordPress ID is empty
            }
            rows_to_write.append(row_data) # Add new article to the list
            existing_ids.add(article_id)   # Add to existing IDs
            newly_saved_count += 1
    
    # Write all rows (old + new) to the file
    try:
        with open(csv_filename, mode='w', newline='', encoding='utf-8') as file: # Open in 'w' mode to rewrite the file
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader() # Always write the header row
            writer.writerows(rows_to_write) # Write all rows
        logger.info(f"{newly_saved_count} new articles saved to '{csv_filename}'.")
    except Exception as e:
        logger.error(f"Error saving articles to '{csv_filename}': {e}")

    return newly_saved_count

def update_article_in_csv(csv_filename, article_id, wordpress_post_id):
    """
    Updates the WordPress publication status and post ID for a specific article in the CSV file.
    """
    updated_rows = []
    found = False
    fieldnames = ['id', 'title', 'text', 'url', 'publish_date', 'language', 'author', 'image', 'is_published_to_wp', 'wordpress_post_id']

    try:
        # Read existing CSV content
        with open(csv_filename, mode='r', newline='', encoding='utf-8') as infile:
            reader = csv.DictReader(infile)
            # We could raise an error if column headers are missing or different, but for now, we assume they are correct
            if not all(field in reader.fieldnames for field in fieldnames[:8]):
                logger.error(f"CSV file column headers are different than expected, cannot update.")
                return False

            for row in reader:
                if row.get('id') == article_id:
                    row['is_published_to_wp'] = 'True'
                    row['wordpress_post_id'] = str(wordpress_post_id) # Save WordPress ID as string
                    found = True
                    logger.debug(f"  CSV record updated: Article ID={article_id}, WordPress Post ID={wordpress_post_id}")
                updated_rows.append(row)
        
        if not found:
            logger.warning(f"  Article ID '{article_id}' not found in CSV file, update failed.")
            return False

        # Write the updated content back to the file
        with open(csv_filename, mode='w', newline='', encoding='utf-8') as outfile:
            writer = csv.DictWriter(outfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(updated_rows)
        logger.info(f"CSV record for article ID '{article_id}' successfully updated.")
        return True

    except Exception as e:
        logger.error(f"Error updating article in CSV file (ID: {article_id}): {e}")
        return False