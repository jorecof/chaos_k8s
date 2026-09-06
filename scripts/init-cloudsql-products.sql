-- Siembra mínima para Cloud SQL (módulo A.4, U3) — solo lo que data-service
-- necesita para /data/products. orders/inventory quedan solo en el Postgres
-- local (service-a/service-b no hablan con Cloud SQL). La tabla `sales` para
-- /data/analytics queda pendiente (gap G-04, fuera del alcance de hoy).
CREATE TABLE IF NOT EXISTS products (
  id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
  name VARCHAR(100) NOT NULL,
  category VARCHAR(50) NOT NULL,
  price NUMERIC(10,2) NOT NULL,
  stock INTEGER NOT NULL DEFAULT 0
);
INSERT INTO products (name, category, price, stock) VALUES
  ('Laptop X1','Electronics',1299.99,15),
  ('Mouse Pro','Peripherals',49.99,50),
  ('Keyboard MK','Peripherals',89.99,30)
ON CONFLICT DO NOTHING;
