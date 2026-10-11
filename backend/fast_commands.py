"""Conservative routing for simple search requests; complex tasks stay with AI."""
import re
from urllib.parse import quote_plus, urlparse


def search_command(instruction, current_url):
    text = instruction.strip().rstrip(".!")
    match = re.fullmatch(
        r"(?:please\s+)?(?:search(?:\s+for)?|find|look\s+up)\s+(.+)",
        text, re.IGNORECASE,
    )
    if not match:
        return None
    query = match.group(1).strip()
    # Multi-step instructions require the planner.
    if re.search(r"\b(?:then|and|summarize|compare|open|play|watch)\b", query, re.I):
        return None
    site_match = re.fullmatch(r"(.+?)\s+on\s+(youtube|wikipedia|github|google)", query, re.I)
    prefix_match = re.fullmatch(r"(youtube|wikipedia|github|google)\s+for\s+(.+)", query, re.I)
    host = (urlparse(current_url).hostname or "").lower()
    site = next((s for s in ("youtube", "wikipedia", "github")
                 if host == s + ".com" or host.endswith("." + s + ".com")
                 or host == s + ".org" or host.endswith("." + s + ".org")), None)
    if site_match:
        query, site = site_match.group(1), site_match.group(2).lower()
    elif prefix_match:
        site, query = prefix_match.group(1).lower(), prefix_match.group(2)
    site = site or "google"
    if not query:
        return None
    encoded = quote_plus(query)
    urls = {
        "google": "https://www.google.com/search?q=" + encoded,
        "youtube": "https://www.youtube.com/results?search_query=" + encoded,
        "wikipedia": "https://en.wikipedia.org/w/index.php?search=" + encoded,
        "github": "https://github.com/search?q=" + encoded,
    }
    return {"site": site, "query": query, "url": urls[site]}
