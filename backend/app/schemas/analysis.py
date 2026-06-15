from pydantic import BaseModel, Field


class AnalysisRequest(BaseModel):
    upload_id: str
    sheet_name: str
    group_field: str
    metric_fields: list[str] = Field(min_length=1, max_length=5)
    anova_factor_fields: list[str] = Field(default_factory=list, max_length=2)
