"""Customer Pydantic schemas for request/response validation."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, ConfigDict


class CustomerBase(BaseModel):
    """Base customer schema with common fields."""
    name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    phone: Optional[str] = Field(None, max_length=50)
    default_voice: Optional[str] = Field(None, max_length=100)
    default_language: str = Field("en", max_length=10)
    notes: Optional[str] = None


class CustomerCreate(CustomerBase):
    """Schema for creating a new customer."""
    pass


class CustomerUpdate(BaseModel):
    """Schema for updating an existing customer."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=50)
    default_voice: Optional[str] = Field(None, max_length=100)
    default_language: Optional[str] = Field(None, max_length=10)
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class CustomerResponse(CustomerBase):
    """Schema for customer response (includes generated fields)."""
    id: str
    api_key: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime
    last_call_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class CustomerList(BaseModel):
    """Schema for paginated customer list."""
    customers: list[CustomerResponse]
    total: int
    page: int
    page_size: int
