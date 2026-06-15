from pydantic import BaseModel, Field


class HeaderDetectRequest(BaseModel):
    sheet_name: str
    header_row: int | None = None
    preview_rows: int = Field(default=20, ge=1, le=50)
