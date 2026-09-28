// Seed data for the MongoDB demo, mirroring examples/seed.sql's shop domain.
db = db.getSiblingDB("shopdb");

db.customers.insertMany([
  { _id: 1, name: "Alice Johnson", email: "alice@example.com" },
  { _id: 2, name: "Bob Smith", email: "bob@example.com" },
  { _id: 3, name: "Carol Diaz", email: null },
]);

db.products.insertMany([
  { _id: 1, name: "Widget", price: 9.99 },
  { _id: 2, name: "Gadget", price: 19.99 },
]);

db.orders.insertMany([
  { _id: 1, customer_id: 1, product_id: 1, total: 9.99, placed_at: new Date() },
  { _id: 2, customer_id: 2, product_id: 2, total: 19.99, placed_at: new Date() },
]);

// No explicit FK to `customers` (Mongo has none) — the naming heuristic
// (`customer_id` -> `customers._id`) is expected to pick this up.
db.reviews.insertMany([
  { _id: 1, customer_id: 1, rating: 5, comment: "Love it!" },
  { _id: 2, customer_id: 3, rating: 3, comment: "It's okay." },
]);
