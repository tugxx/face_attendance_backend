from uuid import UUID
from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional



class UserInput(BaseModel):
    username: str
    email: str
    password: str
    phone: str | None = None
    role: str = "student" # Các role hợp lệ: student, teacher, parent, driver, admin

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
    created_on: Optional[datetime] = None
    updated_on: Optional[datetime] = None
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
    