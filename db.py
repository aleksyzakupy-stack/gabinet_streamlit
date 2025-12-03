import sqlite3
import pandas as pd
from datetime import datetime

DB_PATH = "clinic.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # pacjenci
    c.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            pesel TEXT UNIQUE NOT NULL,
            address TEXT,
            phone TEXT,
            email TEXT,
            created_at TEXT
        )
    """)

    # wizyty
    c.execute("""
        CREATE TABLE IF NOT EXISTS visits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            date TEXT,
            interview TEXT,
            examination TEXT,
            medications TEXT,
            recommendations TEXT,
            FOREIGN KEY(patient_id) REFERENCES patients(id)
        )
    """)

    # rozpoznania ICD-10
    c.execute("""
        CREATE TABLE IF NOT EXISTS diagnoses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            visit_id INTEGER NOT NULL,
            icd_code TEXT,
            icd_name TEXT,
            is_primary INTEGER DEFAULT 0,
            FOREIGN KEY(visit_id) REFERENCES visits(id)
        )
    """)

    conn.commit()
    conn.close()


def run_query(query, params=()):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(query, params)
    conn.commit()
    conn.close()


def fetch_all(query, params=()):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df