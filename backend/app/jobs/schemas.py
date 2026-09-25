from datetime import datetime
from typing import Literal
from pydantic import Field, model_validator
from app.repair_schemas import Strict, OrderEdit, FormPhase


class JobInput(Strict):
    asset_id: int = Field(gt=0)
    template_id: int = Field(gt=0)
    workflow_id: int = Field(gt=0)
    site_id: int | None = Field(default=None, gt=0)
    description: str = Field(min_length=1, max_length=10000)
    job_type: str = Field(default="repair", pattern=r"^[a-z][a-z0-9_]{0,79}$")
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    stage_forms: dict[FormPhase, int] = Field(default_factory=dict)
    values: dict = Field(default_factory=dict)
    due_at: datetime | None = None
    draft: bool = True


class JobEdit(OrderEdit):
    description: str | None = Field(default=None, min_length=1, max_length=10000)
    priority: Literal["low", "normal", "high", "urgent"] | None = None

    @model_validator(mode="after")
    def generic_metadata(self):
        if "description" in self.model_fields_set and self.description is None:
            raise ValueError("Description cannot be null")
        if "priority" in self.model_fields_set and self.priority is None:
            raise ValueError("Priority cannot be null")
        if (
            "description" in self.model_fields_set
            and "problem" in self.model_fields_set
        ):
            raise ValueError("Use description or problem, not both")
        return self
