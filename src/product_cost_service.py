import os
from typing import Optional

from sqlalchemy.orm import Session

from . import models


# Cellulite launch — purchase 3600 DZD ($25.50 USD), sell 5900 DZD
CELLULITE_PURCHASE_DZD = 3600.0
CELLULITE_PURCHASE_USD = 25.50
CELLULITE_SELL_DZD = 5900.0
USD_TO_DZD_FROM_PURCHASE = round(CELLULITE_PURCHASE_DZD / CELLULITE_PURCHASE_USD, 2)  # 141.18

MINI_CLIMA_PURCHASE_DZD = 1450.0
MINI_CLIMA_SELL_DZD = 2900.0

MAKEUP_BAG_PURCHASE_DZD = 2800.0
MAKEUP_BAG_SELL_DZD = 5500.0

HOOD_MAT_PURCHASE_DZD = 2200.0
HOOD_MAT_SELL_DZD = 3900.0

DEFAULT_PRODUCTS = [
    {"product_id": "thermal-massage-brace", "product_name": "جهاز تدليك حراري واهتزاز 3 في 1"},
    {"product_id": "cellulite-device", "product_name": "جهاز إزالة السيلوليت والترهلات"},
    {"product_id": "makeup-organizer-bag", "product_name": "حقيبة تنظيم المكياج الذكية مع مرآة LED"},
    {"product_id": "mini-clima-geant", "product_name": "Mini Clima Geant 3 في 1 — مكيف محمول"},
    {"product_id": "lumbar-belt", "product_name": "حزام دعم قطني للظهر"},
    {"product_id": "car-cushion", "product_name": "وسادة مقعد السيارة"},
    {"product_id": "orthopedic-pillow", "product_name": "وسادة طبية"},
    {"product_id": "hood-insulation-mat", "product_name": "موكات"},
]

LAUNCH_PURCHASE_COSTS = {
    "cellulite-device": CELLULITE_PURCHASE_DZD,
    "makeup-organizer-bag": MAKEUP_BAG_PURCHASE_DZD,
    "mini-clima-geant": MINI_CLIMA_PURCHASE_DZD,
    "hood-insulation-mat": HOOD_MAT_PURCHASE_DZD,
}


def get_cogs_ratio_fallback() -> float:
    try:
        return float(os.getenv("DEFAULT_COGS_RATIO", "0.55"))
    except ValueError:
        return 0.55


def ensure_default_products(db: Session) -> None:
    for item in DEFAULT_PRODUCTS:
        launch_cost = LAUNCH_PURCHASE_COSTS.get(item["product_id"], 0)
        row = (
            db.query(models.ProductCost)
            .filter(models.ProductCost.product_id == item["product_id"])
            .first()
        )
        if not row:
            db.add(
                models.ProductCost(
                    product_id=item["product_id"],
                    product_name=item["product_name"],
                    purchase_cost_dzd=launch_cost,
                )
            )
        elif launch_cost and float(row.purchase_cost_dzd or 0) == 0:
            row.purchase_cost_dzd = launch_cost
    db.commit()


def get_product_cost_row(
    db: Session,
    product_id: Optional[str] = None,
    product_name: Optional[str] = None,
) -> Optional[models.ProductCost]:
    if product_id:
        row = (
            db.query(models.ProductCost)
            .filter(models.ProductCost.product_id == product_id.strip())
            .first()
        )
        if row:
            return row

    name = (product_name or "").strip()
    if not name:
        return None

    row = (
        db.query(models.ProductCost)
        .filter(models.ProductCost.product_name == name)
        .first()
    )
    if row:
        return row

    return (
        db.query(models.ProductCost)
        .filter(models.ProductCost.product_name.like(f"%{name[:40]}%"))
        .first()
    )


def order_product_cost(db: Session, order: models.Order) -> float:
    qty = max(1, int(order.quantity or 1))
    row = get_product_cost_row(db, order.product_id, order.product_name)
    if row and float(row.purchase_cost_dzd or 0) > 0:
        return round(float(row.purchase_cost_dzd) * qty, 2)

    unit = float(order.unit_price or 0)
    if unit > 0:
        return round(unit * qty * get_cogs_ratio_fallback(), 2)

    total = float(order.total_price or 0)
    return round(total * get_cogs_ratio_fallback(), 2)
