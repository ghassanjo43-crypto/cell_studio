"""FastAPI dependencies: DB session, current user, and the worker manager."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .ai.provider import AIProvider
from .experiment_runner import ExperimentManager
from .models import User
from .security import decode_access_token
from .study_runner import StudyManager
from .worker import WorkerManager

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")


def get_db(request: Request) -> Iterator[Session]:
    """Yield a request-scoped session from the app's session factory."""
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)], db: DbSession
) -> User:
    """Resolve the authenticated user from a bearer token, or 401."""
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise credentials_error
    user = db.get(User, user_id)
    if user is None:
        raise credentials_error
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_worker(request: Request) -> WorkerManager:
    """Return the process-wide worker manager stored on app state."""
    worker: WorkerManager = request.app.state.worker
    return worker


Worker = Annotated[WorkerManager, Depends(get_worker)]


def get_experiment_manager(request: Request) -> "ExperimentManager":
    """Return the process-wide experiment manager stored on app state."""
    manager: ExperimentManager = request.app.state.experiment_manager
    return manager


ExperimentManagerDep = Annotated["ExperimentManager", Depends(get_experiment_manager)]


def get_study_manager(request: Request) -> "StudyManager":
    """Return the process-wide study manager stored on app state."""
    manager: StudyManager = request.app.state.study_manager
    return manager


StudyManagerDep = Annotated["StudyManager", Depends(get_study_manager)]


def get_ai_provider(request: Request) -> AIProvider:
    """Return the configured AI provider, or 503 if none is available."""
    provider = getattr(request.app.state, "ai_provider", None)
    if provider is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AI copilot is not configured (no provider available).",
        )
    provider_typed: AIProvider = provider
    return provider_typed


AiProviderDep = Annotated[AIProvider, Depends(get_ai_provider)]
