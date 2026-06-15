from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_analysis import router as analysis_router
from app.api.routes_charts import router as charts_router
from app.api.routes_health import router as health_router
from app.api.routes_upload import router as upload_router
from app.core.paths import ensure_storage_dirs


app = FastAPI(title="Local A/B Test Workbench API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api")
app.include_router(upload_router, prefix="/api")
app.include_router(analysis_router, prefix="/api")
app.include_router(charts_router, prefix="/api")


@app.on_event("startup")
def startup() -> None:
    ensure_storage_dirs()
