# summary.py
from openai import OpenAI
from dotenv import load_dotenv
import os
from content_extractor import extract_article_content

# Load environment variables with debugging
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Check if API key is loaded
if not OPENAI_API_KEY:
    print("❌ OPENAI_API_KEY not found in environment variables")
    print("   Please add OPENAI_API_KEY=your_key_here to your .env file")
    exit(1)

# Initialize the OpenAI client
try:
    client = OpenAI(api_key=OPENAI_API_KEY)
    print("✅ OpenAI client initialized for summary.py")
except Exception as e:
    print(f"❌ Failed to initialize OpenAI client: {e}")
    exit(1)


def get_five_points(article_text: str) -> list:
    """
    Returns the 5 most important sentences from the article as a list.
    """
    prompt = f"""Extract the 5 most important facts/claims from the following article in a short point. 
    
    Return them as a numbered list (1. 2. 3. 4. 5.) with each point containing only the key fact or claim.
    
    Article:
    {article_text}"""

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an expert at extracting key facts and claims from articles. Return exactly 5 numbered points."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=400,
            temperature=0.3
        )

        text = response.choices[0].message.content

        # Split into a list by newlines and process numbering
        points = []
        for line in text.split("\n"):
            line = line.strip()
            if line:
                # Remove numbering if present (1., 2., etc.)
                if line[0:2] in ["1.", "2.", "3.", "4.", "5."] or line[0:3] in ["1. ", "2. ", "3. ", "4. ", "5. "]:
                    # Remove the number and dot/space
                    clean_line = line[2:].strip() if line[1] == "." else line[3:].strip()
                    points.append(clean_line)
                elif line.startswith(("•", "-", "*")):
                    # Handle bullet points
                    points.append(line[1:].strip())
                elif not any(char.isdigit() for char in line[:3]):
                    # If no numbering detected, add as is
                    points.append(line)

        # Filter out empty points and ensure only 5 points
        points = [point for point in points if point and len(point) > 10]  # Filter very short points
        return points[:5]

    except Exception as e:
        print(f"⚠️ Error extracting key points: {e}")
        return [
            "Error: Could not extract key points from article",
            "Please check your OpenAI API key and try again",
            "The article content may be too long or invalid",
            "Consider breaking the article into smaller sections",
            "Contact support if the issue persists"
        ]


# 🔹 Example usage if run as script
if __name__ == "__main__":
    # Extract article content
    print("🔍 Extracting article content...")
    article = extract_article_content(
        "https://thewire.in/politics/sonam-wangchuk-arrest-political-reactions-ladakh-leh"
    )
    
    sample_article = article.get("content")
    
    if sample_article:
        print(f"✅ Article extracted: {len(sample_article)} characters")
        print("\n🔍 Extracting 5 key points...")
        
        five_points_list = get_five_points(sample_article)
        
        print("\n📋 5 Key Points:")
        print("=" * 60)
        for i, point in enumerate(five_points_list, 1):
            print(f"{i}. {point}")
            print("-" * 40)
    else:
        print("❌ Failed to extract article content")