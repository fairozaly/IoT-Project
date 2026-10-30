PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS Customers (
    customer_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name      TEXT NOT NULL,
    last_name       TEXT NOT NULL,
    address         TEXT NOT NULL,
    phone           TEXT UNIQUE,
    email           TEXT UNIQUE,
    membership_number TEXT NOT NULL UNIQUE,
    total_points    INTEGER NOT NULL DEFAULT 0 CHECK (total_points >= 0)
);

CREATE TABLE IF NOT EXISTS Products (
    product_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    category        TEXT NOT NULL,
    upc             TEXT NOT NULL UNIQUE CHECK (length(upc) <= 13),
    epc             TEXT NOT NULL UNIQUE CHECK (length(epc) <= 24),
    SDK             TEXT UNIQUE,
    price           REAL NOT NULL CHECK (price >= 0),
    quantity        INTEGER NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    company         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ProductReceptions (
    reception_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id        INTEGER NOT NULL,
    quantity_received INTEGER NOT NULL CHECK (quantity_received > 0),
    received_at       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    supplier          TEXT,
    FOREIGN KEY (product_id) REFERENCES Products(product_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS Transactions (
    transaction_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id      INTEGER,
    transaction_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    total_amount     REAL NOT NULL CHECK (total_amount >= 0),
    status           TEXT NOT NULL DEFAULT 'completed',
    points_earned    INTEGER NOT NULL DEFAULT 0 CHECK (points_earned >= 0),
    points_redeemed  INTEGER NOT NULL DEFAULT 0 CHECK (points_redeemed >= 0),
    receipt_number   TEXT UNIQUE,
    receipt_email_sent INTEGER NOT NULL DEFAULT 0 CHECK (receipt_email_sent IN (0, 1)),
    emailed_at       TEXT,
    FOREIGN KEY (customer_id) REFERENCES Customers(customer_id)
);

CREATE TABLE IF NOT EXISTS TransactionItems (
    transaction_item_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id          INTEGER NOT NULL,
    product_id              INTEGER NOT NULL,
    quantity                INTEGER NOT NULL CHECK (quantity > 0),
    price_at_sale           REAL NOT NULL CHECK (price_at_sale >= 0),
    FOREIGN KEY (transaction_id) REFERENCES Transactions(transaction_id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES Products(product_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS PaymentMethods (
    payment_method_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id      INTEGER NOT NULL,
    card_type           TEXT,
    method              TEXT NOT NULL DEFAULT 'card',
    amount              REAL NOT NULL CHECK (amount >= 0),
    status              TEXT NOT NULL DEFAULT 'approved',
    paid_at             TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (transaction_id) REFERENCES Transactions(transaction_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS Sensors (
    sensor_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    location    TEXT NOT NULL,
    temp_threshold REAL NOT NULL,
    humid_threshold REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS SensorReadings (
    reading_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    sensor_id   INTEGER NOT NULL,
    timestamp   TEXT DEFAULT CURRENT_TIMESTAMP,
    temperature REAL NOT NULL,
    humidity    REAL NOT NULL,
    FOREIGN KEY (sensor_id) REFERENCES Sensors(sensor_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS Alerts (
    alert_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    reading_id  INTEGER NOT NULL,
    alert_type  TEXT NOT NULL,
    resolved    INTEGER NOT NULL DEFAULT 0,
    timestamp   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (reading_id) REFERENCES SensorReadings(reading_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS Users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    customer_id INTEGER UNIQUE,
    FOREIGN KEY (customer_id) REFERENCES Customers(customer_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS AppSettings (
    name TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS FanSensors (
    sensor_id INTEGER PRIMARY KEY,
    reading_id INTEGER NOT NULL,
    unsafe INTEGER NOT NULL,
    stopped INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS FanRequests (
    token TEXT PRIMARY KEY,
    sensor_id INTEGER NOT NULL,
    recipient TEXT NOT NULL,
    message_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    sent INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_transactions_customer_id
    ON Transactions(customer_id);
CREATE INDEX IF NOT EXISTS idx_transaction_items_transaction_id
    ON TransactionItems(transaction_id);
CREATE INDEX IF NOT EXISTS idx_transaction_items_product_id
    ON TransactionItems(product_id);
CREATE INDEX IF NOT EXISTS idx_product_receptions_product_id
    ON ProductReceptions(product_id);
CREATE INDEX IF NOT EXISTS idx_payment_methods_transaction_id
    ON PaymentMethods(transaction_id);
CREATE INDEX IF NOT EXISTS idx_sensor_readings_sensor_id
    ON SensorReadings(sensor_id);
CREATE INDEX IF NOT EXISTS idx_alerts_reading_id
    ON Alerts(reading_id);
