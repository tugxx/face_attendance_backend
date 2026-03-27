import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserInput(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)
    phone: str | None = Field(default=None)
    role: Literal["student", "teacher", "parent", "driver", "admin"] = "student"

    @field_validator("username")
    @classmethod
    def validate_username(cls, v):
        if not re.match(r"^[a-zA-Z0-9_]+$", v):
            raise ValueError("Username chỉ được chứa chữ cái, số và dấu gạch dưới.")
        return v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v):
        if v is not None and str(v).strip() != "":
            if not re.match(r"^\d{10,12}$", str(v)):
                raise ValueError(
                    "Số điện thoại không hợp lệ (Phải từ 10 đến 12 chữ số)."
                )
        return v

    def to_dict(self, exclude_none: bool = True) -> dict:
        return self.model_dump(exclude_none=exclude_none)


class UserPublicOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    username: str
    email: str
    created_on: datetime | None = None
    phone: str | None

    def to_dict(self, exclude_none: bool = True) -> dict:
        """
        Convert the model to a dictionary.

        Args:
            exclude_none (bool): Whether to exclude keys with None values. Defaults to True.

        Returns:
            dict: A dictionary representation of the model.
        """
        return self.model_dump(exclude_none=exclude_none)


class UserAdminOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str
    email: str
    created_on: datetime | None = None
    updated_on: datetime | None = None
    phone: str | None
    role: str
    is_active: bool

    def to_dict(self, exclude_none: bool = True) -> dict:
        """
        Convert the model to a dictionary.

        Args:
            exclude_none (bool): Whether to exclude keys with None values. Defaults to True.

        Returns:
            dict: A dictionary representation of the model.
        """
        return self.model_dump(exclude_none=exclude_none)
