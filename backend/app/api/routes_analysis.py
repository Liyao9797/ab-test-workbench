from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.paths import STORAGE_ROOT
from app.schemas.analysis import AnalysisRequest
from app.services.analysis_service import run_analysis

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.post("/jobs")
def create_analysis_job(request: AnalysisRequest) -> dict[str, object]:
    try:
        return run_analysis(request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/jobs/{job_id}/workbook")
def download_analysis_workbook(job_id: str) -> FileResponse:
    output_path = STORAGE_ROOT / "results" / job_id / "stage2_result.xlsx"
    if not output_path.exists():
        raise HTTPException(status_code=404, detail=f"Analysis workbook not found: {job_id}")
    return FileResponse(
        output_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"{job_id}_stage2_result.xlsx",
    )
