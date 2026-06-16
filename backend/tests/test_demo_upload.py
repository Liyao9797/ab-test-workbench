import pandas as pd

from app.core.paths import STORAGE_ROOT
from app.services.excel_service import create_chi_square_demo_upload


def test_chi_square_demo_upload_regenerates_data_each_time():
    first = create_chi_square_demo_upload()
    second = create_chi_square_demo_upload()

    assert first["upload_id"] != second["upload_id"]
    assert first["filename"] != second["filename"]

    first_frame = pd.read_excel(STORAGE_ROOT / "uploads" / str(first["upload_id"]) / "original.xlsx", sheet_name="chi_square_demo")
    second_frame = pd.read_excel(STORAGE_ROOT / "uploads" / str(second["upload_id"]) / "original.xlsx", sheet_name="chi_square_demo")

    assert not first_frame.equals(second_frame)


def test_chi_square_demo_upload_includes_numeric_metrics_for_demo_screenshot():
    upload = create_chi_square_demo_upload()
    frame = pd.read_excel(STORAGE_ROOT / "uploads" / str(upload["upload_id"]) / "original.xlsx", sheet_name="chi_square_demo")

    numeric_columns = [
        column
        for column in frame.columns
        if pd.api.types.is_numeric_dtype(frame[column]) and not set(frame[column].dropna().unique()).issubset({0, 1})
    ]

    assert {"login_days", "session_minutes"}.issubset(set(numeric_columns))
