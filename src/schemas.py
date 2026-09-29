from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum

class DeliveryType(str, Enum):
    home = "home"
    office = "office"

class OrderBase(BaseModel):
    order_id: str
    customer_name: str
    phone: str
    wilaya: str
    commune: str
    product_id: Optional[str] = None
    product_name: str
    quantity: int = Field(ge=1, le=4)
    unit_price: float = Field(gt=0)
    shipping_cost: Optional[float] = Field(default=None, ge=0)
    total_price: float
    delivery_type: DeliveryType
    notes: Optional[str] = None

class OrderCreate(OrderBase):
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    referrer: Optional[str] = None
    session_id: Optional[str] = None


class AnalyticsEventCreate(BaseModel):
    event_type: str
    session_id: str = Field(min_length=8, max_length=64)
    page_path: Optional[str] = None
    product_id: Optional[str] = None
    product_name: Optional[str] = None
    referrer: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None

class OrderResponse(OrderBase):
    id: int
    status: str
    risk_score: int
    created_at: datetime

    class Config:
        from_attributes = True


class ShipToDhdRequest(BaseModel):
    order_id: str
    customer_name: str
    phone: str
    wilaya: str
    commune: str
    product_name: str
    total_price: float
    delivery_type: str = "منزل"
    notes: Optional[str] = ""


class OrderSyncRequest(BaseModel):
    order_id: str
    status: Optional[str] = None
    tracking_number: Optional[str] = None


class OrderBulkSyncRequest(BaseModel):
    orders: list[OrderSyncRequest]
