import re
from pydantic import BaseModel, EmailStr, field_validator


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    nombre: str
    apellido: str
    telefono: str | None = None

    @field_validator('password')
    @classmethod
    def validar_password(cls, v: str) -> str:
        errores = []
        if len(v) < 8:
            errores.append('al menos 8 caracteres')
        if not re.search(r'[A-Z]', v):
            errores.append('al menos una mayúscula (A-Z)')
        if not re.search(r'[a-z]', v):
            errores.append('al menos una minúscula (a-z)')
        if not re.search(r'\d', v):
            errores.append('al menos un número (0-9)')
        if not re.search(r'[^A-Za-z0-9]', v):
            errores.append('al menos un carácter especial (!@#$%...)')
        if errores:
            raise ValueError('La contraseña requiere: ' + ', '.join(errores))
        return v


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
    telefono: str | None = None
    roles: list[str]
    estado: str

    model_config = {'from_attributes': True}


class ProfileUpdateRequest(BaseModel):
    nombre: str
    apellido: str
    telefono: str | None = None
