import os
import requests
import json
import datetime
import time
import random
import re
import markdown
import unicodedata
from urllib.parse import quote_plus

from wordpress_xmlrpc import Client, WordPressPost
from wordpress_xmlrpc.methods.posts import NewPost
from wordpress_xmlrpc.methods.media import UploadFile

# --- KONFIGURASI ---
API_SOURCE_URL = "https://rayuanmalam.com/wp-json/wp/v2/posts"
WP_TARGET_API_URL = "https://hanyapadamuh.wordpress.com/xmlrpc.php"
WP_BLOG_ID = "134313143" 

STATE_FILE = 'artikel_terbit.json'
RANDOM_IMAGES_FILE = 'random_images.json'
DEFAULT_TAGS = ["Cerita Dewasa", "Cerita Seks", "Cerita Sex", "Cerita Ngentot"]

# Jumlah artikel yang ingin diterbitkan sekali jalan
MAX_POSTS_PER_RUN = 10 

WP_USERNAME = os.getenv('WP_USERNAME')
WP_APP_PASSWORD = os.getenv('WP_APP_PASSWORD')

REPLACEMENT_MAP = {
    "memek": "serambi lempit",
    "kontol": "rudal",
    "ngentot": "menggenjot",
    "vagina": "serambi lempit",
    "penis": "rudal",
    "seks": "bercinta",
    "mani": "kenikmatan",
    "sex": "bercinta"
}

# --- FUNGSI HELPER (Tetap Sama) ---

def strip_html_and_divs(html):
    if html is None: html = ""
    processed_text = re.sub(r'</p>', r'\n\n', html, flags=re.IGNORECASE)
    processed_text = re.sub(r'<img[^>]*>', '', processed_text)
    processed_text = re.sub(r'</?div[^>]*>', '', processed_text, flags=re.IGNORECASE)
    processed_text = re.sub('<[^<]+?>', '', processed_text) 
    processed_text = re.sub(r'\n{3,}', r'\n\n', processed_text).strip()
    return processed_text

def remove_anchor_tags(html_content):
    return re.sub(r'<a[^>]*>(.*?)<\/a>', r'\1', html_content)

def slugify(value):
    value = str(value)
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('utf-8')
    value = re.sub(r'[^\w\s-]', '', value).strip().lower()
    return re.sub(r'[-\s]+', '-', value)

def replace_custom_words(text):
    processed_text = text
    sorted_replacements = sorted(REPLACEMENT_MAP.items(), key=lambda item: len(item[0]), reverse=True)
    for old_word, new_word in sorted_replacements:
        pattern = re.compile(re.escape(old_word), re.IGNORECASE)
        processed_text = pattern.sub(new_word, processed_text)
    return processed_text

def load_published_posts_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            try:
                data = json.load(f)
                return set(data) if isinstance(data, list) else set()
            except: return set()
    return set()

def save_published_posts_state(published_ids):
    with open(STATE_FILE, 'w') as f:
        json.dump(list(published_ids), f)

def load_image_urls(file_path):
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            try:
                urls = json.load(f)
                return urls if isinstance(urls, list) else []
            except: return []
    return []

def insert_details_tag(content_text, article_url=None, article_title=None):
    paragraphs = content_text.split('\n\n')
    if len(paragraphs) < 2: return content_text
    idx = len(paragraphs) // 2 
    first_part = "\n\n".join(paragraphs[:idx])
    rest_part = "\n\n".join(paragraphs[idx:])
    
    encoded_url = quote_plus(article_url.rstrip('/')) if article_url else ""
    disp_title = article_title.replace('"', '&quot;') if article_title else ""

    details_tag_start = f'<details><summary><a href="https://lanjutbabdua.github.io/lanjut.html?url={encoded_url}#lanjut" rel="nofollow" target="_blank">Lanjut BAB 2: {disp_title}</a></summary><h4>CHAPTER DUA</h4><div id="lanjut">\n'
    details_tag_end = '\n</div></details><p>Semoga Artikel <strong>{disp_title}</strong> Bisa Menghibur Anda. Terima Kasih Sudah Berkunjung.</p>'
    return first_part + '\n\n' + details_tag_start + rest_part + details_tag_end

def add_more_tag_before_send(content_text):
    paragraphs = content_text.split('\n\n')
    if not paragraphs or not paragraphs[0].strip(): return content_text
    return paragraphs[0].strip() + '\n\n<!--more-->\n\n' + "\n\n".join(paragraphs[1:]).strip()

def publish_post_to_wordpress(title, content_html, random_image_url=None):
    if random_image_url:
        image_html = f'<p><img src="{random_image_url}" alt="{title}" style="max-width: 100%; height: auto; display: block; margin: 0 auto;"></p>'
        content_html = image_html + "\n\n" + content_html
    try:
        client = Client(WP_TARGET_API_URL, WP_USERNAME, WP_APP_PASSWORD)
        post = WordPressPost()
        post.title = title
        post.content = content_html
        post.post_status = 'publish'
        post.slug = slugify(title)
        post.terms_names = {'post_tag': DEFAULT_TAGS}
        return client.call(NewPost(post, blog_id=WP_BLOG_ID))
    except Exception as e:
        print(f"❌ Kesalahan XML-RPC: {e}")
        return None

def fetch_raw_posts():
    all_posts = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    for page in range(1, 5): # Ambil sampai 4 halaman untuk cadangan data
        res = requests.get(API_SOURCE_URL, params={'per_page': 50, 'page': page}, headers=headers)
        if res.status_code != 200: break
        batch = res.json()
        if not batch: break
        for p in batch:
            all_posts.append({'id': p['id'], 'title': p['title']['rendered'], 'content': p['content']['rendered'], 'date': p['date']})
    return all_posts

# --- ALUR UTAMA ---

if __name__ == '__main__':
    print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Memulai Batch Publish (Target: {MAX_POSTS_PER_RUN} Artikel)")

    try:
        published_ids = load_published_posts_state()
        random_image_urls = load_image_urls(RANDOM_IMAGES_FILE)
        all_posts = fetch_raw_posts()

        # Filter artikel yang belum pernah diterbitkan
        unpublished = [p for p in all_posts if str(p['id']) not in published_ids]
        unpublished.sort(key=lambda x: x['date'], reverse=True)

        if not unpublished:
            print("🎉 Tidak ada artikel baru.")
            exit()

        # Ambil maksimal 10 artikel
        to_publish = unpublished[:MAX_POSTS_PER_RUN]
        count_success = 0

        for post_data in to_publish:
            orig_id = str(post_data['id'])
            orig_title = post_data['title']
            
            print(f"🔄 Memproses ({count_success+1}/{len(to_publish)}): {orig_title}")

            final_title = replace_custom_words(orig_title)
            content_clean = replace_custom_words(strip_html_and_divs(remove_anchor_tags(post_data['content'])))

            # URL Prediction
            dt = datetime.datetime.fromisoformat(post_data['date'].replace('Z', '+00:00'))
            pred_url = f"https://ekstracrot.wordpress.com/{dt.strftime('%Y/%m/%d')}/{slugify(final_title)}"

            # Format Konten
            content_details = insert_details_tag(content_clean, pred_url, final_title)
            content_final = add_more_tag_before_send(content_details)
            html_output = '<p>' + content_final.replace('\n\n', '</p><p>') + '</p>'

            # Publish
            img = random.choice(random_image_urls) if random_image_urls else None
            res_id = publish_post_to_wordpress(final_title, html_output, img)

            if res_id:
                published_ids.add(orig_id)
                count_success += 1
                print(f"✅ Berhasil! ID: {res_id}")
                time.sleep(2) # Jeda agar tidak dianggap spam oleh WordPress
            else:
                print(f"⚠️ Gagal menerbitkan: {orig_title}")

        save_published_posts_state(published_ids)
        print(f"\n✨ Selesai! Berhasil menerbitkan {count_success} artikel.")

    except Exception as e:
        print(f"❌ Error Fatal: {e}")