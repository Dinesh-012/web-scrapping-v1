"""Tiny SQLite persistence layer for the MVP."""
import sqlite3
from pathlib import Path

import pandas as pd

from config import DB_PATH


def connect():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_db():
    with connect() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS amazon_products (
            id INTEGER PRIMARY KEY, search_term TEXT, product_name TEXT, product_url TEXT,
            price REAL, rating REAL, review_count INTEGER, best_seller_rank INTEGER,
            search_position INTEGER, availability TEXT, scraped_at TEXT
        );
        CREATE TABLE IF NOT EXISTS trends (
            id INTEGER PRIMARY KEY, search_term TEXT, region TEXT, interest_score REAL, scraped_at TEXT
        );
        CREATE TABLE IF NOT EXISTS demand_scores (
            id INTEGER PRIMARY KEY, search_term TEXT, amazon_popularity REAL,
            regional_interest REAL, estimated_demand REAL, created_at TEXT
        );
        """)


def save_amazon(rows):
    if not rows:
        return
    with connect() as conn:
        conn.executemany("""INSERT INTO amazon_products
            (search_term, product_name, product_url, price, rating, review_count,
             best_seller_rank, search_position, availability, scraped_at)
             VALUES (:search_term, :product_name, :product_url, :price, :rating,
             :review_count, :best_seller_rank, :search_position, :availability, :scraped_at)""", rows)


def save_trends(rows):
    if not rows:
        return
    with connect() as conn:
        conn.executemany("INSERT INTO trends (search_term, region, interest_score, scraped_at) VALUES (:search_term, :region, :interest_score, :scraped_at)", rows)


def save_scores(rows):
    if not rows:
        return
    with connect() as conn:
        conn.executemany("INSERT INTO demand_scores (search_term, amazon_popularity, regional_interest, estimated_demand, created_at) VALUES (:search_term, :amazon_popularity, :regional_interest, :estimated_demand, :created_at)", rows)


def read_frame(table):
    if table not in {"amazon_products", "trends", "demand_scores"}:
        raise ValueError("Unknown table")
    with connect() as conn:
        return pd.read_sql_query(f"SELECT * FROM {table}", conn)
