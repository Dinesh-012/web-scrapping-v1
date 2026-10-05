"""Small Amazon India search scraper used by the MVP."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import quote_plus

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


def scrape_amazon(search_term: str = "wireless earbuds", limit: int = 8) -> list[dict]:
    """Return publicly visible search results; raise RuntimeError on blocking."""
    url = f"https://www.amazon.in/s?k={quote_plus(search_term)}"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(locale="en-IN", user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ))
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2500)
            body = page.locator("body").inner_text(timeout=5000).lower()
            if any(marker in body for marker in ("captcha", "robot check", "sorry, we just need to make sure", "access denied")):
                raise RuntimeError("Amazon returned a CAPTCHA or access block; no products collected.")
            cards = page.locator("div[data-component-type='s-search-result']")
            products = []
            scraped_at = datetime.now(timezone.utc).isoformat()
            for i in range(min(cards.count(), limit)):
                card = cards.nth(i)
                title = card.locator("h2 a span").first
                name = title.inner_text().strip() if title.count() else ""
                link = card.locator("h2 a").first
                href = link.get_attribute("href") if link.count() else None
                if not name or not href:
                    continue
                price_whole = card.locator("span.a-price-whole").first
                price = None
                if price_whole.count():
                    raw = re.sub(r"[^0-9.]", "", price_whole.inner_text())
                    try:
                        price = float(raw)
                    except ValueError:
                        pass
                rating = None
                rating_el = card.locator("span.a-icon-alt").first
                if rating_el.count():
                    match = re.search(r"([0-5](?:\.[0-9])?)", rating_el.inner_text())
                    rating = float(match.group(1)) if match else None
                review_count = None
                reviews_el = card.locator("a[href*='customerReviews'] span").last
                if reviews_el.count():
                    raw = reviews_el.inner_text().replace(",", "").strip()
                    match = re.search(r"\d+", raw)
                    review_count = int(match.group()) if match else None
                products.append({
                    "search_term": search_term, "product_name": name,
                    "product_url": "https://www.amazon.in" + href if href.startswith("/") else href,
                    "price": price, "rating": rating, "review_count": review_count,
                    "best_seller_rank": None, "search_position": i + 1,
                    "availability": None, "scraped_at": scraped_at,
                })
            if not products:
                raise RuntimeError("Amazon search page returned no usable product cards.")
            return products
        except PlaywrightTimeoutError as exc:
            raise RuntimeError(f"Amazon page timed out: {exc}") from exc
        finally:
            browser.close()


if __name__ == "__main__":
    try:
        results = scrape_amazon()
        for item in results:
            print(f"{item['search_position']}. {item['product_name']} | ₹{item['price']} | rating {item['rating']}")
    except Exception as exc:
        print(f"Amazon scraper unavailable: {exc}")
