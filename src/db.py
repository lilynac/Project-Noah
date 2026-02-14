import sqlite3
from pathlib import Path
from datetime import datetime

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
    try:
        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        con.executescript(schema)
        con.commit()

        # ---- Task3: daily decay (run at most once per day) ----
        today = datetime.utcnow().strftime("%Y-%m-%d")
        row = con.execute("SELECT value FROM memory_meta WHERE key='last_decay_date'").fetchone()
        last = row["value"] if row else None

        if last != today:
            # import here to avoid circular/import-time side effects
            from src.memory.decay import apply_decay
            u1 = apply_decay("episode", limit=500)
            u2 = apply_decay("summary", limit=200)
            u3 = apply_decay("narrative", limit=100)
            con.execute(
                "INSERT OR REPLACE INTO memory_meta(key,value) VALUES('last_decay_date',?)",
                (today,),
            )
            con.commit()
            print(f"[db] MEMORY_DECAY daily episode={u1} summary={u2} narrative={u3}")

    finally:
        con.close()

if __name__ == "__main__":
    init_db()
    print("DB initialized:", DB_PATH)
