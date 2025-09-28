import asyncio
from typing import TypedDict, Literal
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from typing_extensions import Annotated
import json
import re
from datetime import datetime

# Import your existing modules
from content_extractor import extract_article_content
from summary import get_five_points
from tavily import TavilyClient
from openai import OpenAI
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

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

class WorkflowState(TypedDict):
    """State object that carries data between nodes"""
    url: str
    article_data: dict  # Contains title, content, etc.
    key_claims: list  # Enhanced GPT-extracted claims
    authenticity_score: float
    authenticity_details: dict
    bias_analysis: dict
    final_result: dict
    error: str

def extract_content_node(state: WorkflowState) -> WorkflowState:
    """
    Node 0: Extract content from the provided URL
    """
    try:
        print(f"🔍 Extracting content from: {state['url']}")
        
        # Extract article content using your existing function
        article_data = extract_article_content(state['url'])
        
        if not article_data or not article_data.get('content'):
            return {
                **state,
                "error": "Failed to extract content from URL",
                "final_result": {"status": "failed", "reason": "Content extraction failed"}
            }
        
        print(f"✅ Content extracted successfully")
        print(f"   Title: {article_data.get('title', 'No title')[:80]}...")
        print(f"   Content: {len(article_data.get('content', ''))} characters")
        
        return {
            **state,
            "article_data": article_data
        }
    
    except Exception as e:
        print(f"❌ Error in content extraction: {str(e)}")
        return {
            **state,
            "error": f"Content extraction error: {str(e)}",
            "final_result": {"status": "failed", "reason": f"Content extraction error: {str(e)}"}
        }

def extract_key_claims_node(state: WorkflowState) -> WorkflowState:
    """
    Node 1: Extract verifiable claims using GPT-4 (Enhanced version)
    """
    try:
        print("🤖 Extracting verifiable claims using GPT-4...")
        
        article_content = state['article_data'].get('content', '')
        article_title = state['article_data'].get('title', '')
        
        if not article_content:
            return {
                **state,
                "error": "No content available for claim extraction",
                "final_result": {"status": "failed", "reason": "No content for claims"}
            }
        
        # Initialize OpenAI client
        openai_key = os.getenv("OPENAI_API_KEY")
        if not openai_key:
            print("⚠️ OpenAI API key not found, falling back to basic extraction")
            key_claims = get_five_points(article_content, article_title)
        else:
            # Use GPT-4 for intelligent claim extraction
            openai_client = OpenAI(api_key=openai_key)
            
            prompt = f"""
            Analyze this news article and extract 5-7 specific, factual claims that can be independently verified.
            Focus on:
            1. Specific events with dates, locations, and numbers
            2. Official statements or quotes from named individuals
            3. Concrete actions taken by governments or organizations
            4. Casualty figures, damage assessments, or other quantifiable data
            5. Military actions, diplomatic moves, or policy changes
            
            Article Title: {article_title}
            Article Content: {article_content[:4000]}...
            
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
                    key_claims = json.loads(claims_json.group())
                else:
                    # Fallback to original method if GPT response isn't JSON
                    key_claims = get_five_points(article_content, article_title)
                    
            except Exception as gpt_error:
                print(f"⚠️ GPT claim extraction failed: {gpt_error}")
                key_claims = get_five_points(article_content, article_title)
        
        if not key_claims:
            return {
                **state,
                "error": "Failed to extract key claims",
                "final_result": {"status": "failed", "reason": "Claim extraction failed"}
            }
        
        print(f"✅ Extracted {len(key_claims)} verifiable claims")
        for i, claim in enumerate(key_claims[:3], 1):  # Show first 3
            print(f"   {i}. {claim[:80]}...")
        
        return {
            **state,
            "key_claims": key_claims
        }
    
    except Exception as e:
        print(f"❌ Error in claim extraction: {str(e)}")
        return {
            **state,
            "error": f"Claim extraction error: {str(e)}",
            "final_result": {"status": "failed", "reason": f"Claim extraction error: {str(e)}"}
        }

def enhanced_authenticity_verifier_node(state: WorkflowState) -> WorkflowState:
    """
    Node 2: Enhanced authenticity verification using GPT-4 + Authoritative sources
    """
    try:
        print("🔒 Running enhanced authenticity verification...")
        
        # Initialize clients
        tavily_key = os.getenv("TAVILY_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")
        
        if not tavily_key:
            return {
                **state,
                "error": "TAVILY_API_KEY not found in environment variables",
                "authenticity_score": 0,
                "final_result": {"status": "failed", "reason": "Missing Tavily API key"}
            }
        
        tavily_client = TavilyClient(tavily_key)
        openai_client = OpenAI(api_key=openai_key) if openai_key else None
        
        verification_results = []
        authentic_count = 0
        fake_count = 0
        suspicious_count = 0
        unverifiable_count = 0
        total_claims = len(state['key_claims'])
        
        # Verify each claim with enhanced method
        for i, claim in enumerate(state['key_claims'], 1):
            print(f"   🔍 Verifying claim {i}/{total_claims}: {claim[:60]}...")
            
            try:
                # Step 1: Search for evidence in authoritative sources
                search_results = search_authoritative_sources(claim, tavily_client)
                
                # Step 2: GPT fact-check if available
                if openai_client:
                    gpt_analysis = gpt_fact_check(claim, search_results, openai_client)
                else:
                    # Fallback analysis without GPT
                    gpt_analysis = fallback_analysis(search_results)
                
                # Step 3: Determine final verdict with strict criteria
                final_verdict = determine_final_verdict(gpt_analysis, search_results)
                
                # Count results
                if final_verdict == 'AUTHENTIC':
                    authentic_count += 1
                elif final_verdict == 'FAKE':
                    fake_count += 1
                elif final_verdict == 'SUSPICIOUS':
                    suspicious_count += 1
                else:  # UNVERIFIABLE
                    unverifiable_count += 1
                
                result = {
                    "claim": claim,
                    "verdict": final_verdict,
                    "authoritative_sources": len(search_results.get('authoritative_sources', [])),
                    "total_sources": search_results.get('total_count', 0),
                    "gpt_confidence": gpt_analysis.get('confidence', 0),
                    "reasoning": gpt_analysis.get('reasoning', ''),
                    "red_flags": gpt_analysis.get('red_flags', [])
                }
                
                verification_results.append(result)
                
                # Print result with emoji
                verdict_icons = {
                    'AUTHENTIC': '✅',
                    'FAKE': '❌',
                    'SUSPICIOUS': '⚠️',
                    'UNVERIFIABLE': '❓'
                }
                icon = verdict_icons.get(final_verdict, '❓')
                print(f"     → {icon} {final_verdict} (Auth sources: {result['authoritative_sources']}, Confidence: {result['gpt_confidence']}/10)")
                
            except Exception as claim_error:
                print(f"     → ⚠️ Error: {str(claim_error)}")
                verification_results.append({
                    "claim": claim,
                    "verdict": "ERROR",
                    "error": str(claim_error),
                    "authoritative_sources": 0,
                    "total_sources": 0
                })
                unverifiable_count += 1
        
        # Calculate enhanced authenticity score
        # Only AUTHENTIC claims count toward the score
        if total_claims > 0:
            authenticity_score = (authentic_count / total_claims) * 100
            
            # Apply penalties for fake/suspicious content
            if fake_count > 0:
                authenticity_score *= 0.5  # Heavy penalty for fake content
            elif suspicious_count > authentic_count:
                authenticity_score *= 0.7  # Moderate penalty for suspicious content
        else:
            authenticity_score = 0
        
        authenticity_details = {
            "total_claims": total_claims,
            "authentic_claims": authentic_count,
            "fake_claims": fake_count,
            "suspicious_claims": suspicious_count,
            "unverifiable_claims": unverifiable_count,
            "score_percentage": authenticity_score,
            "verification_results": verification_results,
            "analysis_timestamp": datetime.now().isoformat()
        }
        
        print(f"🎯 Enhanced Authenticity Score: {authenticity_score:.1f}%")
        print(f"   ✅ Authentic: {authentic_count}, ❌ Fake: {fake_count}, ⚠️ Suspicious: {suspicious_count}, ❓ Unverifiable: {unverifiable_count}")
        
        return {
            **state,
            "authenticity_score": authenticity_score,
            "authenticity_details": authenticity_details
        }
    
    except Exception as e:
        print(f"❌ Error in enhanced authenticity verification: {str(e)}")
        return {
            **state,
            "error": f"Enhanced authenticity verification error: {str(e)}",
            "authenticity_score": 0,
            "final_result": {"status": "failed", "reason": f"Enhanced authenticity verification error: {str(e)}"}
        }

def search_authoritative_sources(claim: str, tavily_client, max_results=10):
    """
    Search specifically in authoritative news sources
    """
    authoritative_sources = []
    all_sources = []
    
    try:
        # Perform search
        results = tavily_client.search(claim, max_results=max_results)
        
        if results:
            results_list = extract_results_list(results)
            
            for result in results_list:
                url = result.get('url', '')
                if url:
                    all_sources.append(url)
                    
                    # Check if source is authoritative
                    domain = extract_domain(url)
                    if is_authoritative_source(domain):
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

def gpt_fact_check(claim: str, search_results: dict, openai_client):
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
            return fallback_analysis(search_results)
            
    except Exception as e:
        return {
            "verdict": "INSUFFICIENT_EVIDENCE",
            "confidence": 1,
            "reasoning": f"GPT analysis failed: {str(e)}",
            "red_flags": ["gpt_analysis_failed"]
        }

def fallback_analysis(search_results):
    """
    Fallback analysis when GPT is not available
    """
    auth_count = search_results.get('authoritative_count', 0)
    total_count = search_results.get('total_count', 0)
    
    if auth_count >= 2:
        return {
            "verdict": "VERIFIED",
            "confidence": 7,
            "reasoning": f"Found in {auth_count} authoritative sources",
            "red_flags": []
        }
    elif auth_count == 1:
        return {
            "verdict": "UNVERIFIED",
            "confidence": 5,
            "reasoning": "Found in 1 authoritative source, needs more verification",
            "red_flags": ["single_source"]
        }
    elif total_count > 0:
        return {
            "verdict": "UNVERIFIED",
            "confidence": 3,
            "reasoning": f"Found in {total_count} non-authoritative sources only",
            "red_flags": ["no_authoritative_sources"]
        }
    else:
        return {
            "verdict": "INSUFFICIENT_EVIDENCE",
            "confidence": 1,
            "reasoning": "No sources found",
            "red_flags": ["no_sources_found"]
        }

def determine_final_verdict(gpt_analysis: dict, search_results: dict):
    """
    Combine GPT analysis and search results for final verdict with STRICT criteria
    """
    gpt_verdict = gpt_analysis.get('verdict', 'INSUFFICIENT_EVIDENCE')
    confidence = gpt_analysis.get('confidence', 0)
    authoritative_count = search_results.get('authoritative_count', 0)
    
    # VERY STRICT verification criteria
    if gpt_verdict == 'VERIFIED' and confidence >= 8 and authoritative_count >= 3:
        return 'AUTHENTIC'
    elif gpt_verdict == 'VERIFIED' and confidence >= 7 and authoritative_count >= 2:
        return 'AUTHENTIC'
    elif gpt_verdict == 'CONTRADICTED' or (confidence >= 7 and authoritative_count == 0):
        return 'FAKE'
    elif gpt_verdict == 'UNVERIFIED' and authoritative_count == 0:
        return 'SUSPICIOUS'  # Changed from UNVERIFIABLE to SUSPICIOUS for no auth sources
    elif gpt_verdict == 'INSUFFICIENT_EVIDENCE':
        return 'UNVERIFIABLE'
    else:
        return 'SUSPICIOUS'

def bias_analysis_node(state: WorkflowState) -> WorkflowState:
    """
    Node 3: Analyze bias by finding opposing viewpoint articles (unchanged)
    """
    try:
        print("⚖️ Running bias analysis...")
        
        # Initialize clients
        openai_key = os.getenv("OPENAI_API_KEY")
        tavily_key = os.getenv("TAVILY_API_KEY")
        
        if not openai_key or not tavily_key:
            return {
                **state,
                "error": "Missing required API keys for bias analysis",
                "final_result": {
                    "status": "failed", 
                    "reason": "Missing API keys for bias analysis"
                }
            }
        
        openai_client = OpenAI(api_key=openai_key)
        tavily_client = TavilyClient(api_key=tavily_key)
        
        # Collect all URLs from all claims
        all_opposing_urls = []
        
        # Process each claim to find opposing viewpoints
        for i, claim in enumerate(state['key_claims'], 1):
            print(f"   Analyzing claim {i}/{len(state['key_claims'])}: {claim[:50]}...")
            
            try:
                # Create opposite tone for this claim using OpenAI
                prompt = f"""Take this claim and create the exact opposite viewpoint or tone:

Original claim: {claim}

Create a search query that would find articles with the opposite viewpoint. Make it specific and focused (max 10 words):"""
                
                response = openai_client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "You create opposing search queries for given claims."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=100,
                    temperature=0.5
                )
                
                opposite_query = response.choices[0].message.content.strip().replace('"', '').replace("Search query:", "").strip()
                
                # Search for opposing articles using Tavily
                search_response = tavily_client.search(
                    query=opposite_query,
                    max_results=5,
                    include_answer=False,
                    include_raw_content=False
                )
                
                # Extract news URLs (filter out social media)
                results = search_response.get('results', [])
                all_urls = [result.get('url') for result in results if result.get('url')]
                
                # Filter to news websites only
                blocked_domains = ['facebook.com', 'fb.com', 'instagram.com', 'twitter.com', 'x.com', 
                                 'youtube.com', 'youtu.be', 'tiktok.com', 'linkedin.com', 'pinterest.com',
                                 'reddit.com', 'tumblr.com', 'snapchat.com', 'whatsapp.com', 'telegram.org']
                
                for url in all_urls:
                    if url and not any(domain in url.lower() for domain in blocked_domains):
                        if url not in all_opposing_urls:  # Avoid duplicates
                            all_opposing_urls.append(url)
                
                print(f"     → Found {len([url for url in all_urls if url and not any(domain in url.lower() for domain in blocked_domains)])} opposing articles for this claim")
                
            except Exception as claim_error:
                print(f"     → Error: {str(claim_error)}")
                continue
        
        print(f"✅ Bias analysis completed: Found {len(all_opposing_urls)} total opposing articles")
        
        return {
            **state,
            "final_result": all_opposing_urls
        }
    
    except Exception as e:
        print(f"❌ Error in bias analysis: {str(e)}")
        return {
            **state,
            "error": f"Bias analysis error: {str(e)}",
            "final_result": []
        }

def low_authenticity_node(state: WorkflowState) -> WorkflowState:
    """
    Node for handling low authenticity scores (≤ 30% for enhanced version)
    """
    score = state['authenticity_score']
    details = state.get('authenticity_details', {})
    fake_count = details.get('fake_claims', 0)
    
    print(f"⚠️ Low authenticity score ({score:.1f}%). Generating warning message.")
    
    # Creative warning messages based on the type of issue
    if fake_count > 0:
        warning_message = "🚨 FAKE NEWS ALERT! Our analysis found contradictory information and no credible sources supporting these claims. This appears to be misinformation. Please verify with trusted news outlets! 🚨"
    elif score == 0:
        warning_message = "⚠️ CREDIBILITY WARNING: Zero authoritative sources found for this information. This might be fake news or unverified content. Always cross-check with reliable news sources! 📰❌"
    else:
        warning_message = "🔍 VERIFICATION FAILED: No credible sources could verify these claims. This content may be fabricated or misleading. Trust but verify - check multiple reliable news sources first! 🛡️"
    
    return {
        **state,
        "final_result": warning_message
    }

def should_analyze_bias(state: WorkflowState) -> Literal["bias_analysis", "low_authenticity"]:
    """
    Router function with stricter threshold (30% instead of 70%)
    """
    if state.get('error'):
        return "low_authenticity"
    
    authenticity_score = state.get('authenticity_score', 0)
    
    # Much stricter threshold - only proceed to bias analysis if score > 30%
    if authenticity_score > 30:
        print(f"✅ Authenticity score ({authenticity_score:.1f}%) > 30%, proceeding to bias analysis")
        return "bias_analysis"
    else:
        print(f"❌ Authenticity score ({authenticity_score:.1f}%) ≤ 30%, flagging as low authenticity")
        return "low_authenticity"

# Helper functions
def extract_results_list(results):
    """Extract results list from API response"""
    if isinstance(results, list):
        return results
    elif isinstance(results, dict):
        for key in ['results', 'data', 'items', 'search_results']:
            if key in results and isinstance(results[key], list):
                return results[key]
    return []

def extract_domain(url):
    """Extract domain from URL"""
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc.lower().replace('www.', '')
    except:
        return url

def is_authoritative_source(domain):
    """Check if domain is from an authoritative source"""
    all_authoritative = []
    for source_list in AUTHORITATIVE_SOURCES.values():
        all_authoritative.extend(source_list)
    
    return any(auth_domain in domain for auth_domain in all_authoritative)

def create_clariview_workflow():
    """
    Create and configure the enhanced LangGraph workflow
    """
    # Initialize the workflow
    workflow = StateGraph(WorkflowState)
    
    # Add nodes
    workflow.add_node("extract_content", extract_content_node)
    workflow.add_node("extract_key_claims", extract_key_claims_node)  # Changed name
    workflow.add_node("enhanced_authenticity_verifier", enhanced_authenticity_verifier_node)  # Enhanced
    workflow.add_node("bias_analysis", bias_analysis_node)
    workflow.add_node("low_authenticity", low_authenticity_node)
    
    # Define the workflow edges
    workflow.add_edge("extract_content", "extract_key_claims")
    workflow.add_edge("extract_key_claims", "enhanced_authenticity_verifier")
    workflow.add_conditional_edges(
        "enhanced_authenticity_verifier",
        should_analyze_bias,
        {
            "bias_analysis": "bias_analysis",
            "low_authenticity": "low_authenticity"
        }
    )
    workflow.add_edge("bias_analysis", END)
    workflow.add_edge("low_authenticity", END)
    
    # Set entry point
    workflow.set_entry_point("extract_content")
    
    return workflow.compile()

async def run_clariview_analysis(url: str) -> dict:
    """
    Main function to run the enhanced ClariView analysis workflow
    """
    print(f"🚀 Starting Enhanced ClariView analysis for: {url}")
    print("=" * 80)
    
    # Create the workflow
    app = create_clariview_workflow()
    
    # Initialize state
    initial_state = {
        "url": url,
        "article_data": {},
        "key_claims": [],  # Changed from key_points
        "authenticity_score": 0.0,
        "authenticity_details": {},
        "bias_analysis": {},
        "final_result": {},
        "error": ""
    }
    
    try:
        # Run the workflow
        result = await app.ainvoke(initial_state)
        
        print("=" * 80)
        print("🎉 Enhanced ClariView analysis completed!")
        
        # Print results based on type
        final_result = result['final_result']
        
        print("📋 ANALYSIS RESULT:")
        print("=" * 50)
        
        if isinstance(final_result, str):
            # Warning message for fake/low authenticity news
            print(final_result)
        elif isinstance(final_result, list):
            # List of URLs from bias analysis (authentic news)
            print("✅ NEWS VERIFIED! Here are opposing viewpoint articles for balanced perspective:")
            print()
            for i, url in enumerate(final_result, 1):
                print(f"{i}. {url}")
        else:
            # Fallback for unexpected format
            print("Analysis completed with mixed results.")
        
        print("=" * 50)
        
        return result['final_result']
    
    except Exception as e:
        print(f"❌ Workflow execution error: {str(e)}")
        return {
            "status": "failed",
            "reason": f"Workflow execution error: {str(e)}",
            "url": url
        }

# Synchronous wrapper for easier use
def analyze_url(url: str) -> dict:
    """
    Synchronous wrapper for the enhanced ClariView analysis
    """
    return asyncio.run(run_clariview_analysis(url))

# Example usage and testing
if __name__ == "__main__":
    # Example usage
    test_url = "https://www.dawn.com/news/1908824"
    
    print("Enhanced ClariView LangGraph Workflow")
    print("=" * 50)
    
    # Run the analysis
    result = analyze_url(test_url)
    
    # Display results
    print("\n" + "=" * 60)
    print("🎯 CLARIVIEW FINAL VERDICT")
    print("=" * 60)
    
    if isinstance(result, str):
        # Warning message
        print(result)
    elif isinstance(result, list) and result:
        # List of opposing URLs
        print("✅ NEWS AUTHENTICITY VERIFIED!")
        print("📰 Here are opposing viewpoint articles for balanced reading:")
        print()
        for i, url in enumerate(result, 1):
            print(f"{i:2d}. {url}")
    elif isinstance(result, list) and not result:
        print("✅ NEWS VERIFIED but no opposing viewpoints found.")
    else:
        print("❓ Analysis completed with unexpected result format.")
    
    print("=" * 60)