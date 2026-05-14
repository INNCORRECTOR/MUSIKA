from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Date,
    Enum as SqlEnum,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
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


class AdmissionApplication(Base):
    __tablename__ = "admission_applications"
    __table_args__ = (
        Index("ix_admission_status_created_at", "status", "created_at"),
        Index("ix_admission_created_at", "created_at"),
        Index("ix_admission_name", "last_name", "first_name"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    first_name: Mapped[str] = mapped_column(String(120), nullable=False)
    last_name: Mapped[str] = mapped_column(String(120), nullable=False)
    gender: Mapped[str | None] = mapped_column(String(30), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    guardian_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    guardian_relation: Mapped[str | None] = mapped_column(String(50), nullable=True)
    guardian_occupation: Mapped[str | None] = mapped_column(String(180), nullable=True)
    address_line: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    pin_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    special_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    discipline: Mapped[str | None] = mapped_column(String(150), nullable=True)
    grade: Mapped[str | None] = mapped_column(String(100), nullable=True)
    affiliated: Mapped[str | None] = mapped_column(String(150), nullable=True)
    preferred_teacher: Mapped[str | None] = mapped_column(String(150), nullable=True)
    passport_photo_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    passport_photo_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="new", nullable=False)
    is_seen: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        nullable=False,
    )

    contacts: Mapped[list["AdmissionContact"]] = relationship(
        "AdmissionContact",
        back_populates="application",
        order_by="AdmissionContact.sort_order",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    review: Mapped["AdmissionAdminReview | None"] = relationship(
        "AdmissionAdminReview",
        back_populates="application",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )


class AdmissionDiscipline(Base):
    __tablename__ = "admission_disciplines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )

    grades: Mapped[list["AdmissionGrade"]] = relationship(
        "AdmissionGrade",
        back_populates="discipline",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AdmissionGrade.sort_order",
    )
    teachers: Mapped[list["AdmissionTeacher"]] = relationship(
        "AdmissionTeacher",
        back_populates="discipline",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AdmissionTeacher.name",
    )


class AdmissionGrade(Base):
    __tablename__ = "admission_grades"
    __table_args__ = (
        Index("ix_admission_grades_discipline_id", "discipline_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    discipline_id: Mapped[int] = mapped_column(
        ForeignKey("admission_disciplines.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )

    discipline: Mapped["AdmissionDiscipline"] = relationship(
        "AdmissionDiscipline", back_populates="grades"
    )


class AdmissionTeacher(Base):
    __tablename__ = "admission_teachers"
    __table_args__ = (
        Index("ix_admission_teachers_discipline_id", "discipline_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    discipline_id: Mapped[int] = mapped_column(
        ForeignKey("admission_disciplines.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )

    discipline: Mapped["AdmissionDiscipline"] = relationship(
        "AdmissionDiscipline", back_populates="teachers"
    )


class AdmissionContact(Base):
    __tablename__ = "admission_contacts"
    __table_args__ = (
        Index("ix_admission_contacts_admission_id", "admission_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    admission_id: Mapped[int] = mapped_column(
        ForeignKey("admission_applications.id", ondelete="CASCADE"), nullable=False
    )
    contact_value: Mapped[str] = mapped_column(String(40), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    application: Mapped["AdmissionApplication"] = relationship(
        "AdmissionApplication", back_populates="contacts"
    )


class AdmissionAdminReview(Base):
    __tablename__ = "admission_admin_reviews"
    __table_args__ = (
        Index("ix_admission_admin_reviews_user_id", "reviewed_by_user_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    admission_id: Mapped[int] = mapped_column(
        ForeignKey("admission_applications.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    reviewed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    accepted: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    fees_amount_inr: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    invoice_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    invoice_dated: Mapped[date | None] = mapped_column(Date, nullable=True)
    payment_method: Mapped[str | None] = mapped_column(String(30), nullable=True)
    course_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    course_duration: Mapped[str | None] = mapped_column(String(120), nullable=True)
    class_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=text("CURRENT_TIMESTAMP"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        nullable=False,
    )

    application: Mapped["AdmissionApplication"] = relationship(
        "AdmissionApplication", back_populates="review"
    )
    reviewed_by: Mapped["User | None"] = relationship("User")


class AdmissionPaymentSettings(Base):
    """Singleton row (id=1): bank / UPI / QR used for fee instructions (admin + WhatsApp + PDF)."""

    __tablename__ = "admission_payment_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    account_holder_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    bank_account_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    bank_ifsc: Mapped[str | None] = mapped_column(String(20), nullable=True)
    upi_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    scanner_image_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    scanner_image_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        nullable=False,
    )
