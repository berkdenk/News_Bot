# csv_manager.py

import csv      # CSV dosyalarını okuma/yazma için kütüphane
import os       # Dosya sistemi işlemleri için kütüphane
from datetime import datetime # Tarih ve saat objeleriyle çalışmak için kütüphane
import logging  # Loglama için kütüphane

# main.py'deki logger ile aynı logger'ı kullanıyoruz
logger = logging.getLogger('main_news_bot_logger')

def get_existing_article_ids_and_latest_date(csv_filename):
    """
    Belirtilen CSV dosyasındaki mevcut haber ID'lerini ve en son haber tarihini okur.
    Ayrıca WordPress'e gönderilmiş haberlerin ID'lerini de takip eder.

    Parametreler:
    csv_filename (str): Okunacak CSV dosyasının adı.

    Dönüş:
    tuple: (set<str>, datetime, dict<str, dict>) -
           Mevcut haber ID'lerinin kümesi,
           en son haberin yayın tarihi,
           ve haberlerin WordPress yayınlama durumlarını ve ID'lerini içeren bir sözlük.
           Dosya yoksa veya boşsa boş küme, None ve boş sözlük döner.
    """
    existing_ids = set() # World News API'den gelen haber ID'leri
    latest_date = None   # En son haberin tarihi
    # Her haberin yayınlanma durumunu ve WordPress ID'sini tutacak sözlük
    # Anahtar: World News API haber ID'si, Değer: {'is_published_to_wp': bool, 'wordpress_post_id': int/None}
    article_status = {}

    if not os.path.exists(csv_filename):
        logger.info(f"'{csv_filename}' dosyası henüz mevcut değil.")
        return existing_ids, latest_date, article_status

    try:
        with open(csv_filename, mode='r', newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            
            # Gerekli tüm sütunların olup olmadığını kontrol et
            required_fieldnames = ['id', 'title', 'publish_date', 'is_published_to_wp', 'wordpress_post_id']
            if not all(field in reader.fieldnames for field in required_fieldnames):
                logger.warning(f"'{csv_filename}' dosyasında eksik sütunlar bulundu. Dosya yeniden oluşturulacak.")
                return set(), None, {} # Hatalı dosya formatı, boş döndür

            for row in reader:
                article_id = row.get('id')
                publish_date_str = row.get('publish_date')
                is_published_to_wp_str = row.get('is_published_to_wp', 'False') # Varsayılan 'False'
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
                        logger.warning(f"'{publish_date_str}' tarihi geçersiz formatta, atlanıyor.")

        logger.info(f"'{csv_filename}' dosyasında {len(existing_ids)} mevcut haber bulundu. En son tarih: {latest_date}")
    except Exception as e:
        logger.error(f"'{csv_filename}' dosyasını okurken hata oluştu: {e}. Boş dönecek.")
        return set(), None, {} # Hata durumunda boş döndür

    return existing_ids, latest_date, article_status

def save_articles_to_csv(articles, csv_filename, existing_ids):
    """
    Yeni çekilen haberleri CSV dosyasına kaydeder.
    Mevcut haberlerin üzerine yazmaz, sadece yenilerini ekler.
    'is_published_to_wp' ve 'wordpress_post_id' alanlarını ekler.

    Parametreler:
    articles (list): Kaydedilecek haberlerin listesi (her haber bir sözlük).
    csv_filename (str): Kaydedilecek CSV dosyasının adı.
    existing_ids (set): CSV dosyasında zaten mevcut olan haber ID'lerinin kümesi.

    Dönüş:
    int: CSV dosyasına yeni kaydedilen haber sayısı.
    """
    newly_saved_count = 0
    # Haberlerin kaydedileceği alanlar (sütun başlıkları)
    # YENİ SÜTUNLAR EKLENDİ: 'is_published_to_wp', 'wordpress_post_id'
    fieldnames = ['id', 'title', 'text', 'url', 'publish_date', 'language', 'author', 'image', 'is_published_to_wp', 'wordpress_post_id']

    file_exists = os.path.exists(csv_filename)
    
    # Geçici bir liste kullanarak tüm satırları bellekten yazıyoruz
    rows_to_write = []
    
    # Mevcut dosya içeriğini oku (eğer varsa ve boş değilse)
    current_rows = []
    if file_exists and os.stat(csv_filename).st_size > 0:
        try:
            with open(csv_filename, mode='r', newline='', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                # Geçerli sütun başlıklarına sahipse oku
                if all(field in reader.fieldnames for field in fieldnames[:8]): # İlk 8 sütun yeterli kontrol için
                     current_rows = list(reader)
                else:
                    logger.warning(f"'{csv_filename}' dosyasının sütun başlıkları eski veya eksik. Yeniden oluşturulacak.")
        except Exception as e:
            logger.error(f"Mevcut '{csv_filename}' dosyasını okurken hata oluştu: {e}. Dosya sıfırdan yazılacak.")
            current_rows = [] # Hata durumunda mevcut satırları boşalt

    # Mevcut satırları (yeniden yazmak için) rows_to_write listesine ekle
    rows_to_write.extend(current_rows)

    for article in articles:
        article_id = str(article.get('id'))

        if article_id not in existing_ids: # Sadece yeni olanları ekle
            row_data = {
                'id': article.get('id', ''),
                'title': article.get('title', ''),
                'text': article.get('text', ''),
                'url': article.get('url', ''),
                'publish_date': article.get('publish_date', ''),
                'language': article.get('language', ''),
                'author': article.get('author', ''),
                'image': article.get('image', ''),
                'is_published_to_wp': 'False', # Varsayılan olarak henüz yayınlanmadı
                'wordpress_post_id': ''       # WordPress ID'si boş
            }
            rows_to_write.append(row_data) # Yeni haberi listeye ekle
            existing_ids.add(article_id)   # Mevcut ID'lere ekle
            newly_saved_count += 1
    
    # Tüm satırları (eski + yeni) dosyaya yaz
    try:
        with open(csv_filename, mode='w', newline='', encoding='utf-8') as file: # 'w' modunda açıp dosyayı yeniden yazıyoruz
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader() # Başlık satırını her zaman yaz
            writer.writerows(rows_to_write) # Tüm satırları yaz
        logger.info(f"{newly_saved_count} yeni haber '{csv_filename}' dosyasına kaydedildi.")
    except Exception as e:
        logger.error(f"Haberler '{csv_filename}' dosyasına kaydedilirken hata oluştu: {e}")

    return newly_saved_count

def update_article_in_csv(csv_filename, article_id, wordpress_post_id):
    """
    CSV dosyasındaki belirli bir haberin WordPress yayınlanma durumunu ve post ID'sini günceller.
    """
    updated_rows = []
    found = False
    fieldnames = ['id', 'title', 'text', 'url', 'publish_date', 'language', 'author', 'image', 'is_published_to_wp', 'wordpress_post_id']

    try:
        # Mevcut CSV içeriğini oku
        with open(csv_filename, mode='r', newline='', encoding='utf-8') as infile:
            reader = csv.DictReader(infile)
            # Sütun başlıkları eksikse veya farklıysa hata verebiliriz, ancak şimdilik varsayıyoruz ki doğru
            if not all(field in reader.fieldnames for field in fieldnames[:8]):
                logger.error(f"CSV dosyasının sütun başlıkları beklenenden farklı, güncelleme yapılamıyor.")
                return False

            for row in reader:
                if row.get('id') == article_id:
                    row['is_published_to_wp'] = 'True'
                    row['wordpress_post_id'] = str(wordpress_post_id) # WordPress ID'sini string olarak kaydet
                    found = True
                    logger.debug(f"  CSV kaydı güncellendi: Haber ID={article_id}, WordPress Post ID={wordpress_post_id}")
                updated_rows.append(row)
        
        if not found:
            logger.warning(f"  Haber ID '{article_id}' CSV dosyasında bulunamadı, güncelleme yapılamadı.")
            return False

        # Güncellenmiş içeriği dosyaya geri yaz
        with open(csv_filename, mode='w', newline='', encoding='utf-8') as outfile:
            writer = csv.DictWriter(outfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(updated_rows)
        logger.info(f"Haber ID '{article_id}' için CSV kaydı başarıyla güncellendi.")
        return True

    except Exception as e:
        logger.error(f"CSV dosyasında haber güncellenirken hata oluştu (ID: {article_id}): {e}")
        return False

