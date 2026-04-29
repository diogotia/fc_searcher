from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    group_id: Mapped[str] = mapped_column(String(32), index=True)
    message: Mapped[str] = mapped_column(Text, default="")
    author_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    author_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    permalink_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    raw_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="graph")  # graph | webhook | mock_json | playwright_browser
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)

    analyses: Mapped[list["Analysis"]] = relationship(back_populates="post", cascade="all, delete-orphan")


class ExtractedPhone(Base):
    """Phone-like strings parsed from ``Post.message`` (separate table for export and filtering)."""

    __tablename__ = "extracted_phones"
    __table_args__ = (UniqueConstraint("post_id", "phone_normalized", name="uq_extracted_phone_post_norm"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    post_id: Mapped[str] = mapped_column(String(64), ForeignKey("posts.id", ondelete="CASCADE"), index=True)
    phone_raw: Mapped[str] = mapped_column(String(128))
    phone_normalized: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class ExtractedEmail(Base):
    """Email addresses parsed from ``Post.message``."""

    __tablename__ = "extracted_emails"
    __table_args__ = (UniqueConstraint("post_id", "email_normalized", name="uq_extracted_email_post_norm"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    post_id: Mapped[str] = mapped_column(String(64), ForeignKey("posts.id", ondelete="CASCADE"), index=True)
    email_raw: Mapped[str] = mapped_column(String(255))
    email_normalized: Mapped[str] = mapped_column(String(255), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    post_id: Mapped[str] = mapped_column(String(64), ForeignKey("posts.id", ondelete="CASCADE"), index=True)
    model: Mapped[str] = mapped_column(String(128))
    summary: Mapped[str] = mapped_column(Text, default="")
    trends_json: Mapped[list | dict | None] = mapped_column(JSON, nullable=True)
    raw_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)

    post: Mapped["Post"] = relationship(back_populates="analyses")


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_webhook_idempotency_key"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    payload_digest: Mapped[str] = mapped_column(String(128))
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
