# csv_manager.py
import csv
import os
from datetime import datetime

def get_existing_article_ids_and_latest_date(filename):
    """
    CSV dosyasındaki mevcut haber ID'lerini ve en son yayın tarihini döndürür.
    
    Args:
        filename (str): CSV dosyasının yolu.

    Returns:
        tuple: (existing_ids_set, latest_publish_datetime_obj)
               existing_ids_set: Mevcut haber ID'lerinin kümesi (set).
               latest_publish_datetime_obj: En son haberin yayın tarihi (datetime object) veya None.
    """
    existing_ids = set()
    latest_publish_date = None # YYYY-MM-DD HH:MM:SS formatında datetime objesi
    
    try:
        # Dosya varsa ve boş değilse oku
        if os.path.exists(filename) and os.path.getsize(filename) > 0:
            with open(filename, 'r', newline='', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    # Haber ID'sini ekle
                    if 'id' in row and row['id']: # 'id' alanı var ve boş değilse
                        existing_ids.add(row['id'])
                    
                    # En yeni yayın tarihini bul
                    if 'publish_date' in row and row['publish_date']:
                        try:
                            # API'dan gelen tarih formatı genellikle "YYYY-MM-DD HH:MM:SS" veya "YYYY-MM-DDTHH:MM:SSZ" olabilir.
                            # 'T' ve 'Z' karakterlerini temizleyip milisaniyelerden önceki kısmı alalım.
                            date_str = row['publish_date'].replace('T', ' ').replace('Z', '')
                            # split('.')[0] ile milisaniye kısmını atıyoruz, çünkü strptime standart formatı bekler.
                            current_date = datetime.strptime(date_str.split('.')[0], "%Y-%m-%d %H:%M:%S")
                            
                            if latest_publish_date is None or current_date > latest_publish_date:
                                latest_publish_date = current_date
                        except ValueError:
                            # Tarih formatı hatalıysa bu satırı yoksay
                            print(f"Uyarı: CSV'deki tarih formatı hatası tespit edildi: {row['publish_date']}")
                            pass
        else:
            print(f"'{filename}' dosyası henüz mevcut değil veya boş.")

    except FileNotFoundError:
        # Dosya yoksa veya okuma hatası olursa başlangıç değerlerini döndür
        print(f"'{filename}' dosyası bulunamadı. Yeni bir dosya oluşturulacak.")
    
    return existing_ids, latest_publish_date

def save_articles_to_csv(articles, filename, existing_ids_set):
    """
    Verilen haber listesini CSV dosyasına kaydeder. Sadece mevcut olmayanları ekler.

    Args:
        articles (list): API'dan çekilen haberlerin listesi (sözlükler halinde).
        filename (str): CSV dosyasının yolu.
        existing_ids_set (set): Mevcut haber ID'lerinin kümesi.

    Returns:
        int: Kaydedilen yeni haber sayısı.
    """
    # Kaydedilecek alanlar. API yanıtındaki anahtar isimleriyle eşleşmeli.
    fieldnames = ['id', 'title', 'text', 'url', 'publish_date', 'language', 'source_country']
    
    # Dosyanın daha önce var olup olmadığını ve başlık satırı gerekip gerekmediğini kontrol et
    # os.path.getsize(filename) > 0 kontrolü, dosyanın var olup olmadığını ve boş olup olmadığını anlar.
    file_exists_and_not_empty = os.path.exists(filename) and os.path.getsize(filename) > 0

    new_articles_saved_count = 0
    with open(filename, 'a', newline='', encoding='utf-8') as csvfile: # 'a' (append) modu ile dosyaya ekleme yapılır
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        # Eğer dosya yeni oluşturulduysa veya boşsa başlık satırını yaz
        if not file_exists_and_not_empty:
            writer.writeheader()

        for article in articles:
            # Her haberin benzersiz ID'sini al
            article_id = str(article.get('id')) 
            
            # Eğer haberin ID'si varsa ve daha önce kaydedilmemişse
            if article_id and article_id not in existing_ids_set:
                # Haber verilerini DictWriter için uygun formata getir
                row_data = {
                    'id': article_id,
                    'title': article.get('title', ''),
                    'text': article.get('text', ''),
                    'url': article.get('url', ''),
                    'publish_date': article.get('publish_date', ''),
                    'language': article.get('language', ''),
                    'source_country': article.get('source_country', '')
                }
                writer.writerow(row_data)
                existing_ids_set.add(article_id) # Yeni ID'yi sete ekle ki aynı çalıştırmada tekrar eklenmesin
                new_articles_saved_count += 1
            # else:
            #     # Bu kısım debug için kullanılabilir, mevcut haberlerin neden atlandığını görmek isterseniz açabilirsiniz.
            #     # print(f"Debug: Haber zaten mevcut veya ID'si yok. Başlık: {article.get('title', 'Bilinmeyen Başlık')}")
                
    return new_articles_saved_count