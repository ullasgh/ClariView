import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

def extract_article_content(url: str) -> dict:
    """
    Extracts main content and metadata from a news article URL.
    Includes text from <p> and <li> tags.
    """
    try:
        response = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Headline
        title = soup.title.string.strip() if soup.title else "No Title Found"

        # Paragraphs + list items
        paragraphs = [p.get_text(strip=True) for p in soup.find_all("p")]
        list_items = [li.get_text(strip=True) for li in soup.find_all("li")]

        # Combine into one article text
        content = " ".join(paragraphs + list_items)

        # Metadata
        author = None
        date_published = None
        image = None

        # Try extracting metadata tags
        author_tag = soup.find("meta", attrs={"name": "author"})
        if author_tag and author_tag.get("content"):
            author = author_tag["content"]

        date_tag = soup.find("meta", attrs={"property": "article:published_time"})
        if date_tag and date_tag.get("content"):
            date_published = date_tag["content"]

        image_tag = soup.find("meta", attrs={"property": "og:image"})
        if image_tag and image_tag.get("content"):
            image = image_tag["content"]

        # Extract domain (source)
        domain = urlparse(url).netloc

        return {
            "url": url,
            "source": domain,
            "title": title,
            "author": author,
            "date_published": date_published,
            "image": image,
            "content": content  # full article text
        }

    except Exception as e:
        return {"error": str(e), "url": url}


# 🔹 Example usage
if __name__ == "__main__":
    test_url = "https://www.financialexpress.com/life/technology-apple-iphone-17-iphone-17-pro-iphone-17-pro-max-iphone-air-these-countries-will-get-esim-only-models-3976482/"  # replace with your news/article URL
    article = extract_article_content(test_url)

    print("🔗 URL:", article.get("url"))
    print("📰 Title:", article.get("title"))
    print("📄 Content Preview:", article.get("content"))