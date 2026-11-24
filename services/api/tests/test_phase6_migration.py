"""Preservation check for the Phase 6 schema transition on populated SQLite."""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path


def test_phase6_upgrade_and_rollback_preserve_older_records(tmp_path):
    api_dir = Path(__file__).resolve().parents[1]
    database = tmp_path / "populated.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{database.as_posix()}"}

    def migrate(direction, target):
        subprocess.run([sys.executable, "-m", "alembic", direction, target],
                       cwd=api_dir, env=env, check=True, capture_output=True, text=True)

    migrate("upgrade", "0005_obligations_negotiation")
    with sqlite3.connect(database) as db:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("INSERT INTO users (id,email,full_name,password_hash,failed_logins,created_at) VALUES (?,?,?,?,?,?)",
                   ("user", "owner@example.com", "Owner", "unused", 0, "2026-11-24"))
        db.execute("INSERT INTO businesses (id,name,created_at) VALUES (?,?,?)", ("business", "Shop", "2026-11-24"))
        db.execute("INSERT INTO counterparties (id,business_id,display_name,created_at) VALUES (?,?,?,?)",
                   ("customer", "business", "Buyer", "2026-11-24"))
        db.execute("INSERT INTO transactions (id,business_id,counterparty_id,created_by_user_id,description,transaction_date,total_ugx,paid_ugx,due_date,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                   ("sale", "business", "customer", "user", "Goods", "2026-11-24", 1000, 200, "2026-12-01", "2026-11-24"))
        db.execute("INSERT INTO agreements (id,business_id,transaction_id,status,current_version,created_at) VALUES (?,?,?,?,?,?)",
                   ("agreement", "business", "sale", "draft", 1, "2026-11-24"))
    migrate("upgrade", "head")
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT total_ugx FROM transactions WHERE id='sale'").fetchone()[0] == 1000
        assert db.execute("SELECT transaction_id FROM agreements WHERE id='agreement'").fetchone()[0] == "sale"
        assert db.execute("SELECT client_request_id FROM transactions WHERE id='sale'").fetchone()[0] is None
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0007_proposal_invitations"
    migrate("downgrade", "0005_obligations_negotiation")
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT total_ugx FROM transactions WHERE id='sale'").fetchone()[0] == 1000
        assert db.execute("SELECT transaction_id FROM agreements WHERE id='agreement'").fetchone()[0] == "sale"
