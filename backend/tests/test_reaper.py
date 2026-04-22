"""Tests du reaper de jobs zombies (``app.jobs.reaper``).

Dépend d'une session DB Postgres transactionnelle (fixture ``db`` du
conftest). Marqué avec ``pytest.mark.asyncio`` via la config auto de
``pytest-asyncio`` — on suit le pattern de ``test_users.py``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.models import Job, JobStatus
from app.jobs.reaper import reap_stale_jobs
from app.users.models import User


async def _make_user(db: AsyncSession) -> User:
    """Crée un utilisateur minimal pour rattacher les jobs des tests."""
    user = User(email=f"reaper-{uuid.uuid4().hex[:8]}@test.local", name="Reaper User")
    db.add(user)
    await db.flush()
    return user


async def _make_job(
    db: AsyncSession,
    user: User,
    *,
    status: JobStatus,
    updated_at: datetime,
) -> Job:
    """Crée un job et force son ``updated_at`` pour simuler un zombie."""
    job = Job(
        user_id=user.id,
        status=status,
        input_key=f"uploads/{uuid.uuid4()}.png",
        scale_factor=4,
        model_name="drct-l",
        input_width=1000,
        input_height=1000,
        progress=0.4,
    )
    db.add(job)
    await db.flush()
    # ``updated_at`` a ``onupdate=now()`` — pour simuler un vrai zombie on
    # doit écrire la valeur APRÈS l'insert, puis éviter que le flush
    # suivant la rafraîchisse (pas d'autres writes sur ce job).
    job.updated_at = updated_at
    await db.flush()
    return job


@pytest.mark.asyncio
async def test_should_reap_stale_processing_job(db: AsyncSession) -> None:
    user = await _make_user(db)
    old = datetime.now(UTC) - timedelta(minutes=45)
    job = await _make_job(db, user, status=JobStatus.PROCESSING, updated_at=old)

    result = await reap_stale_jobs(db, threshold_minutes=30)

    assert result == {"reaped": 1}
    # Le bulk UPDATE du reaper ne rafraîchit pas l'identity map — on force
    # un re-fetch via refresh pour voir les valeurs post-UPDATE.
    await db.refresh(job)
    assert job.status == JobStatus.FAILED
    assert job.error_message is not None
    assert "zombie" in job.error_message.lower()
    assert job.completed_at is not None


@pytest.mark.asyncio
async def test_should_not_reap_recently_updated_processing_job(
    db: AsyncSession,
) -> None:
    user = await _make_user(db)
    recent = datetime.now(UTC) - timedelta(minutes=5)
    job = await _make_job(db, user, status=JobStatus.PROCESSING, updated_at=recent)

    result = await reap_stale_jobs(db, threshold_minutes=30)

    assert result == {"reaped": 0}
    await db.refresh(job)
    assert job.status == JobStatus.PROCESSING


@pytest.mark.asyncio
async def test_should_not_reap_completed_or_failed_jobs(db: AsyncSession) -> None:
    user = await _make_user(db)
    old = datetime.now(UTC) - timedelta(hours=6)
    completed = await _make_job(db, user, status=JobStatus.COMPLETED, updated_at=old)
    failed = await _make_job(db, user, status=JobStatus.FAILED, updated_at=old)
    cancelled = await _make_job(db, user, status=JobStatus.CANCELLED, updated_at=old)

    result = await reap_stale_jobs(db, threshold_minutes=30)

    assert result == {"reaped": 0}
    for job, expected in (
        (completed, JobStatus.COMPLETED),
        (failed, JobStatus.FAILED),
        (cancelled, JobStatus.CANCELLED),
    ):
        await db.refresh(job)
        assert job.status == expected


@pytest.mark.asyncio
async def test_should_handle_zero_stale_jobs(db: AsyncSession) -> None:
    result = await reap_stale_jobs(db, threshold_minutes=30)
    assert result == {"reaped": 0}


@pytest.mark.asyncio
async def test_should_bail_out_on_invalid_threshold(db: AsyncSession) -> None:
    result = await reap_stale_jobs(db, threshold_minutes=0)
    assert result == {"reaped": 0}
