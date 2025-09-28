import os
from dotenv import load_dotenv
from content_extractor import extract_article_content
from summary import get_five_points
from openai import OpenAI
from tavily import TavilyClient

# 🔹 Load environment variables
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

# 🔹 Initialize clients
openai_client = OpenAI(api_key=OPENAI_API_KEY)
tavily_client = TavilyClient(api_key=TAVILY_API_KEY)

def create_opposite_tone_for_point(point):
    """Create opposite tone for a single point using OpenAI."""
    prompt = f"""Take this point and create the exact opposite viewpoint or tone:

Original point: {point}

Create a search query that would find articles with the opposite viewpoint. Make it specific and focused (max 10 words):"""
    
    try:
        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You create opposing search queries for given points."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=100,
            temperature=0.5
        )
        
        opposite_query = response.choices[0].message.content.strip()
        # Clean up the query (remove quotes, extra text)
        opposite_query = opposite_query.replace('"', '').replace("Search query:", "").strip()
        return opposite_query
    
    except Exception as e:
        print(f"   ⚠️ Error creating opposite tone: {e}")
        # Fallback: create simple opposite query
        key_words = point.split()[:5]
        return f"{' '.join(key_words)} problems criticism disadvantages"

def is_news_website(url):
    """Check if URL is from a news website (not social media)."""
    if not url:
        return False
    
    # Convert to lowercase for checking
    url_lower = url.lower()
    
    # Block social media and non-news platforms
    blocked_domains = [
        'facebook.com', 'fb.com', 'instagram.com', 'twitter.com', 'x.com',
        'youtube.com', 'youtu.be', 'tiktok.com', 'linkedin.com', 'pinterest.com',
        'reddit.com', 'tumblr.com', 'snapchat.com', 'whatsapp.com', 'telegram.org'
    ]
    
    # Check if URL contains any blocked domains
    for domain in blocked_domains:
        if domain in url_lower:
            return False
    
    # Allow common news website patterns
    news_indicators = [
        '.com', '.org', '.net', '.in', '.co.uk', '.au', '.ca', '.news',
        'news', 'times', 'post', 'herald', 'tribune', 'guardian', 'reuters',
        'bloomberg', 'cnn', 'bbc', 'npr', 'abc', 'nbc', 'cbs', 'fox'
    ]
    
    # If it's not blocked and has news-like indicators, consider it valid
    return True

def search_for_opposite_articles(query):
    """Search Tavily once for articles with opposite viewpoint."""
    try:
        print(f"   🔍 Searching: {query}")
        
        response = tavily_client.search(
            query=query,
            max_results=5,  # Increased to account for filtering
            include_answer=False,
            include_raw_content=False  # We only need URLs
        )
        
        results = response.get('results', [])
        all_urls = [result.get('url') for result in results if result.get('url')]
        
        # Filter to only include news websites
        news_urls = [url for url in all_urls if is_news_website(url)]
        
        # Limit to top 3 news URLs
        news_urls = news_urls[:3]
        
        print(f"   📊 Found {len(all_urls)} total results, {len(news_urls)} news articles")
        return news_urls
    
    except Exception as e:
        print(f"   ⚠️ Search error: {e}")
        return []

def main(article_url):
    """Main function to find opposite viewpoint articles for each point."""
    print(f"🔍 Analyzing article: {article_url}")
    
    # Step 1: Extract article content
    try:
        article = extract_article_content(article_url)
        article_text = article.get("content", "")
        article_title = article.get("title", "")
        
        if not article_text:
            print("❌ Could not extract article content.")
            return []
        
        print(f"✅ Extracted article content: {len(article_text)} characters")
    
    except Exception as e:
        print(f"❌ Error extracting article: {e}")
        return []

    # Step 2: Extract 5 key points
    try:
        five_points = get_five_points(article_text, article_title)
        print(f"✅ Extracted {len(five_points)} key points")
    
    except Exception as e:
        print(f"❌ Error extracting key points: {e}")
        return []

    # Step 3: Process each point individually
    print("\n🔄 Processing each point for opposite articles...")
    results = []
    
    for i, point in enumerate(five_points, 1):
        print(f"\n📍 Point {i}: {point[:80]}...")
        
        # Create opposite tone for this specific point
        opposite_query = create_opposite_tone_for_point(point)
        print(f"   🔄 Opposite query: {opposite_query}")
        
        # Search once for this point's opposite
        article_urls = search_for_opposite_articles(opposite_query)
        
        if article_urls:
            print(f"   ✅ Found {len(article_urls)} opposing articles")
            results.append({
                'point_number': i,
                'original_point': point,
                'opposite_query': opposite_query,
                'article_urls': article_urls
            })
        else:
            print(f"   ❌ No opposing articles found")
    
    return results

def get_all_urls(results):
    """Extract all URLs from all points and return as a single list."""
    all_urls = []
    for result in results:
        all_urls.extend(result.get('article_urls', []))
    return all_urls

def print_results(results):
    """Print the results showing URLs for each point."""
    print("\n" + "="*80)
    print("🔗 OPPOSITE VIEWPOINT ARTICLES BY POINT")
    print("="*80)
    
    if not results:
        print("❌ No opposing articles found for any point.")
        return
    
    for result in results:
        print(f"\n📍 Point {result['point_number']}: {result['original_point'][:100]}...")
        print(f"🔄 Opposite Search: {result['opposite_query']}")
        print(f"🔗 Article URLs:")
        
        for j, url in enumerate(result['article_urls'], 1):
            print(f"   {j}. {url}")
        
        print("-" * 60)

# 🔹 Example usage
if __name__ == "__main__":
    # Test URL
    test_url = "https://thewire.in/politics/sonam-wangchuk-arrest-political-reactions-ladakh-leh"
    
    results = main(test_url)
    print_results(results)
    
    # Get all URLs from all points
    all_urls = get_all_urls(results)
    print(f"\n📝 Total URLs collected: {len(all_urls)}")
    print("🔗 All URLs:")
    for i, url in enumerate(all_urls, 1):
        print(f"   {i}. {url}")