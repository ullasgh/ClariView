# authenticity_verifier.py
import os
from dotenv import load_dotenv
from content_extractor import extract_article_content
from summary import get_five_points
from tavily import TavilyClient

# 🔹 Load environment variables
load_dotenv()
TAVILY_KEY = os.getenv("TAVILY_API_KEY")

# 🔹 Initialize Tavily client
client = TavilyClient(TAVILY_KEY)

# 🔹 Function to verify a long sentence on the web
def verify_long_sentence(sentence: str, max_results: int = 5):
    """
    Checks if a sentence exists on the web.
    Returns Real if found in any result, else Fake.
    """
    try:
        # Perform search
        results = client.search(sentence, max_results=max_results)
        sources = []
        
        # Handle different possible response formats
        if results:
            # Try different ways to extract URLs based on common API response patterns
            results_to_process = []
            
            if isinstance(results, dict):
                # Check for common result container keys
                for key in ['results', 'data', 'items', 'search_results', 'web_results']:
                    if key in results:
                        results_to_process = results[key]
                        break
                else:
                    # If no container key found, maybe the dict itself is a result
                    if any(k in results for k in ['url', 'link', 'href', 'title']):
                        results_to_process = [results]
            elif isinstance(results, list):
                results_to_process = results
            
            # Extract URLs from results
            for item in results_to_process:
                if isinstance(item, dict):
                    # Try different possible URL keys
                    url = item.get('url') or item.get('link') or item.get('href') or item.get('website')
                    if url:
                        sources.append(url)
        
        # Determine verdict
        verdict = "Real ✅" if sources else "Fake ❌"
        return {
            "sentence": sentence, 
            "verdict": verdict, 
            "sources": sources,
            "source_count": len(sources)
        }
    
    except Exception as e:
        return {
            "sentence": sentence, 
            "verdict": "Error ⚠️", 
            "error": str(e),
            "sources": []
        }

# 🔹 Alternative search method using different search parameters
def verify_with_different_method(sentence: str):
    """
    Alternative verification method with different search approach.
    """
    try:
        # Try a more specific search
        search_query = f'"{sentence[:100]}"'  # Use quotes for exact phrase search
        results = client.search(search_query, max_results=3)
        
        sources = extract_sources_safely(results)
        
        if not sources:
            # Try searching for key terms from the sentence
            key_terms = extract_key_terms(sentence)
            if key_terms:
                results = client.search(key_terms, max_results=5)
                sources = extract_sources_safely(results)
        
        verdict = "Real ✅" if sources else "Fake ❌"
        return {
            "sentence": sentence,
            "verdict": verdict,
            "sources": sources,
            "method": "alternative"
        }
    
    except Exception as e:
        return {
            "sentence": sentence,
            "verdict": "Error ⚠️",
            "error": str(e),
            "method": "alternative"
        }

def extract_sources_safely(results):
    """
    Safely extract sources from search results.
    """
    sources = []
    if not results:
        return sources
    
    try:
        # Handle string response
        if isinstance(results, str):
            return sources
        
        # Handle dict response
        if isinstance(results, dict):
            for key in ['results', 'data', 'items', 'search_results']:
                if key in results and isinstance(results[key], list):
                    results = results[key]
                    break
            else:
                # If it's a single result dict
                if 'url' in results:
                    return [results['url']]
                return sources
        
        # Handle list response
        if isinstance(results, list):
            for item in results:
                if isinstance(item, dict):
                    url = item.get('url') or item.get('link') or item.get('href')
                    if url:
                        sources.append(url)
    
    except Exception:
        pass
    
    return sources

def extract_key_terms(sentence: str):
    """
    Extract key terms from a sentence for searching.
    """
    import re
    # Remove common words and extract meaningful terms
    common_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were'}
    words = re.findall(r'\b\w+\b', sentence.lower())
    key_terms = [word for word in words if len(word) > 3 and word not in common_words]
    return ' '.join(key_terms[:5])  # Use top 5 key terms

# 🔹 Main workflow
if __name__ == "__main__":
    # Example article URL
    url = "https://www.financialexpress.com/life/technology-apple-iphone-17-iphone-17-pro-iphone-17-pro-max-iphone-air-these-countries-will-get-esim-only-models-3976482/"
    
    print("🔍 Starting article verification process...\n")
    
    # Step 1: Extract article content
    print("📄 Extracting article content...")
    article = extract_article_content(url)
    article_text = article.get("content", "")
    
    if not article_text:
        print("❌ Could not extract article content.")
        exit(1)
    
    print(f"✅ Article extracted ({len(article_text)} characters)\n")
    
    # Step 2: Extract 5 key points
    print("🔑 Extracting key points...")
    five_points_list = get_five_points(article_text)
    print(f"✅ Extracted {len(five_points_list)} key points\n")
    
    # Step 3: Verify each point online
    print("🌐 Verifying points online...\n")
    
    # Track verification results
    verification_results = []
    real_count = 0
    total_points = len(five_points_list)
    
    for i, point in enumerate(five_points_list, 1):
        print(f"Point {i}: {point[:80]}{'...' if len(point) > 80 else ''}")
        
        # Try primary method
        result = verify_long_sentence(point)
        
        # If primary method fails, try alternative
        if result['verdict'] == "Error ⚠️":
            print(f"   Primary method failed, trying alternative...")
            result = verify_with_different_method(point)
        
        # Count real results
        if result['verdict'] == "Real ✅":
            real_count += 1
        
        verification_results.append(result)
        
        print(f"   Verdict: {result['verdict']}")
        if result.get('sources'):
            print(f"   Sources found: {len(result['sources'])}")
            for source in result['sources'][:3]:  # Show first 3 sources
                print(f"     - {source}")
        if result.get('error'):
            print(f"   Error: {result['error']}")
        print()
    
    # 🔹 Display final authenticity score
    print("=" * 60)
    print("📊 AUTHENTICITY SCORE")
    print("=" * 60)
    print(f"✅ Verified as Real: {real_count}/{total_points} points")
    print(f"🎯 Authenticity Score: {real_count}/{total_points} ({real_count/total_points*100:.1f}%)")
    
    # Add interpretation comment
    if real_count == total_points:
        print("💯 Comment: Highly authentic - All key points verified online")
    elif real_count >= total_points * 0.8:
        print("✨ Comment: Very authentic - Most key points verified online")
    elif real_count >= total_points * 0.6:
        print("👍 Comment: Moderately authentic - Majority of points verified")
    elif real_count >= total_points * 0.4:
        print("⚠️  Comment: Partially authentic - Some points verified")
    elif real_count > 0:
        print("🔍 Comment: Low authenticity - Few points verified online")
    else:
        print("❌ Comment: Cannot verify authenticity - No points found online")
    
    print("=" * 60)