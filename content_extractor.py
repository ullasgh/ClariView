import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import time
import re

# Try selenium import - will use if available
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    SELENIUM_AVAILABLE = True
    print("✅ Selenium available")
except ImportError:
    SELENIUM_AVAILABLE = False
    print("⚠️ Selenium not available - install with: pip install selenium")

def extract_article_content(url: str, use_selenium: bool = True, debug: bool = False) -> dict:
    """
    Enhanced content extractor with Selenium fallback for JavaScript sites.
    """
    print(f"🔍 Extracting content from: {url}")
    
    # Try requests first (faster)
    result = try_requests_extraction(url, debug)
    
    # If requests fails or returns little content, try Selenium
    if (("error" in result or len(result.get("content", "")) < 200) 
        and use_selenium and SELENIUM_AVAILABLE):
        print("🔄 Trying Selenium for JavaScript content...")
        selenium_result = try_selenium_extraction(url, debug)
        if selenium_result and "error" not in selenium_result:
            return selenium_result
    
    return result

def try_requests_extraction(url: str, debug: bool = False) -> dict:
    """Try extracting with requests first."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Cache-Control": "max-age=0"
    }
    
    try:
        print("📡 Making requests call...")
        response = requests.get(url, timeout=15, headers=headers, allow_redirects=True)
        response.raise_for_status()
        
        return parse_html_content(response.text, url, debug)
        
    except Exception as e:
        print(f"❌ Requests failed: {e}")
        return {"error": f"Requests failed: {str(e)}", "url": url}

def try_selenium_extraction(url: str, debug: bool = False) -> dict:
    """Try extracting with Selenium for JavaScript content."""
    if not SELENIUM_AVAILABLE:
        return {"error": "Selenium not available", "url": url}
    
    driver = None
    try:
        # Setup Chrome options
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Run in background
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        
        print("🚀 Starting Chrome driver...")
        driver = webdriver.Chrome(options=chrome_options)
        
        print("📱 Loading page...")
        driver.get(url)
        
        # Wait for content to load
        print("⏳ Waiting for content...")
        time.sleep(3)
        
        # Try to wait for article content
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "p"))
            )
        except:
            print("⚠️ Timeout waiting for paragraphs, proceeding anyway...")
        
        # Get page source after JavaScript execution
        html = driver.page_source
        print("✅ Page loaded with Selenium")
        
        return parse_html_content(html, url, debug)
        
    except Exception as e:
        print(f"❌ Selenium failed: {e}")
        return {"error": f"Selenium failed: {str(e)}", "url": url}
    
    finally:
        if driver:
            driver.quit()
            print("🔚 Chrome driver closed")

def parse_html_content(html: str, url: str, debug: bool = False) -> dict:
    """Parse HTML content and extract article data."""
    soup = BeautifulSoup(html, "html.parser")
    
    # Extract title
    title = extract_title(soup)
    print(f"📰 Title: {title}")
    
    # Extract content with multiple strategies
    content = extract_content_comprehensive(soup, debug)
    print(f"📄 Content length: {len(content)} characters")
    
    # Extract metadata
    metadata = extract_metadata(soup)
    
    # Extract domain
    domain = urlparse(url).netloc
    
    # Debug if content is short or debug mode is on
    if len(content) < 200 or debug:
        debug_content_extraction(soup)
    
    return {
        "url": url,
        "source": domain,
        "title": title,
        "author": metadata.get("author"),
        "date_published": metadata.get("date_published"),
        "image": metadata.get("image"),
        "content": content,
        "debug_info": get_debug_info(soup) if debug else None
    }

def extract_title(soup):
    """Extract title using multiple strategies."""
    strategies = [
        lambda: soup.find("meta", property="og:title"),
        lambda: soup.find("meta", attrs={"name": "twitter:title"}),
        lambda: soup.find("h1", class_=lambda x: x and "title" in x.lower()),
        lambda: soup.find("h1"),
        lambda: soup.title,
        lambda: soup.find(attrs={"class": lambda x: x and "headline" in str(x).lower()}),
    ]
    
    for strategy in strategies:
        try:
            element = strategy()
            if element:
                if element.name == "meta":
                    content = element.get("content")
                    if content:
                        return content.strip()
                else:
                    text = element.get_text(strip=True)
                    if text:
                        return text
        except:
            continue
    
    return "No Title Found"

def extract_content_comprehensive(soup, debug=False):
    """Extract content using comprehensive strategies with better paragraph detection."""
    content_parts = []
    
    # Remove unwanted elements
    for element in soup.find_all(['script', 'style', 'nav', 'footer', 'header', 'aside']):
        element.decompose()
    
    # Strategy 1: Get all substantial paragraphs first (most reliable)
    print("🔍 Extracting all substantial paragraphs...")
    paragraphs = soup.find_all("p")
    substantial_paras = []
    
    # More flexible filtering for paragraphs
    skip_patterns = [
        'subscribe', 'newsletter', 'follow us', 'share', 'tweet', 
        'facebook', 'twitter', 'instagram', 'advertisement', 
        'file photo', 'photo:', 'image:', 'listen to this article',
        'min read', 'wire staff'
    ]
    
    for i, p in enumerate(paragraphs):
        text = p.get_text(strip=True)
        
        if debug:
            print(f"   P{i+1} ({len(text)}): {text[:100]}{'...' if len(text) > 100 else ''}")
        
        # More lenient filtering - reduced minimum length and better skip detection
        if (len(text) > 30 and  # Reduced from 50 to catch shorter but valid paragraphs
            not any(skip.lower() in text.lower() for skip in skip_patterns) and
            not re.match(r'^[A-Z\s]+$', text) and  # Skip all-caps titles
            not re.match(r'^\d+\s*(min|minutes?)\s*read', text.lower()) and  # Skip time indicators
            len(text.split()) > 5):  # Must have at least 5 words
            substantial_paras.append(text)
    
    if substantial_paras:
        print(f"   ✅ Found {len(substantial_paras)} substantial paragraphs")
        content_parts = substantial_paras
    else:
        # Strategy 2: Try Indian news site selectors and more generic ones
        print("🔍 Trying content selectors...")
        content_selectors = [
            # Indian news sites
            '.story-element-text',
            '.content-body',
            '.article-content',
            '.post-content', 
            '.entry-content',
            
            # Generic selectors
            'article p',
            'main p',
            '.content p',
            '[role="main"] p',
            
            # Class-based searches (broader)
            '[class*="story"]',
            '[class*="article"]',
            '[class*="content"]',
            '[class*="text"]',
            '[class*="body"]'
        ]
        
        for selector in content_selectors:
            try:
                elements = soup.select(selector)
                if elements:
                    print(f"   ✅ Found {len(elements)} elements with: {selector}")
                    temp_content = []
                    
                    for element in elements:
                        # Handle different element types
                        if element.name == 'p':
                            text = element.get_text(strip=True)
                            if len(text) > 30:
                                temp_content.append(text)
                        else:
                            # Look for paragraphs within the element
                            paras = element.find_all('p')
                            if paras:
                                for p in paras:
                                    text = p.get_text(strip=True)
                                    if len(text) > 30:
                                        temp_content.append(text)
                            else:
                                # Fallback to element text if no paragraphs
                                text = element.get_text(strip=True)
                                if 50 < len(text) < 2000:  # Reasonable content length
                                    temp_content.append(text)
                    
                    if temp_content:
                        content_parts = temp_content
                        break
            except Exception as e:
                if debug:
                    print(f"   ❌ Selector '{selector}' failed: {e}")
                continue
        
        # Strategy 3: Div content as last resort with better filtering
        if not content_parts:
            print("🔍 Trying div content...")
            divs = soup.find_all("div")
            div_contents = []
            
            for div in divs:
                text = div.get_text(strip=True)
                # Better div content filtering
                if (50 < len(text) < 3000 and  # Increased max length
                    len(text.split()) > 10 and  # At least 10 words
                    not any(skip.lower() in text.lower() for skip in skip_patterns)):
                    div_contents.append(text)
            
            # Take the longest div contents (likely to be article content)
            if div_contents:
                div_contents.sort(key=len, reverse=True)
                content_parts = div_contents[:5]  # Take top 5 longest
    
    # Take more content parts to ensure we don't miss anything
    content_parts = content_parts[:30]  # Increased from 20
    full_content = " ".join(content_parts)
    
    # Clean up repetitive metadata patterns
    full_content = clean_repetitive_content(full_content)
    
    return full_content

def clean_repetitive_content(content):
    """Clean up repetitive metadata and author information."""
    # Remove repetitive "The Wire Staff26/Sep/20255 min read" patterns
    content = re.sub(r'The Wire Staff\d{2}/\w{3}/\d{4}\d+ min read\s*', '', content)
    
    # Remove repetitive date/time patterns
    content = re.sub(r'(\d{2}/\w{3}/\d{4}\s*)+', lambda m: m.group(1), content)
    
    # Remove repetitive "min read" patterns
    content = re.sub(r'(\d+\s*min read\s*)+', lambda m: m.group(1), content)
    
    # Remove repetitive author patterns
    content = re.sub(r'(The Wire Staff\s*)+', 'The Wire Staff ', content)
    
    # Remove photo captions and metadata
    content = re.sub(r'A file photo of[^.]*\.\s*Photo:[^.]*\.\s*', '', content)
    content = re.sub(r'Listen to this article:\s*', '', content)
    
    # Remove duplicate sentences (common in scraped content)
    sentences = content.split('. ')
    unique_sentences = []
    seen = set()
    
    for sentence in sentences:
        sentence_clean = sentence.strip()
        if sentence_clean and sentence_clean not in seen and len(sentence_clean) > 20:
            unique_sentences.append(sentence_clean)
            seen.add(sentence_clean)
    
    content = '. '.join(unique_sentences)
    
    # Clean up extra spaces
    content = re.sub(r'\s+', ' ', content).strip()
    
    return content

def extract_metadata(soup):
    """Extract metadata comprehensively."""
    metadata = {}
    
    # Author extraction
    author_strategies = [
        lambda: soup.find("meta", attrs={"name": "author"}),
        lambda: soup.find("meta", property="article:author"),
        lambda: soup.find(class_=lambda x: x and "author" in str(x).lower()),
        lambda: soup.find("span", class_=lambda x: x and "byline" in str(x).lower()),
        lambda: soup.find(attrs={"rel": "author"}),
    ]
    
    for strategy in author_strategies:
        try:
            elem = strategy()
            if elem:
                if elem.name == "meta":
                    metadata["author"] = elem.get("content")
                else:
                    metadata["author"] = elem.get_text(strip=True)
                break
        except:
            continue
    
    # Date extraction
    date_strategies = [
        lambda: soup.find("meta", property="article:published_time"),
        lambda: soup.find("meta", attrs={"name": "publish-date"}),
        lambda: soup.find("time"),
        lambda: soup.find(class_=lambda x: x and "date" in str(x).lower()),
        lambda: soup.find(attrs={"datetime": True}),
    ]
    
    for strategy in date_strategies:
        try:
            elem = strategy()
            if elem:
                if elem.name == "meta":
                    metadata["date_published"] = elem.get("content")
                elif elem.name == "time":
                    metadata["date_published"] = elem.get("datetime") or elem.get_text(strip=True)
                else:
                    date_text = elem.get_text(strip=True)
                    if date_text and len(date_text) < 50:  # Reasonable date length
                        metadata["date_published"] = date_text
                break
        except:
            continue
    
    # Image
    try:
        img_strategies = [
            lambda: soup.find("meta", property="og:image"),
            lambda: soup.find("meta", attrs={"name": "twitter:image"}),
            lambda: soup.find("img", class_=lambda x: x and "featured" in str(x).lower()),
        ]
        
        for strategy in img_strategies:
            try:
                elem = strategy()
                if elem:
                    if elem.name == "meta":
                        metadata["image"] = elem.get("content")
                    else:
                        metadata["image"] = elem.get("src")
                    break
            except:
                continue
    except:
        pass
    
    return metadata

def get_debug_info(soup):
    """Get debug information about the page structure."""
    return {
        "total_paragraphs": len(soup.find_all('p')),
        "total_divs": len(soup.find_all('div')),
        "has_article_tag": bool(soup.find('article')),
        "has_main_tag": bool(soup.find('main')),
        "content_classes": [elem.get('class') for elem in soup.find_all(class_=lambda x: x and 'content' in str(x).lower())[:5]],
        "article_classes": [elem.get('class') for elem in soup.find_all(class_=lambda x: x and 'article' in str(x).lower())[:5]],
    }

def debug_content_extraction(soup):
    """Debug content extraction when little content is found."""
    print("\n🔍 DEBUGGING - Content extraction analysis")
    print(f"   - Total paragraphs: {len(soup.find_all('p'))}")
    print(f"   - Total divs: {len(soup.find_all('div'))}")
    print(f"   - Has article tag: {bool(soup.find('article'))}")
    print(f"   - Has main tag: {bool(soup.find('main'))}")
    
    # Show all paragraphs with their lengths
    paras = soup.find_all('p')
    print(f"\n📝 All paragraphs found:")
    for i, p in enumerate(paras[:10]):  # Show first 10
        text = p.get_text(strip=True)
        parent_class = p.parent.get('class') if p.parent and p.parent.get('class') else 'no-class'
        print(f"   P{i+1} [{len(text)} chars] (parent: {parent_class}): {text[:100]}{'...' if len(text) > 100 else ''}")
    
    if len(paras) > 10:
        print(f"   ... and {len(paras) - 10} more paragraphs")
    
    # Show classes that might contain content
    content_candidates = soup.find_all(class_=lambda x: x and 
                                      any(keyword in str(x).lower() 
                                          for keyword in ['content', 'article', 'story', 'text', 'body']))
    print(f"\n🎯 Content-like elements found: {len(content_candidates)}")
    for i, elem in enumerate(content_candidates[:5]):
        classes = ' '.join(elem.get('class', []))
        text_length = len(elem.get_text(strip=True))
        print(f"   {i+1}. <{elem.name}> class='{classes}' ({text_length} chars)")

# 🔹 Example usage
if __name__ == "__main__":
    test_url = "https://thewire.in/politics/sonam-wangchuk-arrest-political-reactions-ladakh-leh"
    
    print("="*80)
    print("🚀 ENHANCED CONTENT EXTRACTOR WITH BETTER PARAGRAPH DETECTION")
    print("="*80)
    
    # First install requirements if needed
    if not SELENIUM_AVAILABLE:
        print("\n📦 To use Selenium (for JavaScript sites), install:")
        print("pip install selenium")
        print("And download ChromeDriver: https://chromedriver.chromium.org/\n")
    
    # Extract with debug mode enabled
    article = extract_article_content(test_url, use_selenium=True, debug=True)
    
    if "error" in article:
        print(f"\n❌ Extraction failed: {article['error']}")
    else:
        print("\n✅ EXTRACTION SUCCESSFUL!")
        print("-"*50)
        print(f"🔗 URL: {article.get('url')}")
        print(f"🌐 Source: {article.get('source')}")
        print(f"📰 Title: {article.get('title')}")
        print(f"👤 Author: {article.get('author', 'Not found')}")
        print(f"📅 Date: {article.get('date_published', 'Not found')}")
        print(f"📄 Content Length: {len(article.get('content', ''))} characters")
        
        content = article.get('content', '')
        if len(content) > 100:
            print(f"\n📖 Content Preview (first 800 chars):")
            print("-"*50)
            print(content)
        else:
            print(f"\n⚠️ Short content extracted: {content}")
    
    print("\n" + "="*80)