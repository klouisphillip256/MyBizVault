"""Run schema migrations before a production Vercel backend is released."""

import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    if os.getenv("VERCEL_ENV") != "production":
        print("Skipping production migration outside the production environment")
        return
    url = os.getenv("DATABASE_URL_UNPOOLED") or os.getenv("DATABASE_URL")
    if not url or not url.startswith(("postgresql://", "postgres://", "postgresql+psycopg://")):
        raise RuntimeError("Production migration requires a Neon PostgreSQL connection URL")
    environment = dict(os.environ)
    environment["DATABASE_URL"] = url
    environment["PGCONNECT_TIMEOUT"] = "15"
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                   cwd=Path(__file__).resolve().parent, env=environment, check=True)
    print("Production database migrated to the latest revision")


if __name__ == "__main__":
    main()
