"""
create_admin.py - Create (or add) an Administrator login.

Run once after database/migration_admin.sql:
    python create_admin.py
You are asked for a username and a password (typed hidden). Nothing is stored
in the code, so there is no default admin password to forget to change.
"""
import getpass
import sys

from mysql.connector import Error
from werkzeug.security import generate_password_hash

from database.db_connection import db_cursor
from modules.admin.services import USERNAME_RE
from modules.patients.services import MAX_PASSWORD, MIN_PASSWORD


def main():
    username = input("Admin username (3-50 chars, letters/digits . _ -): ").strip()
    if not USERNAME_RE.match(username):
        print("Invalid username.")
        return 1
    password = getpass.getpass(f"Password (min {MIN_PASSWORD} chars): ")
    if not (MIN_PASSWORD <= len(password) <= MAX_PASSWORD):
        print(f"Password must be {MIN_PASSWORD}-{MAX_PASSWORD} characters.")
        return 1
    if password != getpass.getpass("Repeat password: "):
        print("Passwords do not match.")
        return 1
    try:
        with db_cursor(commit=True) as cur:
            cur.execute("SELECT 1 AS x FROM Users_Roles WHERE LOWER(username) = LOWER(%s)",
                        (username,))
            if cur.fetchone():
                print("That username already exists.")
                return 1
            cur.execute(
                "INSERT INTO Users_Roles (username, password_hash, role, ref_id) "
                "VALUES (%s, %s, 'Admin', NULL)",
                (username, generate_password_hash(password, method="pbkdf2:sha256")))
    except Error as e:
        print(f"Database error: {e}\nDid you run database/migration_admin.sql first?")
        return 1
    print(f"Admin '{username}' created. Log in at http://127.0.0.1:5000")
    return 0


if __name__ == "__main__":
    sys.exit(main())
