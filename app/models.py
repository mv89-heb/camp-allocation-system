from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator


NonNegativeInt = Annotated[int, Field(ge=0, le=1000)]
APARTMENT_PATTERN = r"^[0-9A-Za-z\u0590-\u05FF ._/#-]+$"


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


class HealthResponse(BaseModel):
    status: str
    database: str
    timestamp: datetime
