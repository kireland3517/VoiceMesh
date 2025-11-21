"""Function model - stores registered functions for customers."""

from datetime import datetime
from sqlalchemy import String, DateTime, Boolean, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
import uuid

from src.api.database import Base


class Function(Base):
    """
    Function model.

    Stores registered functions that can be called during voice conversations.
    Functions are defined per customer and execute via MCP sandbox.
    """

    __tablename__ = "functions"

    # Primary Key
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True
    )

    # Foreign Key
    customer_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Function Definition
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Function Code
    code: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(50), default="python", nullable=False)

    # Function Schema (JSON string)
    parameters_schema: Mapped[str | None] = mapped_column(Text, nullable=True)
    return_schema: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_validated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Execution Stats
    total_calls: Mapped[int] = mapped_column(default=0, nullable=False)
    last_called_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    # Metadata
    tags: Mapped[str | None] = mapped_column(Text, nullable=True)
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

    # Relationships
    customer: Mapped["Customer"] = relationship(
        "Customer",
        back_populates="functions"
    )

    # Indexes for performance
    __table_args__ = (
        Index("idx_function_customer_id", "customer_id"),
        Index("idx_function_name", "name"),
        Index("idx_function_active", "is_active"),
        Index("idx_function_customer_name", "customer_id", "name"),
    )

    def __repr__(self) -> str:
        return f"<Function(id={self.id}, name={self.name}, customer_id={self.customer_id})>"
