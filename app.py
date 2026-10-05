import pandas as pd
import streamlit as st

from config import REGIONS, STATE
from database import read_frame

st.set_page_config(page_title="Regional Product Demand Intelligence", page_icon="📊", layout="wide")
st.title("Regional Product Demand Intelligence")
st.subheader("Amazon + Google Trends Market Signal Analysis")
st.caption(f"State: **{STATE}** · The listed cities are representative locations only.")

scores = read_frame("demand_scores")
products = read_frame("amazon_products")
trends = read_frame("trends")

if scores.empty:
    st.info("No collection data yet. Run `python demand_analysis.py` to collect available signals.")
    latest = pd.DataFrame(columns=["search_term", "amazon_popularity", "regional_interest", "estimated_demand"])
else:
    scores["created_at"] = pd.to_datetime(scores["created_at"], errors="coerce", utc=True)
    latest = scores.sort_values("created_at").drop_duplicates("search_term", keep="last")
    latest = latest.sort_values("estimated_demand", ascending=False, na_position="last").reset_index(drop=True)

count = len(latest)
ranked = latest.dropna(subset=["estimated_demand"])
top = ranked.iloc[0] if not ranked.empty else None
cols = st.columns(3)
cols[0].metric("Products Analyzed", count)
cols[1].metric("Top Product", top["search_term"].title() if top is not None else "N/A")
cols[2].metric("Highest Demand Score", f"{top['estimated_demand']:.1f}" if top is not None else "N/A")

st.markdown("### Top Products")
if not latest.empty:
    table = latest.copy()
    score_ranks = {term: i + 1 for i, term in enumerate(latest.dropna(subset=["estimated_demand"]) ["search_term"].tolist())}
    table.insert(0, "Rank", [score_ranks.get(term, "N/A") for term in table["search_term"]])
    table = table.rename(columns={"search_term": "Product", "amazon_popularity": "Amazon Popularity",
                                  "regional_interest": "Regional Interest", "estimated_demand": "Estimated Demand"})
    st.dataframe(table[["Rank", "Product", "Amazon Popularity", "Regional Interest", "Estimated Demand"]],
                 hide_index=True, use_container_width=True, column_config={
                     "Amazon Popularity": st.column_config.NumberColumn(format="%.1f"),
                     "Regional Interest": st.column_config.NumberColumn(format="%.1f"),
                     "Estimated Demand": st.column_config.NumberColumn(format="%.1f"),
                 })
    chart = latest.dropna(subset=["estimated_demand"]).set_index("search_term")[["estimated_demand"]]
    if not chart.empty:
        st.bar_chart(chart, y="estimated_demand", height=280)
else:
    st.caption("Scores will appear after the first collection run.")

st.markdown("### Product Detail")
if not latest.empty:
    selected = st.selectbox("Select a product", latest["search_term"].tolist())
    row = latest[latest["search_term"] == selected].iloc[0]
    amazon_rows = products[products["search_term"] == selected] if not products.empty else pd.DataFrame()
    detail = st.columns(3)
    for col, key, label in zip(detail, ["estimated_demand", "amazon_popularity", "regional_interest"],
                               ["Estimated Demand", "Amazon Popularity", "Regional Interest"]):
        value = row[key]
        col.metric(label, f"{value:.1f}" if pd.notna(value) else "N/A")
    if not amazon_rows.empty:
        amazon_rows = amazon_rows.sort_values("scraped_at").tail(1)
        item = amazon_rows.iloc[0]
        a, b, c, d, e = st.columns(5)
        a.metric("Amazon Rating", item["rating"] if pd.notna(item["rating"]) else "N/A")
        b.metric("Review Count", f"{int(item['review_count']):,}" if pd.notna(item["review_count"]) else "N/A")
        c.metric("BSR", f"{int(item['best_seller_rank']):,}" if pd.notna(item["best_seller_rank"]) else "N/A")
        d.metric("Price", f"₹{item['price']:,.0f}" if pd.notna(item["price"]) else "N/A")
        e.metric("Search Position", int(item["search_position"]) if pd.notna(item["search_position"]) else "N/A")
        st.caption(f"Availability: {item['availability'] if pd.notna(item['availability']) else 'Unavailable from page'}")
        st.caption(f"Amazon product: [{item['product_name']}]({item['product_url']})")
    else:
        st.info("Amazon product signals are unavailable for this term.")

    st.markdown("### Regional Search Interest")
    regional = trends[(trends["search_term"] == selected) & (trends["region"].isin(REGIONS)) & (trends["interest_score"] > 0)] if not trends.empty else pd.DataFrame()
    if not regional.empty:
        regional = regional.sort_values("scraped_at").drop_duplicates("region", keep="last").set_index("region")[["interest_score"]]
        st.bar_chart(regional, y="interest_score", height=260)
    else:
        st.info("City-level Google Trends data unavailable for this query. No city values have been inferred.")
    state_row = trends[(trends["search_term"] == selected) & (trends["region"] == STATE)] if not trends.empty else pd.DataFrame()
    if not state_row.empty:
        st.caption(f"Tamil Nadu relative interest score: {state_row.iloc[-1]['interest_score']:.1f}")

st.caption("Google Trends values represent relative search interest within the compared queries and period, not absolute search volume.")
st.divider()
st.markdown("**Disclaimer:** Estimated demand is based on publicly observable Amazon product signals and Google Trends regional interest. It does not represent actual units sold or verified sales volume.")
