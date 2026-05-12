from datetime import UTC, datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


def utc_now() -> datetime:
    return datetime.now(UTC)


JsonType = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class GitHubInstallation(Base, TimestampMixin):
    __tablename__ = "github_installations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), nullable=True, index=True)
    github_installation_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    account_login: Mapped[str] = mapped_column(String(255), default="")
    account_type: Mapped[str] = mapped_column(String(64), default="")
    permissions_json: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)

    user: Mapped["UserAccount | None"] = relationship(back_populates="github_installations")
    repositories: Mapped[list["Repository"]] = relationship(back_populates="installation")


class UserAccount(Base, TimestampMixin):
    __tablename__ = "user_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    clerk_user_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(320), default="")
    display_name: Mapped[str] = mapped_column(String(255), default="")
    default_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)

    provider_credentials: Mapped[list["ProviderCredential"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    github_installations: Mapped[list[GitHubInstallation]] = relationship(back_populates="user")
    repository_access: Mapped[list["RepositoryAccess"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    agent_runs: Mapped[list["AgentRun"]] = relationship(back_populates="user")
    api_token_grants: Mapped[list["ApiTokenGrant"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class ApiTokenGrant(Base, TimestampMixin):
    __tablename__ = "api_token_grants"
    __table_args__ = (UniqueConstraint("token_family_id", name="uq_api_token_grants_family"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    token_family_id: Mapped[str] = mapped_column(String(128), index=True)
    label: Mapped[str] = mapped_column(String(255), default="")
    scopes_json: Mapped[list[str]] = mapped_column(JsonType, default=list)
    status: Mapped[str] = mapped_column(String(64), default="active", index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_reason: Mapped[str] = mapped_column(String(255), default="")

    user: Mapped[UserAccount] = relationship(back_populates="api_token_grants")
    refresh_tokens: Mapped[list["ApiRefreshToken"]] = relationship(
        back_populates="grant", cascade="all, delete-orphan"
    )


class ApiRefreshToken(Base):
    __tablename__ = "api_refresh_tokens"
    __table_args__ = (UniqueConstraint("token_hash", name="uq_api_refresh_tokens_hash"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    grant_id: Mapped[int] = mapped_column(ForeignKey("api_token_grants.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by_id: Mapped[int | None] = mapped_column(ForeignKey("api_refresh_tokens.id"), nullable=True)

    grant: Mapped[ApiTokenGrant] = relationship(back_populates="refresh_tokens", foreign_keys=[grant_id])
    replaced_by: Mapped["ApiRefreshToken | None"] = relationship(remote_side=[id], foreign_keys=[replaced_by_id])


class ProviderCredential(Base, TimestampMixin):
    __tablename__ = "provider_credentials"
    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_provider_credentials_user_provider"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    provider: Mapped[str] = mapped_column(String(64), index=True)
    encrypted_api_key: Mapped[str] = mapped_column(Text)
    key_hint: Mapped[str] = mapped_column(String(32), default="")
    model_name: Mapped[str] = mapped_column(String(255), default="")
    base_url: Mapped[str] = mapped_column(String(512), default="")
    status: Mapped[str] = mapped_column(String(64), default="stored")
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[UserAccount] = relationship(back_populates="provider_credentials")


class Repository(Base, TimestampMixin):
    __tablename__ = "repositories"
    __table_args__ = (UniqueConstraint("github_repo_id", name="uq_repositories_github_repo_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    installation_id: Mapped[int | None] = mapped_column(ForeignKey("github_installations.id"), nullable=True)
    github_repo_id: Mapped[int] = mapped_column(BigInteger, index=True)
    owner: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(512), index=True)
    default_branch: Mapped[str] = mapped_column(String(255), default="main")
    private: Mapped[bool] = mapped_column(Boolean, default=False)
    policy_json: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)

    installation: Mapped[GitHubInstallation | None] = relationship(back_populates="repositories")
    webhook_events: Mapped[list["WebhookEvent"]] = relationship(back_populates="repository")
    agent_runs: Mapped[list["AgentRun"]] = relationship(back_populates="repository")
    user_access: Mapped[list["RepositoryAccess"]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )


class RepositoryAccess(Base, TimestampMixin):
    __tablename__ = "repository_access"
    __table_args__ = (UniqueConstraint("user_id", "repository_id", name="uq_repository_access_user_repo"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), index=True)
    role: Mapped[str] = mapped_column(String(64), default="admin")

    user: Mapped[UserAccount] = relationship(back_populates="repository_access")
    repository: Mapped[Repository] = relationship(back_populates="user_access")


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    github_delivery_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    github_event: Mapped[str] = mapped_column(String(128), index=True)
    action: Mapped[str] = mapped_column(String(128), default="")
    installation_id: Mapped[int | None] = mapped_column(ForeignKey("github_installations.id"), nullable=True)
    repository_id: Mapped[int | None] = mapped_column(ForeignKey("repositories.id"), nullable=True)
    sender_login: Mapped[str] = mapped_column(String(255), default="")
    payload_json: Mapped[dict[str, Any]] = mapped_column(JsonType)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(64), default="received")

    installation: Mapped[GitHubInstallation | None] = relationship()
    repository: Mapped[Repository | None] = relationship(back_populates="webhook_events")


class AgentRun(Base, TimestampMixin):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), nullable=True, index=True)
    repository_id: Mapped[int | None] = mapped_column(ForeignKey("repositories.id"), nullable=True)
    issue_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    issue_title: Mapped[str] = mapped_column(String(512), default="")
    issue_url: Mapped[str] = mapped_column(String(1024), default="")
    comment_url: Mapped[str] = mapped_column(String(1024), default="")
    pull_request_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pull_request_url: Mapped[str] = mapped_column(String(1024), default="")
    github_delivery_id: Mapped[str] = mapped_column(String(128), index=True)
    trigger_type: Mapped[str] = mapped_column(String(128))
    trigger_actor: Mapped[str] = mapped_column(String(255), default="")
    command: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(64), default="parsed_command", index=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    branch_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    base_sha: Mapped[str | None] = mapped_column(String(128), nullable=True)
    head_sha: Mapped[str | None] = mapped_column(String(128), nullable=True)
    plan_json: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    diff_summary_json: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    test_summary_json: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    review_summary_json: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancellation_requested: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped[UserAccount | None] = relationship(back_populates="agent_runs")
    repository: Mapped[Repository | None] = relationship(back_populates="agent_runs")


class RunEvent(Base):
    __tablename__ = "run_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(128), index=True)
    message: Mapped[str] = mapped_column(Text, default="")
    payload_json: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("user_accounts.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(128), index=True)
    target_type: Mapped[str] = mapped_column(String(128), default="")
    target_id: Mapped[str] = mapped_column(String(128), default="")
    payload_json: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
