import sqlite3
from pathlib import Path

DB_PATH = Path("db/noah.db")
SCHEMA_PATH = Path("db/schema.sql")

def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON;")
    return con

def init_db():
    con = connect()
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    con.executescript(schema)
    con.commit()
    con.close()

if __name__ == "__main__":
    init_db()
    print("DB initialized:", DB_PATH)
