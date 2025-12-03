import csv
import sqlite3

DB = "clinic.db"
CSV = "icd10.csv"

conn = sqlite3.connect(DB)
c = conn.cursor()

c.execute("""
    CREATE TABLE IF NOT EXISTS icd10 (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE,
        name TEXT
    )
""")

with open(CSV, encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        try:
            c.execute("INSERT INTO icd10 (code, name) VALUES (?, ?)", (row["code"], row["name"]))
        except:
            pass

conn.commit()
conn.close()

print("ICD-10 imported.")