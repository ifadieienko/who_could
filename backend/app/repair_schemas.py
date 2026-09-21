from datetime import datetime
from typing import Literal
from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)
from .repair_defaults import PERMISSIONS


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class FieldSpec(Strict):
    key: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_]{0,63}$")
    label: str = Field(min_length=1, max_length=120)
    type: Literal["string", "text", "number", "date", "image", "select", "checkbox"] = (
        "string"
    )
    section: str = Field(default="Приём", max_length=80)
    width: int = Field(default=1, ge=1, le=3)
    row: int | None = Field(default=None, ge=1, le=100)
    required: bool = False
    options: list[str] = Field(default_factory=list, max_length=100)
    condition: dict | None = None
    read_permission: str | None = None
    write_permission: str | None = None

    @model_validator(mode="after")
    def valid(self):
        for p in [self.read_permission, self.write_permission]:
            if p and p not in PERMISSIONS:
                raise ValueError("Unknown permission")
        if self.type == "select" and not self.options:
            raise ValueError("Select needs options")
        if self.condition and (
            set(self.condition) != {"field", "equals"}
            or not isinstance(self.condition["field"], str)
        ):
            raise ValueError("Condition requires field and equals")
        return self


FormPhase = Literal["diagnosis", "repair", "quality"]


class TemplateInput(Strict):
    purpose: Literal["intake", "diagnosis", "repair", "quality"] = "intake"
    name: str = Field(min_length=1, max_length=160)
    fields: list[FieldSpec] = Field(max_length=100)
    columns: int = Field(default=2, ge=1, le=3)

    @model_validator(mode="after")
    def unique_fields(self):
        keys = [f.key for f in self.fields]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate field keys")
        for f in self.fields:
            if f.condition:
                if f.condition["field"] not in keys or f.condition["field"] == f.key:
                    raise ValueError("Invalid condition reference")
                parent = next(x for x in self.fields if x.key == f.condition["field"])
                if parent.condition:
                    raise ValueError("Nested conditions are not supported")
                if (
                    parent.read_permission
                    and parent.read_permission != f.read_permission
                ):
                    raise ValueError("Condition cannot expose a restricted field")
        return self


class StageSpec(Strict):
    form_phase: FormPhase | None = None
    key: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_]{0,63}$")
    name: str = Field(min_length=1, max_length=120)
    category: Literal["active", "waiting", "ready"] = "active"
    next: list[str] = Field(default_factory=list, max_length=30)
    required_fields: list[str] = Field(default_factory=list, max_length=100)
    checks: list[str] = Field(default_factory=list, max_length=50)
    requires_quote: bool = False
    permission: str = "orders.transition"
    sla_hours: int = Field(default=48, ge=1, le=8760)

    @field_validator("permission")
    @classmethod
    def known(cls, v):
        if v not in PERMISSIONS:
            raise ValueError("Unknown permission")
        return v


class WorkflowInput(Strict):
    name: str = Field(min_length=1, max_length=160)
    stages: list[StageSpec] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def graph(self):
        keys = [s.key for s in self.stages]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate stage keys")
        if self.stages[0].category == "ready":
            raise ValueError("Initial stage cannot be ready")
        if not any(s.category == "ready" for s in self.stages):
            raise ValueError("A ready stage is required")
        for s in self.stages:
            if any(k not in keys or k == s.key for k in s.next):
                raise ValueError("Invalid transition")
        reachable = {keys[0]}
        for _ in keys:
            reachable |= {k for s in self.stages if s.key in reachable for k in s.next}
        if reachable != set(keys):
            raise ValueError("All stages must be reachable")
        return self


class CustomerInput(Strict):
    name: str = Field(min_length=1, max_length=160)
    email: EmailStr | None = None
    phone: str = Field(default="", max_length=80)


class OrderInput(Strict):
    stage_forms: dict[FormPhase, int] = Field(default_factory=dict)
    template_id: int
    workflow_id: int
    customer_id: int | None = None
    device_id: int | None = None
    customer: CustomerInput | None = None
    model: str = Field(default="", max_length=160)
    serial: str = Field(default="", max_length=160)
    problem: str = Field(min_length=1, max_length=10000)
    condition: str = Field(default="", max_length=10000)
    accessories: str = Field(default="", max_length=5000)
    location: str = Field(default="", max_length=160)
    values: dict = Field(default_factory=dict)
    due_at: datetime | None = None
    draft: bool = True
    warranty_of: int | None = None


class Version(Strict):
    version: int = Field(ge=1)


class StageFormEdit(Version):
    values: dict


class OrderEdit(Version):
    values: dict | None = None
    problem: str | None = Field(default=None, min_length=1, max_length=10000)
    condition: str | None = Field(default=None, max_length=10000)
    accessories: str | None = Field(default=None, max_length=5000)
    location: str | None = Field(default=None, max_length=160)
    due_at: datetime | None = None
    reason: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def non_null_metadata(self):
        for key in ("problem", "condition", "accessories", "location"):
            if key in self.model_fields_set and getattr(self, key) is None:
                raise ValueError(key + " cannot be null")
        return self


class Transition(Version):
    target: str
    checks: list[str] = Field(default_factory=list, max_length=50)
    reason: str = Field(default="", max_length=1000)


class Assignment(Version):
    user_id: int | None = None


class Note(Version):
    text: str = Field(min_length=1, max_length=10000)


class Issue(Version):
    receiver: str = Field(min_length=2, max_length=160)
    note: str = Field(default="", max_length=2000)
    outstanding_reason: str = Field(default="", max_length=1000)


class Reopen(Version):
    reason: str = Field(min_length=3, max_length=1000)


class EstimateLine(Strict):
    description: str = Field(min_length=1, max_length=200)
    quantity: int = Field(default=1, ge=1, le=10000)
    unit_cents: int = Field(ge=0, le=10000000)


class EstimateInput(Version):
    lines: list[EstimateLine] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def total(self):
        if sum(x.quantity * x.unit_cents for x in self.lines) > 1000000000:
            raise ValueError("Estimate too large")
        return self


class Decision(Strict):
    decision: Literal["accepted", "declined"]
    name: str = Field(min_length=2, max_length=160)
    confirmed: Literal[True]


class PaymentInput(Version):
    amount_cents: int = Field(gt=0, le=1000000000)
    method: Literal["cash", "card", "transfer", "other"]
    reference: str = Field(default="", max_length=160)


class RoleInput(Strict):
    name: str = Field(min_length=1, max_length=80)
    permissions: list[str]
    scope: Literal["all", "own"] = "all"

    @field_validator("permissions")
    @classmethod
    def known(cls, v):
        if any(p not in PERMISSIONS for p in v):
            raise ValueError("Unknown permission")
        if "members.manage" in v:
            raise ValueError("Member administration is reserved for owners")
        return sorted(set(v) | {"orders.read"})


class MemberInput(Strict):
    name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    password: str = Field(min_length=12, max_length=120)
    role_id: int


class MemberEdit(Strict):
    role_id: int
    active: bool
