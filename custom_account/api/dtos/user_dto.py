from pydantic import BaseModel

class UserInput(BaseModel):
    username: str
    email: str
    password: str
    phone: str | None = None
    role: str = "student" # Các role hợp lệ: student, teacher, parent, driver, admin

    def to_dict(self, exclude_none: bool = True) -> dict:
        return self.model_dump(exclude_none=exclude_none)