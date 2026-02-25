import uuid, random
import pandas as pd
from faker import Faker
from datetime import datetime, timezone

fake = Faker()

EVENT_TYPES  = ["page_view", "add_to_cart", "purchase", "search", "logout"]
PRODUCT_CATS = ["electronics", "clothing", "books", "food", "sports"]

def generate_users(n: int = 100) -> pd.DataFrame:
    return pd.DataFrame([{
        "user_id":    str(uuid.uuid4()),
        "name":       fake.name(),
        "email":      fake.email(),
        "country":    fake.country_code(),
        "created_at": fake.date_time_this_year().isoformat(),
    } for _ in range(n)])

def generate_events(users_df: pd.DataFrame, n: int = 1000) -> pd.DataFrame:
    user_ids = users_df["user_id"].tolist()
    records  = []
    for _ in range(n):
        ts = fake.date_time_this_month()
        records.append({
            "event_id":   str(uuid.uuid4()),
            "user_id":    random.choice(user_ids),
            "event_type": random.choice(EVENT_TYPES),
            "category":   random.choice(PRODUCT_CATS),
            "amount":     round(random.uniform(0, 500), 2),
            "ts":         ts.isoformat(),
            "date":       ts.strftime("%Y-%m-%d"),     # partition key
        })
    return pd.DataFrame(records)

def generate_orders(users_df: pd.DataFrame, n: int = 200) -> pd.DataFrame:
    user_ids = users_df["user_id"].tolist()
    return pd.DataFrame([{
        "order_id":   str(uuid.uuid4()),
        "user_id":    random.choice(user_ids),
        "total":      round(random.uniform(10, 1000), 2),
        "status":     random.choice(["pending", "shipped", "delivered", "cancelled"]),
        "created_at": fake.date_time_this_month().isoformat(),
        "date":       fake.date_this_month().isoformat(),
    } for _ in range(n)])
