"""Fallback for any other career page: render it in a headless browser and collect job links."""
from typing import Iterator
from urllib.parse import urldefrag

from ..models import Job
from .base import USER_AGENT, Fetcher

# Without a configured selector, keep links that look like individual job postings.
_COLLECT = """
(selector) => {
  const hint = /(job|career|position|opening|requisition|vacanc|role)s?[\\/=_-]/i;
  const nodes = selector ? [...document.querySelectorAll(selector)] : [...document.querySelectorAll('a[href]')];
  const out = [];
  for (const node of nodes) {
    const a = node.closest('a[href]') || node.querySelector('a[href]');
    if (!a) continue;
    const lines = node.innerText.split('\\n').map(s => s.trim()).filter(Boolean);
    if (!lines.length) continue;
    if (!selector && (!hint.test(a.href) || lines[0].length < 6 || lines[0].length > 140)) continue;
    out.push({href: a.href, title: lines[0], rest: lines.slice(1, 4).join(' | ')});
  }
  return out;
}
"""


class Generic(Fetcher):
    """options: selector (job card or link), wait_for, load_more (button selector), max_clicks"""

    searchable = False
    needs_browser = True

    def _open(self, play, url: str):
        browser = play.chromium.launch(headless=True)
        page = browser.new_context(user_agent=USER_AGENT, viewport={"width": 1366, "height": 900}).new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        return browser, page

    def search(self, term: str) -> Iterator[Job]:
        from playwright.sync_api import sync_playwright

        opts = self.company.options
        with sync_playwright() as play:
            browser, page = self._open(play, self.company.url)
            try:
                if opts.get("wait_for") or opts.get("selector"):
                    page.wait_for_selector(opts.get("wait_for") or opts["selector"], timeout=30_000)
                else:
                    page.wait_for_timeout(8_000)
                for _ in range(int(opts.get("max_clicks", 10)) if opts.get("load_more") else 0):
                    button = page.locator(opts["load_more"]).first
                    if not button.is_visible():
                        break
                    button.click()
                    page.wait_for_timeout(2_000)
                found = page.evaluate(_COLLECT, opts.get("selector"))
            finally:
                browser.close()
        for item in found:
            url = urldefrag(item["href"]).url
            yield Job(id=url, title=item["title"], url=url, location=item["rest"])

    def describe(self, job: Job) -> str:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as play:
            browser, page = self._open(play, job.url)
            try:
                page.wait_for_timeout(4_000)
                return page.inner_text("body")[:20_000]
            finally:
                browser.close()
