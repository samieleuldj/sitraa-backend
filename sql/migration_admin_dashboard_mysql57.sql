-- Velora DZ — Admin dashboard migration (MySQL 5.7 / MariaDB compatible)
-- Run once in EasyPanel → Database → SQL

CREATE TABLE IF NOT EXISTS analytics_events (
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
);

-- Run each line below separately if a column already exists (ignore duplicate errors)

ALTER TABLE orders ADD COLUMN country_code VARCHAR(8) NULL;
ALTER TABLE orders ADD COLUMN city VARCHAR(120) NULL;
ALTER TABLE orders ADD COLUMN isp VARCHAR(255) NULL;
ALTER TABLE orders ADD COLUMN is_proxy TINYINT(1) DEFAULT 0;
ALTER TABLE orders ADD COLUMN is_hosting TINYINT(1) DEFAULT 0;
ALTER TABLE orders ADD COLUMN is_valid_traffic TINYINT(1) DEFAULT 1;
ALTER TABLE orders ADD COLUMN utm_source VARCHAR(120) NULL;
ALTER TABLE orders ADD COLUMN utm_medium VARCHAR(120) NULL;
ALTER TABLE orders ADD COLUMN utm_campaign VARCHAR(120) NULL;
ALTER TABLE orders ADD COLUMN referrer VARCHAR(500) NULL;
ALTER TABLE orders ADD COLUMN session_id VARCHAR(64) NULL;

CREATE TABLE IF NOT EXISTS daily_ad_spend (
  id INT AUTO_INCREMENT PRIMARY KEY,
  spend_date DATE NOT NULL,
  platform VARCHAR(50) NOT NULL,
  amount_dzd DOUBLE DEFAULT 0,
  notes VARCHAR(500) NULL,
  source VARCHAR(20) DEFAULT 'manual',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_spend_date (spend_date),
  INDEX idx_platform (platform),
  INDEX idx_source (source)
);

CREATE TABLE IF NOT EXISTS product_costs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  product_id VARCHAR(120) NOT NULL UNIQUE,
  product_name VARCHAR(255) NOT NULL,
  purchase_cost_dzd DOUBLE DEFAULT 0,
  updated_at TIMESTAMP NULL ON UPDATE CURRENT_TIMESTAMP,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_product_id (product_id)
);

-- Cellulite launch: purchase 3600 DZD, sell 6499 DZD ($25.50 USD)
INSERT INTO product_costs (product_id, product_name, purchase_cost_dzd)
VALUES ('cellulite-device', 'جهاز إزالة السيلوليت والترهلات', 3600)
ON DUPLICATE KEY UPDATE purchase_cost_dzd = 3600, product_name = VALUES(product_name);
