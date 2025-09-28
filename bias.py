import requests
import json
from typing import List, Dict, Any
from dataclasses import dataclass
from enum import Enum
import re
from urllib.parse import urlparse

class Sentiment(Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"

@dataclass
class ArticleAnalysis:
    url: str
    title: str
    content: str
    tone: Sentiment
    key_points: List[str]
    outcome_sentiment: Sentiment
    credibility_score: float

@dataclass
class ComparisonResult:
    original_article: ArticleAnalysis
    alternative_articles: List[ArticleAnalysis]
    bias_detected: bool
    bias_score: float
    conflicting_points: List[str]
    recommended_sources: List[str]

class ClariView:
    def __init__(self, tavily_api_key: str, mistral_api_key: str):
        self.tavily_api_key = tavily_api_key
        self.mistral_api_key = mistral_api_key
        self.mistral_endpoint = "https://api.mistral.ai/v1/chat/completions"
        self.tavily_endpoint = "https://api.tavily.com/search"
    
    def extract_article_content(self, url: str) -> str:
        """Extract article content from URL"""
        try:
            # You might want to use newspaper3k, beautifulsoup, or similar
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            # Basic content extraction (you'd want more sophisticated extraction)
            # Consider using libraries like newspaper3k, readability, or trafilatura
            content = self._clean_html(response.text)
            return content[:5000]  # Limit content length for API
            
        except Exception as e:
            print(f"Error extracting content from {url}: {e}")
            return ""
    
    def _clean_html(self, html_content: str) -> str:
        """Basic HTML cleaning - replace with proper extraction library"""
        import re
        # Remove HTML tags
        clean = re.sub('<.*?>', '', html_content)
        # Remove extra whitespace
        clean = re.sub('\s+', ' ', clean).strip()
        return clean
    
    def search_alternative_sources(self, article_content: str, original_url: str) -> List[str]:
        """Use Tavily to find alternative sources on the same topic"""
        
        # Extract key terms from the original article
        key_terms = self._extract_key_terms(article_content)
        search_query = " ".join(key_terms[:5])  # Use top 5 key terms
        
        payload = {
            "api_key": self.tavily_api_key,
            "query": search_query,
            "search_depth": "advanced",
            "include_domains": [],
            "exclude_domains": [urlparse(original_url).netloc],  # Exclude original domain
            "max_results": 5
        }
        
        try:
            response = requests.post(self.tavily_endpoint, json=payload)
            response.raise_for_status()
            results = response.json()
            
            return [result["url"] for result in results.get("results", [])]
            
        except Exception as e:
            print(f"Error searching with Tavily: {e}")
            return []
    
    def _extract_key_terms(self, content: str) -> List[str]:
        """Extract key terms from content for search"""
        # Simple implementation - you might want to use NLP libraries
        # like spacy, nltk, or transformers for better key term extraction
        words = re.findall(r'\b[A-Z][a-zA-Z]+\b', content)  # Capitalized words
        common_words = ['The', 'This', 'That', 'When', 'Where', 'Who', 'What', 'How']
        key_terms = [word for word in words if word not in common_words]
        return list(set(key_terms))[:10]
    
    def analyze_article_with_mistral(self, content: str, url: str) -> ArticleAnalysis:
        """Analyze article using Mistral-7B"""
        
        prompt = f"""
        Analyze the following article and provide a structured analysis:
        
        Article URL: {url}
        Article Content: {content[:3000]}
        
        Please analyze and respond with:
        1. Overall tone (positive/negative/neutral)
        2. Key points (list 3-5 main points)
        3. Outcome sentiment (positive/negative/neutral regarding the main topic)
        4. Credibility indicators (score 0-1)
        
        Format your response as JSON:
        {{
            "tone": "positive/negative/neutral",
            "key_points": ["point1", "point2", "point3"],
            "outcome_sentiment": "positive/negative/neutral",
            "credibility_score": 0.8,
            "title": "extracted title"
        }}
        """
        
        payload = {
            "model": "mistral-7b-instruct-v0.2",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1000,
            "temperature": 0.1
        }
        
        headers = {
            "Authorization": f"Bearer {self.mistral_api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.post(self.mistral_endpoint, json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()
            
            # Parse the response
            analysis_text = result["choices"][0]["message"]["content"]
            analysis_data = self._parse_mistral_response(analysis_text)
            
            return ArticleAnalysis(
                url=url,
                title=analysis_data.get("title", "Unknown"),
                content=content,
                tone=Sentiment(analysis_data.get("tone", "neutral")),
                key_points=analysis_data.get("key_points", []),
                outcome_sentiment=Sentiment(analysis_data.get("outcome_sentiment", "neutral")),
                credibility_score=analysis_data.get("credibility_score", 0.5)
            )
            
        except Exception as e:
            print(f"Error analyzing with Mistral: {e}")
            return ArticleAnalysis(
                url=url, title="Error", content=content,
                tone=Sentiment.NEUTRAL, key_points=[],
                outcome_sentiment=Sentiment.NEUTRAL, credibility_score=0.0
            )
    
    def _parse_mistral_response(self, response_text: str) -> Dict[str, Any]:
        """Parse Mistral's JSON response"""
        try:
            # Extract JSON from the response
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
        
        # Fallback parsing if JSON fails
        return {
            "tone": "neutral",
            "key_points": [],
            "outcome_sentiment": "neutral",
            "credibility_score": 0.5,
            "title": "Unknown"
        }
    
    def compare_articles(self, original: ArticleAnalysis, alternatives: List[ArticleAnalysis]) -> ComparisonResult:
        """Compare original article with alternatives to detect bias"""
        
        bias_indicators = []
        conflicting_points = []
        
        # Check tone differences
        original_tone = original.tone
        alt_tones = [alt.tone for alt in alternatives]
        
        if original_tone == Sentiment.POSITIVE and all(t == Sentiment.NEGATIVE for t in alt_tones):
            bias_indicators.append("Tone bias: Original positive, alternatives negative")
        elif original_tone == Sentiment.NEGATIVE and all(t == Sentiment.POSITIVE for t in alt_tones):
            bias_indicators.append("Tone bias: Original negative, alternatives positive")
        
        # Check outcome sentiment differences
        original_outcome = original.outcome_sentiment
        alt_outcomes = [alt.outcome_sentiment for alt in alternatives]
        
        if original_outcome != Sentiment.NEUTRAL:
            opposite_outcomes = [o for o in alt_outcomes if o != original_outcome and o != Sentiment.NEUTRAL]
            if len(opposite_outcomes) >= len(alt_outcomes) * 0.6:  # 60% threshold
                conflicting_points.append("Conflicting outcome assessments")
        
        # Check credibility scores
        avg_alt_credibility = sum(alt.credibility_score for alt in alternatives) / len(alternatives) if alternatives else 0
        if original.credibility_score < avg_alt_credibility - 0.3:
            bias_indicators.append("Lower credibility compared to alternative sources")
        
        # Calculate bias score
        bias_score = len(bias_indicators) / 5.0  # Normalize to 0-1
        bias_detected = bias_score > 0.3 or len(conflicting_points) > 0
        
        # Get high-credibility source recommendations
        recommended_sources = [
            alt.url for alt in alternatives 
            if alt.credibility_score > 0.7
        ][:3]
        
        return ComparisonResult(
            original_article=original,
            alternative_articles=alternatives,
            bias_detected=bias_detected,
            bias_score=bias_score,
            conflicting_points=conflicting_points + bias_indicators,
            recommended_sources=recommended_sources
        )
    
    def analyze_article_url(self, article_url: str) -> ComparisonResult:
        """Main method to analyze an article URL"""
        print(f"Analyzing article: {article_url}")
        
        # Step 1: Extract content from original article
        original_content = self.extract_article_content(article_url)
        if not original_content:
            raise ValueError("Could not extract content from the provided URL")
        
        # Step 2: Analyze original article
        print("Analyzing original article...")
        original_analysis = self.analyze_article_with_mistral(original_content, article_url)
        
        # Step 3: Search for alternative sources
        print("Searching for alternative sources...")
        alt_urls = self.search_alternative_sources(original_content, article_url)
        
        # Step 4: Analyze alternative articles
        print(f"Analyzing {len(alt_urls)} alternative sources...")
        alternative_analyses = []
        for alt_url in alt_urls:
            alt_content = self.extract_article_content(alt_url)
            if alt_content:
                alt_analysis = self.analyze_article_with_mistral(alt_content, alt_url)
                alternative_analyses.append(alt_analysis)
        
        # Step 5: Compare and detect bias
        print("Comparing articles for bias detection...")
        comparison_result = self.compare_articles(original_analysis, alternative_analyses)
        
        return comparison_result

    def generate_report(self, comparison_result: ComparisonResult) -> Dict[str, Any]:
        """Generate a comprehensive report of the analysis"""
        
        report = {
            "original_article": {
                "url": comparison_result.original_article.url,
                "title": comparison_result.original_article.title,
                "tone": comparison_result.original_article.tone.value,
                "outcome_sentiment": comparison_result.original_article.outcome_sentiment.value,
                "credibility_score": comparison_result.original_article.credibility_score,
                "key_points": comparison_result.original_article.key_points
            },
            "alternative_articles": [
                {
                    "url": alt.url,
                    "title": alt.title,
                    "tone": alt.tone.value,
                    "outcome_sentiment": alt.outcome_sentiment.value,
                    "credibility_score": alt.credibility_score,
                    "key_points": alt.key_points
                }
                for alt in comparison_result.alternative_articles
            ],
            "bias_analysis": {
                "bias_detected": comparison_result.bias_detected,
                "bias_score": comparison_result.bias_score,
                "conflicting_points": comparison_result.conflicting_points,
                "risk_level": self._get_risk_level(comparison_result.bias_score),
                "recommendation": self._get_recommendation(comparison_result)
            },
            "recommended_sources": comparison_result.recommended_sources,
            "summary": self._generate_summary(comparison_result)
        }
        
        return report
    
    def _get_risk_level(self, bias_score: float) -> str:
        """Determine risk level based on bias score"""
        if bias_score >= 0.7:
            return "HIGH"
        elif bias_score >= 0.4:
            return "MEDIUM" 
        elif bias_score >= 0.2:
            return "LOW"
        else:
            return "MINIMAL"
    
    def _get_recommendation(self, comparison_result: ComparisonResult) -> str:
        """Generate recommendation based on analysis"""
        if not comparison_result.bias_detected:
            return "The article appears to be balanced and consistent with alternative sources."
        
        risk_level = self._get_risk_level(comparison_result.bias_score)
        
        recommendations = {
            "HIGH": "⚠️ HIGH RISK: This article shows significant bias. Strong recommendation to check multiple alternative sources before forming opinions.",
            "MEDIUM": "⚡ MEDIUM RISK: This article may contain bias. We recommend reviewing alternative perspectives.",
            "LOW": "ℹ️ LOW RISK: Minor inconsistencies detected. Consider checking one or two alternative sources.",
            "MINIMAL": "✅ MINIMAL RISK: Article appears relatively balanced."
        }
        
        return recommendations.get(risk_level, "Review recommended.")
    
    def _generate_summary(self, comparison_result: ComparisonResult) -> str:
        """Generate a summary of the analysis"""
        original = comparison_result.original_article
        alternatives = comparison_result.alternative_articles
        
        summary_parts = []
        
        # Basic info
        summary_parts.append(f"Analyzed 1 original article against {len(alternatives)} alternative sources.")
        
        # Tone analysis
        if alternatives:
            alt_tones = [alt.tone for alt in alternatives]
            if original.tone != Sentiment.NEUTRAL:
                same_tone_count = sum(1 for tone in alt_tones if tone == original.tone)
                percentage = (same_tone_count / len(alt_tones)) * 100
                summary_parts.append(f"Tone consistency: {percentage:.0f}% of alternative sources share the same tone.")
        
        # Credibility
        if alternatives:
            avg_credibility = sum(alt.credibility_score for alt in alternatives) / len(alternatives)
            credibility_diff = original.credibility_score - avg_credibility
            if abs(credibility_diff) > 0.2:
                direction = "higher" if credibility_diff > 0 else "lower"
                summary_parts.append(f"Original article has {direction} credibility than alternatives.")
        
        return " ".join(summary_parts)
    
    def save_analysis(self, comparison_result: ComparisonResult, filename: str = None):
        """Save analysis results to a JSON file"""
        if filename is None:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"clariview_analysis_{timestamp}.json"
        
        report = self.generate_report(comparison_result)
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            print(f"Analysis saved to {filename}")
        except Exception as e:
            print(f"Error saving analysis: {e}")

class ClariViewAPI:
    """API wrapper for ClariView for web service integration"""
    
    def __init__(self, tavily_api_key: str, mistral_api_key: str):
        self.clariview = ClariView(tavily_api_key, mistral_api_key)
    
    def analyze_url(self, url: str, save_results: bool = False) -> Dict[str, Any]:
        """API endpoint for analyzing a URL"""
        try:
            # Validate URL
            if not self._is_valid_url(url):
                return {"error": "Invalid URL provided", "status": "error"}
            
            # Perform analysis
            result = self.clariview.analyze_article_url(url)
            
            # Generate report
            report = self.clariview.generate_report(result)
            
            # Save if requested
            if save_results:
                self.clariview.save_analysis(result)
            
            report["status"] = "success"
            return report
            
        except Exception as e:
            return {"error": str(e), "status": "error"}
    
    def _is_valid_url(self, url: str) -> bool:
        """Validate URL format"""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except:
            return False

# Usage examples and testing
def main():
    """Main function with comprehensive examples"""
    
    # Configuration
    TAVILY_API_KEY = "your_tavily_api_key"
    MISTRAL_API_KEY = "your_mistral_api_key"
    
    # Initialize ClariView
    clariview = ClariView(
        tavily_api_key=TAVILY_API_KEY,
        mistral_api_key=MISTRAL_API_KEY
    )
    
    # Example URLs to test (replace with actual URLs)
    test_urls = [
        "https://example.com/news-article-1",
        "https://example.com/news-article-2",
        "https://example.com/blog-post"
    ]
    
    print("🔍 ClariView - Article Bias Detection System")
    print("=" * 50)
    
    for i, article_url in enumerate(test_urls, 1):
        print(f"\n📰 Analyzing Article {i}: {article_url}")
        print("-" * 40)
        
        try:
            # Perform analysis
            result = clariview.analyze_article_url(article_url)
            
            # Display results
            display_results(result)
            
            # Save results
            clariview.save_analysis(result, f"analysis_{i}.json")
            
        except Exception as e:
            print(f"❌ Error analyzing {article_url}: {e}")
            continue
    
    print("\n✅ Analysis complete!")

def display_results(comparison_result: ComparisonResult):
    """Display analysis results in a formatted way"""
    
    original = comparison_result.original_article
    alternatives = comparison_result.alternative_articles
    
    # Original article info
    print(f"📄 Original Article: {original.title}")
    print(f"   URL: {original.url}")
    print(f"   Tone: {original.tone.value.upper()}")
    print(f"   Outcome: {original.outcome_sentiment.value.upper()}")
    print(f"   Credibility: {original.credibility_score:.2f}/1.0")
    
    # Key points
    if original.key_points:
        print(f"   Key Points:")
        for point in original.key_points[:3]:
            print(f"     • {point}")
    
    # Alternative sources summary
    print(f"\n🔍 Alternative Sources Found: {len(alternatives)}")
    if alternatives:
        avg_credibility = sum(alt.credibility_score for alt in alternatives) / len(alternatives)
        print(f"   Average Credibility: {avg_credibility:.2f}/1.0")
        
        tone_distribution = {}
        for alt in alternatives:
            tone_distribution[alt.tone.value] = tone_distribution.get(alt.tone.value, 0) + 1
        
        print(f"   Tone Distribution: {dict(tone_distribution)}")
    
    # Bias detection results
    print(f"\n🎯 Bias Analysis:")
    print(f"   Bias Detected: {'🔴 YES' if comparison_result.bias_detected else '🟢 NO'}")
    print(f"   Bias Score: {comparison_result.bias_score:.2f}/1.0")
    
    risk_level = get_risk_level_emoji(comparison_result.bias_score)
    print(f"   Risk Level: {risk_level}")
    
    # Conflicting points
    if comparison_result.conflicting_points:
        print(f"\n⚠️  Conflicting Points:")
        for point in comparison_result.conflicting_points:
            print(f"     • {point}")
    
    # Recommendations
    if comparison_result.recommended_sources:
        print(f"\n📚 Recommended Sources:")
        for i, source in enumerate(comparison_result.recommended_sources[:3], 1):
            print(f"     {i}. {source}")

def get_risk_level_emoji(bias_score: float) -> str:
    """Get emoji representation of risk level"""
    if bias_score >= 0.7:
        return "🔴 HIGH RISK"
    elif bias_score >= 0.4:
        return "🟡 MEDIUM RISK"
    elif bias_score >= 0.2:
        return "🟠 LOW RISK"
    else:
        return "🟢 MINIMAL RISK"

# API usage example
def api_example():
    """Example of using the API wrapper"""
    
    api = ClariViewAPI(
        tavily_api_key="your_tavily_api_key",
        mistral_api_key="your_mistral_api_key"
    )
    
    # Analyze a URL via API
    result = api.analyze_url("https://example.com/article", save_results=True)
    
    if result["status"] == "success":
        print("✅ Analysis successful!")
        print(f"Bias detected: {result['bias_analysis']['bias_detected']}")
        print(f"Risk level: {result['bias_analysis']['risk_level']}")
    else:
        print(f"❌ Analysis failed: {result['error']}")

if __name__ == "__main__":
    main()
    
    # Uncomment to test API
    # api_example()
