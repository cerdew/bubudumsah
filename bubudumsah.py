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
API_SOURCE_URL = "https://kisahbecek.com/wp-json/wp/v2/posts"
WP_TARGET_API_URL = "https://wiraferita.wordpress.com/xmlrpc.php"
WP_BLOG_ID = "128949820" 
STATE_FILE = 'artikel_terbit.json'
RANDOM_IMAGES_FILE = 'random_images.json'
DEFAULT_TAGS = ["Cerita Dewasa", "Cerita Seks", "Cerita Sex", "Cerita Ngentot"]
# Menghapus konfigurasi dan impor Gemini API
WP_USERNAME = os.getenv('WP_USERNAME')
WP_APP_PASSWORD = os.getenv('WP_APP_PASSWORD')

if not WP_USERNAME or not WP_APP_PASSWORD:
    raise ValueError("WP_USERNAME dan WP_APP_PASSWORD environment variables not set for target WordPress. Please set them in GitHub Secrets.")

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

def extract_first_image_url(html_content):
    match = re.search(r'<img[^>]+src="([^"]+)"', html_content, re.IGNORECASE)
    if match:
        return match.group(1)
    return None

def strip_html_and_divs(html):
    if html is None:
        html = ""
    # Ganti tag penutup paragraf asli dengan dua newline
    processed_text = re.sub(r'</p>', r'\n\n', html, flags=re.IGNORECASE)
    # Hapus semua tag img, div, dan tag HTML lainnya
    processed_text = re.sub(r'<img[^>]*>', '', processed_text)
    processed_text = re.sub(r'</?div[^>]*>', '', processed_text, flags=re.IGNORECASE)
    # Hapus sisa tag HTML, tapi sisakan tag khusus (seperti <details>)
    processed_text = re.sub(r'<[^>]*>', '', processed_text) 
    # Normalisasi multiple newlines menjadi double newline
    processed_text = re.sub(r'\n{3,}', r'\n\n', processed_text).strip()
    return processed_text

def remove_anchor_tags(html_content):
    return re.sub(r'<a[^>]*>(.*?)<\/a>', r'\1', html_content)

def sanitize_filename(title):
    clean_title = re.sub(r'[^\w\s-]', '', title).strip().lower()
    return re.sub(r'[-\s]+', '-', clean_title)

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

# Fungsi ini sekarang hanya mengembalikan judul asli setelah penggantian kata
def edit_title_placeholder(original_title):
    processed_title = replace_custom_words(original_title)
    print(f"🔄 Melewati pengeditan judul AI. Judul akhir: '{processed_title}'")
    return processed_title

# Fungsi ini sekarang hanya mengembalikan konten yang sudah dibersihkan/diganti kata
def edit_content_placeholder(post_id, post_title, full_text_content):
    print(f"🔄 Melewati pengeditan konten 300 kata pertama AI untuk artikel ID: {post_id}.")
    content_after_replacements = replace_custom_words(full_text_content)
    cleaned_content = strip_html_and_divs(content_after_replacements)
    first_300_words = " ".join(content_after_replacements.split()[:300])
    return cleaned_content, first_300_words

def load_published_posts_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            try:
                data = json.load(f)
                if isinstance(data, list): 
                    return set(data)
                else:
                    print(f"Warning: {STATE_FILE} content is not a list. Starting with an empty published posts list.")
                    return set()
            except json.JSONDecodeError:
                print(f"Warning: {STATE_FILE} is corrupted or empty. Starting with an empty published posts list.")
                return set()
    return set()

def save_published_posts_state(published_ids):
    with open(STATE_FILE, 'w') as f:
        json.dump(list(published_ids), f)

def load_image_urls(file_path):
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            try:
                urls = json.load(f)
                if isinstance(urls, list) and all(isinstance(url, str) for url in urls):
                    print(f"✅ Berhasil memuat {len(urls)} URL gambar dari '{file_path}'.")
                    return urls
                else:
                    print(f"❌ Error: Konten '{file_path}' bukan daftar string URL yang valid.")
                    return []
            except json.JSONDecodeError:
                print(f"❌ Error: Gagal mengurai JSON dari '{file_path}'. Pastikan formatnya benar.")
                return []
    else:
        print(f"⚠️ Peringatan: File '{file_path}' tidak ditemukan. Tidak ada gambar acak yang akan ditambahkan.")
        return []

def get_random_image_url(image_urls):
    if image_urls:
        return random.choice(image_urls)
    return None

def insert_details_tag(content_text, article_url=None, article_title=None):
    paragraphs = content_text.split('\n\n')
    total_paragraphs = len(paragraphs)
    
    if total_paragraphs < 2: 
        return content_text

    paragraph_insert_index = total_paragraphs // 2 
    
    first_part = "\n\n".join(paragraphs[:paragraph_insert_index])
    rest_part = "\n\n".join(paragraphs[paragraph_insert_index:])

    encoded_article_url = ""
    encoded_article_title_for_display = ""
    if article_url and article_title:
        clean_article_url = article_url.rstrip('/') 
        encoded_article_url = quote_plus(clean_article_url)
        encoded_article_title_for_display = article_title.replace('"', '&quot;')

    # Memastikan tidak ada \n\n yang memisahkan tag details
    details_tag_start = f'<details><summary><a href="https://lanjutbabdua.github.io/lanjut.html?url={encoded_article_url}#lanjut" rel="nofollow" target="_blank">Lanjut BAB 2: {encoded_article_title_for_display}</a></summary><h4>CHAPTER DUA</h4><div id="lanjut">'
    details_tag_end = '</div></details>'
    
    print(f"📝 Tag <details> akan disisipkan setelah paragraf ke-{paragraph_insert_index} (total {total_paragraphs} paragraf).")
    # Sisipkan tag details sebagai blok teks yang dipisahkan oleh \n\n
    return first_part + '\n\n' + details_tag_start + '\n\n' + rest_part + '\n\n' + details_tag_end

# FUNGSI YANG DIMODIFIKASI: Mengganti tag dengan <!--more--> dan TIDAK menggunakan tanda **
def add_more_tag_before_send(content_text):
    paragraphs = content_text.split('\n\n')

    if not paragraphs or not paragraphs[0].strip():
        print("⚠️ Konten terlalu pendek atau paragraf pertama kosong. Tidak menyisipkan <!--more-->.")
        return content_text
    
    # Menghapus duplikat newline ganda yang mungkin terjadi akibat split/join
    cleaned_paragraphs = [p.strip() for p in paragraphs if p.strip()]

    if not cleaned_paragraphs:
        return content_text
        
    first_paragraph = cleaned_paragraphs[0]
    rest_of_content = "\n\n".join(cleaned_paragraphs[1:]).strip()
    
    # Sisipkan string <!--more--> sebagai blok paragraf yang dipisahkan \n\n
    content_with_more_tag = first_paragraph + '\n\n' + '<!--more-->' + '\n\n' + rest_of_content
    
    print("📝 String <!--more--> disisipkan setelah paragraf pertama.")
    return content_with_more_tag

def publish_post_to_wordpress(wp_xmlrpc_url, blog_id, title, content_html, username, app_password, random_image_url=None, post_status='publish', tags=None):
    print(f"🚀 Menerbitkan '{title}' ke WordPress via XML-RPC: {wp_xmlrpc_url}...")
    final_content_for_wp = content_html
    
    if random_image_url:
        image_html = f'<p><img src="{random_image_url}" alt="{title}" style="max-width: 100%; height: auto; display: block; margin: 0 auto;"></p>'
        final_content_for_wp = image_html + "\n\n" + content_html
        print(f"🖼️ Gambar acak '{random_image_url}' ditambahkan ke artikel.")

    if not username or not app_password:
        print("❌ ERROR: WP_USERNAME atau WP_APP_PASSWORD tidak diatur dengan benar untuk proses publikasi.")
        return None

    try:
        client = Client(wp_xmlrpc_url, username, app_password)
        
        post = WordPressPost()
        post.title = title
        post.content = final_content_for_wp # Konten sudah dalam bentuk HTML yang benar
        post.post_status = post_status
        post.slug = slugify(title)

        if tags:
            post.terms_names = {
                'post_tag': tags
            }
            print(f"🏷️ Menambahkan tag: {', '.join(tags)}")

        print("\n--- Debugging Detail Payload XML-RPC ---")
        print(f"URL XML-RPC: {wp_xmlrpc_url}")
        print(f"Blog ID: {blog_id}")
        print(f"Username: {username}")
        print(f"Title: {post.title}")
        print(f"Status: {post.post_status}")
        print(f"Slug: {post.slug}")
        if tags:
            print(f"Tags: {post.terms_names.get('post_tag')}")
        content_preview = post.content[:500] + '...' if len(post.content) > 500 else post.content
        print(f"Content Preview (sebagian): {content_preview.replace('\n', ' ')}")
        print("---------------------------------------\n")

        post_id = client.call(NewPost(post, blog_id=blog_id))
        
        print(f"✅ Artikel '{title}' berhasil diterbitkan ke WordPress via XML-RPC! Post ID: {post_id}")
        return {'id': post_id, 'URL': None}
    except Exception as e:
        print(f"❌ Terjadi kesalahan saat memposting ke WordPress via XML-RPC: {e}")
        if hasattr(e, 'faultCode') and hasattr(e, 'faultString'):
            print(f"XML-RPC Fault Code: {e.faultCode}")
            print(f"XML-RPC Fault String: {e.faultString}")
        return None

def fetch_raw_posts():
    all_posts_data = []
    page = 1
    per_page_limit = 100
    print(f"📥 Mengambil semua artikel mentah dari WordPress SUMBER: {API_SOURCE_URL}...")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    while True:
        params = {
            'per_page': per_page_limit,
            'page': page,
            'status': 'publish',
            '_fields': 'id,title,content,date'
        }
        try:
            res = requests.get(API_SOURCE_URL, params=params, headers=headers, timeout=30)
            
            if res.status_code == 400:
                if "rest_post_invalid_page_number" in res.text:
                    print(f"Reached end of posts from WordPress API (page {page} does not exist). Stopping fetch.")
                    break
                else:
                    raise Exception(f"Error: Gagal mengambil data dari WordPress REST API: {res.status_code} - {res.text}. "
                                     f"Pastikan URL API Anda benar dan dapat diakses.")
            elif res.status_code != 200:
                raise Exception(f"Error: Gagal mengambil data dari WordPress REST API: {res.status_code} - {res.text}. "
                                 f"Pastikan URL API Anda benar dan dapat diakses.")

            posts_batch = res.json()
            if not posts_batch:
                print(f"Fetched empty batch on page {page}. Stopping fetch.")
                break

            for post in posts_batch:
                all_posts_data.append({
                    'id': post.get('id'),
                    'title': post.get('title', {}).get('rendered', ''),
                    'content': post.get('content', {}).get('rendered', ''),
                    'date': post.get('date', '')
                })
            print(f"✅ Berhasil mengambil {len(posts_batch)} artikel di halaman {page}. Total: {len(all_posts_data)}.")
            page += 1
            time.sleep(0.5)
        except requests.exceptions.Timeout:
            print(f"Timeout: Permintaan ke WordPress API di halaman {page} habis waktu. Mungkin ada masalah jaringan atau server lambat.")
            break
        except requests.exceptions.RequestException as e:
            print(f"Network Error: Gagal terhubung ke WordPress API di halaman {page}: {e}. Cek koneksi atau URL.")
            break
            
    return all_posts_data

# --- FUNGSI UTAMA ---
if __name__ == '__main__':
    print(f"[{datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}] Starting WordPress to WordPress publishing process...")
    print(f"🚀 Mengambil artikel dari WordPress SUMBER: {API_SOURCE_URL}.")
    print(f"🎯 Akan memposting ke WordPress TARGET via XML-RPC: {WP_TARGET_API_URL} dengan Blog ID: {WP_BLOG_ID}.")
    print("❌ Fitur Pengeditan Judul dan Konten (300 kata pertama) oleh Gemini AI **DINONAKTIFKAN** (menggunakan konten asli yang sudah diganti kata).")
    print("📝 Tag <details> akan disisipkan di dalam artikel di pertengahan total paragraf.")
    print("📝 String **<!--more-->** (sebagai placeholder) akan disisipkan setelah paragraf pertama.")
    print("🖼️ Mencoba menambahkan gambar acak di awal konten.")
    print(f"🏷️ Tag default yang akan ditambahkan: {', '.join(DEFAULT_TAGS)}")
    
    published_count = 0
    
    try:
        published_ids = load_published_posts_state()
        print(f"Ditemukan {len(published_ids)} postingan yang sudah diterbitkan sebelumnya.")

        random_image_urls = load_image_urls(RANDOM_IMAGES_FILE)
        if not random_image_urls:
            print("⚠️ Tidak ada URL gambar acak yang tersedia. Artikel akan diterbitkan tanpa gambar acak di awal.")

        all_posts_raw_data = fetch_raw_posts()
        print(f"Total {len(all_posts_raw_data)} artikel ditemukan dari WordPress SUMBER.")

        unpublished_posts = [post for post in all_posts_raw_data if str(post['id']) not in published_ids]
        print(f"Ditemukan **{len(unpublished_posts)}** artikel dari SUMBER yang belum diterbitkan ke TARGET.")

        if not unpublished_posts:
            print("\n🎉 Tidak ada artikel baru yang tersedia untuk diterbitkan. Proses selesai.")
            exit()

        # Urutkan berdasarkan tanggal (paling baru duluan)
        unpublished_posts.sort(key=lambda x: datetime.datetime.fromisoformat(x['date'].replace('Z', '+00:00')), reverse=True)
        
        # --- LOGIKA PENGAMBILAN SEMUA ARTIKEL DIMULAI DI SINI ---
        
        for i, post_to_publish_data in enumerate(unpublished_posts):
            original_id = post_to_publish_data['id']
            original_title = post_to_publish_data['title']
            original_content = post_to_publish_data['content']
            
            print("\n" + "="*80)
            print(f"[{i+1}/{len(unpublished_posts)}] 🎯 Memproses Artikel ID: {original_id} - '{original_title}'")
            print("="*80)
            
            try:
                # Ambil gambar acak baru untuk setiap artikel jika ada daftarnya
                selected_random_image = get_random_image_url(random_image_urls)

                post_date_str = post_to_publish_data['date']
                post_datetime_obj = datetime.datetime.fromisoformat(post_date_str.replace('Z', '+00:00'))
                date_path = post_datetime_obj.strftime('%Y/%m/%d')
                print(f"🗓️ Tanggal untuk URL artikel: {date_path}")

                content_no_anchors = remove_anchor_tags(original_content)
                
                # Fungsi ini seharusnya mengubah </p> menjadi \n\n
                cleaned_content_before_gemini = strip_html_and_divs(content_no_anchors)
                content_after_replacements_all = replace_custom_words(cleaned_content_before_gemini)

                final_processed_content_text, edited_first_300_words_content = edit_content_placeholder(
                    original_id,
                    original_title, 
                    content_after_replacements_all 
                )
                
                final_edited_title = edit_title_placeholder(
                    original_title
                )
                
                post_slug = slugify(final_edited_title)
                base_target_url_for_permalink = "https://wiraferita.wordpress.com"
                predicted_article_url = f"{base_target_url_for_permalink}/{post_datetime_obj.strftime('%Y')}/{post_datetime_obj.strftime('%m')}/{post_slug}"
                print(f"🔗 Memprediksi URL artikel target: {predicted_article_url}")

                content_with_details_tag = insert_details_tag(
                    final_processed_content_text,
                    article_url=predicted_article_url,
                    article_title=final_edited_title
                )
                
                # PENGGANTIAN TAG dengan <!--more-->
                final_content_with_more_tag_placeholder = add_more_tag_before_send(content_with_details_tag)

                # ----------------------------------------------------------------
                # 🚀 LOGIKA KONVERSI HTML YANG DIPERBAIKI 🚀
                # ----------------------------------------------------------------
                
                # 1. Memecah konten berdasarkan newline ganda (\n\n) menjadi array blok.
                content_blocks = final_content_with_more_tag_placeholder.split('\n\n')
                
                final_html_parts = []
                for block in content_blocks:
                    block = block.strip()
                    if not block:
                        continue
                        
                    # Tag khusus yang seharusnya TIDAK dibungkus oleh <p> (termasuk tag details, dan sekarang <!--more-->)
                    # Kita cek jika blok sudah diawali atau diakhiri tag HTML atau merupakan string/tag khusus.
                    if block.startswith('<') or block.endswith('>') or block.startswith('Similar wordpress.com site') or block == '<!--more-->': # Cek untuk <!--more--> tanpa **
                        final_html_parts.append(block)
                    else:
                        # Ini adalah blok teks biasa, bungkus dengan <p>
                        final_html_parts.append(f'<p>{block}</p>')

                # 2. Menggabungkan kembali bagian-bagian, dipisahkan oleh newline tunggal.
                final_post_content_html = '\n'.join(final_html_parts)
                
                # 3. Pembersihan terakhir: memastikan tag khusus tidak terbungkus oleh tag <p> yang tersisa dari proses gabungan.
                
                # Hapus baris penggantian tag <!--more--> -> (sesuai permintaan user)
                
                # Pembersihan lainnya
                final_post_content_html = final_post_content_html.replace('</p>\n\n\n\n<p>', '\n\n')
                final_post_content_html = final_post_content_html.replace('<p></p>', '')
                final_post_content_html = final_post_content_html.replace('</p><details>', '</details><details>') # Perbaikan jika ada </p> yang menempel
                final_post_content_html = final_post_content_html.replace('</details><p>', '</details>\n\n')
                final_post_content_html = final_post_content_html.replace('<p><details>', '<details>')
                final_post_content_html = final_post_content_html.replace('</details></p>', '</details>')
                final_post_content_html = final_post_content_html.replace('</div></p>', '</div>')
                final_post_content_html = final_post_content_html.replace('<p>Similar wordpress.com site', 'Similar wordpress.com site')
                
                # Hapus <p> atau </p> yang tersisa di awal/akhir
                if final_post_content_html.startswith('<p>'):
                    final_post_content_html = final_post_content_html[3:]
                if final_post_content_html.endswith('</p>'):
                    final_post_content_html = final_post_content_html[:-4]
                        
                # ----------------------------------------------------------------
                # 🛑 LOGIKA KONVERSI HTML YANG DIPERBAIKI SELESAI 🛑
                # ----------------------------------------------------------------

                print("💡 Pratinjau Konten HTML Final (untuk cek tag):")
                # Gunakan replace('\n', ' ') untuk pratinjau agar log tidak terlalu panjang
                preview = final_post_content_html[:500]
                if len(final_post_content_html) > 500:
                    preview += '...'
                print(preview.replace('\n', ' '))
                print("-------------------------------------------------------")

                published_result = publish_post_to_wordpress(
                    WP_TARGET_API_URL,
                    WP_BLOG_ID,
                    final_edited_title,
                    final_post_content_html, # Mengirim konten HTML yang sudah diperbaiki
                    WP_USERNAME,
                    WP_APP_PASSWORD,
                    random_image_url=selected_random_image,
                    tags=DEFAULT_TAGS 
                )
                
                if published_result:
                    published_ids.add(str(original_id))
                    save_published_posts_state(published_ids)
                    published_count += 1
                    print(f"✅ State file '{STATE_FILE}' diperbarui dengan ID post dari SUMBER: {original_id}.")
                else:
                    print(f"❌ Gagal menerbitkan artikel ID: {original_id}. Melanjutkan ke artikel berikutnya...")

                # Jeda sejenak untuk menghindari flooding API dan rate limiting
                time.sleep(random.uniform(5, 15)) 
                
            except Exception as e:
                print(f"❌ Terjadi kesalahan saat memproses artikel ID {original_id}: {e}. Melanjutkan ke artikel berikutnya...")
                import traceback
                traceback.print_exc()

        # --- LOGIKA PENGAMBILAN SEMUA ARTIKEL BERAKHIR DI SINI ---
        
        print("\n" + "="*80)
        print(f"🎉 Proses Selesai! **{published_count}** dari {len(unpublished_posts)} artikel baru berhasil diterbitkan ke WordPress TARGET.")
        print("="*80)
        
    except Exception as e:
        print(f"❌ Terjadi kesalahan fatal: {e}")
        import traceback
        traceback.print_exc()
