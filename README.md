# Regional Product Demand Intelligence

A local MVP that combines publicly observable Amazon India product signals with Google Trends interest for Tamil Nadu. It ranks the configured product searches using an **Estimated Demand Score**. It does not estimate or report actual units sold.

Amazon popularity uses search position, BSR, review count, rating, and availability where those signals exist. The heuristic weights are configurable and are not scientifically validated. Missing Amazon signals are excluded and the remaining Amazon weights are redistributed. The combined estimated demand score uses the configured Amazon and Trends weights only when both components exist; otherwise, the missing component and combined score remain N/A.

Google Trends values are relative interest on a normalized comparison scale, not absolute search volumes. City-level results are recorded only when Google Trends returns one of the configured city names. Tamil Nadu results may be available even when city results are not. Chennai, Coimbatore, Madurai, Trichy, and Salem are representative locations only, not an exhaustive or exact measure of statewide demand.

## Installation

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

## Run

Collect available data and calculate scores:

```powershell
python demand_analysis.py
```

Start the dashboard:

```powershell
streamlit run app.py
```

The search terms and scoring weights are in `config.py`. Results are stored in `data/demand.db`.

## Amazon access and limitations

Amazon may return a CAPTCHA, block, or unusable page. The scraper stops when it cannot read usable product cards and does not invent results. If Amazon access is unavailable, the dashboard still runs and shows Amazon popularity and the combined score as unavailable. To provide real, manually gathered observations, fill the rows in `amazon_sample.csv` using the same columns; the collection script imports non-empty rows as a CSV fallback. Amazon BSR is an overall popularity/ranking signal, not a Tamil Nadu sales measure. Google Trends is relative; city-level data may be unavailable. The five configured cities are representative locations only.
