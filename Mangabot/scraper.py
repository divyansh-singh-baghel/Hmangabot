import os
import cloudscraper
import img2pdf
from bs4 import BeautifulSoup
import shutil
import uuid

def create_bot_scraper():
    return cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
    )

# ==========================================
# 1. Fetch manga list
# ==========================================
def get_manga_list(search_tags, limit=5):
    scraper = create_bot_scraper()
    query = "%20".join(search_tags)
    url = f"https://hentaiforce.net/search?q={query}"
    print(f"🔍 Searching on: {url}")
    
    try:
        response = scraper.get(url)
        if response.status_code != 200: return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        containers = soup.find_all('div', class_='gallery-wrapper')
        results = []
        
        for box in containers[:limit]:
            try:
                name_tag = box.find('div', class_='gallery-name')
                link_tag = name_tag.find('a') if name_tag else None
                title = link_tag.text.strip() if link_tag else "No Title"
                manga_link = link_tag['href'] if link_tag else "No Link"
                
                if manga_link.startswith('/'): 
                    manga_link = "https://hentaiforce.net" + manga_link
                    
                results.append({'title': title, 'link': manga_link})
            except Exception: 
                continue
        return results
    except Exception: 
        return []

# ==========================================
# 2. Fetch pages & Cover Image (UPDATED)
# ==========================================
def get_manga_pages(manga_url):
    scraper = create_bot_scraper()
    print(f"📖 Extracting pages & cover from: {manga_url}")
    
    try:
        response = scraper.get(manga_url)
        if response.status_code != 200: 
            return [], None
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # NAYA: HTML se Cover Image nikalna
        cover_url = None
        cover_div = soup.find('div', id='gallery-main-cover')
        if cover_div:
            img_tag = cover_div.find('img')
            if img_tag:
                cover_url = img_tag.get('data-src') or img_tag.get('src')
        
        gallery = soup.find('div', id='gallery-pages')
        if not gallery: return [], cover_url
            
        thumbs = gallery.find_all('div', class_='single-thumb')
        image_links = []
        
        for thumb in thumbs:
            img_tag = thumb.find('img')
            if img_tag:
                thumb_url = img_tag.get('data-src') or img_tag.get('src')
                if thumb_url: 
                    image_links.append(thumb_url.replace('t.jpg', '.jpg').replace('t.png', '.png'))
                    
        return image_links, cover_url # Ab yeh tuple return karega
    except Exception as e:
        print(f"❌ Error extracting pages: {e}")
        return [], None

# ==========================================
# 3. Download & Make PDF (Safe & Splitting)
# ==========================================
def download_and_make_pdf(image_links, title):
    scraper = create_bot_scraper()
    
    # 80 Char Limit OS Error fix
    safe_title = "".join([c for c in title if c.isalpha() or c.isdigit() or c==' ']).rstrip()[:80]
    
    # Unique temp folder fix
    temp_folder = f"temp_{uuid.uuid4().hex[:8]}"
    if not os.path.exists(temp_folder): 
        os.makedirs(temp_folder)
        
    downloaded_images = []
    print(f"📥 Downloading {len(image_links)} images...")
    
    for i, url in enumerate(image_links):
        try:
            response = scraper.get(url)
            if response.status_code == 200:
                img_path = f"{temp_folder}/page_{i+1}.jpg"
                with open(img_path, 'wb') as f: f.write(response.content)
                downloaded_images.append(img_path)
        except Exception: 
            pass
            
    if not downloaded_images:
        shutil.rmtree(temp_folder, ignore_errors=True)
        return []

    pdf_filename = f"{safe_title}.pdf"
    with open(pdf_filename, "wb") as f:
        f.write(img2pdf.convert(downloaded_images))
        
    # 50MB Bypass Logic
    size_mb = os.path.getsize(pdf_filename) / (1024 * 1024)
    final_pdfs = []
    
    if size_mb > 48.0:
        print(f"⚠️ PDF Size: {size_mb:.2f} MB. Splitting...")
        os.remove(pdf_filename)
        mid_index = len(downloaded_images) // 2
        part1_name = f"{safe_title} - Part 1.pdf"
        part2_name = f"{safe_title} - Part 2.pdf"
        
        with open(part1_name, "wb") as f: f.write(img2pdf.convert(downloaded_images[:mid_index]))
        with open(part2_name, "wb") as f: f.write(img2pdf.convert(downloaded_images[mid_index:]))
        final_pdfs = [part1_name, part2_name]
    else:
        final_pdfs = [pdf_filename]
    
    # Safe cleanup
    shutil.rmtree(temp_folder, ignore_errors=True)
    return final_pdfs
