"""
database/db_connection.py - MySQL/MariaDB connection helper.

Other modules will use it like this (from Phase 3 onwards):

    from database.db_connection import db_cursor

    with db_cursor() as cur:                      # read
        cur.execute("SELECT * FROM Doctors")
        doctors = cur.fetchall()

    with db_cursor(commit=True) as cur:           # write (commits on success,
        cur.execute("UPDATE ...")                 #  rolls back on any error)

Run this file directly to test the connection:
    python database/db_connection.py
"""
import os
import sys
from contextlib import contextmanager

# Lets this file be run directly (python database/db_connection.py)
# and still find config.py in the project root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mysql.connector import Error, pooling  # noqa: E402

from config import Config  # noqa: E402

_pool = None  # created on first use


def _get_pool():
    global _pool
    if _pool is None:
        _pool = pooling.MySQLConnectionPool(
            pool_name="umc_pool",
            pool_size=Config.DB_POOL_SIZE,
            pool_reset_session=True,
            host=Config.DB_HOST,
            port=Config.DB_PORT,
            user=Config.DB_USER,
            password=Config.DB_PASSWORD,
            database=Config.DB_NAME,
            charset="utf8mb4",
        )
    return _pool


def get_connection():
    """Borrow a connection from the pool. Call .close() to give it back."""
    return _get_pool().get_connection()


@contextmanager
def db_cursor(dictionary=True, commit=False):
    """
    Yield a cursor on a pooled connection.
      commit=True  -> commit when the block succeeds.
      commit=False -> roll back at the end (safe for SELECTs; it also stops
                      a pooled connection from holding a stale read snapshot).
    Any exception rolls back and is re-raised.
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=dictionary)
    try:
        yield cursor
        if commit:
            conn.commit()
        else:
            conn.rollback()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()  # returns the connection to the pool


# ---------------------------------------------------------------------------
# Connection test
# ---------------------------------------------------------------------------
_TABLES = [
    "Students_Patients", "Users_Roles", "Doctors", "Daily_Tokens",
    "Medicines_Inventory", "Prescriptions", "Prescription_Items",
]

_HINTS = {
    2003: "MySQL is not reachable. Start MySQL in the XAMPP Control Panel and "
          "check DB_HOST / DB_PORT in .env.",
    1045: "Wrong username or password. Check DB_USER / DB_PASSWORD in .env "
          "(XAMPP's default is user 'root' with an empty password).",
    1049: "Database not found. Re-import database/schema.sql in phpMyAdmin.",
}


def test_connection():
    print("Connecting to MySQL ...")
    print(f"  host={Config.DB_HOST}  port={Config.DB_PORT}  "
          f"user={Config.DB_USER}  database={Config.DB_NAME}\n")
    try:
        with db_cursor() as cur:
            cur.execute("SELECT VERSION() AS version, DATABASE() AS db")
            info = cur.fetchone()
            print(f"[OK] Connected. Server version: {info['version']}, "
                  f"database: {info['db']}\n")

            print("Row counts:")
            for table in _TABLES:  # fixed list above, not user input
                cur.execute(f"SELECT COUNT(*) AS n FROM {table}")
                print(f"  {table:<22} {cur.fetchone()['n']}")

            cur.execute(
                """
                SELECT t.token_number, p.first_name, p.last_name, t.status
                  FROM Daily_Tokens t
                  JOIN Students_Patients p ON p.patient_id = t.patient_id
                 WHERE t.token_date = CURDATE()
                 ORDER BY t.token_number
                """
            )
            rows = cur.fetchall()
            print(f"\nToday's tokens ({len(rows)}):")
            for r in rows:
                print(f"  #{r['token_number']}  {r['first_name']} {r['last_name']}"
                      f"  [{r['status']}]")
        print("\n[OK] Phase 2 connection test passed.")
        return True
    except Error as e:
        print(f"[ERROR] {e}")
        if e.errno in _HINTS:
            print(f"Hint: {_HINTS[e.errno]}")
        return False


if __name__ == "__main__":
    sys.exit(0 if test_connection() else 1)
