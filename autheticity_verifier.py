# enhanced_authenticity_verifier.py
import os
from dotenv import load_dotenv
from content_extractor import extract_article_content
from summary import get_five_points
from tavily import TavilyClient
from openai import OpenAI
import requests
import json
from datetime import datetime
import re

# 🔹 Load environment variables
load_dotenv()
TAVILY_KEY = os.getenv("TAVILY_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# 🔹 Initialize clients
tavily_client = TavilyClient(TAVILY_KEY)
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# 🔹 Authoritative news sources for cross-verification
AUTHORITATIVE_SOURCES = {
    'international': [
        'reuters.com', 'bbc.com', 'apnews.com', 'cnn.com', 'nytimes.com',
        'washingtonpost.com', 'theguardian.com', 'aljazeera.com', 'npr.org'
    ],
    'regional_south_asia': [
        'timesofindia.com', 'hindustantimes.com', 'indianexpress.com',
        'thenews.com.pk', 'geo.tv', 'express.pk', 'tribune.com.pk',
        'dailystar.net', 'dhakatribune.com'
    ],
    'fact_checkers': [
        'snopes.com', 'factcheck.org', 'politifact.com', 'reuters.com/fact-check',
        'apnews.com/hub/ap-fact-check', 'afp.com/en/news/826'
    ]
}

class EnhancedAuthenticityVerifier:
    def __init__(self):
        self.verification_results = []
        self.gpt_analysis = None
        
    def extract_key_claims(self, article_text, article_title):
        """
        Use GPT-4 to extract specific, verifiable claims from the article
        """
        prompt = f"""
        Analyze this news article and extract 5-7 specific, factual claims that can be independently verified.
        Focus on:
        1. Specific events with dates, locations, and numbers
        2. Official statements or quotes from named individuals
        3. Concrete actions taken by governments or organizations
        4. Casualty figures, damage assessments, or other quantifiable data
        5. Military actions, diplomatic moves, or policy changes
        
        Article Title: {article_title}
        Article Content: {article_text[:4000]}...
        
        Return ONLY a JSON array of claims, like this:
        ["Claim 1 with specific details", "Claim 2 with specific details", ...]
        
        Each claim should be a complete sentence with specific details that can be fact-checked.
        """
        
        try:
            response = openai_client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=1000
            )
            
            claims_text = response.choices[0].message.content.strip()
            # Extract JSON array from the response
            claims_json = re.search(r'\[.*\]', claims_text, re.DOTALL)
            if claims_json:
                claims = json.loads(claims_json.group())
                return claims
            else:
                # Fallback to original method if GPT response isn't JSON
                return get_five_points(article_text, article_title)
                
        except Exception as e:
            print(f"⚠️ GPT claim extraction failed: {e}")
            return get_five_points(article_text, article_title)
    
    def search_authoritative_sources(self, claim, max_results=10):
        """
        Search specifically in authoritative news sources
        """
        authoritative_sources = []
        all_sources = []
        
        try:
            # First, do a general search
            results = tavily_client.search(claim, max_results=max_results)
            
            if results:
                results_list = self._extract_results_list(results)
                
                for result in results_list:
                    url = result.get('url', '')
                    if url:
                        all_sources.append(url)
                        
                        # Check if source is authoritative
                        domain = self._extract_domain(url)
                        if self._is_authoritative_source(domain):
                            authoritative_sources.append({
                                'url': url,
                                'title': result.get('title', ''),
                                'snippet': result.get('content', result.get('snippet', ''))[:200],
                                'domain': domain
                            })
            
            return {
                'authoritative_sources': authoritative_sources,
                'all_sources': all_sources,
                'authoritative_count': len(authoritative_sources),
                'total_count': len(all_sources)
            }
            
        except Exception as e:
            return {
                'error': str(e),
                'authoritative_sources': [],
                'all_sources': [],
                'authoritative_count': 0,
                'total_count': 0
            }
    
    def gpt_fact_check(self, claim, search_results):
        """
        Use GPT-4 to analyze the claim against search results
        """
        authoritative_sources = search_results.get('authoritative_sources', [])
        
        if not authoritative_sources:
            source_context = "No authoritative sources found for this claim."
        else:
            source_context = "Authoritative sources found:\n"
            for i, source in enumerate(authoritative_sources[:3], 1):
                source_context += f"{i}. {source['domain']}: {source['snippet']}\n"
        
        prompt = f"""
        As a fact-checker, analyze this claim against the available evidence:

        CLAIM TO VERIFY: {claim}

        EVIDENCE FROM AUTHORITATIVE SOURCES:
        {source_context}

        Please provide:
        1. VERDICT: One of [VERIFIED, UNVERIFIED, CONTRADICTED, INSUFFICIENT_EVIDENCE]
        2. CONFIDENCE: Scale of 1-10 (10 = very confident)
        3. REASONING: Brief explanation of your analysis
        4. RED_FLAGS: Any suspicious elements in the claim

        Consider:
        - Are the specific details (dates, numbers, names) corroborated?
        - Do authoritative sources report this event?
        - Are there any logical inconsistencies?
        - Does this seem plausible given the context?

        Respond in JSON format:
        {{
            "verdict": "VERIFIED|UNVERIFIED|CONTRADICTED|INSUFFICIENT_EVIDENCE",
            "confidence": 1-10,
            "reasoning": "Your analysis here",
            "red_flags": ["flag1", "flag2"]
        }}
        """
        
        try:
            response = openai_client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=500
            )
            
            analysis_text = response.choices[0].message.content.strip()
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', analysis_text, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group())
                return analysis
            else:
                return {
                    "verdict": "INSUFFICIENT_EVIDENCE",
                    "confidence": 1,
                    "reasoning": "Could not parse GPT analysis",
                    "red_flags": ["analysis_parsing_failed"]
                }
                
        except Exception as e:
            return {
                "verdict": "INSUFFICIENT_EVIDENCE",
                "confidence": 1,
                "reasoning": f"GPT analysis failed: {str(e)}",
                "red_flags": ["gpt_analysis_failed"]
            }
    
    def verify_claim(self, claim):
        """
        Comprehensive verification of a single claim
        """
        print(f"🔍 Analyzing: {claim[:80]}{'...' if len(claim) > 80 else ''}")
        
        # Search for evidence
        search_results = self.search_authoritative_sources(claim)
        
        # GPT fact-check
        gpt_analysis = self.gpt_fact_check(claim, search_results)
        
        # Determine final verdict
        final_verdict = self._determine_final_verdict(gpt_analysis, search_results)
        
        result = {
            'claim': claim,
            'search_results': search_results,
            'gpt_analysis': gpt_analysis,
            'final_verdict': final_verdict,
            'timestamp': datetime.now().isoformat()
        }
        
        self._print_claim_result(result)
        return result
    
    def _determine_final_verdict(self, gpt_analysis, search_results):
        """
        Combine GPT analysis and search results for final verdict
        """
        gpt_verdict = gpt_analysis.get('verdict', 'INSUFFICIENT_EVIDENCE')
        confidence = gpt_analysis.get('confidence', 0)
        authoritative_count = search_results.get('authoritative_count', 0)
        
        # Strict verification criteria
        if gpt_verdict == 'VERIFIED' and confidence >= 7 and authoritative_count >= 2:
            return 'AUTHENTIC'
        elif gpt_verdict == 'CONTRADICTED' or (confidence >= 7 and authoritative_count == 0):
            return 'FAKE'
        elif gpt_verdict == 'UNVERIFIED' and authoritative_count == 0:
            return 'UNVERIFIABLE'
        else:
            return 'SUSPICIOUS'
    
    def _print_claim_result(self, result):
        """
        Print formatted result for a single claim
        """
        verdict_icons = {
            'AUTHENTIC': '✅',
            'FAKE': '❌',
            'SUSPICIOUS': '⚠️',
            'UNVERIFIABLE': '❓'
        }
        
        verdict = result['final_verdict']
        icon = verdict_icons.get(verdict, '❓')
        
        print(f"   {icon} Verdict: {verdict}")
        print(f"   🤖 GPT Analysis: {result['gpt_analysis']['verdict']} (confidence: {result['gpt_analysis']['confidence']}/10)")
        print(f"   📰 Authoritative sources: {result['search_results']['authoritative_count']}")
        print(f"   💭 Reasoning: {result['gpt_analysis']['reasoning'][:100]}...")
        
        if result['gpt_analysis']['red_flags']:
            print(f"   🚩 Red flags: {', '.join(result['gpt_analysis']['red_flags'])}")
        
        if result['search_results']['authoritative_sources']:
            print(f"   📑 Sources: {', '.join([s['domain'] for s in result['search_results']['authoritative_sources'][:3]])}")
        
        print()
    
    def verify_article(self, url):
        """
        Main method to verify an entire article
        """
        print("🔍 Starting enhanced article verification...\n")
        
        # Extract article content
        print("📄 Extracting article content...")
        article = extract_article_content(url)
        article_text = article.get("content", "")
        article_title = article.get("title", "")
        
        if not article_text:
            print("❌ Could not extract article content.")
            return None
        
        print(f"✅ Article extracted: {article_title}\n")
        
        # Extract key claims using GPT
        print("🔑 Extracting verifiable claims using GPT-4...")
        claims = self.extract_key_claims(article_text, article_title)
        print(f"✅ Extracted {len(claims)} claims\n")
        
        # Verify each claim
        print("🌐 Verifying claims with authoritative sources...\n")
        
        self.verification_results = []
        for claim in claims:
            result = self.verify_claim(claim)
            self.verification_results.append(result)
        
        # Generate final report
        return self._generate_final_report(article_title)
    
    def _generate_final_report(self, article_title):
        """
        Generate comprehensive authenticity report
        """
        total_claims = len(self.verification_results)
        authentic_count = sum(1 for r in self.verification_results if r['final_verdict'] == 'AUTHENTIC')
        fake_count = sum(1 for r in self.verification_results if r['final_verdict'] == 'FAKE')
        suspicious_count = sum(1 for r in self.verification_results if r['final_verdict'] == 'SUSPICIOUS')
        unverifiable_count = sum(1 for r in self.verification_results if r['final_verdict'] == 'UNVERIFIABLE')
        
        print("=" * 80)
        print("📊 ENHANCED AUTHENTICITY REPORT")
        print("=" * 80)
        print(f"📰 Article: {article_title[:60]}...")
        print(f"📅 Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        print("📈 CLAIM VERIFICATION BREAKDOWN:")
        print(f"   ✅ Authentic: {authentic_count}/{total_claims}")
        print(f"   ❌ Fake/Contradicted: {fake_count}/{total_claims}")
        print(f"   ⚠️  Suspicious: {suspicious_count}/{total_claims}")
        print(f"   ❓ Unverifiable: {unverifiable_count}/{total_claims}")
        print()
        
        # Overall authenticity determination
        authenticity_score = (authentic_count / total_claims) * 100 if total_claims > 0 else 0
        
        if fake_count > 0 or suspicious_count >= total_claims * 0.5:
            overall_verdict = "❌ LIKELY FAKE/UNRELIABLE"
        elif authentic_count >= total_claims * 0.7:
            overall_verdict = "✅ LIKELY AUTHENTIC"
        elif unverifiable_count >= total_claims * 0.7:
            overall_verdict = "❓ UNVERIFIABLE"
        else:
            overall_verdict = "⚠️ MIXED/SUSPICIOUS"
        
        print(f"🎯 OVERALL VERDICT: {overall_verdict}")
        print(f"📊 Authenticity Score: {authenticity_score:.1f}%")
        print()
        
        # Provide reasoning
        if fake_count > 0:
            print("⚠️  WARNING: Some claims were contradicted by authoritative sources")
        if suspicious_count > authentic_count:
            print("⚠️  WARNING: More suspicious claims than verified ones")
        if unverifiable_count == total_claims:
            print("⚠️  WARNING: No claims could be verified with authoritative sources")
        
        print("=" * 80)
        
        return {
            'overall_verdict': overall_verdict,
            'authenticity_score': authenticity_score,
            'breakdown': {
                'authentic': authentic_count,
                'fake': fake_count,
                'suspicious': suspicious_count,
                'unverifiable': unverifiable_count,
                'total': total_claims
            },
            'detailed_results': self.verification_results
        }
    
    # Helper methods
    def _extract_results_list(self, results):
        """Extract results list from API response"""
        if isinstance(results, list):
            return results
        elif isinstance(results, dict):
            for key in ['results', 'data', 'items', 'search_results']:
                if key in results and isinstance(results[key], list):
                    return results[key]
        return []
    
    def _extract_domain(self, url):
        """Extract domain from URL"""
        try:
            from urllib.parse import urlparse
            return urlparse(url).netloc.lower().replace('www.', '')
        except:
            return url
    
    def _is_authoritative_source(self, domain):
        """Check if domain is from an authoritative source"""
        all_authoritative = []
        for source_list in AUTHORITATIVE_SOURCES.values():
            all_authoritative.extend(source_list)
        
        return any(auth_domain in domain for auth_domain in all_authoritative)


# 🔹 Main execution
if __name__ == "__main__":
    verifier = EnhancedAuthenticityVerifier()
    
    # Test with the Dawn article
    url = "https://www.dawn.com/news/1908824"
    
    try:
        report = verifier.verify_article(url)
        
        if report:
            print("\n🎉 Verification complete! Check the report above for details.")
        else:
            print("❌ Verification failed.")
            
    except Exception as e:
        print(f"❌ Error during verification: {e}")