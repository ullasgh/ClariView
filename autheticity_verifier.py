import requests
from typing import Dict, Any
from dotenv import load_dotenv
import os
import summary
from summary import get_five_points
import content_extractor
from content_extractor import extract_article_content

article = extract_article_content("https://www.financialexpress.com/life/technology-apple-iphone-17-iphone-17-pro-iphone-17-pro-max-iphone-air-these-countries-will-get-esim-only-models-3976482/")

load_dotenv()  # take environment variables from .env.
news_api_key = os.getenv("NEWS_API")


# Replace with your own API key from https://newsapi.org
NEWSAPI_KEY = news_api_key
NEWSAPI_URL = "https://newsapi.org/v2/everything"

def verify_authenticity(headline: str, max_results: int = 10) -> Dict[str, Any]:
    """
    Verifies authenticity of a news headline using NewsAPI.
    Returns score, sources, and verdict (Real/Fake).
    """
    try:
        params = {
            "q": headline,
            "language": "en",
            "pageSize": max_results,
            "sortBy": "relevancy",
            "apiKey": NEWSAPI_KEY,
        }


        response = requests.get(NEWSAPI_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get("status") != "ok":
            return {"error": data}

        # Extract unique sources
        sources = list({article["source"]["name"] for article in data.get("articles", [])})
        num_sources = len(sources)

        # Simple authenticity scoring
        authenticity_score = num_sources / max_results  # crude scoring
        verdict = "Real ✅" if authenticity_score >= 0.5 else "Fake ❌"

        return {
            "headline": headline,
            "sources_found": sources,
            "authenticity_score": round(authenticity_score, 2),
            "verdict": verdict,
        }

    except Exception as e:
        return {"error": str(e)}


# 🔹 Example usage
if __name__ == "__main__":
    test_headline = "Apple launches iPhone 17 with USB-C support"
    result = verify_authenticity(test_headline)
    print(result)
    sample_article = article.get("content")
    five_points_list = get_five_points(sample_article)
    for point in five_points_list:
        result = verify_authenticity(test_headline)
        print(result)