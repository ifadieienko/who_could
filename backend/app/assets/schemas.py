import json
from typing import Literal
from pydantic import Field, field_validator, model_validator
from app.repair_schemas import Strict, CustomerInput


class CustomerRecord(CustomerInput):
    kind: Literal["person", "company"] = "person"
    company_name: str = Field(default="", max_length=160)
    tax_id: str = Field(default="", max_length=80)
    contact_person: str = Field(default="", max_length=160)
    address: str = Field(default="", max_length=5000)

    @model_validator(mode="after")
    def company(self):
        if self.kind == "company" and not self.company_name:
            raise ValueError("Company name is required")
        return self


class CustomerEdit(CustomerRecord):
    version: int = Field(ge=1)


class SiteInput(Strict):
    customer_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=160)
    address: str = Field(default="", max_length=5000)
    notes: str = Field(default="", max_length=10000)


class SiteEdit(SiteInput):
    version: int = Field(ge=1)


class AssetInput(Strict):
    customer_id: int = Field(gt=0)
    site_id: int | None = Field(default=None, gt=0)
    asset_type: str = Field(default="device", pattern=r"^[a-z][a-z0-9_]{0,79}$")
    name: str = Field(min_length=1, max_length=160)
    manufacturer: str = Field(default="", max_length=160)
    model: str = Field(default="", max_length=160)
    serial: str = Field(default="", max_length=160)
    external_id: str | None = Field(default=None, max_length=160)
    status: Literal["active", "retired", "quarantined"] = "active"
    custom_values: dict = Field(default_factory=dict)

    @field_validator("external_id")
    @classmethod
    def blank_to_null(cls, value):
        return value or None

    @field_validator("custom_values")
    @classmethod
    def bounded(cls, value):
        if len(json.dumps(value, allow_nan=False)) > 32000:
            raise ValueError("Asset details exceed 32 KB")
        return value


class AssetEdit(AssetInput):
    version: int = Field(ge=1)
