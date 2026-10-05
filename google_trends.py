"""Fetch relative Google Trends interest for Tamil Nadu and listed cities."""
from datetime import datetime, timezone

from pytrends.request import TrendReq

from config import REGIONS, SEARCH_TERMS, STATE_TRENDS_GEO


def collect_trends():
    """Use one comparison payload so keyword scores share the same scale.

    Values are relative Google Trends interest, not search volumes. City-level
    rows are stored only when the provider returns the exact configured city.
    """
    # pytrends 4.9.2 uses urllib3's removed ``method_whitelist`` option when
    # retries are enabled; the no-retry path works with current urllib3.
    client = TrendReq(hl="en-IN", tz=330, timeout=(10, 25), retries=0)
    client.build_payload(SEARCH_TERMS, timeframe="today 12-m", geo=STATE_TRENDS_GEO)
    rows = []
    captured = datetime.now(timezone.utc).isoformat()

    timeline = client.interest_over_time()
    for term in SEARCH_TERMS:
        if term in timeline.columns and not timeline.empty:
            score = float(timeline[term].mean())
            rows.append({"search_term": term, "region": "Tamil Nadu", "interest_score": score, "scraped_at": captured})

    # This exact-city lookup intentionally leaves unavailable cities absent.
    city_data = client.interest_by_region(resolution="CITY", inc_low_vol=True)
    if not city_data.empty:
        for term in SEARCH_TERMS:
            if term not in city_data.columns:
                continue
            for city in REGIONS:
                matches = [idx for idx in city_data.index if str(idx).strip().casefold() == city.casefold()]
                if matches:
                    value = float(city_data.loc[matches[0], term])
                    # Trends uses 0 where it cannot report measurable interest;
                    # do not present that as a usable city comparison.
                    if value > 0:
                        rows.append({"search_term": term, "region": city,
                                     "interest_score": value, "scraped_at": captured})
    return rows


if __name__ == "__main__":
    try:
        for row in collect_trends():
            print(f"{row['search_term']} | {row['region']}: {row['interest_score']:.1f}")
    except Exception as exc:
        print(f"Google Trends unavailable: {exc}")
