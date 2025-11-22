"""Database models for VoiceMesh."""

from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import String, Boolean, DateTime, Integer, Float, Text, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.api.database import Base


def utcnow() -> datetime:
    """Get current UTC time."""
    return datetime.now(timezone.utc)


class Customer(Base):
    """Customer model - represents a VoiceMesh customer."""

    __tablename__ = "customers"

    # Primary key
    id: Mapped[str] = mapped_column(String(50), primary_key=True)

    # Basic info
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20))

    # API authentication
    api_key: Mapped[Optional[str]] = mapped_column(String(100))  # Plain key (only shown once)
    api_key_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # Voice settings
    default_voice: Mapped[Optional[str]] = mapped_column(String(100))
    default_language: Mapped[str] = mapped_column(String(10), default="en")
    system_prompt: Mapped[Optional[str]] = mapped_column(Text)  # AI conversation prompt
    voice_config: Mapped[Optional[dict]] = mapped_column(JSON)  # Cartesia voice configuration

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Metadata
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relationships
    functions: Mapped[List["Function"]] = relationship("Function", back_populates="customer", cascade="all, delete-orphan")
    calls: Mapped[List["Call"]] = relationship("Call", back_populates="customer", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Customer(id={self.id}, name={self.name}, email={self.email})>"


class Function(Base):
    """Function model - represents a custom function that can be called by the AI."""

    __tablename__ = "functions"

    # Primary key
    id: Mapped[str] = mapped_column(String(50), primary_key=True)

    # Foreign key
    customer_id: Mapped[str] = mapped_column(String(50), ForeignKey("customers.id"), nullable=False, index=True)

    # Function details
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    parameters: Mapped[dict] = mapped_column(JSON)  # JSON schema for parameters
    endpoint_url: Mapped[str] = mapped_column(String(500), nullable=False)
    http_method: Mapped[str] = mapped_column(String(10), default="POST")

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relationships
    customer: Mapped["Customer"] = relationship("Customer", back_populates="functions")

    def __repr__(self) -> str:
        return f"<Function(id={self.id}, name={self.name}, customer_id={self.customer_id})>"


class Call(Base):
    """Call model - represents a voice call record."""

    __tablename__ = "calls"

    # Primary key
    id: Mapped[str] = mapped_column(String(50), primary_key=True)

    # Foreign key
    customer_id: Mapped[str] = mapped_column(String(50), ForeignKey("customers.id"), nullable=False, index=True)

    # Call details
    call_sid: Mapped[Optional[str]] = mapped_column(String(100), index=True)  # SignalWire call SID
    from_number: Mapped[Optional[str]] = mapped_column(String(20))
    to_number: Mapped[Optional[str]] = mapped_column(String(20))
    direction: Mapped[str] = mapped_column(String(20), default="inbound")  # inbound or outbound

    # Call status
    status: Mapped[str] = mapped_column(String(20), default="initiated")  # initiated, in_progress, completed, failed

    # Conversation data
    transcript: Mapped[Optional[str]] = mapped_column(Text)
    recording_url: Mapped[Optional[str]] = mapped_column(String(500))

    # Cost tracking
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    cost_deepgram: Mapped[Optional[float]] = mapped_column(Float)  # STT cost
    cost_cartesia: Mapped[Optional[float]] = mapped_column(Float)  # TTS cost
    cost_llm: Mapped[Optional[float]] = mapped_column(Float)  # LLM cost
    cost_telephony: Mapped[Optional[float]] = mapped_column(Float)  # SignalWire/Daily cost
    cost_total: Mapped[Optional[float]] = mapped_column(Float)

    # Timestamps
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Relationships
    customer: Mapped["Customer"] = relationship("Customer", back_populates="calls")

    def __repr__(self) -> str:
        return f"<Call(id={self.id}, customer_id={self.customer_id}, status={self.status})>"
