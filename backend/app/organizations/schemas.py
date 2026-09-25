from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import Field, field_validator
from app.repair_schemas import Strict


class OrganizationSettings(Strict):
    name: str = Field(min_length=2, max_length=160)
    locale: Literal["en", "pl", "ru"] = "en"
    timezone: str = Field(default="Europe/Warsaw", max_length=80)
    currency: Literal["PLN", "EUR", "GBP", "CZK"] = "PLN"
    country: str = Field(default="PL", pattern=r"^[A-Z]{2}$")
    settings: dict = Field(default_factory=dict)

    @field_validator("timezone")
    @classmethod
    def valid_zone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Unknown IANA timezone")
        return value

    @field_validator("settings")
    @classmethod
    def bounded_settings(cls, value):
        import json
        if len(json.dumps(value)) > 16000:
            raise ValueError("Settings exceed 16 KB")
        return value


class OrganizationEdit(OrganizationSettings):
    version: int = Field(ge=1)
