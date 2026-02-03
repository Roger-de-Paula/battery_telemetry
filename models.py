from datetime import datetime
from decimal import Decimal
from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Device(Base):
    __tablename__ = "devices"

    device_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="online")

    telemetry_rows: Mapped[list["Telemetry"]] = relationship(
        "Telemetry", back_populates="device", cascade="all, delete-orphan"
    )
    alerts_rows: Mapped[list["Alert"]] = relationship(
        "Alert", back_populates="device", cascade="all, delete-orphan"
    )


class Telemetry(Base):
    __tablename__ = "telemetry"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("devices.device_id", ondelete="CASCADE"), nullable=False
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    soc_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    voltage_v: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    current_a: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    temp_c: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False)

    device: Mapped["Device"] = relationship("Device", back_populates="telemetry_rows")


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("devices.device_id", ondelete="CASCADE"), nullable=False
    )
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    device: Mapped["Device"] = relationship("Device", back_populates="alerts_rows")
