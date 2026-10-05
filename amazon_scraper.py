"""Amazon India search scraper for the Regional Product Demand MVP.

This scraper only collects publicly visible search-result information.
It does not attempt to bypass CAPTCHA, robot checks, or access blocks.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import quote_plus

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


AMAZON_BASE_URL = "https://www.amazon.in"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


def _clean_text(value: str | None) -> str | None:
    """Normalize scraped text."""
    if not value:
        return None

    value = re.sub(r"\s+", " ", value).strip()

    return value or None


def _parse_price(text: str | None) -> float | None:
    """Convert Amazon price text such as ₹1,299.00 into a float."""
    if not text:
        return None

    # Keep digits and decimal point only.
    cleaned = re.sub(r"[^0-9.]", "", text.replace(",", ""))

    if not cleaned:
        return None

    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_rating(text: str | None) -> float | None:
    """Extract rating from text such as '4.4 out of 5 stars'."""
    if not text:
        return None

    match = re.search(r"([0-5](?:\.[0-9])?)", text)

    if not match:
        return None

    try:
        rating = float(match.group(1))

        if 0 <= rating <= 5:
            return rating

    except ValueError:
        pass

    return None


def _parse_review_count(text: str | None) -> int | None:
    """Extract review count from Amazon text."""
    if not text:
        return None

    text = text.replace(",", "").strip()

    # Examples:
    # 18,542 -> 18542
    # 12.5K -> 12500
    # 1.2M -> 1200000
    match = re.search(r"([\d.]+)\s*([KMkm]?)", text)

    if not match:
        return None

    try:
        number = float(match.group(1))
        suffix = match.group(2).lower()

        if suffix == "k":
            number *= 1_000

        elif suffix == "m":
            number *= 1_000_000

        return int(number)

    except ValueError:
        return None


def _is_blocked(page) -> bool:
    """Detect obvious Amazon CAPTCHA/robot/access-block pages."""
    try:
        title = (page.title() or "").lower()
    except Exception:
        title = ""

    try:
        body = page.locator("body").inner_text(timeout=5000).lower()
    except Exception:
        body = ""

    markers = [
        "captcha",
        "robot check",
        "enter the characters you see below",
        "sorry, we just need to make sure you're not a robot",
        "sorry, we just need to make sure",
        "automated access",
        "access denied",
        "request was blocked",
    ]

    combined = f"{title}\n{body}"

    return any(marker in combined for marker in markers)


def _extract_products(page, search_term: str, limit: int) -> list[dict]:
    """Extract product information from Amazon search-result cards."""

    # Amazon's search-result container.
    cards = page.locator(
        "[data-component-type='s-search-result']"
    )

    card_count = cards.count()

    print(f"Amazon result cards detected: {card_count}")

    if card_count == 0:
        return []

    products = []

    scraped_at = datetime.now(timezone.utc).isoformat()

    for index in range(min(card_count, limit)):

        card = cards.nth(index)

        # ---------------------------------------------------------
        # ASIN
        # ---------------------------------------------------------
        asin = card.get_attribute("data-asin")

        if not asin:
            continue

        # ---------------------------------------------------------
        # Product name
        #
        # Amazon has used several variations of the title structure.
        # Try multiple selectors instead of depending on one exact DOM.
        # ---------------------------------------------------------
        name = None

        title_selectors = [
            "h2 span",
            "h2 a span",
            "h2 a",
            "a.s-link-style",
        ]

        for selector in title_selectors:
            try:
                locator = card.locator(selector).first

                if locator.count():
                    candidate = _clean_text(locator.inner_text())

                    if candidate:
                        name = candidate
                        break

            except Exception:
                continue

        # No title means this is not a usable product result.
        if not name:
            continue

        # ---------------------------------------------------------
        # Product URL
        # ---------------------------------------------------------
        href = None

        link_selectors = [
            "h2 a",
            "h2 a.a-link-normal",
            "a.s-link-style",
            "a[href*='/dp/']",
        ]

        for selector in link_selectors:
            try:
                locator = card.locator(selector).first

                if locator.count():
                    candidate = locator.get_attribute("href")

                    if candidate:
                        href = candidate
                        break

            except Exception:
                continue

        if not href:
            continue

        if href.startswith("/"):
            product_url = AMAZON_BASE_URL + href
        elif href.startswith("http"):
            product_url = href
        else:
            product_url = None

        if not product_url:
            continue

        # ---------------------------------------------------------
        # Price
        #
        # .a-offscreen usually contains the complete formatted price
        # such as "₹1,299".
        # ---------------------------------------------------------
        price = None

        price_selectors = [
            ".a-price .a-offscreen",
            "span.a-price-whole",
            ".a-price",
        ]

        for selector in price_selectors:
            try:
                locator = card.locator(selector).first

                if locator.count():
                    price_text = _clean_text(locator.inner_text())

                    if price_text:
                        price = _parse_price(price_text)

                        if price is not None:
                            break

            except Exception:
                continue

        # ---------------------------------------------------------
        # Rating
        # ---------------------------------------------------------
        rating = None

        rating_selectors = [
            "[aria-label*='out of 5 stars']",
            "span.a-icon-alt",
            ".a-icon-alt",
        ]

        for selector in rating_selectors:
            try:
                locator = card.locator(selector).first

                if locator.count():

                    rating_text = (
                        locator.get_attribute("aria-label")
                        or locator.inner_text()
                    )

                    rating = _parse_rating(rating_text)

                    if rating is not None:
                        break

            except Exception:
                continue

        # ---------------------------------------------------------
        # Review count
        # ---------------------------------------------------------
        review_count = None

        review_selectors = [
            "a[href*='customerReviews']",
            "a[href*='#customerReviews']",
            "span[aria-label*='ratings']",
            "span.a-size-base.s-underline-text",
        ]

        for selector in review_selectors:
            try:
                locator = card.locator(selector).first

                if locator.count():

                    review_text = (
                        locator.get_attribute("aria-label")
                        or locator.inner_text()
                    )

                    review_count = _parse_review_count(review_text)

                    if review_count is not None:
                        break

            except Exception:
                continue

        # ---------------------------------------------------------
        # Availability
        #
        # Search-result pages do not always expose reliable
        # availability information. Therefore leave it NULL when
        # it cannot be confidently determined.
        # ---------------------------------------------------------
        availability = None

        try:
            card_text = card.inner_text().lower()

            if "currently unavailable" in card_text:
                availability = "unavailable"

            elif "only" in card_text and "left in stock" in card_text:
                availability = "limited"

            elif "in stock" in card_text:
                availability = "in stock"

        except Exception:
            pass

        # ---------------------------------------------------------
        # Build record
        # ---------------------------------------------------------
        product = {
            "search_term": search_term,
            "product_name": name,
            "product_url": product_url,
            "price": price,
            "rating": rating,
            "review_count": review_count,
            "best_seller_rank": None,
            "search_position": index + 1,
            "availability": availability,
            "scraped_at": scraped_at,
        }

        products.append(product)

    return products


def scrape_amazon(
    search_term: str = "wireless earbuds",
    limit: int = 8,
) -> list[dict]:
    """Scrape the first few publicly visible Amazon India results.

    Raises RuntimeError when Amazon blocks the request or the page
    does not contain usable search results.
    """

    url = (
        f"{AMAZON_BASE_URL}/s"
        f"?k={quote_plus(search_term)}"
    )

    print()
    print("=" * 70)
    print(f"Amazon search: {search_term}")
    print(f"URL: {url}")
    print("=" * 70)

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True
        )

        context = browser.new_context(
            locale="en-IN",
            user_agent=USER_AGENT,
            viewport={
                "width": 1366,
                "height": 900,
            },
            extra_http_headers={
                "Accept-Language": "en-IN,en;q=0.9",
            },
        )

        page = context.new_page()

        try:

            # -----------------------------------------------------
            # Navigate directly to the Amazon search URL.
            # -----------------------------------------------------
            response = page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=30_000,
            )

            if response:
                print(f"HTTP status: {response.status}")

            print(f"Final URL: {page.url}")
            print(f"Page title: {page.title()}")

            # -----------------------------------------------------
            # Give Amazon's dynamic content some time.
            # -----------------------------------------------------
            page.wait_for_timeout(3_000)

            # -----------------------------------------------------
            # Check for CAPTCHA / blocking BEFORE looking for cards.
            # -----------------------------------------------------
            if _is_blocked(page):

                # Save evidence so we can inspect it if necessary.
                try:
                    page.screenshot(
                        path="amazon_blocked.png",
                        full_page=True,
                    )
                    print(
                        "Saved Amazon blocking screenshot: "
                        "amazon_blocked.png"
                    )
                except Exception:
                    pass

                raise RuntimeError(
                    "Amazon returned a CAPTCHA, robot check, "
                    "or access-block page."
                )

            # -----------------------------------------------------
            # Wait specifically for Amazon search-result cards.
            #
            # This is better than simply sleeping for a fixed amount
            # of time because Amazon may load results at different
            # speeds.
            # -----------------------------------------------------
            try:

                page.locator(
                    "[data-component-type='s-search-result']"
                ).first.wait_for(
                    state="attached",
                    timeout=10_000,
                )

            except PlaywrightTimeoutError:

                print(
                    "No search-result card appeared within 10 seconds."
                )

                # Save screenshot + HTML for diagnosis.
                try:
                    page.screenshot(
                        path="amazon_no_results.png",
                        full_page=True,
                    )

                    with open(
                        "amazon_no_results.html",
                        "w",
                        encoding="utf-8",
                    ) as file:
                        file.write(page.content())

                    print(
                        "Saved diagnostic files:"
                    )
                    print("  amazon_no_results.png")
                    print("  amazon_no_results.html")

                except Exception:
                    pass

            # -----------------------------------------------------
            # Extract products.
            # -----------------------------------------------------
            products = _extract_products(
                page=page,
                search_term=search_term,
                limit=limit,
            )

            # -----------------------------------------------------
            # If nothing was extracted, provide useful diagnostics.
            # -----------------------------------------------------
            if not products:

                try:
                    body_text = page.locator("body").inner_text(
                        timeout=5_000
                    )

                    preview = re.sub(
                        r"\s+",
                        " ",
                        body_text,
                    ).strip()

                    print()
                    print("Amazon page text preview:")
                    print(preview[:1000])

                except Exception:
                    pass

                try:
                    page.screenshot(
                        path="amazon_no_products.png",
                        full_page=True,
                    )

                    with open(
                        "amazon_no_products.html",
                        "w",
                        encoding="utf-8",
                    ) as file:
                        file.write(page.content())

                    print()
                    print(
                        "Saved diagnostic files:"
                    )
                    print("  amazon_no_products.png")
                    print("  amazon_no_products.html")

                except Exception:
                    pass

                raise RuntimeError(
                    "Amazon search page loaded, but no usable "
                    "product cards were extracted."
                )

            print()
            print(f"Successfully scraped {len(products)} products.")
            print()

            for product in products:
                print(
                    f"{product['search_position']}. "
                    f"{product['product_name'][:80]}"
                )
                print(
                    f"   Price: {product['price']}"
                    f" | Rating: {product['rating']}"
                    f" | Reviews: {product['review_count']}"
                )

            return products

        except PlaywrightTimeoutError as exc:

            raise RuntimeError(
                f"Amazon page timed out: {exc}"
            ) from exc

        finally:

            context.close()
            browser.close()


if __name__ == "__main__":

    try:

        results = scrape_amazon(
            search_term="wireless earbuds",
            limit=8,
        )

        print()
        print("=" * 70)
        print("FINAL RESULTS")
        print("=" * 70)

        for item in results:

            print(
                f"{item['search_position']}. "
                f"{item['product_name']}"
            )

            print(
                f"   Price: ₹{item['price']}"
                f" | Rating: {item['rating']}"
                f" | Reviews: {item['review_count']}"
            )

            print(
                f"   URL: {item['product_url']}"
            )

    except Exception as exc:

        print()
        print("=" * 70)
        print("AMAZON SCRAPER FAILED")
        print("=" * 70)
        print(str(exc))