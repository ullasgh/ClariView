# summary.py
from huggingface_hub import InferenceClient
from dotenv import load_dotenv
import os
from content_extractor import extract_article_content

# Extract article content
article = extract_article_content(
    "https://www.financialexpress.com/life/technology-apple-iphone-17-iphone-17-pro-iphone-17-pro-max-iphone-air-these-countries-will-get-esim-only-models-3976482/"
)

# Load environment variables
load_dotenv()
HG_API_KEY = os.getenv("HG_API")

# Initialize the client once
client = InferenceClient("mistralai/Mistral-7B-Instruct-v0.2", token=HG_API_KEY)


def get_five_points(article_text: str) -> list:
    """
    Returns the 5 most important sentences from the article as a list.
    """
    prompt = f"Extract the 5 most important sentences from the following article:\n\n{article_text}"

    response = client.chat_completion(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300
    )

    text = response['choices'][0]['message']['content']

    # Split into a list by newlines or numbering
    points = []
    for line in text.split("\n"):
        line = line.strip()
        if line and not line.startswith(("1.", "2.", "3.", "4.", "5.")):
            points.append(line)
        elif line.startswith(("1.", "2.", "3.", "4.", "5.")):
            # Remove numbering
            points.append(line[2:].strip())

    # Ensure only 5 points
    return points[:5]


# 🔹 Example usage if run as script
if __name__ == "__main__":
    sample_article = article.get("content")
    five_points_list = get_five_points(sample_article)

    print(five_points_list)
