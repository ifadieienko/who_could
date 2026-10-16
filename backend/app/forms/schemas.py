from pydantic import Field
from app.repair_schemas import Strict


class InstanceEdit(Strict):
    job_version: int = Field(ge=1)
    version: int = Field(ge=1)
    values: dict
