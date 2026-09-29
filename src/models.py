from sqlalchemy import Boolean, Column, Date, DateTime, Float, Integer, String, Text
from sqlalchemy.sql import func

from .database import Base


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(String(64), unique=True, index=True)
    customer_name = Column(String(255), index=True)
    phone = Column(String(20), index=True)
    wilaya = Column(String(100), index=True)
    commune = Column(String(150))
    delivery_type = Column(String(50), default="home")
    product_id = Column(String(120), nullable=True, index=True)
    product_name = Column(String(255), index=True)
    quantity = Column(Integer, default=1)
    tracking_number = Column(String(120), nullable=True, index=True)
    shipping_cost = Column(Float, nullable=True)
    unit_price = Column(Float, nullable=True)
    total_price = Column(Float)
    status = Column(String(50), default="Pending", index=True)
    notes = Column(Text, nullable=True)

    risk_score = Column(Integer, default=0)
    ip_address = Column(String(45), nullable=True)
    country_code = Column(String(8), nullable=True)
    city = Column(String(120), nullable=True)
    isp = Column(String(255), nullable=True)
    is_proxy = Column(Boolean, default=False)
    is_hosting = Column(Boolean, default=False)
    is_valid_traffic = Column(Boolean, default=True, index=True)

    utm_source = Column(String(120), nullable=True)
    utm_medium = Column(String(120), nullable=True)
    utm_campaign = Column(String(120), nullable=True)
    referrer = Column(String(500), nullable=True)
    session_id = Column(String(64), nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class ProductCost(Base):
    __tablename__ = "product_costs"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(String(120), unique=True, index=True)
    product_name = Column(String(255), nullable=False)
    purchase_cost_dzd = Column(Float, default=0)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DailyAdSpend(Base):
    __tablename__ = "daily_ad_spend"

    id = Column(Integer, primary_key=True, index=True)
    spend_date = Column(Date, index=True)
    platform = Column(String(50), index=True)
    product_id = Column(String(120), nullable=True, index=True)
    product_name = Column(String(255), nullable=True)
    amount_dzd = Column(Float, default=0)
    notes = Column(String(500), nullable=True)
    source = Column(String(20), default="manual", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"

    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String(50), index=True)
    session_id = Column(String(64), index=True)
    page_path = Column(String(500), nullable=True)
    product_id = Column(String(120), nullable=True, index=True)
    product_name = Column(String(255), nullable=True)
    referrer = Column(String(500), nullable=True)
    utm_source = Column(String(120), nullable=True)
    utm_medium = Column(String(120), nullable=True)
    utm_campaign = Column(String(120), nullable=True)
    user_agent = Column(String(500), nullable=True)
    ip_address = Column(String(45), nullable=True)
    country_code = Column(String(8), nullable=True)
    city = Column(String(120), nullable=True)
    isp = Column(String(255), nullable=True)
    is_proxy = Column(Boolean, default=False)
    is_hosting = Column(Boolean, default=False)
    is_valid = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
