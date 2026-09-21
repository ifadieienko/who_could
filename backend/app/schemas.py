from datetime import date
from enum import Enum
from typing import Any

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


class WorkMode(str, Enum):
    online = "online"
    offline = "offline"
    hybrid = "hybrid"


class Duration(str, Enum):
    one_day = "one_day"
    short = "short"
    long = "long"


class BudgetType(str, Enum):
    fixed = "fixed"
    hourly = "hourly"
    negotiable = "negotiable"


class JobStatus(str, Enum):
    open = "open"
    in_progress = "in_progress"
    closed = "closed"


class ApplicationStatus(str, Enum):
    sent = "sent"
    accepted = "accepted"
    declined = "declined"


class DeviceIntakeFieldType(str, Enum):
    string = "string"
    number = "number"
    date = "date"
    image = "image"


class DeviceIntakeFieldCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    field_type: DeviceIntakeFieldType

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("field name cannot be empty")
        return value


class DeviceIntakeFormCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    fields: list[DeviceIntakeFieldCreate] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("form name cannot be empty")
        return value


class DeviceIntakeFieldPublic(BaseModel):
    id: int
    name: str
    field_type: DeviceIntakeFieldType
    position: int


class DeviceIntakeFormPublic(BaseModel):
    id: int
    name: str
    fields: list[DeviceIntakeFieldPublic] = Field(default_factory=list)
    created_at: str


class DeviceIntakeOrderStatus(str, Enum):
    deferred = "deferred"
    accepted = "accepted"


class DeviceIntakeOrderCreate(BaseModel):
    form_id: int = Field(gt=0)
    values: dict[str, Any] = Field(default_factory=dict)
    status: DeviceIntakeOrderStatus


class DeviceIntakeOrderUpdate(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)
    status: DeviceIntakeOrderStatus


class DeviceIntakeOrderPublic(BaseModel):
    id: int
    form_id: int | None = None
    form_name: str
    fields: list[DeviceIntakeFieldPublic] = Field(default_factory=list)
    values: dict[str, Any] = Field(default_factory=dict)
    status: DeviceIntakeOrderStatus
    created_at: str
    updated_at: str


class RoleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=50, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    description: str | None = Field(default=None, max_length=300)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip().lower()


class RolePublic(BaseModel):
    id: int
    name: str
    description: str | None = None
    is_system: bool = False
    created_at: str


class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    password: str = Field(min_length=8, max_length=120)
    city: str | None = Field(default=None, max_length=80)
    bio: str | None = Field(default=None, max_length=600)
    skills: str | None = Field(default=None, max_length=400)


class AdminUserCreate(UserCreate):
    role_ids: list[int] = Field(default_factory=list, max_length=100)


class RoleAssignmentUpdate(BaseModel):
    role_ids: list[int] = Field(default_factory=list, max_length=100)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserPublic(BaseModel):
    id: int
    name: str
    email: str
    city: str | None = None
    bio: str | None = None
    skills: str | None = None
    roles: list[RolePublic] = Field(default_factory=list)
    created_at: str


class AuthResponse(BaseModel):
    user: UserPublic


class JobCreate(BaseModel):
    title: str = Field(min_length=6, max_length=120)
    description: str = Field(min_length=20, max_length=3000)
    category: str = Field(min_length=2, max_length=80)
    work_mode: WorkMode
    duration: Duration
    location: str | None = Field(default=None, max_length=120)
    budget_type: BudgetType
    budget_min: int | None = Field(default=None, ge=0)
    budget_max: int | None = Field(default=None, ge=0)
    currency: str = Field(default="USD", pattern=r"^[A-Za-z]{3}$")
    deadline: date | None = None
    skills: str | None = Field(default=None, max_length=400)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def validate_budget_range(self):
        if self.budget_min is not None and self.budget_max is not None and self.budget_min > self.budget_max:
            raise ValueError("budget_min cannot exceed budget_max")
        return self


class JobPublic(JobCreate):
    id: int
    owner_id: int
    owner_name: str
    status: JobStatus
    created_at: str
    applications_count: int = 0


class JobStatusUpdate(BaseModel):
    status: JobStatus


class ApplicationStatusUpdate(BaseModel):
    status: ApplicationStatus


class ApplicationCreate(BaseModel):
    message: str = Field(min_length=12, max_length=1600)
    proposed_rate: int | None = Field(default=None, ge=0)
    estimated_time: str | None = Field(default=None, max_length=120)


class ApplicationPublic(ApplicationCreate):
    id: int
    job_id: int
    job_title: str
    applicant_id: int
    applicant_name: str
    owner_id: int
    status: ApplicationStatus
    created_at: str


class Dashboard(BaseModel):
    owned_jobs: list[JobPublic]
    sent_applications: list[ApplicationPublic]
    received_applications: list[ApplicationPublic]
