from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.db.session import engine
from app.core.config import settings
from app.modules.routes import router
from app.modules.agreement_routes import router as agreement_router
from app.modules.vault_routes import router as vault_router
from app.modules.obligation_routes import router as obligation_router
from app.modules.proposal_routes import router as proposal_router
from app.modules.delivery_routes import router as delivery_router
from app.modules.ussd_routes import router as ussd_router

app = FastAPI(title="MyBizVault API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_origin],
    allow_credentials=True, allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-CSRF-Token", "X-Invitation-Token"])
app.include_router(router)
app.include_router(agreement_router)
app.include_router(vault_router)
app.include_router(obligation_router)
app.include_router(proposal_router)
app.include_router(delivery_router)
app.include_router(ussd_router)


@app.get("/api/health")
def health() -> dict[str, str]:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}
