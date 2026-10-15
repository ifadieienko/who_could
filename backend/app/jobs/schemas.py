from datetime import datetime
from typing import Literal
from pydantic import Field, model_validator
from app.repair_schemas import Strict, OrderEdit, FormPhase

Priority = Literal["low", "normal", "high", "urgent"]


class JobInput(Strict):
    customer_id: int = Field(gt=0)
    asset_id: int = Field(gt=0)
    site_id: int | None = Field(default=None, gt=0)
    job_type: str = Field(default="repair", pattern=r"^[a-z][a-z0-9_]{0,79}$")
    priority: Priority = "normal"
    template_id: int = Field(gt=0)
    workflow_id: int = Field(gt=0)
    description: str = Field(min_length=1, max_length=10000)
    condition: str = Field(default="", max_length=10000)
    accessories: str = Field(default="", max_length=5000)
    location: str = Field(default="", max_length=160)
    stage_forms: dict[FormPhase, int] = Field(default_factory=dict)
    values: dict = Field(default_factory=dict)
    due_at: datetime | None = None
    draft: bool = True


class JobEdit(OrderEdit):
    problem: str | None = Field(default=None, alias="description", min_length=1, max_length=10000)
    priority: Priority | None = None
    site_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def priority_not_null(self):
        if "priority" in self.model_fields_set and self.priority is None:
            raise ValueError("priority cannot be null")
        return self
