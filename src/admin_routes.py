from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from . import models
from .admin_auth import authenticate_admin, verify_admin_token
from .admin_schemas import (
    AdSpendCreate,
    AdSpendEntry,
    AdminLatestOrderResponse,
    AdminLoginRequest,
    AdminLoginResponse,
    AdminOrderDetail,
    AdminOrderSummary,
    OrderStatusUpdate,
    ProductCostEntry,
    ProductCostUpdate,
)
from .analytics_service import default_date_range, get_metrics, valid_order_filter
from .order_status import ALL_STATUSES, apply_admin_status_filter
from .product_cost_service import ensure_default_products
from .sync_service import run_auto_sync, sync_dhd_order_statuses
from .database import SessionLocal

router = APIRouter(prefix="/api/admin", tags=["admin"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/login", response_model=AdminLoginResponse)
def admin_login(payload: AdminLoginRequest):
    token = authenticate_admin(payload.username.strip(), payload.password)
    if not token:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    from .admin_auth import TOKEN_HOURS

    return AdminLoginResponse(
        access_token=token,
        expires_in_hours=TOKEN_HOURS,
    )


@router.get("/metrics")
def admin_metrics(
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
    sync: bool = Query(False, description="Sync DHD + Meta before computing metrics"),
    db: Session = Depends(get_db),
    _: str = Depends(verify_admin_token),
):
    sync_info = None
    if sync:
        sync_info = run_auto_sync(db)
    metrics = get_metrics(db, date_from, date_to)
    if sync_info:
        metrics["last_sync"] = sync_info
    return metrics


@router.get("/orders", response_model=list[AdminOrderSummary])
def admin_orders(
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: str = Depends(verify_admin_token),
):
    start, end = default_date_range(date_from, date_to)
    query = db.query(models.Order)

    if status:
        query = query.filter(
            or_(
                and_(models.Order.created_at >= start, models.Order.created_at <= end),
                and_(models.Order.updated_at >= start, models.Order.updated_at <= end),
            )
        )
        query = apply_admin_status_filter(query, status)
    else:
        query = query.filter(
            models.Order.created_at >= start,
            models.Order.created_at <= end,
        )

    query = query.order_by(models.Order.updated_at.desc())

    if search:
        term = f"%{search.strip()}%"
        query = query.filter(
            (models.Order.customer_name.like(term))
            | (models.Order.phone.like(term))
            | (models.Order.order_id.like(term))
            | (models.Order.product_name.like(term))
        )

    return query.offset(offset).limit(limit).all()


@router.get("/orders/latest", response_model=AdminLatestOrderResponse)
def admin_latest_order(
    db: Session = Depends(get_db),
    _: str = Depends(verify_admin_token),
):
    order = (
        db.query(models.Order)
        .order_by(models.Order.id.desc())
        .first()
    )
    return {"order": order}


@router.get("/orders/{order_id}", response_model=AdminOrderDetail)
def admin_order_detail(
    order_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(verify_admin_token),
):
    order = (
        db.query(models.Order)
        .filter(models.Order.order_id == order_id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.patch("/orders/{order_id}", response_model=AdminOrderDetail)
def admin_update_order_status(
    order_id: str,
    payload: OrderStatusUpdate,
    db: Session = Depends(get_db),
    _: str = Depends(verify_admin_token),
):
    order = (
        db.query(models.Order)
        .filter(models.Order.order_id == order_id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    order.status = payload.status.strip()
    db.commit()
    db.refresh(order)
    return order


@router.get("/statuses")
def admin_statuses(
    _: str = Depends(verify_admin_token),
):
    return ALL_STATUSES


@router.get("/ad-spend", response_model=list[AdSpendEntry])
def list_ad_spend(
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
    db: Session = Depends(get_db),
    _: str = Depends(verify_admin_token),
):
    start, end = default_date_range(date_from, date_to)
    return (
        db.query(models.DailyAdSpend)
        .filter(
            models.DailyAdSpend.spend_date >= start.date(),
            models.DailyAdSpend.spend_date <= end.date(),
        )
        .order_by(models.DailyAdSpend.spend_date.desc())
        .all()
    )


@router.post("/ad-spend", response_model=AdSpendEntry)
def create_ad_spend(
    payload: AdSpendCreate,
    db: Session = Depends(get_db),
    _: str = Depends(verify_admin_token),
):
    product_id = (payload.product_id or "").strip() or None
    product_name = (payload.product_name or "").strip() or None
    if product_id and not product_name:
        product = (
            db.query(models.ProductCost)
            .filter(models.ProductCost.product_id == product_id)
            .first()
        )
        if product:
            product_name = product.product_name

    row = models.DailyAdSpend(
        spend_date=payload.spend_date,
        platform=payload.platform.strip().lower(),
        product_id=product_id,
        product_name=product_name,
        amount_dzd=payload.amount_dzd,
        notes=(payload.notes or "")[:500] or None,
        source="manual",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/ad-spend/{entry_id}")
def delete_ad_spend(
    entry_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(verify_admin_token),
):
    row = db.query(models.DailyAdSpend).filter(models.DailyAdSpend.id == entry_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Ad spend entry not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.get("/products", response_model=list[ProductCostEntry])
def list_product_costs(
    db: Session = Depends(get_db),
    _: str = Depends(verify_admin_token),
):
    ensure_default_products(db)
    return (
        db.query(models.ProductCost)
        .order_by(models.ProductCost.product_name.asc())
        .all()
    )


@router.patch("/products/{product_id}", response_model=ProductCostEntry)
def update_product_cost(
    product_id: str,
    payload: ProductCostUpdate,
    db: Session = Depends(get_db),
    _: str = Depends(verify_admin_token),
):
    ensure_default_products(db)
    row = (
        db.query(models.ProductCost)
        .filter(models.ProductCost.product_id == product_id.strip())
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Product not found")

    row.purchase_cost_dzd = round(payload.purchase_cost_dzd, 2)
    db.commit()
    db.refresh(row)
    return row


@router.post("/sync/run")
def admin_run_sync(
    db: Session = Depends(get_db),
    _: str = Depends(verify_admin_token),
):
    return run_auto_sync(db)


@router.get("/deliveries")
def admin_deliveries(
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
    sync: bool = Query(False, description="Sync DHD statuses before listing deliveries"),
    db: Session = Depends(get_db),
    _: str = Depends(verify_admin_token),
):
    """Return delivered orders for the period; optional DHD sync."""
    sync_result = sync_dhd_order_statuses(db, limit=500) if sync else {"skipped": True}
    start, end = default_date_range(date_from, date_to)

    query = (
        db.query(models.Order)
        .filter(
            or_(
                and_(models.Order.created_at >= start, models.Order.created_at <= end),
                and_(models.Order.updated_at >= start, models.Order.updated_at <= end),
            )
        )
        .order_by(models.Order.updated_at.desc())
    )
    query = apply_admin_status_filter(query, "تم التسليم")
    orders = query.limit(500).all()

    revenue = round(sum(float(o.total_price or 0) for o in orders), 2)
    return {
        "sync": sync_result,
        "orders": orders,
        "total": len(orders),
        "revenue_delivered": revenue,
        "from": start.date().isoformat(),
        "to": end.date().isoformat(),
    }
