import os
import cloudscraper
import img2pdf
from bs4 import BeautifulSoup
import shutil
import uuid

def create_bot_scraper():
    # Setup Chrome-like behavior
    return cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
    )

# ==========================================
# FUNCTION 1: Search and fetch manga list
# ==========================================
def get_manga_list(search_tags, limit=5):
    scraper = create_bot_scraper()
    query = "%20".join(search_tags)
    url = f"https://hentaiforce.net/search?q={query}"
    
    print(f"🔍 Searching Manga on: {url}")
    
    try:
        response = scraper.get(url)
        if response.status_code != 200:
            return []
            
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
    except Exception as e:
        print(f"❌ Error in search: {e}")
        return []

# ==========================================
# FUNCTION 2: Fetch all page links for a manga
# ==========================================
def get_manga_pages(manga_url):
    scraper = create_bot_scraper()
    print(f"📖 Extracting pages from: {manga_url}")
    
    try:
        response = scraper.get(manga_url)
        if response.status_code != 200:
            print("❌ Manga page failed to load.")
            return []
            
        soup = BeautifulSoup(response.text, 'html.parser')
        gallery = soup.find('div', id='gallery-pages')
        
        if not gallery:
            print("❌ Gallery container not found.")
            return []
            
        thumbs = gallery.find_all('div', class_='single-thumb')
        image_links = []
        
        for thumb in thumbs:
            img_tag = thumb.find('img')
            if img_tag:
                thumb_url = img_tag.get('data-src') or img_tag.get('src')
                if thumb_url:
                    # TRICK: Convert thumbnail 't.jpg' to high quality '.jpg'
                    full_image_url = thumb_url.replace('t.jpg', '.jpg').replace('t.png', '.png')
                    image_links.append(full_image_url)
                    
        return image_links
    except Exception as e:
        print(f"❌ Error extracting pages: {e}")
        return []

# ==========================================
# FUNCTION 3: Download images and create PDF (Fixes Applied)
# ==========================================
def download_and_make_pdf(image_links, title):
    scraper = create_bot_scraper()
    
    # FIX 1: Truncate title to max 80 characters to fix OS "File name too long" error
    safe_title = "".join([c for c in title if c.isalpha() or c.isdigit() or c==' ']).rstrip()[:80]
    pdf_filename = f"{safe_title}.pdf"
    
    # FIX 2: Generate unique temp folder using UUID to prevent "Directory not empty" crashes
    temp_folder = f"temp_images_{uuid.uuid4().hex[:8]}"
    if not os.path.exists(temp_folder):
        os.makedirs(temp_folder)
        
    downloaded_images = []
    print(f"\n📥 Downloading {len(image_links)} images...")
    
    for i, url in enumerate(image_links):
        try:
            response = scraper.get(url)
            if response.status_code == 200:
                img_path = f"{temp_folder}/page_{i+1}.jpg"
                with open(img_path, 'wb') as f:
                    f.write(response.content)
                downloaded_images.append(img_path)
            else:
                 print(f"⚠️ Page {i+1} failed to download.")
        except Exception as e:
            print(f"❌ Error downloading page {i+1}: {e}")
            
    if not downloaded_images:
        shutil.rmtree(temp_folder, ignore_errors=True) # Safe cleanup if empty
        return []

    print("\n📄 Generating PDF and verifying file size...")
    # Create single PDF first
    with open(pdf_filename, "wb") as f:
        f.write(img2pdf.convert(downloaded_images))
        
    # Check File Size in MB
    size_mb = os.path.getsize(pdf_filename) / (1024 * 1024)
    final_pdfs = []
    
    if size_mb > 48.0:
        print(f"⚠️ PDF exceeds 48MB ({size_mb:.2f} MB). Splitting into 2 parts...")
        os.remove(pdf_filename) # Delete the oversized file
        
        mid_index = len(downloaded_images) // 2
        part1_name = f"{safe_title} - Part 1.pdf"
        part2_name = f"{safe_title} - Part 2.pdf"
        
        with open(part1_name, "wb") as f:
            f.write(img2pdf.convert(downloaded_images[:mid_index]))
        with open(part2_name, "wb") as f:
            f.write(img2pdf.convert(downloaded_images[mid_index:]))
            
        final_pdfs = [part1_name, part2_name]
    else:
        print(f"✅ PDF Size safe: {size_mb:.2f} MB")
        final_pdfs = [pdf_filename]
    
    # FIX 3: Use shutil to forcefully and safely delete the temp folder and all its contents
    shutil.rmtree(temp_folder, ignore_errors=True)
    
    return final_pdfs

# ==========================================
# LOCAL TESTING BLOCK
# ==========================================
if __name__ == "__main__":
    print("--- STEP 1: SEARCHING ---")
    manga_list = get_manga_list(["color", "english"], limit=1)
    
    if manga_list:
        first_manga = manga_list[0]
        print(f"✅ Found Manga: {first_manga['title']}")
        
        print("\n--- STEP 2: GETTING PAGES ---")
        pages = get_manga_pages(first_manga['link'])
        
        if pages:
            print(f"✅ Total {len(pages)} pages found!")
            
            print("\n--- STEP 3: MAKING PDF ---")
            pdf_file = download_and_make_pdf(pages, first_manga['title'])
        else:
            print("❌ No pages extracted.")
    else:
        print("❌ No search results.")
