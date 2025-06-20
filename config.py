# config.py

import os

# World News API Temel Ayarları
BASE_URL = "https://api.worldnewsapi.com/search-news"

# Dosya İsimleri
CSV_FILENAME = "polonya_turk_haberleri.csv"

# Haber Filtreleme Parametreleri
POLAND_COUNTRY_CODE = "PL" # Polonya'nın ISO 3166 ülke kodu

# Türkleri ilgilendiren anahtar kelimeler (API'ın 100 karakter limiti olduğunu unutmayın)
# 'OR' operatörü büyük harfle yazılmalı.
SEARCH_KEYWORDS ="Turkish OR Turkey OR Turkish Student OR Poland OR economy OR politics OR EU OR Ukraine OR Russia"



# Aramak istediğimiz dillerin ISO 639-1 kodları.
# API tek istekte birden fazla dil desteklemediği için her biri için ayrı istek yapacağız.
TARGET_LANGUAGES = ["pl","en"] # Lehçe ve Türkçe

# Sayfalama ve Limit Ayarları
ARTICLES_PER_REQUEST = 5  # Her API isteğinde çekilecek haber sayısı (API'ın ücretsiz limitine göre ayarlayın, genellikle 10 veya 20)
MAX_PAGES_TO_FETCH = 5    # Her dil için çekilecek maksimum sayfa sayısı (API limitini aşmamak için dikkatli olun)
INITIAL_HISTORY_DAYS = 30   # CSV dosyası boşsa, başlangıçta kaç gün öncesine kadar haber çekileceği

# API İstekleri Arasındaki Bekleme Süresi (Saniye)
# '429 Too Many Requests' hatasını önlemek için önemlidir.
SLEEP_TIME_BETWEEN_REQUESTS = 1

# Loglama Ayarları
LOG_DIR = "logs" # Log dosyalarının tutulacağı klasör
LOG_FILE = os.path.join(LOG_DIR, "news_bot.log") # Log dosyasının adı
LOG_LEVEL = "INFO" # DEBUG, INFO, WARNING, ERROR, CRITICAL olabilir