import math

POINTS_PER_DOLLAR = 1


def calculate_points(total_amount):
    return math.floor(round(total_amount, 2) * POINTS_PER_DOLLAR)


def award_points(db, transaction_id):
    txn = db.execute(
        "SELECT customer_id, total_amount, points_earned "
        "FROM Transactions WHERE transaction_id = ?", (transaction_id,),
    ).fetchone()
    if txn is None or txn["customer_id"] is None:  # guest checkout: no points
        return 0
    if txn["points_earned"] > 0:  # already awarded; dont award twice
        return txn["points_earned"]

    points = calculate_points(txn["total_amount"])
    db.execute("UPDATE Transactions SET points_earned = ? WHERE transaction_id = ?",
               (points, transaction_id))
    db.execute("UPDATE Customers SET total_points = total_points + ? WHERE customer_id = ?",
               (points, txn["customer_id"]))
    return points
