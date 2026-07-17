"""Authentication endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from ..deps import CurrentUser, DbSession
from ..schemas.auth import Token, UserCreate, UserRead
from ..security import create_access_token
from ..services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(data: UserCreate, db: DbSession) -> object:
    """Register a new user."""
    return auth_service.register_user(db, data.email, data.password)


@router.post("/token", response_model=Token)
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbSession) -> Token:
    """OAuth2 password grant — exchange email/password for a bearer token.

    (The OAuth2 form field is named ``username``; supply the user's email there.)
    """
    user = auth_service.authenticate(db, form.username, form.password)
    return Token(access_token=create_access_token(str(user.id)))


@router.get("/me", response_model=UserRead)
def me(user: CurrentUser) -> object:
    """Return the authenticated user."""
    return user
