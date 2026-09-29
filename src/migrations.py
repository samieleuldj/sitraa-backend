from sqlalchemy import inspect, text

from .database import engine


def _add_column_if_missing(table: str, column: str, ddl: str) -> None:
    inspector = inspect(engine)
    if table not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns(table)}
    if column not in columns:
        with engine.begin() as conn:
            conn.execute(text(ddl))


def ensure_schema_updates() -> None:
    """Add new columns/tables safely on existing MySQL databases."""
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    if "orders" in tables:
        order_columns = {
            "delivery_type": "ALTER TABLE orders ADD COLUMN delivery_type VARCHAR(50) DEFAULT 'home'",
            "unit_price": "ALTER TABLE orders ADD COLUMN unit_price DOUBLE NULL",
            "country_code": "ALTER TABLE orders ADD COLUMN country_code VARCHAR(8) NULL",
            "city": "ALTER TABLE orders ADD COLUMN city VARCHAR(120) NULL",
            "isp": "ALTER TABLE orders ADD COLUMN isp VARCHAR(255) NULL",
            "is_proxy": "ALTER TABLE orders ADD COLUMN is_proxy TINYINT(1) DEFAULT 0",
            "is_hosting": "ALTER TABLE orders ADD COLUMN is_hosting TINYINT(1) DEFAULT 0",
            "is_valid_traffic": "ALTER TABLE orders ADD COLUMN is_valid_traffic TINYINT(1) DEFAULT 1",
            "utm_source": "ALTER TABLE orders ADD COLUMN utm_source VARCHAR(120) NULL",
            "utm_medium": "ALTER TABLE orders ADD COLUMN utm_medium VARCHAR(120) NULL",
            "utm_campaign": "ALTER TABLE orders ADD COLUMN utm_campaign VARCHAR(120) NULL",
            "referrer": "ALTER TABLE orders ADD COLUMN referrer VARCHAR(500) NULL",
            "session_id": "ALTER TABLE orders ADD COLUMN session_id VARCHAR(64) NULL",
            "product_id": "ALTER TABLE orders ADD COLUMN product_id VARCHAR(120) NULL",
            "tracking_number": "ALTER TABLE orders ADD COLUMN tracking_number VARCHAR(120) NULL",
            "shipping_cost": "ALTER TABLE orders ADD COLUMN shipping_cost DOUBLE NULL",
        }
        existing = {col["name"] for col in inspector.get_columns("orders")}
        for column, ddl in order_columns.items():
            if column not in existing:
                with engine.begin() as conn:
                    conn.execute(text(ddl))

    if "analytics_events" not in tables:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE analytics_events (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        event_type VARCHAR(50) NOT NULL,
                        session_id VARCHAR(64) NOT NULL,
                        page_path VARCHAR(500) NULL,
                        product_id VARCHAR(120) NULL,
                        product_name VARCHAR(255) NULL,
                        referrer VARCHAR(500) NULL,
                        utm_source VARCHAR(120) NULL,
                        utm_medium VARCHAR(120) NULL,
                        utm_campaign VARCHAR(120) NULL,
                        user_agent VARCHAR(500) NULL,
                        ip_address VARCHAR(45) NULL,
                        country_code VARCHAR(8) NULL,
                        city VARCHAR(120) NULL,
                        isp VARCHAR(255) NULL,
                        is_proxy TINYINT(1) DEFAULT 0,
                        is_hosting TINYINT(1) DEFAULT 0,
                        is_valid TINYINT(1) DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_event_type (event_type),
                        INDEX idx_session_id (session_id),
                        INDEX idx_product_id (product_id),
                        INDEX idx_is_valid (is_valid),
                        INDEX idx_created_at (created_at)
                    )
                    """
                )
            )

    if "daily_ad_spend" not in tables:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE daily_ad_spend (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        spend_date DATE NOT NULL,
                        platform VARCHAR(50) NOT NULL,
                        product_id VARCHAR(120) NULL,
                        product_name VARCHAR(255) NULL,
                        amount_dzd DOUBLE DEFAULT 0,
                        notes VARCHAR(500) NULL,
                        source VARCHAR(20) DEFAULT 'manual',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_spend_date (spend_date),
                        INDEX idx_platform (platform),
                        INDEX idx_product_id (product_id),
                        INDEX idx_source (source)
                    )
                    """
                )
            )
    else:
        _add_column_if_missing(
            "daily_ad_spend",
            "source",
            "ALTER TABLE daily_ad_spend ADD COLUMN source VARCHAR(20) DEFAULT 'manual'",
        )
        _add_column_if_missing(
            "daily_ad_spend",
            "product_id",
            "ALTER TABLE daily_ad_spend ADD COLUMN product_id VARCHAR(120) NULL",
        )
        _add_column_if_missing(
            "daily_ad_spend",
            "product_name",
            "ALTER TABLE daily_ad_spend ADD COLUMN product_name VARCHAR(255) NULL",
        )

    if "product_costs" not in tables:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE product_costs (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        product_id VARCHAR(120) NOT NULL UNIQUE,
                        product_name VARCHAR(255) NOT NULL,
                        purchase_cost_dzd DOUBLE DEFAULT 0,
                        updated_at TIMESTAMP NULL ON UPDATE CURRENT_TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_product_id (product_id)
                    )
                    """
                )
            )
