from duckduckgo_search import DDGS
import requests
from bs4 import BeautifulSoup

def free_web_search(query):
    """
    Perform a web search using DuckDuckGo (free, no API key required).
    Returns a list of search results.
    """
    try:
        # DDGS().text() is the modern method for searching
        # backend="lite" or "html" often works better in server environments
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=10, backend="lite"))
        return results
    except Exception as e:
        return [{"error": str(e)}]

def extract_readable_text(url):
    """
    Fetch a URL and extract the readable text content using BeautifulSoup.
    """
    try:
        # Use a common user-agent to avoid being blocked by some sites
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Clean up: remove scripts and styles
        for script_or_style in soup(["script", "style"]):
            script_or_style.decompose()
            
        # Get text and clean up whitespace
        text = soup.get_text(separator=' ')
        return ' '.join(text.split())
    except Exception as e:
        return f"Error fetching or parsing URL: {str(e)}"

if __name__ == "__main__":
    # Quick test
    print("Testing web search...")
    search_results = free_web_search("Python programming")
    print(f"Found {len(search_results)} results.")
    if search_results and "error" not in search_results[0]:
        print(f"Top result: {search_results[0]['title']} - {search_results[0]['href']}")
    elif search_results:
        print(f"Search failed with error: {search_results[0].get('error')}")
        
    print("\nTesting text extraction...")
    test_url = "https://www.python.org/about/"
    text_content = extract_readable_text(test_url)
    print(f"Extracted {len(text_content)} characters.")
    print(f"Snippet: {text_content[:200]}...")
