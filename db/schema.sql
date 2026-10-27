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
    barcode         TEXT UNIQUE,   
    SDK             TEXT UNIQUE,
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
    FOREIGN KEY (sensor_id) REFERENCES Sensors(sensor_id)
);

CREATE TABLE IF NOT EXISTS Alerts (
    alert_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    reading_id  INTEGER NOT NULL,
    alert_type  TEXT NOT NULL,
    resolved    INTEGER NOT NULL DEFAULT 0,
    timestamp   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (reading_id) REFERENCES SensorReadings(reading_id)
);
CREATE TABLE IF NOT EXISTS Users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL
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
