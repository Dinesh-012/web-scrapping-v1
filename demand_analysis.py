"""Collect available signals, persist them, and calculate the MVP demand score."""
from datetime import datetime, timezone
import math
from pathlib import Path

import pandas as pd

from amazon_scraper import scrape_amazon
from config import AMAZON_SIGNAL_WEIGHTS, AMAZON_WEIGHT, SEARCH_TERMS, TRENDS_WEIGHT
from database import init_db, read_frame, save_amazon, save_scores, save_trends
from google_trends import collect_trends


def _scaled_bsr(values):
    present = [float(v) for v in values if pd.notna(v)]
    if not present:
        return [None] * len(values)
    lo, hi = min(present), max(present)
    return [None if pd.isna(v) else (100.0 if lo == hi else 100 * (hi - float(v)) / (hi - lo)) for v in values]


def calculate_amazon_popularity(products):
    """Return per-search-term mean score; omitted signals redistribute weight."""
    if products.empty:
        return {}
    df = products.copy()
    df["position_score"] = df["search_position"].apply(lambda p: max(0, 110 - 10 * int(p)) if pd.notna(p) else None)
    df["rating_score"] = df["rating"].apply(lambda r: float(r) / 5 * 100 if pd.notna(r) else None)
    max_reviews = max([int(v) for v in df["review_count"].dropna()] or [0])
    df["review_score"] = df["review_count"].apply(lambda r: (100 * math.log1p(int(r)) / math.log1p(max_reviews)) if pd.notna(r) and max_reviews > 0 else None)
    df["bsr_score"] = _scaled_bsr(df["best_seller_rank"].tolist())
    availability = {"in stock": 100, "limited": 50, "unavailable": 0}
    df["availability_score"] = df["availability"].apply(lambda x: availability.get(str(x).strip().lower()) if pd.notna(x) else None)
    mapping = {"position": "position_score", "bsr": "bsr_score", "reviews": "review_score", "rating": "rating_score", "availability": "availability_score"}
    scores = {}
    for term, group in df.groupby("search_term"):
        product_scores = []
        for _, row in group.iterrows():
            available = [(AMAZON_SIGNAL_WEIGHTS[k], row[col]) for k, col in mapping.items() if pd.notna(row[col])]
            total_weight = sum(w for w, _ in available)
            if total_weight >= 0.25:
                product_scores.append(sum(w * float(value) for w, value in available) / total_weight)
        scores[term] = sum(product_scores) / len(product_scores) if product_scores else None
    return scores


def calculate_demand(amazon_scores, trend_rows):
    """Combine relative signals; both inputs stay absent when not observed."""
    if not trend_rows:
        trend_scores = {}
    else:
        averages = {}
        # State score drives the statewide ranking. City rows remain available
        # for the regional chart and never get blended into Tamil Nadu's score.
        for row in trend_rows:
            if row["region"] != "Tamil Nadu":
                continue
            averages.setdefault(row["search_term"], []).append(float(row["interest_score"]))
        means = {term: sum(vals) / len(vals) for term, vals in averages.items()}
        ceiling = max(means.values(), default=0)
        trend_scores = {term: (score * 100 / ceiling if ceiling > 0 else 0) for term, score in means.items()}
    output = []
    created = datetime.now(timezone.utc).isoformat()
    for term in SEARCH_TERMS:
        amazon = amazon_scores.get(term)
        trends = trend_scores.get(term)
        # The combined score is meaningful only when both inputs exist; unlike
        # missing per-product Amazon fields, do not redistribute this weight.
        demand = (amazon * AMAZON_WEIGHT + trends * TRENDS_WEIGHT
                  if amazon is not None and trends is not None else None)
        output.append({"search_term": term, "amazon_popularity": amazon, "regional_interest": trends,
                       "estimated_demand": demand, "created_at": created})
    return output


def run_pipeline():
    init_db()
    try:
        products = scrape_amazon("wireless earbuds", limit=8)
        save_amazon(products)
        # Extend collection to the remaining terms only after the first term worked.
        for term in SEARCH_TERMS[1:]:
            save_amazon(scrape_amazon(term, limit=8))
        print(f"Amazon: saved {len(products)} products for wireless earbuds.")
    except Exception as exc:
        print(f"Amazon signal unavailable; stopping scraper attempts: {exc}")
        fallback_path = Path("amazon_sample.csv")
        try:
            fallback = pd.read_csv(fallback_path)
            expected = {"search_term", "product_name", "product_url", "price", "rating", "review_count",
                        "best_seller_rank", "search_position", "availability", "scraped_at"}
            if not fallback.empty and expected.issubset(fallback.columns):
                fallback = fallback.where(pd.notna(fallback), None)
                rows = fallback[list(expected)].to_dict("records")
                save_amazon(rows)
                print(f"Amazon CSV fallback: saved {len(rows)} user-provided rows from {fallback_path}.")
        except (pd.errors.EmptyDataError, FileNotFoundError):
            pass
    try:
        trends = collect_trends()
        save_trends(trends)
        print(f"Google Trends: saved {len(trends)} available regional rows.")
    except Exception as exc:
        trends = []
        print(f"Google Trends unavailable: {exc}")
    products = read_frame("amazon_products")
    all_trends = read_frame("trends")
    amazon_scores = calculate_amazon_popularity(products)
    scores = calculate_demand(amazon_scores, all_trends.to_dict("records"))
    save_scores(scores)
    print("Estimated demand results:")
    for row in sorted(scores, key=lambda r: r["estimated_demand"] if r["estimated_demand"] is not None else -1, reverse=True):
        demand = "N/A" if row["estimated_demand"] is None else f"{row['estimated_demand']:.1f}"
        print(f"  {row['search_term']}: {demand}")


if __name__ == "__main__":
    run_pipeline()
