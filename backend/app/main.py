from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router, public_router
from app.api.auth_routes import router as auth_router
from app.db.database import init_db
from app.core.config import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield
app=FastAPI(title="evidenceARCH API",version="1.0.0",lifespan=lifespan,description="Local forensic evidence management and integration API. Demo adapters are explicitly labelled; verification statuses are assigned by the verification adapter.")
app.add_middleware(CORSMiddleware,allow_origins=settings.cors_origins,allow_credentials=True,allow_methods=["GET","POST","PATCH","PUT","DELETE","OPTIONS"],allow_headers=["Content-Type","Authorization"])
@app.exception_handler(Exception)
async def unexpected_error(request,exc):
    import logging
    logging.getLogger("evidencearch").exception("Unhandled request failure",exc_info=exc)
    return JSONResponse(status_code=500,content={"detail":"An unexpected server error occurred."})
app.include_router(public_router)
app.include_router(router)
app.include_router(auth_router)
