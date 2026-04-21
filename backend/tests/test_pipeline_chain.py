"""Tests des étapes et du callback d'erreur du pipeline Canvas.

Ne teste pas la chain Celery complète (nécessite broker + workers réels),
mais vérifie :

- L'enregistrement des 6 tâches Celery aux bons noms.
- ``_handle_pipeline_failure`` : transition correcte vers FAILED.
- Idempotence : un job déjà terminal n'est pas écrasé.
- ``_step_validate`` : transition DB PENDING → PROCESSING.
"""

from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.models import Job, JobStatus
from app.upscaling.pipeline import (
    _handle_pipeline_failure,
    _step_validate,
    task_notify,
    task_preprocess,
    task_route,
    task_save,
    task_upscale,
    task_validate,
)
from app.users.models import User


async def _make_job(db: AsyncSession, status: JobStatus = JobStatus.PENDING) -> Job:
    """Crée un utilisateur + un job en DB pour les tests."""
    user = User(email="chain-test@gegm.local")
    db.add(user)
    await db.commit()
    await db.refresh(user)

    job = Job(
        user_id=user.id,
        status=status,
        input_key="uploads/test.png",
        scale_factor=4,
        model_name="drct-l",
        input_width=1000,
        input_height=1000,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


def test_should_register_all_six_tasks() -> None:
    """Les 6 tâches Celery du pipeline doivent être enregistrées aux bons noms.

    Vérifie que la refacto Canvas n'a pas cassé le routage des tâches.
    """
    assert task_validate.name == "pipeline.validate"
    assert task_preprocess.name == "pipeline.preprocess"
    assert task_route.name == "pipeline.route"
    assert task_upscale.name == "pipeline.upscale"
    assert task_save.name == "pipeline.save"
    assert task_notify.name == "pipeline.notify"


def test_upscale_task_has_retry_config() -> None:
    """Seule ``task_upscale`` a un retry auto — les autres étapes sont locales."""
    # max_retries et autoretry_for sont stockés dans l'objet tâche.
    assert task_upscale.max_retries == 3
    assert task_upscale.autoretry_for == (ConnectionError, TimeoutError, OSError)

    # Les autres tâches n'ont pas de retry auto (pas d'attribut ou valeur par défaut 3).
    for task in (task_validate, task_preprocess, task_route, task_save, task_notify):
        assert not getattr(task, "autoretry_for", ()), (
            f"{task.name} ne devrait pas avoir d'autoretry_for"
        )


async def test_handle_failure_marks_job_failed(db: AsyncSession) -> None:
    """``_handle_pipeline_failure`` met le job en FAILED avec le message d'erreur."""
    job = await _make_job(db, status=JobStatus.PROCESSING)

    # On doit patcher ``_open_db_session`` pour utiliser notre session de test,
    # sinon la fonction crée son propre engine qui ne voit pas nos données
    # (isolation SAVEPOINT).
    with _patch_open_db_session(db), _mock_redis_client():
        await _handle_pipeline_failure(str(job.id), error_message="Erreur de test")

    await db.refresh(job)
    assert job.status == JobStatus.FAILED
    assert job.error_message == "Erreur de test"
    assert job.completed_at is not None


async def test_handle_failure_is_idempotent_on_completed_job(db: AsyncSession) -> None:
    """Un job déjà COMPLETED ne doit pas être écrasé par un handle_failure tardif."""
    job = await _make_job(db, status=JobStatus.COMPLETED)
    job.error_message = None
    await db.commit()

    with _patch_open_db_session(db), _mock_redis_client():
        await _handle_pipeline_failure(str(job.id), error_message="Erreur tardive")

    await db.refresh(job)
    assert job.status == JobStatus.COMPLETED
    assert job.error_message is None  # Pas écrasé.


async def test_handle_failure_gracefully_ignores_missing_job(db: AsyncSession) -> None:
    """Un ``job_id`` inexistant ne doit pas lever d'exception."""
    with _patch_open_db_session(db), _mock_redis_client():
        # UUID random qui n'existe pas.
        await _handle_pipeline_failure(
            "00000000-0000-0000-0000-000000000000",
            error_message="Erreur fantôme",
        )
    # Aucune exception attendue — le handler log un warning et retourne.


async def test_step_validate_transitions_job_to_processing(db: AsyncSession) -> None:
    """``_step_validate`` doit passer un job PENDING → PROCESSING."""
    job = await _make_job(db, status=JobStatus.PENDING)

    with _patch_open_db_session(db), _mock_redis_client():
        await _step_validate(str(job.id))

    await db.refresh(job)
    assert job.status == JobStatus.PROCESSING


# ──────────────────────────────────────────────────────────────
# Helpers de test
# ──────────────────────────────────────────────────────────────


def _patch_open_db_session(test_session: AsyncSession) -> object:
    """Patch ``_open_db_session`` pour utiliser la session de test existante.

    Nécessaire car chaque étape du pipeline crée son propre engine (pour
    isolation en production), ce qui contourne la session SAVEPOINT des
    tests. On redirige vers la session test via un context manager mocké.
    """
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _fake_open_db_session():  # type: ignore[no-untyped-def]
        yield test_session

    return patch("app.upscaling.pipeline._open_db_session", _fake_open_db_session)


def _mock_redis_client() -> object:
    """Patch ``get_sync_redis`` pour retourner un mock qui absorbe tout.

    Les étapes appellent Redis pour publier la progression ; on n'a pas
    besoin d'un vrai client dans les tests unitaires.
    """
    fake_redis = AsyncMock()
    fake_redis.close = lambda: None  # close synchrone
    fake_redis.pipeline = lambda **_: _FakePipeline()
    fake_redis.delete = lambda *_: None
    return patch("app.upscaling.pipeline.get_sync_redis", return_value=fake_redis)


class _FakePipeline:
    """Pipeline Redis mocké — absorbe toutes les opérations sans effet."""

    def set(self, *_args, **_kwargs) -> "_FakePipeline":
        return self

    def publish(self, *_args, **_kwargs) -> "_FakePipeline":
        return self

    def execute(self) -> list[object]:
        return []
