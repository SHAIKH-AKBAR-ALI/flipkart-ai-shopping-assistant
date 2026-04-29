import ast
import os
import re

import pandas as pd
from langchain_core.documents import Document

_CATEGORY_MAP = {
    "flipkart_laptops": "Laptop",
    "flipkart_mobiles": "Mobile",
    "flipkart_refrigerator": "Refrigerator",
    "flipkart_smart_watch": "Smart Watch",
    "flipkart_tv": "TV",
    "flipkart_washing_machine": "Washing Machine",
}


def _clean_price(val) -> int:
    try:
        return int(re.sub(r"[₹,\s]", "", str(val)))
    except (ValueError, TypeError):
        return 0


def _clean_rating(val) -> float:
    try:
        match = re.search(r"(\d+\.?\d*)", str(val))
        return float(match.group(1)) if match else 0.0
    except (ValueError, TypeError):
        return 0.0


def _clean_num_ratings(val) -> int:
    try:
        s = str(val)
        match = re.search(r"([\d,]+)\s*Ratings", s, re.IGNORECASE)
        if match:
            return int(match.group(1).replace(",", ""))
        match = re.search(r"(\d[\d,]*)", s)
        return int(match.group(1).replace(",", "")) if match else 0
    except (ValueError, TypeError):
        return 0


def _clean_details(val) -> str:
    s = str(val).strip()
    try:
        parsed = ast.literal_eval(s)
        if isinstance(parsed, list):
            return " | ".join(str(item).strip() for item in parsed if str(item).strip())
        return str(parsed).strip()
    except Exception:
        items = re.findall(r"'([^']*)'|\"([^\"]*)\"", s)
        if items:
            extracted = [a or b for a, b in items if (a or b).strip()]
            if extracted:
                return " | ".join(extracted)
        return s


def load_documents() -> list[Document]:
    base = os.path.dirname(os.path.dirname(__file__))
    data_dir = os.path.join(base, "data")

    documents = []

    for filename, category in _CATEGORY_MAP.items():
        csv_path = os.path.join(data_dir, f"{filename}.csv")
        if not os.path.exists(csv_path):
            print(f"Warning: {csv_path} not found, skipping.")
            continue

        try:
            df = pd.read_csv(csv_path, encoding="utf-8")
        except UnicodeDecodeError:
            df = pd.read_csv(csv_path, encoding="latin1")

        df = df.dropna(subset=["Name", "Details"])
        df = df[df["Name"].str.strip().astype(bool) & df["Details"].str.strip().astype(bool)]

        for _, row in df.iterrows():
            name = str(row["Name"]).strip()
            brand = str(row.get("Brand", "")).strip()
            price = _clean_price(row.get("Selling Price", 0))
            mrp = _clean_price(row.get("MRP", 0))
            discount = str(row.get("Discount", "")).strip()
            rating = _clean_rating(row.get("Ratings", 0))
            num_ratings = _clean_num_ratings(row.get("No_of_ratings", 0))
            details = _clean_details(row["Details"])

            doc = Document(
                page_content=f"{name}. {brand}. {details}",
                metadata={
                    "product_name": name,
                    "brand": brand,
                    "price": price,
                    "mrp": mrp,
                    "discount": discount,
                    "rating": rating,
                    "num_ratings": num_ratings,
                    "category": category,
                },
            )
            documents.append(doc)

    print(f"Loaded {len(documents)} documents from {len(_CATEGORY_MAP)} CSV files.")
    return documents
