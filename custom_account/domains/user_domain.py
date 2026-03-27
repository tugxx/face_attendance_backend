import re
from dataclasses import dataclass, fields
from datetime import datetime
from typing import Any, TypedDict

from custom_account.models import UserModel

# from custom_account.domains.profile_domain import ProfileDomain


class UserDict(TypedDict):
    """Dataclass representing the UserSettings object."""

    id: int
    username: str
    email: str
    created_on: datetime
    role: str
    phone: str | None


@dataclass
class UserDomain:
    """Value object representing a user's settings.
    Attributes:
        id: int | None. Unique identifier of the user (from DB).
        username: str. The unique of the user. Identifiable username to display in the UI.
        email: str. The user email.
        created_on: datetime. The date and time when the user was created.
        role: str. Role of the user.
        phone: str. The phone number of the user.
    """

    PASSWORD_PATTERN = re.compile(r"^(?=.*[a-z])(?=.[A-Z])(?=.*\d).{8,}$")

    id: int | None = None
    username: str = ""
    email: str = ""
    raw_password: str | None = None
    created_on: datetime | None = None
    updated_on: datetime | None = None
    role: str = "student"
    phone: str | None = None
    is_active: bool = True
    is_staff: bool = False

    # --- Validation ---
    def validate(self):
        """Validate the UserDomain object.
        Raises:
            ValueError: If any of the required attributes are missing or invalid.
        """
        if not self.username:
            raise ValueError("Username is required.")

        if not self.email:
            raise ValueError("Email is required.")
        # Basic email format check
        if not re.match(r"[^@]+@[^@]+\.[^@]+", self.email):
            raise ValueError("Invalid email format.")

        if self.role not in ["student", "instructor", "admin"]:
            raise ValueError("Role must be one of 'student', 'instructor', or 'admin'.")

    # --- Serialization ---
    def to_dict(self) -> UserDict:  # domain to dict
        """Convert the UserDomain object to a dictionary.
        Returns:
            dict. The dictionary representation of the UserDomain object.
        """
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "created_on": self.created_on,
            "role": self.role,
            "phone": self.phone,
        }

    @classmethod
    def from_dict(cls, data: UserDict) -> "UserDomain":  # dict to domain
        """Create a UserDomain object from a dictionary.
        Args:
            data: dict. The dictionary representation of the UserDomain object.
        Returns:
            UserDomain. The UserDomain object created from the dictionary.
        """
        return cls(
            id=data.get("id"),
            username=data["username"],
            email=data["email"],
            created_on=data.get("created_on"),
            role=data.get("role", "student"),
            phone=data.get("phone"),
        )

    # --- Mapping methods ---
    @classmethod
    def from_model(cls, user_model: UserModel) -> "UserDomain":  # model -> domain
        """Convert a UserModel instance → UserDomain."""
        return cls(
            id=user_model.id,
            username=user_model.username,
            email=user_model.email,
            raw_password="***",
            phone=user_model.phone,
            role=user_model.role,
            created_on=user_model.created_on,
        )

    def to_model(self) -> UserModel:
        user = UserModel(
            username=self.username,
            email=self.email,
            role=self.role,
            phone=self.phone,
        )
        user.set_password(self.raw_password)  # hash ở đây
        return user

    def apply_updates(self, updates: dict[str, Any]) -> None:
        """Apply updates from a dict and validate."""
        for field in fields(self):
            field_name = field.name
            if field_name in updates and updates[field_name] is not None:
                setattr(self, field_name, updates[field_name])
        self.validate()

    # def update_password(self, new_password: str) -> None:
    #     """Change the user's password.
    #     Args:
    #         new_password: str. The new password for the user.
    #     Raises:
    #         ValueError: If the new password is invalid.
    #     """
    #     # Basic password complexity check: at least 8 characters, one uppercase, one lowercase, one digit
    #     if not re.match(self.PASSWORD_PATTERN, new_password):
    #         raise ValueError("Password must be at least 8 characters long and include at least one uppercase letter, one lowercase letter, and one digit.")

    #     self.password = new_password

    # def create_profile(self): # Mới tạo chưa cần validate
    #     profile_domain = ProfileDomain(user_id=self.id)
    #     # profile_domain.validate()
    #     return profile_domain
