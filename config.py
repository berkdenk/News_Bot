# config.py

import os
import logging # Loglama seviyelerini tanımlamak için gerekli

# --- World News API Temel Ayarları ---
# API'dan haber çekmek için kullanılan ana URL
BASE_URL = "https://api.worldnewsapi.com/search-news"

# --- Dosya İsimleri ---
# Çekilen haberlerin kaydedileceği CSV dosyasının adı
CSV_FILENAME = "polonya_turk_haberleri.csv"

# --- Haber Filtreleme ve Arama Parametreleri ---
# Polonya ile ilgili haberleri filtrelemek için Polonya'nın ISO 3166 ülke kodu
POLAND_COUNTRY_CODE = "PL"

# API'dan aratılacak anahtar kelimeler. 'OR' operatörü ile birden fazla kelime aranabilir.
# World News API'ın 'text' parametresi için 100 karakter limiti vardır.
SEARCH_KEYWORDS = "Poland AND (Türkiye OR Turkish OR student OR Visa)"
#SEARCH_KEYWORDS = "Polska AND (Turcja OR turecki OR migracja OR ambasada OR student OR wiza OR ekonomia)"
#SEARCH_KEYWORDS = "Poland AND (Türkiye OR migration OR student OR visa OR economy)"

# Haberlerin çekileceği dillerin ISO 639-1 kodları
# 'pl' (Lehçe) ve 'en' (İngilizce) dillerinde haberler çekilecek
TARGET_LANGUAGES = ["en","pl"]

# --- Sayfalama ve Limit Ayarları ---
# Her API isteğinde kaç makale çekileceği
ARTICLES_PER_REQUEST = 2
# Her dil için API'dan çekilecek maksimum sayfa sayısı.
# Bu limit, API kullanım kotasına dikkat etmek için önemlidir.
MAX_PAGES_TO_FETCH = 2
# CSV dosyası boşsa veya yeni bir başlangıç yapılıyorsa, kaç gün öncesine kadar haber çekileceği
INITIAL_HISTORY_DAYS = 30

# --- API İstekleri Arasındaki Bekleme Süresi (Saniye) ---
# API kullanım limitlerine takılmamak için her istek arasında beklenmesi gereken süre
SLEEP_TIME_BETWEEN_REQUESTS = 1

# --- Hata Yönetimi ve Yeniden Deneme Ayarları (Tenacity Kütüphanesi İçin) ---
# API'ya veya WordPress'e bağlanırken maksimum kaç kez yeniden deneme yapılacağı
MAX_RETRIES = 5
# Yeniden denemeler arasında beklenecek süre (saniye cinsinden)
RETRY_DELAY_SECONDS = 10

# --- Loglama Ayarları ---
# Log dosyalarının kaydedileceği klasör
LOG_DIR = "logs"
# Log dosyasının tam yolu
LOG_FILE = os.path.join(LOG_DIR, "news_bot.log")
# Loglama seviyesi.
# DEBUG: En detaylı loglar (geliştirme aşamasında faydalıdır)
# INFO: Genel bilgi mesajları
# WARNING: Potansiyel sorunlar
# ERROR: Hata durumları
# CRITICAL: Kritik hatalar (uygulamanın durmasına neden olabilecek)
LOG_LEVEL = logging.DEBUG

# --- WordPress Entegrasyon Ayarları ---
# WordPress REST API'sinin gönderi (posts) uç noktasının URL'si
WORDPRESS_API_URL = "http://localhost/haberlerim/wp-json/wp/v2/posts"
# WordPress'e gönderi yayınlamak için kullanılan kullanıcı adı.
# Bu kullanıcının uygulama parolası '.env' dosyasında tanımlı olmalıdır.
WORDPRESS_USERNAME = "aliyigitogun"
# WORDPRESS_APP_PASSWORD, .env dosyasından çekilecektir. (Güvenlik için doğrudan burada tutulmaz.)

# --- WordPress Kategori ve Etiket ID'leri ---
# ÖNEMLİ: Bu sözlüklerdeki ID'ler, SİZİN WordPress sitenizdeki kategori ve etiketlerin GERÇEK ID'leri olmalıdır.
# WordPress admin panelinizden (Yazılar > Kategoriler / Etiketler, düzenleme ekranı URL'sinden) bulabilirsiniz.

# Haberleri atamak istediğimiz WordPress kategorilerinin isimleri ve ID'leri
WORDPRESS_CATEGORIES = {
    "genel": 1,
    "siyaset": 3,       # Örneğin: "siyaset", "hükümet", "seçim", "politika", "parlamento"
    "polonya": 7,       # Örneğin: "polonya", "polska", "varşova", "warszawa", "lehistan"
    "ekonomi": 5,       # Örneğin: "ekonomi", "gospodarka", "economy", "enflasyon", "inflacja", "ticaret", "handel"
    "ukrayna": 8,       # Örneğin: "ukrayna", "ukraina", "kyiv", "kiev"
    "öğrenci": 9,      # Örneğin: "öğrenci", "student", "eğitim", "universite", "burs"
    "türk": 10,         # Örneğin: "türk", "türkiye", "turkey", "ankara", "istanbul"
    "vize": 11,         # Örneğin: "vize", "schengen", "pasaport", "göç", "mülteci"
    "rusya": 12,        # Örneğin: "rusya", "rosja", "moskova", "moscow"
    "savaş": 13,         # Örneğin: "savaş", "çatışma", "operasyon", "conflict", "war"
    # Diğer kategoriler...
}

WORDPRESS_TAGS = {
    "ukrayna": 14,
    "rusya": 15,
    "polonya": 16,
    "savaş": 17,
    "ekonomi": 18,
    "siyaset": 19,
    "türk": 20,
    "öğrenci": 21,
    "vize": 22,
    "schengen": 23,
    "abd": 24,          # Örneğin: "abd", "amerika", "usa"
    "avrupa": 25,       # Örneğin: "avrupa", "avrupa birliği", "ab", "eu"
    # Diğer etiketler...
}

# Eğer bir haber için hiçbir spesifik kategori belirlenemezse atanacak varsayılan kategori ID'si
DEFAULT_WORDPRESS_CATEGORY_ID = 1