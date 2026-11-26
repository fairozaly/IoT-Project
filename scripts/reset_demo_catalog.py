#!/usr/bin/env python3
"""Reset the local demo catalog to the bundled product image set.

This intentionally removes product-linked demo sales and inventory records,
then recreates the catalog with one in-stock EPC per seeded unit.
Customer accounts and sensor history are preserved.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


PRODUCTS = (
    ("Coca-Cola Original 355ml", "Drinks", "004900000099", "Coca-Cola", 2.49, 1.10, "catalog-coca-cola-original.jpg", 12),
    ("Evian Water 500ml", "Water", "306832012345", "Evian", 1.49, 0.55, "catalog-evian-water.jpg", 14),
    ("Hershey's Milk Chocolate", "Chocolate", "034000015575", "Hershey's", 1.99, 0.80, "catalog-hersheys-milk-chocolate.jpg", 8),
    ("KitKat Classic", "Chocolate", "099999000001", "Nestle", 1.79, 0.70, "catalog-kitkat-classic.jpg", 11),
    ("M&M's Peanut", "Candy", "040000000112", "Mars", 2.29, 0.95, "catalog-mms-peanut.jpg", 9),
    ("Pepsi Original 355ml", "Drinks", "012000001234", "PepsiCo", 2.49, 1.10, "catalog-pepsi-original.jpg", 13),
    ("Pringles Original 165g", "Snacks", "038000138318", "Kellanova", 3.99, 2.00, "catalog-pringles-original.jpg", 7),
    ("Red Bull Original 250ml", "Energy Drinks", "611269991001", "Red Bull", 3.49, 1.70, "catalog-red-bull-original.jpg", 12),
)


def reset_catalog(database_path: Path, project_root: Path) -> int:
    for product in PRODUCTS:
        image_path = project_root / "static" / "images" / "products" / product[6]
        if not image_path.is_file():
            raise FileNotFoundError(f"Missing bundled product image: {image_path}")

    database = sqlite3.connect(database_path)
    database.row_factory = sqlite3.Row
    database.execute("PRAGMA foreign_keys = ON")
    try:
        with database:
            # Product-linked demo data must be removed before Products because
            # transaction items and receptions intentionally use RESTRICT.
            database.execute("DELETE FROM CartItems")
            database.execute("DELETE FROM GuestCartItems")
            database.execute("DELETE FROM PaymentMethods")
            database.execute("DELETE FROM TransactionItems")
            database.execute("DELETE FROM Transactions")
            database.execute("DELETE FROM ReceivedTags")
            database.execute("DELETE FROM ProductTagEvents")
            database.execute("DELETE FROM ProductTags")
            database.execute("DELETE FROM ProductReceptions")
            database.execute("DELETE FROM CategoryStockThresholds")
            database.execute("DELETE FROM ParetoMetrics")
            database.execute("DELETE FROM Products")

            for index, (name, category, upc, company, price, cost, image_name, quantity) in enumerate(PRODUCTS, start=1):
                cursor = database.execute(
                    """
                    INSERT INTO Products
                        (name, category, upc, SDK, price, cost_price, taxable,
                         quantity, company, image_url)
                    VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
                    """,
                    (
                        name,
                        category,
                        upc,
                        f"SKU-{index:03d}",
                        price,
                        cost,
                        quantity,
                        company,
                        f"/static/images/products/{image_name}",
                    ),
                )
                product_id = cursor.lastrowid
                reception_id = database.execute(
                    """
                    INSERT INTO ProductReceptions
                        (product_id, quantity_received, supplier)
                    VALUES (?, ?, ?)
                    """,
                    (product_id, quantity, "Demo catalog seed"),
                ).lastrowid

                for unit in range(1, quantity + 1):
                    # EPCs are hexadecimal by contract; avoid letters outside A-F.
                    epc = f"{index:02X}{unit:04X}A1B2C3"
                    tag_id = database.execute(
                        "INSERT INTO ProductTags (product_id, epc, status) VALUES (?, ?, 'in_stock')",
                        (product_id, epc),
                    ).lastrowid
                    database.execute(
                        "INSERT INTO ReceivedTags (tag_id, reception_id) VALUES (?, ?)",
                        (tag_id, reception_id),
                    )
                    database.execute(
                        "INSERT INTO ProductTagEvents (tag_id, status, note) VALUES (?, 'in_stock', ?)",
                        (tag_id, "Demo catalog seed"),
                    )

            database.execute(
                "INSERT INTO AppSettings (name, value) VALUES ('stock_tags_reconciled', '1') "
                "ON CONFLICT(name) DO UPDATE SET value = excluded.value"
            )
    finally:
        database.close()

    return sum(product[7] for product in PRODUCTS)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "smart_store.db",
    )
    args = parser.parse_args()
    total_tags = reset_catalog(args.database, Path(__file__).resolve().parents[1])
    print(f"Seeded {len(PRODUCTS)} products and {total_tags} in-stock EPCs into {args.database}")


if __name__ == "__main__":
    main()
