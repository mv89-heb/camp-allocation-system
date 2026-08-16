from datetime import datetime
from decimal import Decimal
from typing import Annotated
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


NonNegativeInt = Annotated[int, Field(ge=0, le=1000)]
NonNegativeMoney = Annotated[Decimal, Field(ge=0, le=100000000, max_digits=12, decimal_places=2)]
APARTMENT_PATTERN = r"^[0-9A-Za-z\u0590-\u05FF ._/#-]+$"
DAMAGE_CATEGORIES = {"FURNITURE", "ELECTRICAL", "PLUMBING", "STRUCTURE", "CLEANLINESS", "HVAC", "OTHER"}
DAMAGE_SEVERITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
DAMAGE_STATUSES = {"OPEN", "INSPECTION", "IN_PROGRESS", "RESOLVED", "CLOSED"}
STATUS_TRANSITIONS = {
    "OPEN": {"OPEN", "INSPECTION", "IN_PROGRESS"},
    "INSPECTION": {"INSPECTION", "IN_PROGRESS", "OPEN"},
    "IN_PROGRESS": {"IN_PROGRESS", "RESOLVED", "OPEN"},
    "RESOLVED": {"RESOLVED", "CLOSED", "IN_PROGRESS"},
    "CLOSED": {"CLOSED", "IN_PROGRESS"},
}


class ActualInventoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    apartment: str = Field(min_length=1, max_length=120, pattern=APARTMENT_PATTERN)
    beds: NonNegativeInt = 0
    mattresses: NonNegativeInt = 0
    closets: NonNegativeInt = 0
    ac_units: NonNegativeInt = 0
    ac_remotes: NonNegativeInt = 0

    @field_validator("apartment")
    @classmethod
    def validate_apartment(cls, value: str) -> str:
        if not value:
            raise ValueError("שם הדירה/הקרוון הוא שדה חובה")
        return value


class GroupAllocationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=120)
    size: NonNegativeInt


class AllocationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    groups: list[GroupAllocationRequest] = Field(min_length=1, max_length=1000)
    allow_split: bool = False


class DamageCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    apartment: str = Field(min_length=1, max_length=120, pattern=APARTMENT_PATTERN)
    category: str = Field(min_length=2, max_length=40)
    severity: str = Field(default="MEDIUM", min_length=3, max_length=20)
    description: str = Field(min_length=5, max_length=5000)
    estimated_cost: NonNegativeMoney | None = None
    responsible_party: str | None = Field(default=None, max_length=160)
    resolution_notes: str | None = Field(default=None, max_length=5000)
    evidence_urls: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str) -> str:
        value = value.upper()
        if value not in DAMAGE_CATEGORIES:
            raise ValueError(f"category must be one of: {', '.join(sorted(DAMAGE_CATEGORIES))}")
        return value

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, value: str) -> str:
        value = value.upper()
        if value not in DAMAGE_SEVERITIES:
            raise ValueError(f"severity must be one of: {', '.join(sorted(DAMAGE_SEVERITIES))}")
        return value

    @field_validator("evidence_urls")
    @classmethod
    def validate_urls(cls, values: list[str]) -> list[str]:
        for value in values:
            parsed = urlparse(value)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("evidence URLs must use http or https")
        return values


class FieldRoomReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    inventory: ActualInventoryUpdate
    damages: list[DamageCreateRequest] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_damage_rooms(self):
        for damage in self.damages:
            if damage.apartment != self.inventory.apartment:
                raise ValueError("All damages must belong to the reported room")
        return self


class DamageUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    severity: str | None = None
    status: str | None = None
    description: str | None = Field(default=None, min_length=5, max_length=5000)
    estimated_cost: NonNegativeMoney | None = None
    actual_cost: NonNegativeMoney | None = None
    responsible_party: str | None = Field(default=None, max_length=160)
    resolution_notes: str | None = Field(default=None, max_length=5000)
    evidence_urls: list[str] | None = Field(default=None, max_length=10)

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.upper()
        if value not in DAMAGE_SEVERITIES:
            raise ValueError("invalid damage severity")
        return value

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.upper()
        if value not in DAMAGE_STATUSES:
            raise ValueError("invalid damage status")
        return value

    @field_validator("evidence_urls")
    @classmethod
    def validate_urls(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        for value in values:
            parsed = urlparse(value)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("evidence URLs must use http or https")
        return values

    @model_validator(mode="after")
    def validate_resolution(self):
        if self.status in {"RESOLVED", "CLOSED"} and not self.resolution_notes:
            raise ValueError("resolution_notes is required when closing/resolving a damage report")
        return self


class HealthResponse(BaseModel):
    status: str
    database: str
    timestamp: datetime
