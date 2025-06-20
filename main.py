# main.py
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import requests
import base64
import logging
from logging.handlers import RotatingFileHandler
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

from config import (
    CSV_FILENAME,
    TARGET_LANGUAGES,
    ARTICLES_PER_REQUEST,
    MAX_PAGES_TO_FETCH,
    INITIAL_HISTORY_DAYS,
    # WordPress Ayarları (şimdilik yorum satırı, ileride kullanılacak)
    # WORDPRESS_API_URL,
    # WORDPRESS_USERNAME,
    LOG_DIR,
    LOG_FILE,
    LOG_LEVEL
)
from api_utils import fetch_news_from_api
from csv_manager import get_existing_article_ids_and_latest_date, save_articles_to_csv

# --- Loglama konfigürasyonu ---
# Log klasörünü oluştur
os.makedirs(LOG_DIR, exist_ok=True)

# Logger'ı ayarla. Özel bir isim vererek api_utils.py'den de aynı logger'ı kullanabiliriz.
logger = logging.getLogger('main_news_bot_logger')
logger.setLevel(LOG_LEVEL)

# Mevcut handler'ları temizle (birden fazla çalıştırmada mükerrer loglamayı önlemek için)
if not logger.handlers:
    # Konsol handler'ı (terminale çıktı için)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    logger.addHandler(console_handler)

    # Dosya handler'ı (log dosyasına yazmak için)
    # RotatingFileHandler: Belirli boyuta ulaşınca yeni bir dosyaya geçer ve eski logları siler
    file_handler = RotatingFileHandler(LOG_FILE, maxBytes=10*1024*1024, backupCount=5) # 10MB, 5 yedek dosya
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
# --- Loglama konfigürasyonu sonu ---

# --- WordPress Entegrasyon Fonksiyonu (Şimdilik Yorum Satırı) ---
# def publish_article_to_wordpress(article_title, article_content, article_url):
#     """
#     Bir haberi WordPress'e yeni bir gönderi olarak yayınlar.
#     """
#     wp_username = WORDPRESS_USERNAME
#     wp_app_password = os.getenv("WORDPRESS_APP_PASSWORD")

#     if not wp_app_password:
#         logger.error("HATA: WordPress uygulama şifresi bulunamadı. Lütfen '.env' dosyasında 'WORDPRESS_APP_PASSWORD' tanımlı olduğundan emin olun.")
#         return False

#     credentials = f"{wp_username}:{wp_app_password}"
#     token = base64.b64encode(credentials.encode()).decode("utf-8")
    
#     headers = {
#         "Authorization": f"Basic {token}",
#         "Content-Type": "application/json"
#     }

#     post_data = {
#         "title": article_title,
#         "content": f"{article_content}<p>Orijinal kaynak: <a href='{article_url}'>{article_url}</a></p>",
#         "status": "publish" # Veya "draft" olarak ayarlayabilirsiniz
#         # "categories": [1, 2],
#         # "tags": ["haber", "polonya"],
#     }

#     try:
#         response = requests.post(WORDPRESS_API_URL, headers=headers, json=post_data)
#         response.raise_for_status()

#         if response.status_code == 201:
#             logger.info(f"  WordPress'e başarıyla gönderildi: '{article_title}'")
#             return True
#         else:
#             logger.error(f"  WordPress'e gönderilirken bir hata oluştu: {response.status_code} - {response.text}")
#             return False

#     except requests.exceptions.RequestException as e:
#         logger.error(f"  WordPress API'ye bağlanırken hata oluştu: {e}")
#         return False
# --- WordPress Entegrasyon Fonksiyonu Sonu ---


def run_news_scraper():
    """
    World News API'dan haberleri çeker ve CSV dosyasına kaydeder.
    """
    load_dotenv()
    API_KEY = os.getenv("WORLD_NEWS_API_KEY")

    if not API_KEY:
        logger.error("HATA: API anahtarı bulunamadı. Lütfen '.env' dosyasında 'WORLD_NEWS_API_KEY' tanımlı olduğundan emin olun.")
        return

    logger.info(f"'{CSV_FILENAME}' dosyasındaki mevcut haberler ve en son tarih kontrol ediliyor...")
    existing_ids, latest_date_in_csv = get_existing_article_ids_and_latest_date(CSV_FILENAME)
    
    # API'dan her zaman son INITIAL_HISTORY_DAYS kadar geçmişe bak.
    start_date_for_api = (datetime.now() - timedelta(days=INITIAL_HISTORY_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"API'dan haberler '{start_date_for_api}' tarihinden itibaren (son {INITIAL_HISTORY_DAYS} gün) çekilecek.")
            
    total_new_articles_fetched_and_saved = 0
    
    for lang_code in TARGET_LANGUAGES:
        logger.info(f"\n--- {lang_code.upper()} dilinde haberler çekiliyor ---")
        current_offset = 0
        
        for page_num in range(MAX_PAGES_TO_FETCH):
            logger.info(f"  {lang_code.upper()} dilinde, Offset {current_offset} ile sayfa {page_num + 1} için istek gönderiliyor...")
            
            fetched_articles = None
            try:
                # API çağrısı
                fetched_articles = fetch_news_from_api(API_KEY, lang_code, start_date_for_api, current_offset)
            except Exception as e: # Tenacity'nin fırlatabileceği RetryError'ı veya diğer beklenmedik hataları yakala
                logger.error(f"  API'dan haber çekme başarısız oldu veya yeniden deneme limitine ulaşıldı: {e}")
                break # Bu dildeki haber çekmeyi durdur

            if not fetched_articles: # Boş liste gelirse
                logger.info(f"  {lang_code.upper()} dilinde daha fazla yeni haber bulunamadı.")
                break 
            
            newly_saved_count = save_articles_to_csv(fetched_articles, CSV_FILENAME, existing_ids)
            total_new_articles_fetched_and_saved += newly_saved_count
            
            logger.info(f"  {lang_code.upper()} dilinde {len(fetched_articles)} haber çekildi, bunlardan {newly_saved_count} tanesi yeni ve kaydedildi.")
            
            # --- YENİ EKLENEN KISIM: Haberleri WordPress'e Gönder (Şimdilik Yorum Satırı) ---
            # if newly_saved_count > 0:
            #     logger.info(f"  Yeni haberler WordPress'e gönderiliyor...")
            #     for article in fetched_articles:
            #         if article['id'] not in existing_ids: # Zaten existing_ids setine eklenmiş olmalı, bu kontrol bir safety net.
            #             title = article.get('title') or "Başlıksız Haber"
            #             text = article.get('text') or "İçeriksiz Haber"
            #             url = article.get('url') or "#" 
            #             publish_article_to_wordpress(title, text, url)
            #             existing_ids.add(article['id'])
            # --- YENİ EKLENEN KISIM SONU ---

            current_offset += ARTICLES_PER_REQUEST

    logger.info(f"\n--- Veri Çekme Tamamlandı ---")
    logger.info(f"Toplamda {total_new_articles_fetched_and_saved} yeni haber '{CSV_FILENAME}' dosyasına kaydedildi.")
    logger.info(f"CSV dosyasında toplam {len(existing_ids)} benzersiz haber mevcut.")

if __name__ == "__main__":
    run_news_scraper()