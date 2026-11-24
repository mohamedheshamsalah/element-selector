"""Run on the Windows PC with ETABS open, then share the generated text report.

Usage: python DEBUG_REPORT.py [optional exact table name]
This script reads model metadata and a database table; it does not edit the model.
"""
from __future__ import annotations

import json
import sys
import traceback

from etabs_client import RealEtabsClient


def main() -> int:
    chosen_table = " ".join(sys.argv[1:]).strip()
    print("=== ELEMENT SELECTOR ETABS DEBUG REPORT ===")
    try:
        client = RealEtabsClient()
        info = client.status()
        print("\n[Connection]")
        print(json.dumps(info, indent=2, ensure_ascii=False, default=str))
        tables = client.list_tables()
        print("\n[Available tables]")
        print(json.dumps(tables, indent=2, ensure_ascii=False))
        if not tables:
            print("No tables were returned. Open a model and run the required analysis/design.")
            return 2
        table_name = chosen_table if chosen_table in tables else tables[0]
        print(f"\n[First five rows: {table_name}]")
        rows = client.get_table(table_name)
        print(json.dumps(rows[:5], indent=2, ensure_ascii=False, default=str))
        if chosen_table and chosen_table not in tables:
            print(f"\nNOTE: requested table not found; showed first available table instead: {table_name}")
        print("\nEnd of report. Review and remove confidential model/table values before sharing.")
        return 0
    except Exception as exc:
        print("\n[ERROR]")
        print(f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
