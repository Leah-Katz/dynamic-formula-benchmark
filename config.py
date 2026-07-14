"""
Single source of truth for the database connection string used by every
Python script in this project (seed_data.py, seed_formulas.py, eval_engine.py,
numpy_engine.py, run_sp.py, compare_results.py, export_report.py, run_all.py).

Override via the PAYMENTSYSTEM_CONNECTION_STRING environment variable;
otherwise falls back to a local Windows-auth default that matches the
SQL Server 2025 Developer Edition instance set up for this project.
"""
import os

CONNECTION_STRING = os.environ.get(
    "PAYMENTSYSTEM_CONNECTION_STRING",
    "Driver={ODBC Driver 18 for SQL Server};"
    "Server=localhost;"
    "Database=PaymentSystem;"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;",
)
