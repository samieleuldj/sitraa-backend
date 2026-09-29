from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class AdminLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_hours: int


class OrderStatusUpdate(BaseModel):
    status: str = Field(min_length=2, max_length=50)


class AdSpendCreate(BaseModel):
    spend_date: date
    platform: str = Field(min_length=2, max_length=50)
    amount_dzd: float = Field(gt=0)
    product_id: Optional[str] = None
    product_name: Optional[str] = None
    notes: Optional[str] = None


class AdSpendEntry(BaseModel):
    id: int
    spend_date: date
    platform: str
    product_id: Optional[str] = None
    product_name: Optional[str] = None
    amount_dzd: float
    notes: Optional[str] = None
    source: Optional[str] = "manual"

    class Config:
        from_attributes = True


class ProductCostUpdate(BaseModel):
    purchase_cost_dzd: float = Field(ge=0)


class ProductCostEntry(BaseModel):
    id: int
    product_id: str
    product_name: str
    purchase_cost_dzd: float

    class Config:
        from_attributes = True


class AdminOrderSummary(BaseModel):
    id: int
    order_id: str
    customer_name: str
    phone: str
    wilaya: str
    commune: str
    product_name: str
    quantity: int
    total_price: float
    status: str
    tracking_number: Optional[str] = None
    risk_score: int
    is_valid_traffic: Optional[bool] = True
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AdminLatestOrderResponse(BaseModel):
    order: Optional[AdminOrderSummary] = None


class AdminOrderDetail(AdminOrderSummary):
    delivery_type: str
    unit_price: Optional[float] = None
    notes: Optional[str] = None
    ip_address: Optional[str] = None
    country_code: Optional[str] = None
    city: Optional[str] = None
    isp: Optional[str] = None
    is_proxy: bool = False
    is_hosting: bool = False
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    referrer: Optional[str] = None
    session_id: Optional[str] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
