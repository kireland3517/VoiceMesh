"""Call model - stores call records and metadata."""

from datetime import datetime
from sqlalchemy import String, DateTime, Integer, Float, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
import uuid

from src.api.database import Base


class Call(Base):
    """
    Call model.

    Stores records of voice calls, including metadata, duration,
    costs, and references to recordings in object storage.
    """

    __tablename__ = "calls"

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

    # Call Information
    call_sid: Mapped[str | None] = mapped_column(
        String(255),
        unique=True,
        nullable=True,
        index=True
    )
    from_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    to_number: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Status
    status: Mapped[str] = mapped_column(
        String(50),
        default="initiated",
        nullable=False
    )

    # Duration (in seconds)
    duration: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Costs (in USD)
    cost_stt: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_llm: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_tts: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_telephony: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_total: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Recording
    recording_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    recording_duration: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Transcript
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Functions Called (JSON string - list of function IDs)
    functions_called: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Error tracking
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Metadata
    metadata_: Mapped[str | None] = mapped_column("metadata", Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    # Relationships
    customer: Mapped["Customer"] = relationship(
        "Customer",
        back_populates="calls"
    )

    # Indexes for performance
    __table_args__ = (
        Index("idx_call_customer_id", "customer_id"),
        Index("idx_call_sid", "call_sid"),
        Index("idx_call_status", "status"),
        Index("idx_call_created_at", "created_at"),
        Index("idx_call_customer_created", "customer_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Call(id={self.id}, customer_id={self.customer_id}, status={self.status})>"
