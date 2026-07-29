# ───────────────────────────────────────────────────────────────────
# actions/web_actions.py — searches the internet
# ───────────────────────────────────────────────────────────────────
# This module lets Claude search the web for information.
#
# We use the DuckDuckGo search API because:
#   1. It's FREE (no API key needed).
#   2. It works without any registration.
#   3. It returns useful search results that Claude can read.
#
# For scraping actual page content, we fetch the URL and extract
# text. This lets Claude "browse the web" to answer questions.
# ───────────────────────────────────────────────────────────────────

import requests


def search_web(query, config):
    """
    Search the internet for the given query and return results.

    PARAMETERS
    ----------
    query : str
        What to search for (e.g. "weather today", "latest news").
    config : dict
        App configuration (may contain API keys for alternative
        search providers).

    RETURNS
    -------
    str
        Search results as text (titles and snippets of web pages).

    HOW IT WORKS
    ------------
    1. We use DuckDuckGo's instant answer API (no key needed).
    2. DuckDuckGo returns JSON with a "Abstract" (summary) and
       "RelatedTopics" (list of results).
    3. We format this into readable text for the user.
    """
    if not query:
        return "No search query provided"

    print(f"  [web] Searching for: {query}")

    try:
        # ── DuckDuckGo Instant Answer API ────────────────────────
        # This API doesn't need any authentication — it's free and
        # open. Just send a GET request with the query.
        url = "https://api.duckduckgo.com/"
        params = {
            "q": query,          # The search query.
            "format": "json",    # Get JSON response.
            "no_html": 1,        # Remove HTML from results.
            "skip_disambig": 1   # Skip disambiguation pages.
        }

        response = requests.get(
            url,
            params=params,
            timeout=15
        )

        if response.status_code != 200:
            return f"Search failed (HTTP {response.status_code})"

        data = response.json()

        # ── Format the results ───────────────────────────────────
        results_text = ""

        # Abstract: DuckDuckGo's summary of the topic (like a
        # mini-Wikipedia article).
        abstract = data.get("Abstract", "")
        if abstract:
            results_text += f"Summary: {abstract}\n\n"

        # Source URL for the abstract.
        source = data.get("AbstractURL", "")
        if source:
            results_text += f"Source: {source}\n\n"

        # Related topics: list of search results.
        related = data.get("RelatedTopics", [])
        if related:
            results_text += "Results:\n"
            for i, topic in enumerate(related[:5]):  # Top 5 results.
                # DuckDuckGo sometimes groups results in categories.
                if "Topics" in topic:
                    # It's a category with nested topics.
                    for sub_topic in topic["Topics"][:3]:
                        title = sub_topic.get("Text", "")
                        url_sub = sub_topic.get("FirstURL", "")
                        if title:
                            results_text += f"  {i+1}. {title}\n"
                            results_text += f"     {url_sub}\n"
                else:
                    title = topic.get("Text", "")
                    url_sub = topic.get("FirstURL", "")
                    if title:
                        results_text += f"  {i+1}. {title}\n"
                        results_text += f"     {url_sub}\n"

        if not results_text:
            return "No search results found."

        print(f"  [web] Found results ({len(results_text)} chars)")
        return results_text[:1500]  # Limit to 1500 chars.

    except ImportError:
        return "`requests` library required. Run: pip install requests"
    except requests.Timeout:
        return "Search timed out"
    except Exception as e:
        return f"Search error: {e}"
