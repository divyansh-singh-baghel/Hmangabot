import os
import cloudscraper
import img2pdf
from bs4 import BeautifulSoup

def create_bot_scraper():
    # Chrome browser ki tarah behave karne ke liye
    return cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
    )

# ==========================================
# FUNCTION 1: Search karke list lana
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
# FUNCTION 2: Ek Manga ke saare pages nikalna
# ==========================================
def get_manga_pages(manga_url):
    scraper = create_bot_scraper()
    print(f"📖 Pages nikal rahe hain: {manga_url}")
    
    try:
        response = scraper.get(manga_url)
        if response.status_code != 200:
            print("❌ Manga page load nahi hua.")
            return []
            
        soup = BeautifulSoup(response.text, 'html.parser')
        gallery = soup.find('div', id='gallery-pages')
        
        if not gallery:
            print("❌ Gallery container nahi mila.")
            return []
            
        thumbs = gallery.find_all('div', class_='single-thumb')
        image_links = []
        
        for thumb in thumbs:
            img_tag = thumb.find('img')
            if img_tag:
                thumb_url = img_tag.get('data-src') or img_tag.get('src')
                if thumb_url:
                    # TRICK: 't.jpg' ko '.jpg' me badalna high quality ke liye
                    full_image_url = thumb_url.replace('t.jpg', '.jpg').replace('t.png', '.png')
                    image_links.append(full_image_url)
                    
        return image_links
    except Exception as e:
        print(f"❌ Error in getting pages: {e}")
        return []

# ==========================================
# FUNCTION 3: Images ko PDF mein convert karna (NAYA KAAM)
# ==========================================
def download_and_make_pdf(image_links, title):
    scraper = create_bot_scraper()
    
    # Title mein se ajeeb characters hatana taaki file save ho sake
    safe_title = "".join([c for c in title if c.isalpha() or c.isdigit() or c==' ']).rstrip()
    pdf_filename = f"{safe_title}.pdf"
    
    temp_folder = "temp_images"
    if not os.path.exists(temp_folder):
        os.makedirs(temp_folder)
        
    downloaded_images = []
    print(f"\n📥 {len(image_links)} images download karna shuru kar rahe hain...")
    
    for i, url in enumerate(image_links):
        try:
            response = scraper.get(url)
            if response.status_code == 200:
                img_path = f"{temp_folder}/page_{i+1}.jpg"
                with open(img_path, 'wb') as f:
                    f.write(response.content)
                downloaded_images.append(img_path)
                print(f"✅ Page {i+1} downloaded!")
            else:
                 print(f"⚠️ Page {i+1} download nahi hua.")
        except Exception as e:
            print(f"❌ Error downloading page {i+1}: {e}")
            
    # PDF Banana
    if downloaded_images:
        print("\n📄 PDF ban raha hai, please wait...")
        with open(pdf_filename, "wb") as f:
            f.write(img2pdf.convert(downloaded_images))
        print(f"🎉 SUCCESS! PDF Ready ho gayi: {pdf_filename}")
    else:
        print("❌ Koi image download nahi hui, PDF nahi ban sakti.")
        return None
    
    # Kachra saaf karna
    print("🧹 Temporary images saaf kar rahe hain...")
    for img in downloaded_images:
        os.remove(img)
    os.rmdir(temp_folder)
    
    return pdf_filename

# ==========================================
# TEST KARNE KE LIYE (Ab teeno step ek saath chalenge)
# ==========================================
if __name__ == "__main__":
    print("--- STEP 1: SEARCHING ---")
    manga_list = get_manga_list(["color", "english"], limit=1)
    
    if manga_list:
        first_manga = manga_list[0]
        print(f"✅ Ek manga mil gayi: {first_manga['title']}")
        
        print("\n--- STEP 2: GETTING PAGES ---")
        pages = get_manga_pages(first_manga['link'])
        
        if pages:
            print(f"✅ Total {len(pages)} pages mile!")
            
            print("\n--- STEP 3: MAKING PDF ---")
            pdf_file = download_and_make_pdf(pages, first_manga['title'])
        else:
            print("❌ Pages nahi mile.")
    else:
        print("❌ Kuch nahi mila!")