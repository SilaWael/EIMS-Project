#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Date Normalizer for EIMS Database
---------------------------------
Ensures all report_date values in master_registry are stored as YYYY-MM-DD.
Run this script whenever date ordering issues appear in the EIMS app.
"""

import sqlite3
from datetime import datetime
import sys

DB_PATH = "eims.db"


def normalize_date_to_db(date_str):
    """Standardizes any date format to YYYY-MM-DD for database storage."""
    if not date_str:
        return "2026-05-18"
    date_str = str(date_str).strip()
    if date_str.endswith(".0"):
        date_str = date_str[:-2]
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
    return date_str


def fix_dates():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT id, report_date FROM master_registry")
    rows = cursor.fetchall()

    updated = 0
    skipped = 0
    anomalies = []

    for rec_id, raw_date in rows:
        normalized = normalize_date_to_db(raw_date)
        if normalized != raw_date:
            cursor.execute(
                "UPDATE master_registry SET report_date = ? WHERE id = ?",
                (normalized, rec_id),
            )
            updated += cursor.rowcount
        else:
            skipped += 1

        # Sanity check: after normalization, must be YYYY-MM-DD
        if len(normalized) != 10 or normalized[4] != "-" or normalized[7] != "-":
            anomalies.append((rec_id, raw_date, normalized))

    conn.commit()

    print(f"✅ Updated:  {updated} records")
    print(f"✅ Skipped:  {skipped} records (already YYYY-MM-DD)")
    if anomalies:
        print(f"⚠️  Anomalies: {len(anomalies)} records could not be normalized:")
        for rec_id, raw, norm in anomalies:
            print(f"      ID {rec_id}: '{raw}' → '{norm}'")
    else:
        print("✅ No anomalies detected.")

    # Verify ordering
    print("\n--- Latest 10 dates after fix ---")
    cursor.execute(
        "SELECT report_date FROM master_registry ORDER BY report_date DESC LIMIT 10"
    )
    for (d,) in cursor.fetchall():
        print(f"  {d}")

    conn.close()
    return 0 if not anomalies else 1


if __name__ == "__main__":
    sys.exit(fix_dates())
