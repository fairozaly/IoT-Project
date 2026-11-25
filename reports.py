from datetime import date, datetime, time, timedelta, timezone

from flask import Blueprint, abort, render_template, request

from db import get_db
from receipts import LOCAL_TZ, to_local

reports = Blueprint("reports", __name__)


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


def customer_activity(db, start, end, bounds):
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
        """, bounds,
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


@reports.get("/reports")
def overview():
    report = request.args.get("report", "inventory")
    db = get_db()
    data = {"report": report, "active_page": "reports"}
    if report == "inventory":
        category = request.args.get("category", "")
        data["category"] = category
        data["categories"] = db.execute(
            "SELECT DISTINCT category FROM Products ORDER BY category"
        ).fetchall()
        data["products"] = db.execute(
            """
            SELECT p.product_id, p.name, p.category, p.quantity,
                   MAX(r.received_at) AS last_restocked
            FROM Products p LEFT JOIN ProductReceptions r USING (product_id)
            WHERE ? = '' OR p.category = ?
            GROUP BY p.product_id ORDER BY p.name, p.product_id
            """, (category, category),
        ).fetchall()
        if request.headers.get("X-Report-Fragment") == "inventory":
            return render_template("_report_inventory.html", **data), 200, {"Cache-Control": "no-store"}
    elif report in ("sales", "customers"):
        today = datetime.now(LOCAL_TZ).date()
        start, end, bounds = date_range(today.replace(day=1), today)
        data.update(start=start, end=end)
        if report == "customers":
            data.update(customer_activity(db, start, end, bounds))
        else:
            limit = request.args.get("limit", 3, type=int)
            if not 1 <= limit <= 50:
                abort(400, "Enter a ranking size from 1 to 50.")
            products = db.execute(
                """
                SELECT p.product_id, p.name, SUM(i.quantity) AS sold
                FROM Transactions t JOIN TransactionItems i USING (transaction_id)
                JOIN Products p USING (product_id)
                WHERE t.status = 'completed' AND t.transaction_date >= ? AND t.transaction_date < ?
                GROUP BY p.product_id ORDER BY sold DESC, p.name, p.product_id
                """, bounds,
            ).fetchall()
            sales = db.execute(
                """
                SELECT COALESCE(SUM(total_amount), 0) AS revenue, COUNT(*) AS transactions
                FROM Transactions
                WHERE status = 'completed' AND transaction_date >= ? AND transaction_date < ?
                """, bounds,
            ).fetchone()
            data.update(products=products, sales=sales, limit=limit, top=products[:limit],
                        bottom=sorted(products, key=lambda row: (row["sold"], row["name"], row["product_id"]))[:limit])
    else:
        abort(404)
    return render_template("reports.html", **data)
