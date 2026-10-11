"""Conservative routing for simple search requests; complex tasks stay with AI."""
import re
from urllib.parse import quote_plus, urlparse


def direct_command(instruction):
    """Recognize complete, explicit commands only; never infer arbitrary clicks."""
    text = re.sub(r'^please\s+', '', instruction.strip(), flags=re.I).rstrip('.!').strip()
    simple = {
        'skip': 'youtube_skip_ad', 'skip ad': 'youtube_skip_ad',
        'skip the ad': 'youtube_skip_ad', 'skip ads': 'youtube_skip_ad',
        'skip youtube ad': 'youtube_skip_ad', 'skip the advertisement': 'youtube_skip_ad',
        'play': 'youtube_play', 'resume': 'youtube_play',
        'play video': 'youtube_play', 'resume video': 'youtube_play',
        'play the video': 'youtube_play', 'play the current video': 'youtube_play',
        'resume the video': 'youtube_play',
        'pause': 'youtube_pause', 'pause video': 'youtube_pause',
        'pause the video': 'youtube_pause',
        'list tabs': 'list_tabs', 'show tabs': 'list_tabs',
        'scroll down': 'scroll_page', 'scroll up': 'scroll_page',
    }
    lowered = text.lower()
    if lowered in simple:
        args = {'direction': lowered.split()[-1]} if lowered.startswith('scroll ') else {}
        return simple[lowered], args
    match = re.fullmatch(r'(?:switch to|switch|close) tab (\d+)', text, re.I)
    if match:
        number = int(match.group(1))
        if number < 1:
            return None
        return ('close_tab' if lowered.startswith('close') else 'switch_tab'), {'index': number - 1}
    match = re.fullmatch(r'(?:play|open) (?:video |result )?(\d+)', text, re.I)
    if match and int(match.group(1)) >= 1:
        return 'youtube_open_video', {'index': int(match.group(1)) - 1}
    match = re.fullmatch(r'(?:open|go to|navigate to) (.+?)( in (?:a )?new tab)?', text, re.I)
    if match:
        target = match.group(1).strip()
        sites = {'youtube': 'https://www.youtube.com/', 'github': 'https://github.com/',
                 'wikipedia': 'https://www.wikipedia.org/', 'google': 'https://www.google.com/'}
        url = sites.get(target.lower(), target)
        if re.fullmatch(r'https://[^\s]+', url):
            return ('open_tab' if match.group(2) else 'navigate'), {'url': url}
    return None


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


def video_request(instruction):
    match = re.fullmatch(r'(?:please\s+)?(?:play|watch)\s+(.+?)\s+on\s+youtube[.!]?',
                         instruction.strip(), re.I)
    if not match or re.search(r'\b(?:then|afterwards)\b', match.group(1), re.I):
        return None
    return match.group(1)
