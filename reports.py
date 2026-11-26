import csv
from io import StringIO
from datetime import date, datetime, time, timedelta, timezone

from flask import Blueprint, Response, abort, render_template, request

from db import DEFAULT_LOW_STOCK_THRESHOLD, get_db
from receipts import LOCAL_TZ, to_local

reports = Blueprint("reports", __name__)


def csv_download(filename, columns, rows):
    output = StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(columns)
    for row in rows:
        writer.writerow(
            "'" + value if isinstance(value, str)
            and (value.startswith(("\t", "\r", "\n")) or value.lstrip().startswith(("=", "+", "-", "@")))
            else value
            for value in row
        )
    return Response(
        "\ufeff" + output.getvalue(), content_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"',
                 "Cache-Control": "private, no-store"},
    )


def sales_trend(db, start, end, bounds, interval, category):
    totals = {}
    transactions = 0
    revenue = 0
    if category:
        # Price at sale is the historical unit price of the matching items.
        rows = db.execute(
            """
            SELECT t.transaction_date, SUM(i.quantity * i.price_at_sale) AS total_amount
            FROM Transactions t JOIN TransactionItems i USING (transaction_id)
            JOIN Products p USING (product_id)
            WHERE t.status = 'completed' AND t.transaction_date >= ? AND t.transaction_date < ?
              AND p.category = ?
            GROUP BY t.transaction_id
            """, (*bounds, category),
        )
    else:
        rows = db.execute(
            """
            SELECT transaction_date, total_amount FROM Transactions
            WHERE status = 'completed' AND transaction_date >= ? AND transaction_date < ?
            """, bounds,
        )
    for row in rows:
        day = date.fromisoformat(to_local(row["transaction_date"])[:10])
        bucket = (day - start).days // interval
        cents = round(row["total_amount"] * 100)
        totals[bucket] = totals.get(bucket, 0) + cents
        transactions += 1
        revenue += cents

    bucket_count = (end - start).days // interval + 1
    maximum = max(1, max(totals.values(), default=0))
    trend = [
        {
            "start": start + timedelta(days=i * interval),
            "end": start + timedelta(days=min((i + 1) * interval - 1, (end - start).days)),
            "revenue": totals.get(i, 0) / 100,
            "x": 64 + 510 * i / (bucket_count - 1) if bucket_count > 1 else 319,
            "y": 128 - 100 * totals.get(i, 0) / maximum,
        }
        for i in range(bucket_count)
    ]
    return {"revenue": revenue / 100, "transactions": transactions}, trend, maximum / 100


def sales_financials(db, bounds, category=""):
    """Return the financial snapshot required by the administrator sales report."""
    if not category:
        # Receipts round GST/QST per transaction. Summing the stored transaction
        # totals keeps the report aligned with what customers actually paid;
        # recalculating tax from line items can differ by a cent across receipts.
        row = db.execute(
            """
            SELECT COALESCE(SUM(subtotal_amount), 0) AS subtotal,
                   COALESCE(SUM(cost_amount), 0) AS cost,
                   COALESCE(SUM(gst_amount), 0) AS gst,
                   COALESCE(SUM(qst_amount), 0) AS qst,
                   COALESCE(SUM(total_amount), 0) AS revenue,
                   COALESCE(SUM(COALESCE(profit_amount, subtotal_amount - cost_amount)), 0) AS profit,
                   COUNT(*) AS transactions
            FROM Transactions
            WHERE status = 'completed' AND transaction_date >= ? AND transaction_date < ?
            """, bounds,
        ).fetchone()
        subtotal = round(row["subtotal"] or 0, 2)
        cost = round(row["cost"] or 0, 2)
        gst = round(row["gst"] or 0, 2)
        qst = round(row["qst"] or 0, 2)
        return {
            "subtotal": subtotal,
            "gst": gst,
            "qst": qst,
            "tax": round(gst + qst, 2),
            "cost": cost,
            "profit": round(row["profit"] or 0, 2),
            "revenue": round(row["revenue"] or 0, 2),
            "transactions": row["transactions"],
        }

    category_clause = "" if not category else " AND p.category = ?"
    params = list(bounds) + ([category] if category else [])
    row = db.execute(
        """
        SELECT COALESCE(SUM(i.quantity * i.price_at_sale), 0) AS subtotal,
               COALESCE(SUM(i.quantity * i.cost_at_sale), 0) AS cost,
               COALESCE(SUM(CASE WHEN i.taxable_at_sale = 1
                                 THEN i.quantity * i.price_at_sale * t.gst_rate ELSE 0 END), 0) AS gst,
               COALESCE(SUM(CASE WHEN i.taxable_at_sale = 1
                                 THEN i.quantity * i.price_at_sale * t.qst_rate ELSE 0 END), 0) AS qst,
               COUNT(DISTINCT t.transaction_id) AS transactions
        FROM Transactions t
        JOIN TransactionItems i USING (transaction_id)
        JOIN Products p USING (product_id)
        WHERE t.status = 'completed' AND t.transaction_date >= ? AND t.transaction_date < ?
        """ + category_clause,
        params,
    ).fetchone()
    subtotal = round(row["subtotal"] or 0, 2)
    cost = round(row["cost"] or 0, 2)
    gst = round(row["gst"] or 0, 2)
    qst = round(row["qst"] or 0, 2)
    tax = round(gst + qst, 2)
    return {
        "subtotal": subtotal,
        "gst": gst,
        "qst": qst,
        "tax": tax,
        "cost": cost,
        "profit": round(subtotal - cost, 2),
        "revenue": round(subtotal + tax, 2),
        "transactions": row["transactions"],
    }


def date_range(default_start, default_end):
    try:
        start = date.fromisoformat(request.args.get("start") or default_start.isoformat())
        end = date.fromisoformat(request.args.get("end") or default_end.isoformat())
        if start > end:
            raise ValueError
        bounds = tuple(
            datetime.combine(day, time.min, LOCAL_TZ).astimezone(timezone.utc)
            .replace(tzinfo=None).isoformat(sep=" ", timespec="seconds")
            for day in (start, end + timedelta(days=1))
        )
    except (ValueError, OverflowError):
        abort(400, "Enter a valid date range with the start on or before the end.")
    return start, end, bounds


def customer_activity(db, start, end, bounds, customer_id):
    visits = {}
    customers = set()
    first_purchases = set()
    for row in db.execute(
        """
        WITH first_purchase AS (
            SELECT customer_id, MIN(transaction_date) AS first_date
            FROM Transactions WHERE status = 'completed' AND customer_id IS NOT NULL
            GROUP BY customer_id
        )
        SELECT t.customer_id, t.transaction_date, f.first_date
        FROM Transactions t JOIN first_purchase f USING (customer_id)
        WHERE t.status = 'completed' AND t.transaction_date >= ? AND t.transaction_date < ?
          AND (? IS NULL OR t.customer_id = ?)
        """, (*bounds, customer_id, customer_id),
    ):
        day = date.fromisoformat(to_local(row["transaction_date"])[:10])
        visits.setdefault(day, set()).add(row["customer_id"])
        customers.add(row["customer_id"])
        if row["first_date"] >= bounds[0]:
            first_purchases.add(row["customer_id"])

    daily = [
        (day, len(visits.get(day, ())))
        for day in (start + timedelta(days=i) for i in range((end - start).days + 1))
    ]
    return {
        "total": len(customers),
        "new": len(first_purchases),
        "returning": len(customers - first_purchases),
        "busiest": max(count for _, count in daily),
        "quietest": min(count for _, count in daily),
        "daily": daily,
    }


@reports.app_template_global()
def activity_label(count, busiest, quietest):
    if count == busiest == quietest:
        return "Busiest and quietest (tie)"
    if count == busiest:
        return "Busiest"
    if count == quietest:
        return "Quietest"
    return ""


def stock_status(quantity, threshold):
    if quantity < threshold:
        return "Low"
    if quantity < 2 * threshold:
        return "Moderate"
    return "OK"


@reports.get("/reports")
def overview():
    report = request.args.get("report", "inventory")
    db = get_db()
    export = request.args.get("format") == "csv"
    data = {"report": report, "active_page": "reports"}
    if report in ("inventory", "sales"):
        category = request.args.get("category", "")
        data["category"] = category
        data["categories"] = db.execute(
            "SELECT DISTINCT category FROM Products ORDER BY category"
        ).fetchall()
    if report == "inventory":
        data["products"] = db.execute(
            """
            SELECT p.product_id, p.name, p.category, p.quantity,
                   MAX(r.received_at) AS last_restocked,
                   COALESCE(t.threshold, ?) AS stock_threshold
            FROM Products p LEFT JOIN ProductReceptions r USING (product_id)
            LEFT JOIN CategoryStockThresholds t USING (category)
            WHERE ? = '' OR p.category = ?
            GROUP BY p.product_id ORDER BY p.name, p.product_id
            """, (DEFAULT_LOW_STOCK_THRESHOLD, category, category),
        ).fetchall()
        data["products"] = [dict(row) for row in data["products"]]
        for row in data["products"]:
            row["stock_status"] = stock_status(row["quantity"], row["stock_threshold"])
        data["low_stock_count"] = sum(row["stock_status"] == "Low" for row in data["products"])
        if export:
            return csv_download(
                "inventory.csv",
                ("Product ID", "Product", "Category", "Available", "Last restocked (Montreal)",
                 "Low-stock limit", "Stock status"),
                ((row["product_id"], row["name"], row["category"], row["quantity"],
                  to_local(row["last_restocked"]) if row["last_restocked"] else "",
                  row["stock_threshold"],
                  row["stock_status"])
                 for row in data["products"]),
            )
        if request.headers.get("X-Report-Fragment") == "inventory":
            return render_template("report_inventory.html", **data), 200, {"Cache-Control": "no-store"}
    elif report in ("sales", "customers"):
        today = datetime.now(LOCAL_TZ).date()
        start, end, bounds = date_range(today.replace(day=1), today)
        data.update(start=start, end=end)
        if report == "customers":
            customer_id = None
            if request.args.get("customer_id"):
                customer_id = request.args.get("customer_id", type=int)
                if customer_id is None or customer_id <= 0 or customer_id > 2**63 - 1:
                    abort(400, "Enter a valid customer ID.")
            data.update(customer_activity(db, start, end, bounds, customer_id), customer_id=customer_id)
            if export:
                return csv_download(
                    "customer-activity.csv",
                    ("From", "Through", "Unique customers", "New", "Returning", "Activity", "Customer ID"),
                    [(start, end, data["total"], data["new"], data["returning"], "Period total", customer_id)]
                    + [(day, day, count, "", "", activity_label(count, data["busiest"], data["quietest"]), customer_id)
                       for day, count in data["daily"]],
                )
        else:
            limit = request.args.get("limit", 3, type=int)
            if not 1 <= limit <= 50:
                abort(400, "Enter a ranking size from 1 to 50.")
            products = db.execute(
                """
                SELECT p.product_id, p.name, p.category, SUM(i.quantity) AS sold,
                       SUM(i.quantity * i.price_at_sale) AS revenue,
                       SUM(i.quantity * i.cost_at_sale) AS cost,
                       SUM(CASE WHEN i.taxable_at_sale = 1
                                THEN i.quantity * i.price_at_sale * (t.gst_rate + t.qst_rate)
                                ELSE 0 END) AS tax,
                       SUM(i.quantity * (i.price_at_sale - i.cost_at_sale)) AS profit
                FROM Transactions t JOIN TransactionItems i USING (transaction_id)
                JOIN Products p USING (product_id)
                WHERE t.status = 'completed' AND t.transaction_date >= ? AND t.transaction_date < ?
                  AND (? = '' OR p.category = ?)
                GROUP BY p.product_id ORDER BY sold DESC, p.name, p.product_id
                """, (*bounds, category, category),
            ).fetchall()
            grouping = request.args.get("grouping", "day")
            if grouping not in ("day", "week"):
                abort(400, "Choose daily or weekly sales.")
            sales, trend, chart_max = sales_trend(
                db, start, end, bounds, 7 if grouping == "week" else 1, category
            )
            sales = sales_financials(db, bounds, category)
            top = products[:limit]
            bottom = sorted(products, key=lambda row: (row["sold"], row["name"], row["product_id"]))[:limit]
            data.update(products=products, sales=sales, limit=limit, top=top, bottom=bottom,
                        grouping=grouping, trend=trend, chart_max=chart_max)
            if export:
                top_ranks = {row["product_id"]: rank for rank, row in enumerate(top, 1)}
                bottom_ranks = {row["product_id"]: rank for rank, row in enumerate(bottom, 1)}
                return csv_download(
                    "sales.csv",
                    ("Type", "From", "Through", "Product ID", "Product", "Units sold", "Revenue (CAD)",
                     "Purchases", "Most sold rank", "Least sold rank", "Category", "Cost (CAD)",
                     "Tax (CAD)", "Profit (CAD)"),
                    [("Total", start, end, "", "", "", f'{sales["revenue"]:.2f}', sales["transactions"], "", "", category,
                      f'{sales["cost"]:.2f}', f'{sales["tax"]:.2f}', f'{sales["profit"]:.2f}')]
                    + [("Product", start, end, row["product_id"], row["name"], row["sold"],
                        f'{(row["revenue"] or 0):.2f}', "", top_ranks.get(row["product_id"]),
                        bottom_ranks.get(row["product_id"]), row["category"], f'{(row["cost"] or 0):.2f}',
                        f'{(row["tax"] or 0):.2f}', f'{(row["profit"] or 0):.2f}') for row in products]
                    + [("Trend", point["start"], point["end"], "", "", "", f'{point["revenue"]:.2f}', "", "", "", category, "", "", "")
                       for point in trend],
                )
    else:
        abort(404)
    return render_template("reports.html", **data)
