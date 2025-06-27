# api_utils.py

import requests # HTTP istekleri için kütüphane
import json     # JSON verilerini işlemek için kütüphane
import time     # İşlemler arasında beklemek için kütüphane
import logging  # Loglama için kütüphane
# tenacity: Hata durumlarında otomatik yeniden deneme yapmak için kullanılan kütüphane
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

# config.py'den gerekli ayarları import ediyoruz
from config import (
    SEARCH_KEYWORDS,             # Arama anahtar kelimeleri
    ARTICLES_PER_REQUEST,        # Her istekte çekilecek makale sayısı
    SLEEP_TIME_BETWEEN_REQUESTS, # İstekler arası bekleme süresi
    MAX_RETRIES,                 # Maksimum yeniden deneme sayısı
    RETRY_DELAY_SECONDS          # Yeniden denemeler arası bekleme süresi
)

# main.py'deki logger ile aynı logger'ı kullanıyoruz, böylece tüm loglar tek bir dosyada toplanır
logger = logging.getLogger('main_news_bot_logger')

# --- Retry Dekorasyonu ---
# Bu dekoratör, 'fetch_news_from_api' fonksiyonu bir hata fırlattığında (Exception),
# belirlenen sayıda (MAX_RETRIES) ve aralıkta (RETRY_DELAY_SECONDS) tekrar denemesini sağlar.
# requests.exceptions.RequestException: Network sorunları, timeout gibi HTTP istek hataları
# json.JSONDecodeError: API'dan gelen yanıtın geçerli bir JSON olmaması durumları
@retry(stop=stop_after_attempt(MAX_RETRIES), wait=wait_fixed(RETRY_DELAY_SECONDS),
       retry=(retry_if_exception_type(requests.exceptions.RequestException) |
              retry_if_exception_type(json.JSONDecodeError)))
def fetch_news_from_api(api_key, lang, earliest_publish_date, offset):
    """
    World News API'dan belirli parametrelere göre haberleri çeker.
    Yeniden deneme (retry) mekanizması içerir.

    Parametreler:
    api_key (str): World News API anahtarı.
    lang (str): Haberlerin çekileceği dil kodu (örn: "pl", "en").
    earliest_publish_date (str): Haberlerin çekileceği en eski yayın tarihi (YYYY-MM-DD HH:MM:SS formatında).
    offset (int): API'dan haber çekmeye başlanacak ofset (sayfalama için).

    Dönüş:
    list: Çekilen haberlerin bir listesi (her haber bir sözlük olarak).
    """
    url = "https://api.worldnewsapi.com/search-news" # API'ın temel arama URL'si
    params = {
        "api-key": api_key,
        "language": lang,
        "earliest-publish-date": earliest_publish_date,
        "text": SEARCH_KEYWORDS, # config.py'den gelen anahtar kelimeler
        "offset": offset,
        "number": ARTICLES_PER_REQUEST # Her istekte çekilecek haber sayısı
    }

    try:
        logger.debug(f"  API isteği gönderiliyor ({lang.upper()} dili, Offset: {offset}).")
        # HTTP GET isteği gönderilir. timeout: isteğin maksimum kaç saniye beklemesi gerektiğini belirtir.
        response = requests.get(url, params=params, timeout=10)
        # response.raise_for_status() metodu, 4xx (Client Error) veya 5xx (Server Error) yanıt kodları alındığında
        # bir HTTPError istisnası fırlatır. Bu, tenacity'nin hatayı yakalamasını sağlar.
        response.raise_for_status()

        data = response.json() # Yanıtı JSON formatında ayrıştırır.
        logger.info(f"API'dan {lang.upper()} dilinde {len(data.get('news', []))} haber çekildi (Offset: {offset}).")

        # API kullanım limitlerine takılmamak için her başarılı istekten sonra bekleme
        time.sleep(SLEEP_TIME_BETWEEN_REQUESTS)

        # 'news' anahtarının olup olmadığını kontrol et, yoksa boş liste dön
        return data.get("news", [])

    except requests.exceptions.Timeout:
        # İstek zaman aşımına uğradığında yakalanan hata
        logger.error(f"API isteği zaman aşımına uğradı ({lang.upper()} dili, Offset: {offset}).")
        # Hatayı yeniden fırlatıyoruz ki 'tenacity' bunu yakalayıp yeniden denesin
        raise

    except requests.exceptions.RequestException as e:
        # Genel HTTP istek hataları (bağlantı hatası, geçersiz URL vb.)
        logger.error(f"API isteği sırasında bir hata oluştu ({lang.upper()} dili, Offset: {offset}): {e}")
        # Eğer yanıtta bir hata mesajı varsa, onu da logla
        if hasattr(e, 'response') and e.response is not None:
            logger.debug(f"API yanıtı: {e.response.text[:500]}") # Yanıt metninin ilk 500 karakterini logla
        raise # Hatayı yeniden fırlat

    except json.JSONDecodeError as e:
        # API'dan gelen yanıtın JSON formatında olmaması durumu
        logger.error(f"API yanıtı JSON olarak çözümlenemedi ({lang.upper()} dili, Offset: {offset}): {e}")
        if response is not None:
            logger.debug(f"API yanıtı metni: {response.text[:500]}")
        raise # Hatayı yeniden fırlat

    except Exception as e:
        # Yukarıdaki spesifik hatalar dışında oluşan tüm diğer beklenmedik hatalar
        logger.critical(f"API'dan haber çekerken kritik hata oluştu ({lang.upper()} dili, Offset: {offset}): {e}", exc_info=True)
        raise # Hatayı yeniden fırlat