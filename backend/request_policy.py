"""Owner-thread request policy. No sleeps, challenge interaction, or evasion."""
import copy
import time
from urllib.parse import urlparse


def protected_site(url):
    host = (urlparse(url).hostname or '').lower()
    for site in ('google.com', 'youtube.com'):
        if host == site or host.endswith('.' + site):
            return site
    return None


def verification(page):
    site = protected_site(page.url)
    if not site:
        return None
    if site == 'google.com' and (urlparse(page.url).path == '/sorry' or urlparse(page.url).path.startswith('/sorry/')):
        evidence = 'Google unusual-traffic verification URL'
    else:
        evidence = page.evaluate("""() => {
          const visible = el => el.getBoundingClientRect().width > 0 &&
            el.getBoundingClientRect().height > 0 && getComputedStyle(el).visibility !== 'hidden' &&
            !el.closest('[hidden], [aria-hidden="true"]') && getComputedStyle(el).opacity !== '0';
          const challenge = [...document.querySelectorAll(
            'iframe[src*="recaptcha"], .g-recaptcha, #captcha-form, form[action*="/sorry"], input[name="captcha"]'
          )].some(visible);
          const text = (document.body?.innerText || '').toLowerCase().replaceAll(String.fromCharCode(8217), "'");
          const playerChallenge = [...document.querySelectorAll(
            '.yt-playability-error-supported-renderers, ytd-enforcement-message-view-model'
          )].some(el => visible(el) && /confirm you('re| are) not a bot/.test(el.innerText.toLowerCase().replaceAll(String.fromCharCode(8217), "'")));
          const resultContent = document.querySelector('#search, #rso, ytd-search, ytd-video-renderer');
          const traffic = !resultContent && (text.includes('our systems have detected unusual traffic') ||
            text.includes('to continue, please type the characters below'));
          const human = /verify (that )?you('re| are) (a )?human|confirm you('re| are) not a bot/.test(text);
          const widget = [...document.querySelectorAll(
            'iframe[src*="recaptcha"], .g-recaptcha, [data-sitekey]'
          )].some(visible);
          return playerChallenge ? 'YouTube player requires human sign-in verification' : traffic ? 'Visible unusual-traffic challenge text' :
            challenge ? 'Visible CAPTCHA challenge control' :
            human && widget ? 'Human-verification prompt and visible CAPTCHA widget' : null;
        }""")
    if not evidence:
        return None
    return {'error': 'Human verification required. Complete the challenge manually in Chrome, then explicitly retry the task. ORION will not solve or dismiss it.',
            'human_intervention_required': True, 'verification': {'site': site, 'url': page.url, 'evidence': evidence}}


class RequestPolicy:
    def __init__(self):
        self.cache = {}
        self.attempts = {}

    def cached(self, url, pages):
        item = self.cache.get(url)
        if not item or time.monotonic() - item[0] > 5:
            return None
        _, page, result, document = item
        if page not in pages or page.is_closed() or page.url != url:
            self.cache.pop(url, None)
            return None
        if page.evaluate('() => window.__orionSearchDocument') != document:
            self.cache.pop(url, None)
            return None
        blocked = verification(page)
        if blocked:
            self.cache.pop(url, None)
            return page, blocked
        return page, {**copy.deepcopy(result), 'reused': True}

    def begin(self, url):
        now = time.monotonic()
        previous = self.attempts.get(url)
        self.attempts = {key: stamp for key, stamp in self.attempts.items() if now - stamp < 2}
        if previous is not None and now - previous < 2:
            return {'error': 'Repeated network request suppressed. Check the current page before explicitly retrying.'}
        self.attempts[url] = now
        return None

    def save(self, url, page, result):
        if 'error' not in result and page.url == url:
            self.cache = {key: value for key, value in self.cache.items() if time.monotonic() - value[0] < 5}
            document = time.monotonic()
            page.evaluate('(stamp) => { window.__orionSearchDocument = stamp; }', document)
            self.cache[url] = (document, page, copy.deepcopy(result), document)
