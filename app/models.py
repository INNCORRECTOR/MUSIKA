from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    DateTime,
    Date,
    Enum as SqlEnum,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    Time,
    TIMESTAMP,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    forgot_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    forgot_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class GalleryGenre(Base):
    __tablename__ = "gallery_genres"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class GalleryImage(Base):
    __tablename__ = "gallery_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    genre_id: Mapped[int] = mapped_column(
        ForeignKey("gallery_genres.id", ondelete="CASCADE"), nullable=False, index=True
    )
    s3_key: Mapped[str] = mapped_column(String(512), nullable=False)
    image_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class Artist(Base):
    __tablename__ = "artists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    hero_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    featured_media_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    featured_media_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    featured_media_thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    facebook_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    instagram_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    twitter_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    whatsapp_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    youtube_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    spotify_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    youtube_music_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    amazon_music_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    imusic_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        nullable=False,
    )


class Media(Base):
    __tablename__ = "media"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    artist_id: Mapped[int] = mapped_column(
        ForeignKey("artists.id", ondelete="CASCADE"), nullable=False, index=True
    )
    media_type: Mapped[str] = mapped_column(
        SqlEnum("image", "video", name="media_type_enum"), nullable=False
    )
    media_url: Mapped[str] = mapped_column(Text, nullable=False)
    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )


class CourseFeeStructure(Base):
    __tablename__ = "course_fee_structures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mode: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    data_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_event_date", "event_date"),
        Index("ix_events_event_date_event_time", "event_date", "event_time"),
        Index("ix_events_state_event_date", "state", "event_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    event_time: Mapped[time] = mapped_column(Time, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        nullable=False,
    )

    images: Mapped[list["EventImage"]] = relationship(
        "EventImage",
        back_populates="event",
        order_by="EventImage.created_at",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class EventImage(Base):
    __tablename__ = "event_images"
    __table_args__ = (
        Index("ix_event_images_event_id_created_at", "event_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    image_url: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )

    event: Mapped["Event"] = relationship("Event", back_populates="images")


class ContactMessage(Base):
    __tablename__ = "contact_messages"
    __table_args__ = (
        Index("ix_contact_messages_created_at", "created_at"),
        Index("ix_contact_messages_email", "email"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_seen: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )


class NewsletterSubscription(Base):
    __tablename__ = "newsletter_subscriptions"
    __table_args__ = (
        Index("ix_newsletter_subscriptions_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_seen: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        nullable=False,
    )
