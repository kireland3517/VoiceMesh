"""Customer model - stores customer information and API keys."""

from datetime import datetime
from typing import List
from sqlalchemy import String, DateTime, Boolean, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
import uuid

from src.api.database import Base


class Customer(Base):
    """
    Customer model.

    Stores customer information, API keys, and configuration.
    Each customer can register multiple functions and make calls.
    """

    __tablename__ = "customers"

    # Primary Key
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True
    )

    # Basic Information
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # API Authentication
    api_key: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True
    )
    api_key_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Configuration
    default_voice: Mapped[str | None] = mapped_column(String(100), nullable=True)
    default_language: Mapped[str] = mapped_column(String(10), default="en", nullable=False)

    # Metadata
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[str | None] = mapped_column("metadata", Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    last_call_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    # Relationships
    functions: Mapped[List["Function"]] = relationship(
        "Function",
        back_populates="customer",
        cascade="all, delete-orphan"
    )
    calls: Mapped[List["Call"]] = relationship(
        "Call",
        back_populates="customer",
        cascade="all, delete-orphan"
    )

    # Indexes for performance
    __table_args__ = (
        Index("idx_customer_email", "email"),
        Index("idx_customer_api_key", "api_key"),
        Index("idx_customer_active", "is_active"),
        Index("idx_customer_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Customer(id={self.id}, email={self.email}, name={self.name})>"
