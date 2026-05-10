import os
import requests
import json
import datetime
import time
import random
import re
import unicodedata
import base64
from urllib.parse import quote_plus

# --- KONFIGURASI ---
API_SOURCE_URL = "https://rayuanmalam.com/wp-json/wp/v2/posts"
# Endpoint REST API untuk WordPress.com
WP_TARGET_REST_URL = "https://public-api.wordpress.com/wp/v2/sites/hanyapadamuh.wordpress.com/posts"
STATE_FILE = 'artikel_terbit.json'
RANDOM_IMAGES_FILE = 'random_images.json'
DEFAULT_TAGS = ["Cerita Dewasa", "Cerita Seks", "Cerita Sex", "Cerita Ngentot"]

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

# --- FUNGSI UTILITY ---

def strip_html_and_divs(html):
    if html is None: html = ""
    processed_text = re.sub(r'</p>', r'\n\n', html, flags=re.IGNORECASE)
    processed_text = re.sub(r'<img[^>]*>', '', processed_text)
    processed_text = re.sub(r'</?div[^>]*>', '', processed_text, flags=re.IGNORECASE)
    processed_text = re.sub(r'<[^>]*>', '', processed_text) 
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

def insert_details_tag(content_text, article_url=None, article_title=None):
    paragraphs = content_text.split('\n\n')
    if len(paragraphs) < 2: return content_text
    idx = len(paragraphs) // 2 
    
    encoded_url = quote_plus(article_url.rstrip('/')) if article_url else ""
    enc_title = article_title.replace('"', '&quot;') if article_title else ""

    details_start = f'<details><summary><a href="https://lanjutbabdua.github.io/lanjut.html?url={encoded_url}#lanjut" rel="nofollow" target="_blank">Lanjut BAB 2: {enc_title}</a></summary><h4>CHAPTER DUA</h4><div id="lanjut">'
    details_end = '</div></details>'
    
    return "\n\n".join(paragraphs[:idx]) + '\n\n' + details_start + '\n\n' + "\n\n".join(paragraphs[idx:]) + '\n\n' + details_end

# FUNGSI KEMBALI KE SEMULA: Menyisipkan <!--more--> sebagai teks
def add_more_tag_before_send(content_text):
    paragraphs = [p.strip() for p in content_text.split('\n\n') if p.strip()]
    if not paragraphs: return content_text
    
    first_paragraph = paragraphs[0]
    rest_of_content = "\n\n".join(paragraphs[1:]).strip()
    
    # Tetap menggunakan <!--more--> sesuai permintaan
    content_with_more_tag = first_paragraph + '\n\n' + '<!--more-->' + '\n\n' + rest_of_content
    print("📝 String <!--more--> disisipkan setelah paragraf pertama.")
    return content_with_more_tag

# --- FUNGSI PUBLISH VIA REST API ---
def publish_post_to_wordpress_rest(title, content_html, random_image_url=None, post_status='publish', tags=None):
    auth_str = f"{WP_USERNAME}:{WP_APP_PASSWORD}"
    encoded_auth = base64.b64encode(auth_str.encode()).decode()
    
    headers = {
        'Authorization': f'Basic {encoded_auth}',
        'Content-Type': 'application/json'
    }

    final_content = content_html
    if random_image_url:
        image_html = f'<p><img src="{random_image_url}" alt="{title}" style="max-width: 100%; height: auto; display: block; margin: 0 auto;"></p>'
        final_content = image_html + "\n\n" + content_html

    payload = {
        'title': title,
        'content': final_content,
        'status': post_status,
        'slug': slugify(title),
        'tags': tags 
    }

    try:
        response = requests.post(WP_TARGET_REST_URL, headers=headers, json=payload, timeout=30)
        if response.status_code in [200, 201]:
            print(f"✅ Artikel '{title}' berhasil diterbitkan!")
            return response.json()
        else:
            print(f"❌ Gagal: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

# --- MAIN LOGIC ---
if __name__ == '__main__':
    # ... (logika load state dan fetch posts sama seperti sebelumnya) ...
    # Di dalam loop pemrosesan artikel:
    
    # 1. Olah konten dasar
    content_clean = strip_html_and_divs(remove_anchor_tags(original_content))
    content_replaced = replace_custom_words(content_clean)
    final_title = replace_custom_words(original_title)
    
    # 2. Sisipkan tag details di tengah
    content_with_details = insert_details_tag(content_replaced, predicted_url, final_title)
    
    # 3. Sisipkan <!--more--> setelah paragraf pertama
    final_body_text = add_more_tag_before_send(content_with_details)
    
    # 4. Konversi ke HTML Paragraphs
    content_blocks = final_body_text.split('\n\n')
    final_html_parts = []
    for block in content_blocks:
        block = block.strip()
        if not block: continue
        
        # Logika firewall agar <!--more--> atau tag HTML tidak dibungkus <p>
        if block.startswith('<') or block.endswith('>') or block == '<!--more-->':
            final_html_parts.append(block)
        else:
            final_html_parts.append(f'<p>{block}</p>')

    final_post_content_html = '\n'.join(final_html_parts)
    
    # 5. Kirim ke WordPress
    publish_post_to_wordpress_rest(final_title, final_post_content_html, selected_image, tags=DEFAULT_TAGS)