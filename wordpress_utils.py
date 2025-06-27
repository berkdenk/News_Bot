# wordpress_utils.py
import requests
import json
import base64
import time
from config import WORDPRESS_API_URL, WORDPRESS_USERNAME, WORDPRESS_APP_PASSWORD, MAX_RETRIES, RETRY_DELAY_SECONDS
import logging

logger = logging.getLogger(__name__)

def send_news_to_wordpress(news_item):
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Basic " + base64.b64encode(f"{WORDPRESS_USERNAME}:{WORDPRESS_APP_PASSWORD}".encode()).decode("utf-8")
    }

    # Örnek kategori ve etiket ataması. Bunu dinamik hale getirmek için daha sonra mantık ekleyebilirsiniz.
    # Örneğin, haberin başlığında veya içeriğinde belirli anahtar kelimeler arayarak.
    # Şimdilik sabit ID'ler kullanacağız.

    category_ids = []
    tag_ids = []

    # Örnek: Eğer haber başlığı 'Ukraine' içeriyorsa belirli bir kategori/etiket ata
    title_lower = news_item['title'].lower()
    if "ukraine" in title_lower or "ukrayna" in title_lower:
        # Buradaki ID'leri kendi WordPress kategorilerinizin/etiketlerinizin ID'leriyle değiştirin
        # KATEGORİ ID'LERİ BURAYA (örneğin 5)
        if 5 not in category_ids: category_ids.append(5) # 'Savaş Haberleri' veya ilgili kategori ID'si
        # ETİKET ID'LERİ BURAYA (örneğin 10)
        if 10 not in tag_ids: tag_ids.append(10) # 'Ukrayna' veya ilgili etiket ID'si

    if "poland" in title_lower or "polonya" in title_lower:
        # KATEGORİ ID'LERİ BURAYA (örneğin 6)
        if 6 not in category_ids: category_ids.append(6) # 'Polonya Haberleri' veya ilgili kategori ID'si
        # ETİKET ID'LERİ BURAYA (örneğin 11)
        if 11 not in tag_ids: tag_ids.append(11) # 'Polonya' veya ilgili etiket ID'si

    # Eğer hiç kategori belirlenmediyse varsayılan bir kategori atayabiliriz (örneğin "Genel" kategorisi ID'si 1)
    if not category_ids:
        category_ids.append(1) # WordPress'teki "Genel" kategorisinin ID'si genellikle 1'dir. Kontrol edin.


    data = {
        "title": news_item['title'],
        "content": news_item['text'],
        "status": "publish",
        "categories": category_ids, # Kategori ID'leri listesi
        "tags": tag_ids # Etiket ID'leri listesi
    }

    json_data = json.dumps(data)

    for attempt in range(MAX_RETRIES):
        try:
            logger.debug(f"  WordPress API'ye gönderiliyor: Başlık='{news_item['title'][:50]}...'")
            response = requests.post(WORDPRESS_API_URL, headers=headers, data=json_data)
            response.raise_for_status()
            logger.debug(f"  WordPress API yanıt kodu: {response.status_code}")
            logger.debug(f"  WordPress API yanıt metni: {response.text[:100]}...")
            logger.info(f"  WordPress'e başarıyla gönderildi: '{news_item['title']}'")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"  WordPress API'ye bağlanırken hata oluştu (Deneme {attempt + 1}/{MAX_RETRIES}): '{news_item['title']}' - {e}")
            if response is not None:
                logger.debug(f"  WordPress API yanıt kodu: {response.status_code}")
                logger.debug(f"  WordPress API yanıt metni: {response.text}")
            if attempt < MAX_RETRIES - 1:
                logger.info(f"  {RETRY_DELAY_SECONDS} saniye sonra tekrar denenecek...")
                time.sleep(RETRY_DELAY_SECONDS)
            else:
                logger.error(f"  Maksimum yeniden deneme sayısına ulaşıldı. Haber gönderilemedi: '{news_item['title']}'")
                return False
        except json.JSONDecodeError as e:
            logger.error(f"  WordPress API yanıtı JSON olarak ayrıştırılamadı (Deneme {attempt + 1}/{MAX_RETRIES}): '{news_item['title']}' - {e}")
            if response is not None:
                logger.debug(f"  WordPress API yanıt kodu: {response.status_code}")
                logger.debug(f"  WordPress API yanıt metni: {response.text}")
            if attempt < MAX_RETRIES - 1:
                logger.info(f"  {RETRY_DELAY_SECONDS} saniye sonra tekrar denenecek...")
                time.sleep(RETRY_DELAY_SECONDS)
            else:
                logger.error(f"  Maksimum yeniden deneme sayısına ulaşıldı. Haber gönderilemedi: '{news_item['title']}'")
                return False
        except Exception as e:
            logger.error(f"  WordPress'e gönderilirken beklenmeyen bir hata oluştu (Deneme {attempt + 1}/{MAX_RETRIES}): '{news_item['title']}' - {e}")
            if attempt < MAX_RETRIES - 1:
                logger.info(f"  {RETRY_DELAY_SECONDS} saniye sonra tekrar denenecek...")
                time.sleep(RETRY_DELAY_SECONDS)
            else:
                logger.error(f"  Maksimum yeniden deneme sayısına ulaşıldı. Haber gönderilemedi: '{news_item['title']}'")
                return False