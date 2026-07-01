from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class RAGProduct(BaseModel):
    """Shared product document data model placeholder."""
    product_id: str
    name: str
    brand: str
    category: str
    price: float
    mrp: float
    discount: str
    rating: float
    review_count: int
    image_url: str
    summary: str
    specifications: Dict[str, Any] = {}
