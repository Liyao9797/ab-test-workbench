from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.paths import STORAGE_ROOT
from app.services.chart_service import generate_charts

router = APIRouter(tags=["charts"])


@router.post("/analysis/jobs/{job_id}/generate-charts")
def create_charts(job_id: str) -> dict[str, object]:
    try:
        return generate_charts(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/analysis/jobs/{job_id}/charts")
def get_charts(job_id: str) -> dict[str, object]:
    manifest_path = STORAGE_ROOT / "charts" / job_id / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail=f"Charts not found for job: {job_id}")
    return {"job_id": job_id, "manifest_url": f"/api/charts/{job_id}/manifest.json"}


@router.get("/charts/{job_id}/{filename}")
def get_chart_file(job_id: str, filename: str) -> FileResponse:
    if "/" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename.")
    chart_path = STORAGE_ROOT / "charts" / job_id / filename
    if not chart_path.exists():
        raise HTTPException(status_code=404, detail=f"Chart file not found: {filename}")
    media_type = "application/json" if filename.endswith(".json") else "image/png"
    return FileResponse(chart_path, media_type=media_type, filename=filename)
