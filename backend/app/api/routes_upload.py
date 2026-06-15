import shutil

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.schemas.upload import HeaderDetectRequest
from app.services.excel_service import create_chi_square_demo_upload, detect_headers, save_upload

router = APIRouter(prefix="/uploads", tags=["uploads"])


@router.post("")
def upload_excel(file: UploadFile = File(...)) -> dict[str, object]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename.")
    if not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="Only .xlsx and .xlsm files are supported in v1.")

    try:
        return save_upload(file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (OSError, shutil.Error) as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save upload: {exc}") from exc


@router.post("/demo/chi-square")
def create_chi_square_demo() -> dict[str, object]:
    try:
        return create_chi_square_demo_upload()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create demo workbook: {exc}") from exc


@router.post("/{upload_id}/detect-headers")
def detect_upload_headers(upload_id: str, request: HeaderDetectRequest) -> dict[str, object]:
    try:
        return detect_headers(
            upload_id=upload_id,
            sheet_name=request.sheet_name,
            header_row=request.header_row,
            preview_rows=request.preview_rows,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
