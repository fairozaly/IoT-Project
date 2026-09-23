PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS Customers (
    customer_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name      TEXT NOT NULL,
    last_name       TEXT NOT NULL,
    address         TEXT NOT NULL,
    phone           TEXT UNIQUE,
    email           TEXT UNIQUE              
);

CREATE TABLE IF NOT EXISTS Products (
    product_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    barcode         TEXT UNIQUE NOT NULL,   
    price           REAL NOT NULL,
    quantity        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS Transactions (
    transaction_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id      INTEGER,
    transaction_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    total_amount     REAL NOT NULL,
    status           TEXT NOT NULL DEFAULT 'completed',
    FOREIGN KEY (customer_id) REFERENCES Customers(customer_id)
);

CREATE TABLE IF NOT EXISTS TransactionItems (
    transaction_item_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id          INTEGER NOT NULL,
    product_id              INTEGER NOT NULL,
    quantity                INTEGER NOT NULL,
    price_at_sale           REAL NOT NULL,   
    FOREIGN KEY (transaction_id) REFERENCES Transactions(transaction_id),
    FOREIGN KEY (product_id) REFERENCES Products(product_id)
);

CREATE TABLE IF NOT EXISTS PaymentMethods (
    payment_method_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id      INTEGER NOT NULL,
    card_type           TEXT,              
    status              TEXT NOT NULL DEFAULT 'approved',
    FOREIGN KEY (transaction_id) REFERENCES Transactions(transaction_id)
);