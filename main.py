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
from PIL import Image # Pillow kütüphanesi, pip install Pillow ile kurulmalı

from deep_translator import GoogleTranslator # pip install deep-translator ile kurulmalı

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

# --- Loglama Konfigürasyonu ---
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
# --- Loglama Konfigürasyonu Sonu ---

# --- Çevirici nesnesini deep_translator ile başlat ---
translator = GoogleTranslator(source='auto', target='tr')

# --- GÜÇLENDİRİLMİŞ ÇEVİRİ FONKSİYONU ---
def translate_text(text, dest_lang='tr'):
    """Metni hedef dile (varsayılan: Türkçe) çevirir ve uzunluk limitini yönetir."""
    # MAX_TRANSLATION_LENGTH kaldırıldı. Çeviri API'sının kendi limitleri olabilir.
    text_to_translate = str(text) if text is not None else ""

    if not text_to_translate.strip():
        return ""
    
    # Uzunluk uyarısı kaldırıldı, ancak çeviri API'sının kendi limitleri olduğunu unutmayın.
    # Bu uyarı, çeviri API'sının kendi sınırlarına ulaşılması durumunda faydalı olabilir.
    # Eğer çok uzun metinlerde çeviri hatası alırsanız, bu uyarıyı tekrar açmayı düşünebilirsiniz.
    # original_length = len(text_to_translate)
    # if original_length > MAX_TRANSLATION_LENGTH:
    #     logger.warning(f"Uyarı: Çevrilecek metin çok uzun ({original_length} karakter). İlk {MAX_TRANSLATION_LENGTH} karakteri çevrilecek. Orijinal: '{text_to_translate[:50]}...'")
    #     text_to_translate = text_to_translate[:MAX_TRANSLATION_LENGTH]

    try:
        translated_text = translator.translate(text_to_translate)
        
        if translated_text:
            return translated_text
        else:
            logger.error(f"Çeviri hatası oluştu: deep_translator boş metin döndürdü. Orijinal metin kullanılacak. Orijinal: '{text_to_translate[:50]}...'")
            return text_to_translate
    except Exception as e:
        logger.error(f"Çeviri hatası oluştu (deep_translator): {e}. Orijinal metin kullanılacak. Orijinal: '{text_to_translate[:50]}...'")
        return text_to_translate

# --- GÜNCELLENMİŞ FONKSİYON: Görseli WordPress'e Yükle ---
def upload_image_to_wordpress(image_url):
    """
    Belirtilen görsel URL'sinden görseli indirir ve WordPress medya kütüphanesine yükler.
    Tüm görselleri yüklemeden önce JPEG'e dönüştürmeyi dener.
    Başarılı olursa yüklenen görselin medya ID'sini döndürür, aksi takdirde None.
    """
    wp_username = WORDPRESS_USERNAME
    wp_app_password = os.getenv("WORDPRESS_APP_PASSWORD")

    if not wp_app_password:
        logger.error("HATA: WordPress uygulama şifresi bulunamadı. Görsel yüklenemiyor.")
        return None

    credentials = f"{wp_username}:{wp_app_password}"
    token = base64.b64encode(credentials.encode()).decode("utf-8")

    headers = {
        "Authorization": f"Basic {token}"
    }

    try:
        logger.debug(f"  Görsel indiriliyor: {image_url}")
        image_response = requests.get(image_url, stream=True, timeout=15)
        image_response.raise_for_status()

        original_image_content = image_response.content

        # Dosya adını ve uzantısını URL'den veya MIME tipinden tahmin et
        parsed_url = urlparse(image_url)
        path = parsed_url.path
        extension = os.path.splitext(path)[1].lower() # Uzantıyı küçük harfe çevir
        
        # İçerik tipi üzerinden MIME tipi belirleme
        content_type_header = image_response.headers.get('Content-Type')
        mime_type = mimetypes.guess_type(image_url)[0] # URL'den tahmin et
        if not mime_type and content_type_header: # URL'den tahmin edemediyse Content-Type'tan al
            mime_type = content_type_header
        # Eğer hala mime_type yoksa veya dönüştürme sonrası varsayılan olarak image/jpeg ata
        if not mime_type:
            mime_type = 'image/jpeg' 
            extension = '.jpg'

        # Görseli JPEG'e dönüştürmeyi dene (tüm görseller için)
        # Bu, WordPress sunucunun farklı formatları işleme sorunlarını çözmeye yardımcı olabilir.
        converted_image_content = original_image_content
        converted_mime_type = 'image/jpeg'
        converted_extension = '.jpg'

        try:
            img = Image.open(BytesIO(original_image_content))
            # RGBA modunda ise JPEG'e kaydederken uyumsuzluk olmaması için RGB'ye çevir
            if img.mode == 'RGBA':
                img = img.convert('RGB')
            img_byte_arr = BytesIO()
            img.save(img_byte_arr, format='JPEG') # JPEG olarak kaydet
            converted_image_content = img_byte_arr.getvalue()
            logger.info(f"  Görsel başarıyla JPEG'e dönüştürüldü (orijinal MIME: {mime_type}).")
        except Exception as e:
            logger.warning(f"  Görsel JPEG'e dönüştürülürken hata oluştu: {e}. Orijinal görsel formatıyla yüklenmeye çalışılacak. URL: {image_url}")
            # Dönüştürme başarısız olursa, orijinal MIME ve içeriği kullanmaya devam et
            converted_image_content = original_image_content
            converted_mime_type = mime_type # Orijinal MIME tipini koru
            converted_extension = extension # Orijinal uzantıyı koru

        # Desteklenen görsel formatlarını kontrol et (dönüşüm sonrası)
        # Sadece JPEG, PNG ve GIF'i destekliyoruz. WEBP artık dönüştürülüyor.
        if converted_mime_type not in ['image/jpeg', 'image/png', 'image/gif', 'image/jpg']: 
            logger.warning(f"  Desteklenmeyen veya dönüştürülemeyen görsel formatı: {converted_mime_type}. Görsel yüklenemedi. URL: {image_url}")
            return None
        
        # Güvenli bir dosya adı oluştur
        file_name = f"haber_gorseli_{datetime.now().strftime('%Y%m%d%H%M%S_%f')}{converted_extension}"
        
        # WordPress medya yükleme endpoint'i
        media_upload_url = WORDPRESS_API_URL.replace('/posts', '/media') 
        
        # requests.post'un 'files' parametresi multipart/form-data'yı yönetir.
        files = {
            'file': (file_name, converted_image_content, converted_mime_type)
        }
        
        # 'files' kullanıldığında Content-Type başlığını otomatik ayarlar, bu yüzden kendi başlıklarımızdan çıkaralım
        upload_headers = {k:v for k,v in headers.items() if k.lower() != 'content-type'}

        logger.debug(f"  Görsel WordPress'e yükleme isteği gönderiliyor: {file_name}, MIME: {converted_mime_type}")
        upload_response = requests.post(media_upload_url, headers=upload_headers, files=files, timeout=30)
        upload_response.raise_for_status() # HTTP hataları için

        media_data = upload_response.json()
        logger.debug(f"  Görsel yükleme yanıtı: {json.dumps(media_data)[:200]}...")
        
        return media_data.get('id') # Yüklenen görselin ID'sini döndür

    except requests.exceptions.RequestException as e:
        # Görsel indirme veya WordPress'e yükleme hatası durumunda daha spesifik loglama
        if hasattr(e, 'response') and e.response is not None:
            if e.response.status_code in [401, 403]:
                logger.error(f"  Görsel indirme hatası: Kaynak sunucu yetkilendirme (401/403) hatası döndürdü. Görsel atlanıyor. URL: {image_url}")
                logger.debug(f"  Kaynak sunucu yanıtı: {e.response.text[:500]}...") # Kaynak sunucunun yanıtını logla
                return None # Yetkilendirme hatasında hemen None dön (görseli atla)
            else:
                logger.error(f"  Görsel indirme veya WordPress'e yükleme hatası ({e.response.status_code}): {e}. URL: {image_url}")
                logger.error(f"  WordPress/API hata yanıtı: {e.response.text}")
        else:
            logger.error(f"  Görsel indirme veya WordPress'e yükleme hatası: {e}. URL: {image_url}")
        return None # Diğer istek hatalarında da None dön

    except Exception as e:
        logger.error(f"  Beklenmedik görsel yükleme hatası: {e}. URL: {image_url}")
        return None

# --- GÜNCELLENMİŞ FONKSİYON: WordPress'te Gönderinin Var Olup Olmadığını Kontrol Et ---
def check_if_post_exists_in_wordpress(post_title):
    """
    Belirtilen başlığa sahip bir gönderinin WordPress'te zaten var olup olmadığını kontrol eder.
    Aramayı daha geniş yapmak için başlığın bir kısmını kullanır ve logları detaylandırır.
    'status=any' parametresi kaldırıldı.
    """
    wp_username = WORDPRESS_USERNAME
    wp_app_password = os.getenv("WORDPRESS_APP_PASSWORD")

    if not wp_app_password:
        logger.error("HATA: WordPress uygulama şifresi bulunamadı. WordPress'te gönderi varlığı kontrol edilemiyor.")
        return False

    credentials = f"{wp_username}:{wp_app_password}"
    token = base64.b64encode(credentials.encode()).decode("utf-8")

    headers = {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json"
    }

    # Başlığın ilk 50 karakterini veya tamamını al (çok uzun başlıklar için)
    search_query = post_title[:50] if len(post_title) > 50 else post_title
    
    # search_url: status=any parametresi kaldırıldı, sadece yayınlanmış gönderilerde arama yapacak
    search_url = f"{WORDPRESS_API_URL}?search={requests.utils.quote(search_query)}&per_page=1"
    
    try:
        logger.debug(f"  WordPress'te '{post_title[:50]}...' başlıklı gönderi aranıyor. Arama URL: {search_url}")
        response = requests.get(search_url, headers=headers, timeout=10)
        response.raise_for_status() # HTTP hataları için hata fırlat

        data = response.json()
        logger.debug(f"  WordPress arama API yanıtı (ilk 200 char): {json.dumps(data)[:200]}...")

        if isinstance(data, list) and len(data) > 0:
            for post in data:
                # Tam başlık eşleşmesi kontrolü yapıyoruz.
                # WordPress API'nin arama parametresi bazen kısmi eşleşmeler de döndürebilir.
                if post.get('title', {}).get('rendered') == post_title:
                    logger.info(f"  '{post_title}' başlıklı gönderi WordPress'te zaten mevcut (ID: {post['id']}).")
                    return True
            logger.debug(f"  '{post_title}' başlıklı gönderi WordPress'te arama sonucu bulundu ancak tam eşleşme sağlanamadı.")
            return False
        else:
            logger.debug(f"  '{post_title}' başlıklı gönderi WordPress'te bulunamadı.")
            return False

    except requests.exceptions.Timeout:
        logger.warning(f"  WordPress gönderi kontrolü zaman aşımına uğradı: '{post_title}'")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"  WordPress'te gönderi kontrol edilirken hata oluştu: '{post_title}' - {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"  WordPress kontrol hata yanıtı: {e.response.text}")
        return False
    except json.JSONDecodeError as e:
        logger.error(f"  WordPress gönderi kontrol yanıtı JSON olarak ayrıştırılamadı: '{post_title}' - {e}")
        return False
    except Exception as e:
        logger.critical(f"  WordPress gönderi kontrolünde kritik hata: '{post_title}' - {e}", exc_info=True)
        return False

# --- WordPress Entegrasyon Fonksiyonu ---
@retry(stop=stop_after_attempt(MAX_RETRIES), wait=wait_fixed(RETRY_DELAY_SECONDS),
       retry=(retry_if_exception_type(requests.exceptions.RequestException) |
              retry_if_exception_type(json.JSONDecodeError) |
              retry_if_result(lambda result: result is False)))
def publish_article_to_wordpress(article_data):
    """
    Bir haber sözlüğünü (article_data) WordPress'e yeni bir gönderi olarak yayınlar.
    Otomatik olarak kategori ve etiket ataması yapar ve görseli öne çıkan görsel olarak ekler.
    """
    article_title = article_data.get('title') or "Başlıksız Haber"
    article_content = article_data.get('text') or "İçeriksiz Haber"
    article_url = article_data.get('url') or "#"
    image_url = article_data.get('image', '') # Görsel URL'sini al

    wp_username = WORDPRESS_USERNAME
    wp_app_password = os.getenv("WORDPRESS_APP_PASSWORD")

    if not wp_app_password:
        logger.error("HATA: WordPress uygulama şifresi bulunamadı. Lütfen '.env' dosyasında 'WORDPRESS_APP_PASSWORD' tanımlı olduğundan emin olun.")
        raise ValueError("WordPress uygulama şifresi bulunamadı.")

    credentials = f"{wp_username}:{wp_app_password}"
    token = base64.b64encode(credentials.encode()).decode("utf-8")
    
    headers = {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json"
    }

    # İçerik uzunluğu kısıtlaması kaldırıldı. WordPress'in kendi sınırları veya sunucu performansını etkileyebilir.
    # if len(article_content) > 100000:
    #     logger.warning(f"Uyarı: '{article_title}' başlıklı haberin içeriği çok uzun ({len(article_content)} karakter). Kısaltılıyor...")
    #     article_content = article_content[:99000] + "..."

    post_content = f"{article_content}<p>Orijinal kaynak: <a href='{article_url}'>{article_url}</a></p>"

    assigned_categories = []
    assigned_tags = []

    if DEFAULT_WORDPRESS_CATEGORY_ID is not None and DEFAULT_WORDPRESS_CATEGORY_ID not in assigned_categories:
        assigned_categories.append(DEFAULT_WORDPRESS_CATEGORY_ID)

    title_lower = article_title.lower()
    content_lower = article_content.lower() # Haber içeriğini de küçük harfe çeviriyoruz
    
    # Kategori atamasını hem başlık hem de içerik üzerinden yapalım
    for keyword, category_id in WORDPRESS_CATEGORIES.items():
        if keyword.replace("_", " ") in title_lower or keyword.replace("_", " ") in content_lower: # Hem başlık hem içerik kontrolü
            if category_id not in assigned_categories:
                assigned_categories.append(category_id)
    assigned_categories = list(set(assigned_categories))

    # Etiket atamasını da hem başlık hem de içerik üzerinden yapalım
    for keyword, tag_id in WORDPRESS_TAGS.items():
        if keyword.replace("_", " ") in title_lower or keyword.replace("_", " ") in content_lower: # Hem başlık hem içerik kontrolü
            if tag_id not in assigned_tags:
                assigned_tags.append(tag_id)
    assigned_tags = list(set(assigned_tags))

    # --- YENİ EKLENEN KISIM: Görsel yükleme ve öne çıkan görsel olarak atama ---
    featured_media_id = None
    if image_url:
        logger.debug(f"  Görsel URL bulundu: {image_url}")
        try:
            featured_media_id = upload_image_to_wordpress(image_url)
            if featured_media_id:
                logger.info(f"  Görsel WordPress'e yüklendi, medya ID: {featured_media_id}")
            else:
                logger.warning(f"  Görsel WordPress'e yüklenemedi: {image_url}")
                # Görsel yüklenemediyse varsayılan görseli kullanmayı dene
                # Config'den DEFAULT_FEATURED_IMAGE_ID'yi import ettiğimizi varsayalım
                # Eğer import edilmediyse, buraya eklememiz gerekir.
                # Şimdilik DEFAULT_FEATURED_IMAGE_ID'nin config'de tanımlı ve import edildiğini varsayıyorum.
                if hasattr(__import__('config'), 'DEFAULT_FEATURED_IMAGE_ID') and __import__('config').DEFAULT_FEATURED_IMAGE_ID is not None:
                    featured_media_id = __import__('config').DEFAULT_FEATURED_IMAGE_ID
                    logger.info(f"  Görsel yüklenemediği için varsayılan öne çıkan görsel ({featured_media_id}) atanacak.")

        except Exception as e:
            logger.error(f"  Görsel yüklenirken beklenmedik hata oluştu: {e}")
            # Görsel yüklenirken hata oluştuysa varsayılan görseli kullanmayı dene
            if hasattr(__import__('config'), 'DEFAULT_FEATURED_IMAGE_ID') and __import__('config').DEFAULT_FEATURED_IMAGE_ID is not None:
                featured_media_id = __import__('config').DEFAULT_FEATURED_IMAGE_ID
                logger.info(f"  Görsel yüklenirken hata oluştuğu için varsayılan öne çıkan görsel ({featured_media_id}) atanacak.")

    post_data = {
        "title": article_title,
        "content": post_content,
        "status": "publish",
        "categories": assigned_categories,
        "tags": assigned_tags
    }

    if featured_media_id: # Eğer görsel başarıyla yüklendiyse VEYA varsayılan atandıysa
        post_data['featured_media'] = featured_media_id
        logger.debug(f"  Post verisine featured_media eklendi: {featured_media_id}")

    try:
        logger.debug(f"  WordPress API'ye gönderiliyor: Başlık='{article_title[:50]}...'")
        logger.debug(f"  Atanan Kategoriler: {assigned_categories}, Atanan Etiketler: {assigned_tags}")
        response = requests.post(WORDPRESS_API_URL, headers=headers, json=post_data, timeout=20)
        
        logger.debug(f"  WordPress API yanıt kodu: {response.status_code}")
        logger.debug(f"  WordPress API yanıt metni: {response.text[:500]}...")
        
        if response.status_code in [201, 200]: 
            logger.info(f"  WordPress'e başarıyla gönderildi: '{article_title}'")
            return response.json().get('id')
        else:
            logger.error(f"  WordPress'e gönderilirken beklenmeyen durum oluştu: Status={response.status_code} - Yanıt={response.text}")
            return False
            
    except requests.exceptions.Timeout:
        logger.error(f"  WordPress API isteği zaman aşımına uğradı: '{article_title}'")
        raise
    except requests.exceptions.RequestException as e:
        logger.error(f"  WordPress API'ye bağlanırken hata oluştu: '{article_title}' - {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"  WordPress hata yanıtı: {e.response.text}")
        raise
    except Exception as e:
        logger.critical(f"  WordPress'e gönderirken kritik hata: '{article_title}' - {e}", exc_info=True)
        raise


def run_news_scraper():
    """
    Botun ana çalışma akışını yöneten fonksiyon.
    World News API'dan haberleri çeker, CSV dosyasına kaydeder ve WordPress'e yayınlar.
    """
    load_dotenv()
    API_KEY = os.getenv("WORLD_NEWS_API_KEY")

    if not API_KEY:
        logger.error("HATA: API anahtarı bulunamadı. Lütfen '.env' dosyasında 'WORLD_NEWS_API_KEY' tanımlı olduğundan emin olun.")
        return

    logger.info(f"'{CSV_FILENAME}' dosyasındaki mevcut haberler ve en son tarih kontrol ediliyor...")
    existing_ids, latest_date_in_csv, article_publish_status = get_existing_article_ids_and_latest_date(CSV_FILENAME)
    
    if latest_date_in_csv:
        start_date_for_api = latest_date_in_csv.strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"CSV'deki en son tarih '{start_date_for_api}'. Bu tarihten sonraki haberler çekilecek.")
    else:
        start_date_for_api = (datetime.now() - timedelta(days=INITIAL_HISTORY_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"CSV boş. API'dan haberler '{start_date_for_api}' tarihinden itibaren (son {INITIAL_HISTORY_DAYS} gün) çekilecek.")
            
    total_new_articles_fetched_and_saved = 0
    
    for lang_code in TARGET_LANGUAGES:
        logger.info(f"\n--- {lang_code.upper()} dilinde haberler çekiliyor ---")
        current_offset = 0
        
        for page_num in range(MAX_PAGES_TO_FETCH):
            logger.info(f"  {lang_code.upper()} dilinde, Offset {current_offset} ile sayfa {page_num + 1} için istek gönderiliyor...")
            
            fetched_articles = []
            try:
                fetched_articles = fetch_news_from_api(API_KEY, lang_code, start_date_for_api, current_offset)
            except Exception as e:
                logger.error(f"  API'dan haber çekme başarısız oldu veya yeniden deneme limitine ulaşıldı: {e}")
                break

            if not fetched_articles:
                logger.info(f"  {lang_code.upper()} dilinde daha fazla yeni haber bulunamadı.")
                break

            articles_to_add_to_csv = [
                article for article in fetched_articles
                if str(article.get('id')) not in existing_ids
            ]

            if articles_to_add_to_csv:
                newly_saved_count = save_articles_to_csv(articles_to_add_to_csv, CSV_FILENAME, existing_ids)
                total_new_articles_fetched_and_saved += newly_saved_count
                
                logger.info(f"  {lang_code.upper()} dilinde {len(fetched_articles)} haber çekildi, bunlardan {newly_saved_count} tanesi yeni ve '{CSV_FILENAME}' dosyasına kaydedildi.")
            else:
                logger.info(f"  {lang_code.upper()} dilinde CSV'ye eklenecek yeni haber bulunamadı.")
            
            articles_to_publish_to_wp = []
            for article in fetched_articles:
                article_id_str = str(article.get('id'))
                if article_id_str in article_publish_status and not article_publish_status[article_id_str]['is_published_to_wp']:
                    articles_to_publish_to_wp.append(article)
                elif article_id_str not in article_publish_status:
                     articles_to_publish_to_wp.append(article)

            if articles_to_publish_to_wp:
                logger.info(f"  WordPress'e gönderilecek {len(articles_to_publish_to_wp)} haber var...")
                for article in articles_to_publish_to_wp:
                    article_title = article.get('title', 'Bilinmeyen Haber')
                    article_world_news_id = str(article.get('id'))

                    # WordPress'te zaten var olup olmadığını kontrol et (ikincil, başlık bazlı kontrol)
                    if check_if_post_exists_in_wordpress(article_title):
                        logger.info(f"  '{article_title}' başlıklı gönderi WordPress'te zaten mevcut (ikincil kontrol). CSV güncelleniyor.")
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
                            logger.error(f"  WordPress'e gönderim başarısız oldu veya post ID alınamadı: '{article_title}'")
                    except Exception as e:
                        logger.error(f"  WordPress'e haber gönderilirken kalıcı hata oluştu: '{article_title}' - {e}")
            else:
                logger.info(f"  {lang_code.upper()} dilinde WordPress'e gönderilecek yeni haber bulunamadı.")


            current_offset += ARTICLES_PER_REQUEST

    logger.info(f"\n--- Veri Çekme Tamamlandı ---")
    final_existing_ids, _, final_article_status = get_existing_article_ids_and_latest_date(CSV_FILENAME)
    logger.info(f"Toplamda {total_new_articles_fetched_and_saved} yeni haber '{CSV_FILENAME}' dosyasına kaydedildi.")
    logger.info(f"CSV dosyasında toplam {len(final_existing_ids)} benzersiz haber mevcut.")
    published_count = sum(1 for status in final_article_status.values() if status['is_published_to_wp'])
    logger.info(f"CSV'deki toplam {len(final_existing_ids)} haberden {published_count} tanesi WordPress'e yayınlanmış olarak işaretlendi.")

if __name__ == "__main__":
    run_news_scraper()
