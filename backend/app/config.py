"""Application settings, loaded from the environment.

Defaults target local development (SQLite, a dev JWT secret). In production these
are supplied via environment variables (e.g. ``DATABASE_URL`` pointing at Postgres,
a real ``JWT_SECRET``). No Redis: the job queue is Postgres-backed (the
``simulations`` table itself), per the MVP infrastructure decision.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-secret-change-me-in-production-0123456789"


class Settings(BaseSettings):
    """Runtime configuration.

    Every field is overridable via a ``VCS_``-prefixed environment variable (e.g.
    ``VCS_DATABASE_URL``, ``VCS_JWT_SECRET``). Defaults target local development;
    production supplies a Postgres URL, a real secret, an explicit CORS allowlist,
    and ``VCS_WORKER_MODE=external`` (jobs run in a separate worker process).
    """

    model_config = SettingsConfigDict(env_prefix="VCS_", env_file=".env", extra="ignore")

    # Deployment environment: "development" | "production".
    environment: str = "development"

    # Database. SQLite for dev/tests; a Postgres URL in production.
    database_url: str = "sqlite:///./vcs.db"

    # Auth.
    jwt_secret: str = DEV_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24

    # CORS. Comma-separated allowed origins; empty ⇒ localhost dev default.
    cors_origins: str = ""

    # Simulation worker.
    #   "thread"   — run jobs in a background thread of the web process (single-node dev)
    #   "inline"   — run jobs synchronously inside the request (tests)
    #   "external" — the web process does not run jobs; a separate worker claims them
    worker_mode: str = "thread"
    batch_steps: int = 10  # engine steps between control checks / DB commits
    frame_stride: int = 1  # persist a frame every N steps
    worker_poll_seconds: float = 1.0  # external worker idle poll interval

    # WebSocket streaming.
    ws_poll_seconds: float = 0.2

    # AI copilot.
    ai_provider: str = "claude"  # "claude" (default) or "openai"
    ai_model: str = "claude-opus-4-8"
    openai_model: str = ""  # set to enable the OpenAI fallback

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def normalized_database_url(self) -> str:
        """SQLAlchemy-ready URL.

        Render (and many hosts) hand out ``postgres://…`` and bare
        ``postgresql://…`` URLs; SQLAlchemy 2 wants an explicit driver. Normalize
        both to ``postgresql+psycopg://…`` (psycopg 3).
        """
        url = self.database_url
        if url.startswith("postgres://"):
            return "postgresql+psycopg://" + url[len("postgres://"):]
        if url.startswith("postgresql://"):
            return "postgresql+psycopg://" + url[len("postgresql://"):]
        return url

    def cors_allow_origins(self) -> list[str]:
        """The CORS allowlist (explicit in prod; localhost in dev)."""
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        if origins:
            return origins
        return ["http://localhost:5173", "http://127.0.0.1:5173"]


def check_production_config(settings: Settings) -> None:
    """Fail fast on unsafe production configuration.

    Raises:
        RuntimeError: in production if the dev JWT secret is still in use, the DB
            is SQLite, or no CORS allowlist is configured.
    """
    if not settings.is_production:
        return
    problems: list[str] = []
    if settings.jwt_secret == DEV_JWT_SECRET:
        problems.append("VCS_JWT_SECRET is still the development default")
    if settings.normalized_database_url.startswith("sqlite"):
        problems.append("VCS_DATABASE_URL must be Postgres in production, not SQLite")
    if not settings.cors_origins.strip():
        problems.append("VCS_CORS_ORIGINS must list the allowed frontend origin(s)")
    if problems:
        raise RuntimeError("Unsafe production configuration: " + "; ".join(problems))


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings singleton."""
    return Settings()
