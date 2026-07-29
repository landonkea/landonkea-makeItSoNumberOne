# ───────────────────────────────────────────────────────────────────
# ai.py — Talks to Claude (the brain of the whole system)
# ───────────────────────────────────────────────────────────────────
# This module sends the user's transcribed speech to Claude (via
# Anthropic's API) and parses the response into:
#   1. What to SAY aloud (text response).
#   2. What to DO (actions like opening apps, searching, etc.).
#
# Claude is the "computer" from Star Trek — it receives the user's
# request, thinks about it, and responds with both spoken words
# and actions to execute on the machine.
#
# PREREQUISITE
# ------------
# You need an Anthropic API key. Get one at console.anthropic.com.
# Put it in config.yaml:
#   anthropic_api_key: "sk-ant-..."
# ───────────────────────────────────────────────────────────────────

# Import the `json` module so we can work with JSON data.
# JSON is a text format that looks like JavaScript objects.
# We use it to read and write structured data like API responses.
import json

# Import the `os` module so we can interact with the operating system.
# This lets us do things like find file paths and check if files exist.
import os

# Import the `re` module so we can use regular expressions.
# Regular expressions are patterns that help us search and extract
# text — like finding "RESPONSE:" in Claude's reply.
import re


# Define a function named `get_system_prompt` that takes no arguments.
# Functions are reusable blocks of code. This one loads the instructions
# that tell Claude HOW to behave (like a Star Trek computer).
def get_system_prompt():
    """
    Load the Star Trek computer system prompt from the shared file.

    This prompt tells Claude HOW to behave (as the Enterprise
    computer) and what FORMAT to respond in (RESPONSE: ... ACTIONS:
    ...).

    RETURNS
    -------
    str
        The full system prompt text.
    """
    # Build the path to the system_prompt.txt file.
    # `os.path.abspath(__file__)` gets the full path of THIS file (ai.py).
    # `os.path.dirname(...)` goes up one folder (from ai.py to core/).
    # We call it 3 times to go from core/ -> desktop/ -> project root.
    # Then we join "shared", "prompts", "system_prompt.txt" to get the
    # final path like: /Users/.../shared/prompts/system_prompt.txt
    # We do this because the prompt file is in a shared folder at the
    # top level of the project, not inside the desktop/ folder.
    prompt_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))),
        "shared",
        "prompts",
        "system_prompt.txt"
    )

    # Try to open and read the prompt file.
    # `try:` means "attempt this code, but if something goes wrong,
    # catch the error instead of crashing."
    try:
        # Open the file at `prompt_path` in read mode ("r").
        # `with open(...) as f:` automatically closes the file when
        # we're done, even if an error happens.
        # `f.read()` reads ALL the text from the file and returns it.
        with open(prompt_path, "r") as f:
            return f.read()
    # If the file doesn't exist, Python raises a FileNotFoundError.
    # `except FileNotFoundError:` catches that specific error so the
    # program doesn't crash — it falls back to a default prompt instead.
    except FileNotFoundError:
        # Return a simple default prompt as a fallback.
        # This is a multi-line string (triple quotes) that tells Claude
        # to act like the Enterprise computer and respond in a specific
        # format. This way, the app still works even if the file is missing.
        return (
            "You are the computer from the USS Enterprise. "
            "Respond helpfully and concisely. "
            "Format: RESPONSE: ... ACTIONS: ..."
        )


# Define a function named `process_with_claude` that sends text to
# Claude and gets back a response. It takes 3 parameters:
#   - user_text: the words the user spoke (a string).
#   - config: a dictionary of settings like API keys.
#   - conversation_history: previous messages (so Claude remembers
#     what was said before). Defaults to None (no history).
def process_with_claude(user_text, config, conversation_history=None):
    """
    Send the user's request to Claude and get back the response.

    PARAMETERS
    ----------
    user_text : str
        What the user said (transcribed from speech-to-text).
    config : dict
        Configuration dictionary. Must contain "anthropic_api_key".
    conversation_history : list or None
        Previous messages for context (maintains conversation flow).
        If None, starts a new conversation.

    RETURNS
    -------
    dict or None
        Parsed response with keys:
            "spoken_text" : str  — What to say out loud.
            "actions" : list     — Actions to execute (each is a
                                   dict with "action" and "params").
        Returns None if the API call failed.
    """
    # Get the Anthropic API key from the config dictionary.
    # `config.get("anthropic_api_key", "")` tries to find the key
    # "anthropic_api_key" in the config. If it's missing, it returns
    # an empty string "" instead of crashing.
    api_key = config.get("anthropic_api_key", "")
    # Check if the API key is empty (missing or blank).
    # `not api_key` is True when api_key is "" (empty string),
    # which means the user hasn't set up their API key yet.
    if not api_key:
        # Print a blank line for spacing before the error box.
        print()
        # Print the top border of a box that tells the user the API
        # key is missing. The ╔═╗ characters draw a fancy box border
        # in the terminal.
        print("  ╔══════════════════════════════════════════════════╗")
        # Print a message inside the box telling them the key is missing.
        print("  ║  Missing Anthropic API Key!                    ║")
        # Print an empty separator line in the box.
        print("  ║                                                ║")
        # Print instructions on where to add the API key.
        print("  ║  Add to desktop/config.yaml:                   ║")
        # Print the exact format the config file should use.
        print("  ║     anthropic_api_key: \"sk-ant-...\"           ║")
        # Print an empty separator line.
        print("  ║                                                ║")
        # Print where to get a free API key.
        print("  ║  Get one at: https://console.anthropic.com/    ║")
        # Print the bottom border of the box.
        print("  ╚══════════════════════════════════════════════════╝")
        # Print a blank line for spacing after the box.
        print()
        # Return None to signal that we couldn't process the request.
        # None means "no value" — the caller will check for this and
        # skip speaking / acting.
        return None

    # ── Build the conversation messages ──────────────────────────
    # We send Claude:
    #   1. A SYSTEM prompt (tells it how to behave).
    #   2. A list of USER and ASSISTANT messages (the conversation
    #      history so far).
    #   3. The new USER message (what the user just said).
    # Create an empty list that will hold all the messages we send
    # to Claude. A list is like a shopping cart — you can put items
    # in it and loop through them later.
    messages = []

    # Check if there IS any conversation history from previous turns.
    # If `conversation_history` is a list with items, Python treats
    # it as True. If it's None or empty, Python treats it as False.
    if conversation_history:
        # Loop through each message in the conversation history.
        # `for msg in conversation_history:` runs the indented code
        # once for EVERY message, with `msg` set to the current one.
        for msg in conversation_history:
            # Add (append) each message to our messages list.
            # Each message is a dictionary (key-value pairs) with:
            #   "role": who said it ("user" or "assistant")
            #   "content": the actual text they said
            # We copy the role and content from the history so Claude
            # can see the full conversation context.
            messages.append({
                "role": msg["role"],      # "user" or "assistant"
                "content": msg["content"] # The text they said.
            })

    # Add the new user message (the latest thing the user said) to
    # the list. This is the current request we want Claude to answer.
    messages.append({
        "role": "user",
        "content": user_text
    })

    # ── Call the Anthropic API ────────────────────────────────────
    # Print a status message so the user can see what's happening.
    # The `[ai]` tag helps identify which part of the system printed it.
    print("  [ai] Sending to Claude...")
    # Print the actual text that was sent, so the user can verify the
    # speech-to-text worked correctly.
    print(f"  [ai] Request: \"{user_text}\"")

    # Try to send the request to Claude's API.
    # If anything fails (network error, wrong key, etc.), we catch
    # the error and return None instead of crashing.
    try:
        # Import the `requests` library INSIDE the function.
        # This library lets us send HTTP requests (like a web browser
        # would) to fetch web pages or call APIs.
        import requests

        # Define the URL for Anthropic's messages API endpoint.
        # An API endpoint is like a specific phone number you dial to
        # reach a specific service. This one handles chat messages.
        url = "https://api.anthropic.com/v1/messages"

        # Build the payload (the data we send to the API).
        # A payload is like a package you mail — it contains everything
        # the API needs to process your request.
        payload = {
            # Specify which Claude model to use.
            # "claude-sonnet-4-20250514" is a specific version of Claude
            # that balances speed and intelligence. It's faster and
            # cheaper than the most powerful model (Opus) but still
            # very capable.
            "model": "claude-sonnet-4-20250514",
            # Set the maximum number of tokens in the response.
            # A token is roughly a word or part of a word. 1024 tokens
            # is about 700-800 words — enough for a detailed answer
            # without being too expensive or slow.
            "max_tokens": 1024,
            # Set the system prompt that tells Claude how to behave.
            # This calls our get_system_prompt() function above to
            # load the Star Trek computer instructions.
            "system": get_system_prompt(),
            # Pass the conversation messages we built above.
            "messages": messages,
            # Set the "temperature" (creativity level) to 0.7.
            # Temperature controls randomness: 0.0 = always picks the
            # most likely word (boring but reliable), 1.0 = more
            # random/creative. 0.7 is a good balance.
            "temperature": 0.7
        }

        # Build the HTTP headers for the request.
        # Headers are like envelope markings — they tell the server
        # metadata about your request (who you are, what format you
        # want, etc.).
        headers = {
            # Send our API key so Anthropic knows who's calling.
            # The key goes in the "x-api-key" header for security.
            "x-api-key": api_key,
            # Specify which version of the Anthropic API we're using.
            # This ensures backward compatibility if the API changes.
            "anthropic-version": "2023-06-01",
            # Tell the server we're sending JSON data.
            "content-type": "application/json"
        }

        # Send the POST request to Claude's API.
        # POST is the HTTP method for sending data (like submitting a
        # form). We pass the URL, headers, payload (as JSON), and a
        # timeout of 30 seconds (so it doesn't hang forever).
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=30
        )

        # Check if the response status code is NOT 200 (success).
        # HTTP status codes: 200 = OK, 404 = Not Found, 500 = Server Error.
        # If it's not 200, something went wrong on Anthropic's side.
        if response.status_code != 200:
            # Print the error code so we know what went wrong.
            print(f"  [ai] Claude API error: {response.status_code}")
            # Print the full response text from the server to help
            # diagnose the problem.
            print(f"  [ai] Response: {response.text}")
            # Return None to signal failure.
            return None

        # ── Parse the response ───────────────────────────────────
        # Convert the JSON response into a Python dictionary.
        # `.json()` parses the JSON text and gives us a nested
        # dictionary we can access with square brackets.
        result = response.json()

        # Claude's response text is inside the "content" array.
        # An array (or list) can have multiple items. Claude usually
        # returns one text block at index 0.
        # Start with an empty string to hold the full response text.
        full_response = ""
        # Loop through each "block" in the content array.
        # We loop instead of just taking index 0 to be safe in case
        # the format changes.
        for block in result.get("content", []):
            # Each block has a "type" field. We're looking for the
            # block of type "text" (as opposed to tool_use or other).
            if block.get("type") == "text":
                # Extract the actual text from the block.
                # `.get("text", "")` returns the text or empty string
                # if the "text" key doesn't exist.
                full_response = block.get("text", "")
                # Exit the loop early since we found our text block.
                break

        # If the response text is empty (Claude didn't say anything),
        # print an error and return None.
        if not full_response:
            print("  [ai] Claude returned empty response.")
            return None

        # Print how many characters the response contains.
        # `len(full_response)` counts the number of characters in the
        # string. This helps us see if the response was reasonable.
        print(f"  [ai] Response received ({len(full_response)} chars)")

        # ── Parse structured response ────────────────────────────
        # Claude responds in the format:
        #   RESPONSE: <spoken text>
        #
        #   ACTIONS:
        #   - action: open_app
        #     params:
        #       name: Messages
        #   - action: search_web
        #     params:
        #       query: weather today
        #
        # We need to extract the spoken text and the actions list.
        # Call the private helper function `_parse_claude_response` to
        # split the raw text into spoken words and a list of actions.
        # The underscore prefix means "internal use only" (a convention,
        # not enforced by Python).
        return _parse_claude_response(full_response)

    # If the `requests` library isn't installed, Python raises an
    # ImportError. This catches it so we can show a helpful message
    # instead of crashing with a scary traceback.
    except ImportError:
        print("  [ai] `requests` library not installed.")
        print("  Run: pip install requests")
        return None
    # Catch ANY other exception (error) that might happen.
    # This is a safety net — network timeouts, bad responses, etc.
    except Exception as e:
        # Print the error message so the developer can debug.
        print(f"  [ai] Error communicating with Claude: {e}")
        # Return None to tell the caller something went wrong.
        return None


# Define a private helper function that parses Claude's structured
# response text into two parts: the spoken text and the actions list.
# The underscore prefix `_` means "this is internal to this module."
def _parse_claude_response(full_text):
    """
    Parse Claude's structured response into spoken text + actions.

    PARAMETERS
    ----------
    full_text : str
        The raw text from Claude in the format:
        RESPONSE: ...
        ACTIONS:
        - action: ...
          params: ...

    RETURNS
    -------
    dict
        {
            "spoken_text": str,       # What to speak aloud.
            "actions": list of dict   # Actions to execute.
        }
    """
    # Create an empty string to hold the spoken text portion.
    # We'll fill this in if we find a "RESPONSE:" section.
    spoken_text = ""
    # Create an empty list to hold the extracted actions.
    # Each action will be a dictionary with "action" and "params".
    actions = []

    # ── Extract the RESPONSE section ─────────────────────────────
    # Use a regular expression (re.search) to find "RESPONSE:" in
    # the text. The pattern `r"RESPONSE:\s*(.+?)(?=\n\s*ACTIONS:|\Z)"`
    # searches for:
    #   RESPONSE:    - the literal word "RESPONSE:"
    #   \s*          - zero or more spaces after the colon
    #   (.+?)        - capture everything after (the actual response text)
    #   (?=...|\Z)   - stop when you see "ACTIONS:" or end of string
    # re.DOTALL means the dot (.) matches newlines too.
    response_match = re.search(
        r"RESPONSE:\s*(.+?)(?=\n\s*ACTIONS:|\Z)",
        full_text,
        re.DOTALL
    )
    # If the regex found a match (response_match is not None)...
    if response_match:
        # Extract the captured text from group(1) — the part inside
        # the parentheses in the regex. `.strip()` removes any extra
        # spaces or newlines at the start and end.
        spoken_text = response_match.group(1).strip()

    # ── Extract the ACTIONS section ──────────────────────────────
    # Use regex to find "ACTIONS:" followed by everything else.
    # The pattern `r"ACTIONS:\s*(.+)"` captures all text after
    # "ACTIONS:" until the end of the string.
    actions_match = re.search(
        r"ACTIONS:\s*(.+)",
        full_text,
        re.DOTALL
    )
    # If the regex found an ACTIONS section...
    if actions_match:
        # Extract the text after "ACTIONS:" and strip whitespace.
        actions_text = actions_match.group(1).strip()
        # Parse that text into a list of action dictionaries using
        # our helper function `_parse_actions_yaml`.
        actions = _parse_actions_yaml(actions_text)

    # Return a dictionary (key-value pairs) containing the extracted
    # spoken text and the list of actions.
    return {
        "spoken_text": spoken_text,
        "actions": actions
    }


# Define a private helper function that parses the YAML-like action
# list text into a Python list of dictionaries.
# YAML is a simple data format that uses indentation (like Python)
# to structure data. Claude outputs actions in this format.
def _parse_actions_yaml(actions_text):
    """
    Parse the YAML-like action list from Claude's response.

    Claude responds with action blocks like:
        - action: open_app
          params:
            name: Safari

    This function extracts each action as a dictionary.

    PARAMETERS
    ----------
    actions_text : str
        The raw text after "ACTIONS:" in Claude's response.

    RETURNS
    -------
    list of dict
        Each dict has "action" (str) and "params" (dict).
    """
    # Create an empty list to hold all the parsed actions.
    actions = []

    # Split the text into blocks using a regular expression.
    # The pattern `r"\n\s*-\s+action:"` finds newlines followed by
    # optional spaces, a dash, more spaces, and "action:".
    # Each block starts with "- action:" on its own line.
    # This splits the text into chunks, one per action.
    action_blocks = re.split(r"\n\s*-\s+action:", actions_text)

    # Loop through each action block to parse it.
    # `for block in action_blocks:` runs once per action.
    for block in action_blocks:
        # Remove leading/trailing whitespace from the block.
        # This makes parsing cleaner by removing stray spaces/newlines.
        block = block.strip()
        # If the block is empty after stripping, skip it and move to
        # the next one. This handles the text before the first action
        # or any empty splits.
        if not block:
            continue

        # Get the action name (the first line of the block).
        # Split the block into separate lines using newline `\n`.
        # `split("\n")` returns a list of strings, one per line.
        lines = block.split("\n")
        # The first line [0] is the action name (e.g., "open_app").
        # `.strip()` removes any extra whitespace around it.
        action_name = lines[0].strip()

        # Create an empty dictionary to hold the action's parameters.
        # Parameters are like "which app to open" or "what to search".
        params = {}
        # Use regex to find the "params:" section.
        # The pattern looks for "params:" followed by everything after
        # it (capturing all indented key-value pairs below it).
        params_match = re.search(r"params:\s*(.+)", block, re.DOTALL)
        # If we found a "params:" section...
        if params_match:
            # Extract the text after "params:" and strip whitespace.
            params_text = params_match.group(1).strip()
            # Split the params text by newlines and process each line.
            # Each line should be in the format "key: value".
            for line in params_text.split("\n"):
                # Remove extra whitespace from the line.
                line = line.strip()
                # Check if the line contains a colon (key-value separator).
                # Lines without a colon might be blank or comments.
                if ":" in line:
                    # Split the line at the FIRST colon only.
                    # `split(":", 1)` gives ["key", "value"] with the
                    # limit of 1 split so values with colons work.
                    key, value = line.split(":", 1)
                    # Remove spaces around the key name.
                    key = key.strip()
                    # Remove spaces around the value.
                    value = value.strip()
                    # Store the key-value pair in our params dictionary.
                    params[key] = value

        # Add the parsed action (name + params) to our actions list.
        # Each action is a dictionary with "action" (string) and
        # "params" (dictionary of key-value pairs).
        actions.append({
            "action": action_name,
            "params": params
        })

    # Return the complete list of parsed actions.
    # The caller will use this list to execute each action.
    return actions
