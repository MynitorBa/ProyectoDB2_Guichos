from pydantic import BaseModel, EmailStr


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    nombre: str
    apellido: str
    telefono: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'


class UserResponse(BaseModel):
    id: int
    email: str
    nombre: str
    apellido: str
    roles: list[str]
    estado: str

    model_config = {'from_attributes': True}
