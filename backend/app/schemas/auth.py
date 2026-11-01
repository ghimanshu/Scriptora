from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class Register(BaseModel):
    role: Literal["AUTHOR", "REVIEWER"] = "AUTHOR"
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=12, max_length=128)


class Login(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class Token(BaseModel):
    token: str = Field(min_length=20, max_length=500)


class Refresh(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=500)


class Forgot(BaseModel):
    email: EmailStr


class Reset(Token):
    password: str = Field(min_length=12, max_length=128)


class InvitationAccept(Reset):
    display_name: str = Field(min_length=1, max_length=200)
