import os
import re
import ast
import uuid
import glob
import logging
import pandas as pd
from typing import List, Dict, Any, Optional
from llama_index.core import Document
from rag.models import RAGProduct

logger = logging.getLogger(__name__)

# List of common brands in our indexed categories to resolve missing/generic brand fields
PREDEFINED_BRANDS = [
    "Samsung", "LG", "ASUS", "Dell", "HP", "Lenovo", "Acer", "Apple", "Sony", 
    "OnePlus", "Xiaomi", "Realme", "Oppo", "Vivo", "Motorola", "Nokia", "IFB", 
    "Whirlpool", "Haier", "Godrej", "Bosch", "Mi", "Noise", "boAt", "Fire-Boltt", 
    "Amazfit", "Toshiba", "Panasonic", "Dyson", "Symphony", "Voltas"
]

def _clean_price(val) -> float:
    if pd.isna(val):
        return 0.0
    try:
        cleaned = re.sub(r"[₹,\s]", "", str(val))
        return float(cleaned) if cleaned else 0.0
    except (ValueError, TypeError):
        return 0.0

def _clean_rating(val) -> float:
    if pd.isna(val):
        return 0.0
    try:
        match = re.search(r"(\d+\.?\d*)", str(val))
        return float(match.group(1)) if match else 0.0
    except (ValueError, TypeError):
        return 0.0

def _clean_num_ratings(val) -> int:
    if pd.isna(val):
        return 0
    try:
        s = str(val).strip()
        match = re.search(r"([\d,]+)\s*Ratings", s, re.IGNORECASE)
        if match:
            return int(match.group(1).replace(",", ""))
        match = re.search(r"(\d[\d,]*)", s)
        return int(match.group(1).replace(",", "")) if match else 0
    except (ValueError, TypeError):
        return 0

def _clean_details(val) -> str:
    if pd.isna(val):
        return ""
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

def _detect_category_from_filename(filename: str) -> str:
    fn = filename.lower()
    if "laptop" in fn:
        return "Laptop"
    if "mobile" in fn:
        return "Mobile"
    if "refrigerator" in fn or "fridge" in fn:
        return "Refrigerator"
    if "watch" in fn:
        return "Smart Watch"
    if "tv" in fn:
        return "TV"
    if "washing" in fn or "washer" in fn:
        return "Washing Machine"
    return "Unknown"

def _resolve_brand(row_brand: Any, name: str) -> str:
    if not pd.isna(row_brand) and str(row_brand).strip() and str(row_brand).lower() != "generic":
        return str(row_brand).strip()
    
    # Check if a predefined brand is mentioned in the product name
    name_lower = name.lower()
    for brand in PREDEFINED_BRANDS:
        if brand.lower() in name_lower:
            return brand
            
    return "Unknown"

def generate_product_summary(product: RAGProduct) -> str:
    """Generates a structured, deterministic Option B text summary for a product."""
    details = product.specifications.get("details", "")
    return (
        f"Product Name: {product.name}\n"
        f"Brand: {product.brand}\n"
        f"Category: {product.category}\n"
        f"Price: ₹{product.price:.0f}\n"
        f"Rating: {product.rating:.1f} out of 5 stars ({product.review_count} ratings)\n"
        f"Specifications: {details}"
    )

def create_llama_document(product: RAGProduct) -> Document:
    """Converts a RAGProduct into a validated LlamaIndex Document with metadata exclusions."""
    # 1. Validate required fields
    if not product.product_id:
        raise ValueError("Missing required field: product_id")
    if not product.name or not product.name.strip():
        raise ValueError("Missing required field: name")
    if not product.category or not product.category.strip():
        raise ValueError("Missing required field: category")
    if product.price < 0:
        raise ValueError(f"Invalid price value: {product.price}")

    # 2. Compile document summary text
    summary_text = generate_product_summary(product)

    # 3. Compile metadata
    metadata = {
        "product_id": product.product_id,
        "product_name": product.name,
        "brand": product.brand,
        "category": product.category,
        "price": product.price,
        "mrp": product.mrp,
        "discount": product.discount,
        "rating": product.rating,
        "review_count": product.review_count,
        "image_url": product.image_url,
    }

    # 4. Configure metadata exclusions
    # All metadata is excluded from the embedding text to avoid duplication with the Option B template
    excluded_embed_keys = list(metadata.keys())
    # Exclude technical IDs and image URLs from LLM context to optimize token usage
    excluded_llm_keys = ["product_id", "image_url"]

    return Document(
        text=summary_text,
        metadata=metadata,
        excluded_embed_metadata_keys=excluded_embed_keys,
        excluded_llm_metadata_keys=excluded_llm_keys
    )

class ProductDataPipeline:
    def __init__(self, data_dir: str = None):
        if not data_dir:
            base = os.path.dirname(os.path.dirname(__file__))
            data_dir = os.path.join(base, "data")
        self.data_dir = data_dir

    def load_and_clean_all(self) -> List[RAGProduct]:
        """Automatically discovers CSVs, cleans fields, removes duplicates, and returns structured data models."""
        csv_pattern = os.path.join(self.data_dir, "*.csv")
        csv_files = glob.glob(csv_pattern)
        
        if not csv_files:
            logger.warning(f"No CSV files found in {self.data_dir}")
            return []

        all_products: List[RAGProduct] = []
        seen_products = set()  # Tracks (name, brand, category) to prevent duplicates

        for filepath in csv_files:
            filename = os.path.basename(filepath)
            category = _detect_category_from_filename(filename)
            logger.info(f"Processing CSV: {filename} mapped to Category: {category}")

            try:
                try:
                    df = pd.read_csv(filepath, encoding="utf-8")
                except UnicodeDecodeError:
                    df = pd.read_csv(filepath, encoding="latin1")
            except Exception as e:
                logger.error(f"Failed to read {filename}: {e}")
                continue

            # Skip files missing required columns for parsing Name or Details
            required_cols = {"Name", "Details"}
            if not required_cols.issubset(df.columns):
                logger.warning(f"Skipping {filename}: missing required columns {required_cols - set(df.columns)}")
                continue

            df = df.dropna(subset=["Name", "Details"])
            df = df[df["Name"].str.strip().astype(bool) & df["Details"].str.strip().astype(bool)]

            for _, row in df.iterrows():
                name = str(row["Name"]).strip()
                brand = _resolve_brand(row.get("Brand"), name)
                
                # Deduplication logic
                dup_key = (name.lower(), brand.lower(), category.lower())
                if dup_key in seen_products:
                    continue
                seen_products.add(dup_key)

                price = _clean_price(row.get("Selling Price", 0))
                mrp = _clean_price(row.get("MRP", 0))
                discount = str(row.get("Discount", "")).strip()
                rating = _clean_rating(row.get("Ratings", 0))
                review_count = _clean_num_ratings(row.get("No_of_ratings", 0))
                details = _clean_details(row["Details"])
                image_url = str(row.get("Image_URL", "")).strip()

                # Generate a unique deterministic UUID based on name, brand, and category
                product_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{category}:{brand}:{name}"))

                product = RAGProduct(
                    product_id=product_id,
                    name=name,
                    brand=brand,
                    category=category,
                    price=price,
                    mrp=mrp,
                    discount=discount,
                    rating=rating,
                    review_count=review_count,
                    image_url=image_url,
                    summary="",  # Will be generated in a later phase
                    specifications={"details": details}
                )
                all_products.append(product)

        logger.info(f"Total processed and cleaned products: {len(all_products)}")
        return all_products

    def load_and_build_documents(self) -> List[Document]:
        """Loads and cleans raw data, then generates fully validated LlamaIndex Document nodes."""
        products = self.load_and_clean_all()
        documents: List[Document] = []

        for product in products:
            try:
                doc = create_llama_document(product)
                documents.append(doc)
            except ValueError as e:
                logger.error(f"Validation failed for product '{product.name}': {e}")
                continue

        logger.info(f"Successfully constructed {len(documents)} LlamaIndex Document nodes.")
        return documents

    def ingest_to_astradb(self) -> int:
        """Loads CSV data, builds LlamaIndex Documents, generates local embeddings, and uploads to AstraDB."""
        from llama_index.vector_stores.astra_db import AstraDBVectorStore
        from llama_index.core import VectorStoreIndex, StorageContext, Settings
        from rag.embeddings import EmbeddingManager

        # 1. Build documents
        documents = self.load_and_build_documents()
        if not documents:
            logger.warning("No documents to ingest.")
            return 0

        # 2. Get credentials from environment
        endpoint = os.getenv("ASTRA_DB_API_ENDPOINT")
        token = os.getenv("ASTRA_DB_APPLICATION_TOKEN")
        keyspace = os.getenv("ASTRA_DB_KEYSPACE", "default_keyspace")
        collection = os.getenv("ASTRA_DB_COLLECTION", "flipkart_reviews")

        if not endpoint or not token:
            raise ValueError("Missing AstraDB connection variables (ASTRA_DB_API_ENDPOINT or ASTRA_DB_APPLICATION_TOKEN)")

        # 3. Setup AstraDB vector store
        logger.info(f"Connecting to AstraDB Vector Store Collection: {collection}")
        vector_store = AstraDBVectorStore(
            token=token,
            api_endpoint=endpoint,
            keyspace=keyspace,
            collection_name=collection,
            embedding_dimension=384
        )

        # 4. Configure local embedding model in settings
        embed_manager = EmbeddingManager()
        Settings.embed_model = embed_manager.get_embedding_model()

        # 5. Index documents using VectorStoreIndex
        logger.info("Initializing VectorStoreIndex (calculating embeddings and uploading nodes)...")
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        
        index = VectorStoreIndex.from_documents(
            documents,
            storage_context=storage_context,
            show_progress=True
        )
        
        logger.info(f"Ingestion successful! Loaded {len(documents)} nodes into AstraDB.")
        return len(documents)
