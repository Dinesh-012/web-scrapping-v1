"""MVP settings. Change the search terms and score weights here."""
STATE = "Tamil Nadu"
STATE_TRENDS_GEO = "IN-TN"
REGIONS = ["Chennai", "Coimbatore", "Madurai", "Trichy", "Salem"]
SEARCH_TERMS = ["wireless earbuds", "headphones", "smartwatch", "bluetooth speaker", "power bank"]
AMAZON_WEIGHT = 0.60
TRENDS_WEIGHT = 0.40
AMAZON_SIGNAL_WEIGHTS = {
    "position": 0.25, "bsr": 0.30, "reviews": 0.20,
    "rating": 0.15, "availability": 0.10,
}
DB_PATH = "data/demand.db"
