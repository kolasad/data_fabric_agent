-- Sample dataset for the Agent Data Fabric demo.
-- Exercises: FK relationships, a naming-heuristic relationship (no FK),
-- comments, composite-ish keys, and a couple of data types.

CREATE SCHEMA IF NOT EXISTS shop;

CREATE TABLE shop.customers (
    id          SERIAL PRIMARY KEY,
    email       TEXT NOT NULL UNIQUE,
    full_name   TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE shop.customers IS 'People who place orders.';
COMMENT ON COLUMN shop.customers.email IS 'Unique login / contact email.';

CREATE TABLE shop.products (
    id          SERIAL PRIMARY KEY,
    sku         TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    price_cents INTEGER NOT NULL CHECK (price_cents >= 0)
);
COMMENT ON TABLE shop.products IS 'Sellable catalog items.';

CREATE TABLE shop.orders (
    id           SERIAL PRIMARY KEY,
    customer_id  INTEGER NOT NULL REFERENCES shop.customers (id),
    status       TEXT NOT NULL DEFAULT 'pending',
    placed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    total_cents  INTEGER NOT NULL DEFAULT 0
);
COMMENT ON TABLE shop.orders IS 'Customer orders (header).';

CREATE TABLE shop.order_items (
    id          SERIAL PRIMARY KEY,
    order_id    INTEGER NOT NULL REFERENCES shop.orders (id),
    product_id  INTEGER NOT NULL REFERENCES shop.products (id),
    quantity    INTEGER NOT NULL CHECK (quantity > 0),
    unit_cents  INTEGER NOT NULL
);
COMMENT ON TABLE shop.order_items IS 'Line items belonging to an order.';

-- No FK on purpose: relationship inferred by naming heuristic (customer_id -> customers.id).
CREATE TABLE shop.reviews (
    id           SERIAL PRIMARY KEY,
    product_id   INTEGER NOT NULL REFERENCES shop.products (id),
    customer_id  INTEGER NOT NULL,
    rating       SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    body         TEXT
);
COMMENT ON TABLE shop.reviews IS 'Product reviews (customer_id intentionally lacks an FK).';

INSERT INTO shop.customers (email, full_name) VALUES
    ('ada@example.com',  'Ada Lovelace'),
    ('alan@example.com', 'Alan Turing');

INSERT INTO shop.products (sku, name, price_cents) VALUES
    ('SKU-1', 'Mechanical Keyboard', 12900),
    ('SKU-2', 'Ergonomic Mouse',      4500);

INSERT INTO shop.orders (customer_id, status, total_cents) VALUES
    (1, 'paid',    17400),
    (2, 'pending',  4500);

INSERT INTO shop.order_items (order_id, product_id, quantity, unit_cents) VALUES
    (1, 1, 1, 12900),
    (1, 2, 1,  4500),
    (2, 2, 1,  4500);

INSERT INTO shop.reviews (product_id, customer_id, rating, body) VALUES
    (1, 1, 5, 'Fantastic tactile feel.'),
    (2, 2, 4, 'Comfortable for long sessions.');
