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

# NOTE: `requests` is deliberately imported inside search_web() below,
# not here at the top of the file. If we imported it here and the
# `requests` library wasn't installed, Python would raise ImportError
# the moment this module gets loaded (which happens automatically at
# startup via actions/__init__.py) — crashing the whole app before it
# even starts, instead of showing the friendly "please pip install"
# message below. Importing inside the function's try/except lets us
# catch that case and fail gracefully, matching the pattern used in
# ai.py and stt.py for the same reason.


# Define a function named `search_web` that takes two parameters:
#   - `query`: the search phrase the user wants to look up (a string).
#   - `config`: a dictionary of settings (might have API keys for
#     alternative search providers, but DuckDuckGo doesn't need one).
# This function searches the internet and returns the results as text.
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
    # Check if the query is empty (the user didn't provide a search term).
    # `if not query:` is True when query is an empty string "", None,
    # or any other "falsy" value.
    if not query:
        # Return a simple error message explaining the problem.
        # We return early because there's nothing to search for.
        return "No search query provided"

    # Print a status message showing what we're searching for.
    # The `[web]` tag helps identify which module printed this message.
    # `f"..."` is an f-string — it lets us embed variables (like {query})
    # directly inside the string.
    print(f"  [web] Searching for: {query}")

    # Try to perform the search. If anything goes wrong (network error,
    # connection timeout, etc.), we catch the error and return a message
    # instead of crashing the entire voice assistant.
    try:
        # Import here (not at the top of the file) so a missing
        # `requests` library produces a friendly error message below
        # instead of crashing the app at startup. See NOTE above.
        import requests

        # ── DuckDuckGo Instant Answer API ────────────────────────
        # This API doesn't need any authentication — it's free and
        # open. Just send a GET request with the query.
        # Define the API endpoint URL. An "endpoint" is like a specific
        # phone number at a company that handles a specific type of request.
        url = "https://api.duckduckgo.com/"
        # Define the query parameters (like adding ?q=weather to a URL).
        # Parameters are key-value pairs that customize the request.
        params = {
            # "q" is the search query itself (what we're searching for).
            "q": query,
            # "format" tells DuckDuckGo to return JSON (structured data),
            # not HTML (web page code). JSON is easier for Python to read.
            "format": "json",
            # "no_html" tells DuckDuckGo to remove HTML tags from results,
            # giving us clean text without markup code.
            "no_html": 1,
            # "skip_disambig" tells DuckDuckGo to skip disambiguation
            # pages (like Wikipedia's "did you mean X or Y?" pages).
            "skip_disambig": 1
        }

        # Send the GET request to DuckDuckGo's API.
        # `requests.get()` is like typing a URL into a browser and pressing
        # Enter — it fetches the data from the server.
        # The `params` dictionary gets converted into URL parameters.
        # `timeout=15` means "wait up to 15 seconds, then give up" —
        # this prevents the program from hanging forever on a slow network.
        response = requests.get(
            url,
            params=params,
            timeout=15
        )

        # Check if the HTTP status code is NOT 200 (success).
        # HTTP status codes: 200 = OK, 404 = Not Found, 500 = Server Error.
        # If DuckDuckGo didn't return a success code, something went wrong.
        if response.status_code != 200:
            # Return an error message that includes the status code so we
            # know what type of error occurred (e.g., 502 = bad gateway).
            return f"Search failed (HTTP {response.status_code})"

        # Parse the JSON response from DuckDuckGo into a Python dictionary.
        # `response.json()` converts the JSON text into nested Python data
        # structures (dictionaries within dictionaries).
        data = response.json()

        # ── Format the results ───────────────────────────────────
        # Start with an empty string that we'll build up with formatted
        # results. We'll keep appending text to this string as we process
        # different parts of the response.
        results_text = ""

        # Abstract: DuckDuckGo's summary of the topic (like a
        # mini-Wikipedia article). This is the main knowledge panel
        # that appears at the top of DuckDuckGo search results.
        # `data.get("Abstract", "")` gets the "Abstract" field from the
        # response, or returns "" if the field is missing.
        abstract = data.get("Abstract", "")
        # If there's an abstract (non-empty string)...
        if abstract:
            # Add the summary to our results text with a label.
            # We use += to append new text to the existing string.
            results_text += f"Summary: {abstract}\n\n"

        # Source URL for the abstract (where the summary came from).
        source = data.get("AbstractURL", "")
        # If there's a source URL...
        if source:
            # Add the source URL to the results text with a label.
            # The user can visit this URL for more information.
            results_text += f"Source: {source}\n\n"

        # Related topics: list of search results (titles and URLs).
        # `data.get("RelatedTopics", [])` gets the list of results or
        # an empty list if there are none.
        related = data.get("RelatedTopics", [])
        # If there are related topics (non-empty list)...
        if related:
            # Add a "Results:" header to the output text.
            results_text += "Results:\n"
            # Loop through the first 5 results (or fewer if there aren't 5).
            # `enumerate(related[:5])` gives us both the index (i, starting
            # at 0) and the topic item. `[:5]` is a slice that takes the
            # first 5 items from the list.
            for i, topic in enumerate(related[:5]):  # Top 5 results.
                # DuckDuckGo sometimes groups results into categories.
                # Check if this topic has sub-topics (a "Topics" field).
                if "Topics" in topic:
                    # It's a category with nested topics inside it.
                    # Loop through up to 3 sub-topics within the category.
                    # `topic["Topics"][:3]` takes the first 3 sub-topics.
                    for sub_topic in topic["Topics"][:3]:
                        # Get the title/text of the sub-topic.
                        title = sub_topic.get("Text", "")
                        # Get the URL of the sub-topic.
                        url_sub = sub_topic.get("FirstURL", "")
                        # If there's a title (non-empty)...
                        if title:
                            # Add the result number, title, and URL to the
                            # output text with indentation for readability.
                            results_text += f"  {i+1}. {title}\n"
                            results_text += f"     {url_sub}\n"
                else:
                    # It's a regular result (not a category).
                    # Get the title/text of the result.
                    title = topic.get("Text", "")
                    # Get the URL of the result.
                    url_sub = topic.get("FirstURL", "")
                    # If there's a title...
                    if title:
                        # Add the result number, title, and URL to the
                        # output text with proper formatting.
                        results_text += f"  {i+1}. {title}\n"
                        results_text += f"     {url_sub}\n"

        # If we never added anything to results_text (no abstract, no
        # sources, no related topics), the search returned nothing.
        if not results_text:
            # Return a simple "no results" message.
            return "No search results found."

        # Print how many characters of results we found.
        # `len(results_text)` counts characters in the string.
        print(f"  [web] Found results ({len(results_text)} chars)")
        # Return the results text, limited to 1500 characters.
        # `[:1500]` is a slice that takes only the first 1500 characters.
        # This prevents the response from being too long for the user
        # or for Claude to process.
        return results_text[:1500]

    # If the `requests` library isn't installed, this catches the error
    # and returns a helpful message instead of crashing.
    except ImportError:
        return "`requests` library required. Run: pip install requests"
    # If the request timed out (took longer than 15 seconds), return
    # a clear timeout message.
    except requests.Timeout:
        return "Search timed out"
    # Catch ANY other exception that might occur (network down, DNS
    # failure, etc.) and return the error message as a string.
    except Exception as e:
        return f"Search error: {e}"
