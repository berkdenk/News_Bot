# api_utils.py
import requests
import os
from dotenv import load_dotenv
import logging # Yeni ekledik (main.py'den logger'ı kullanmak için)
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type # Yeni ekledik

# main.py'deki logger'ı alalım
logger = logging.getLogger(__name__)

# --- Retry Dekorasyonu ---
# requests.exceptions.RequestException türündeki hatalarda 3 defa, 5 saniye aralıklarla dene
@retry(stop=stop_after_attempt(3), wait=wait_fixed(5), retry=retry_if_exception_type(requests.exceptions.RequestException))
def fetch_news_from_api(api_key, lang, earliest_publish_date, offset):
    """
    World News API'dan belirli parametrelere göre haberleri çeker.
    """
    # config.py'den SEARCH_KEYWORDS'ü çekmeliyiz (burada yok, main'den geliyor. Ya da burada da import edilebilir)
    # Şimdilik global bir değişken veya parametre olarak kabul edelim
    from config import SEARCH_KEYWORDS, ARTICLES_PER_REQUEST # Buraya da ekledik
    
    url = "https://api.worldnewsapi.com/search-news"
    params = {
        "api-key": api_key,
        "language": lang,
        "earliest-publish-date": earliest_publish_date,
        "text": SEARCH_KEYWORDS,
        "offset": offset,
        "number": ARTICLES_PER_REQUEST
    }

    try:
        # Timeout değeri ekledik (örneğin 10 saniye)
        response = requests.get(url, params=params, timeout=10) 
        response.raise_for_status() # HTTP hataları (4xx, 5xx) için istisna fırlatır

        data = response.json()
        logger.info(f"API'dan {lang.upper()} dilinde {len(data.get('news', []))} haber çekildi (Offset: {offset}).")
        return data.get("news", [])

    except requests.exceptions.Timeout:
        logger.error(f"API isteği zaman aşımına uğradı ({lang.upper()} dili, Offset: {offset}).")
        raise # Tenacity'nin yakalaması için istisnayı yeniden fırlat

    except requests.exceptions.RequestException as e:
        logger.error(f"API isteği sırasında bir hata oluştu ({lang.upper()} dili, Offset: {offset}): {e}")
        raise # Tenacity'nin yakalaması için istisnayı yeniden fırlat

    except ValueError as e: # JSON decode hatası için
        logger.error(f"API yanıtı JSON olarak çözümlenemedi ({lang.upper()} dili, Offset: {offset}): {e}")
        return None # Bu durumda retry yapmayız, çünkü format hatası kalıcı olabilir