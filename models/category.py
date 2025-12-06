# models/category.py

from uuid import UUID
from pydantic import BaseModel, ConfigDict


class DocumentCategory(BaseModel):
    """Model for document categories from document_categories table."""
    id: UUID
    name: str

    model_config = ConfigDict(from_attributes=True)


class DocumentSubcategory(BaseModel):
    """Model for document subcategories from document_subcategories table."""
    id: UUID
    name: str
    category_id: UUID  # Foreign key to document_categories

    model_config = ConfigDict(from_attributes=True)

