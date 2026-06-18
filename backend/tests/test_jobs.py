"""Tests du module de gestion des jobs d'upscaling."""

from io import BytesIO
from unittest.mock import patch

from httpx import AsyncClient
from PIL import Image

from tests.conftest import AUTH_HEADERS


def _make_test_image(width: int = 100, height: int = 80) -> bytes:
    """Crée une image PNG de test en mémoire."""
    img = Image.new("RGB", (width, height), color="blue")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


async def _upload_image(client: AsyncClient, width: int = 100, height: int = 80) -> str:
    """Upload une image de test et retourne la clé de stockage."""
    content = _make_test_image(width, height)
    response = await client.post(
        "/api/uploads",
        files={"file": ("img.png", content, "image/png")},
        headers=AUTH_HEADERS,
    )
    return response.json()["key"]


# ── Création de job ──────────────────────────────────────────────


@patch("app.jobs.tasks.process_upscale")
async def test_should_create_job(mock_task: object, client: AsyncClient) -> None:
    """La création d'un job retourne 201 avec le statut pending."""
    key = await _upload_image(client, 200, 150)

    response = await client.post(
        "/api/jobs",
        json={"input_key": key},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "pending"
    assert data["input_key"] == key
    assert data["input_width"] == 200
    assert data["input_height"] == 150
    assert data["scale_factor"] == 4
    # x4 → DRCT-L (routé par `_model_for_scale`).
    assert data["model_name"] == "drct-l"
    mock_task.delay.assert_called_once()  # type: ignore[attr-defined]


@patch("app.jobs.tasks.process_upscale")
async def test_should_route_scale_to_model(mock_task: object, client: AsyncClient) -> None:
    """Le modèle est dérivé du scale_factor côté serveur (pas un champ client).

    x4 → drct-l, x2 → hat-l. Tout ``model_name`` envoyé par le client est
    ignoré — c'est la source de vérité serveur qui tranche.
    """
    key = await _upload_image(client)

    # scale_factor=2 → doit router sur hat-l, même si le client tente
    # d'envoyer model_name=drct-l (champ ignoré par le schéma Pydantic).
    response = await client.post(
        "/api/jobs",
        json={"input_key": key, "scale_factor": 2, "model_name": "drct-l"},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["scale_factor"] == 2
    assert data["model_name"] == "hat-l"


@patch("app.jobs.tasks.process_upscale")
async def test_should_reject_missing_input_key(mock_task: object, client: AsyncClient) -> None:
    """Un input_key inexistant retourne 404."""
    response = await client.post(
        "/api/jobs",
        json={"input_key": "uploads/nonexistent.png"},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 404


# ── Listing ──────────────────────────────────────────────────────


@patch("app.jobs.tasks.process_upscale")
async def test_should_list_user_jobs(mock_task: object, client: AsyncClient) -> None:
    """Le listing retourne les jobs de l'utilisateur courant."""
    key = await _upload_image(client)
    await client.post("/api/jobs", json={"input_key": key}, headers=AUTH_HEADERS)
    await client.post("/api/jobs", json={"input_key": key}, headers=AUTH_HEADERS)

    response = await client.get("/api/jobs", headers=AUTH_HEADERS)

    assert response.status_code == 200
    assert len(response.json()) == 2


# ── Détail ───────────────────────────────────────────────────────


@patch("app.jobs.tasks.process_upscale")
async def test_should_get_job_detail(mock_task: object, client: AsyncClient) -> None:
    """Le détail d'un job retourne ses métadonnées complètes."""
    key = await _upload_image(client)
    create_resp = await client.post("/api/jobs", json={"input_key": key}, headers=AUTH_HEADERS)
    job_id = create_resp.json()["id"]

    response = await client.get(f"/api/jobs/{job_id}", headers=AUTH_HEADERS)

    assert response.status_code == 200
    assert response.json()["id"] == job_id


@patch("app.jobs.tasks.process_upscale")
async def test_should_return_404_for_unknown_job(mock_task: object, client: AsyncClient) -> None:
    """Un ID de job inexistant retourne 404."""
    response = await client.get(
        "/api/jobs/00000000-0000-0000-0000-000000000000",
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 404


# ── Annulation ───────────────────────────────────────────────────


@patch("app.jobs.tasks.process_upscale")
async def test_should_cancel_pending_job(mock_task: object, client: AsyncClient) -> None:
    """L'annulation d'un job pending retourne 204 et passe en cancelled."""
    key = await _upload_image(client)
    create_resp = await client.post("/api/jobs", json={"input_key": key}, headers=AUTH_HEADERS)
    job_id = create_resp.json()["id"]

    cancel_resp = await client.post(f"/api/jobs/{job_id}/cancel", headers=AUTH_HEADERS)
    assert cancel_resp.status_code == 204

    detail = await client.get(f"/api/jobs/{job_id}", headers=AUTH_HEADERS)
    assert detail.json()["status"] == "cancelled"


# ── Suppression ──────────────────────────────────────────────────


@patch("app.jobs.tasks.process_upscale")
async def test_should_delete_cancelled_job_and_its_files(
    mock_task: object, client: AsyncClient
) -> None:
    """Supprimer un job terminé retourne 204, retire la ligne ET l'input du storage."""
    key = await _upload_image(client)
    create_resp = await client.post("/api/jobs", json={"input_key": key}, headers=AUTH_HEADERS)
    job_id = create_resp.json()["id"]
    # Passe le job en état terminal (cancelled) pour autoriser la suppression.
    await client.post(f"/api/jobs/{job_id}/cancel", headers=AUTH_HEADERS)

    delete_resp = await client.delete(f"/api/jobs/{job_id}", headers=AUTH_HEADERS)
    assert delete_resp.status_code == 204

    # La ligne a disparu (404) et le fichier source n'est plus servi.
    detail = await client.get(f"/api/jobs/{job_id}", headers=AUTH_HEADERS)
    assert detail.status_code == 404
    upload_resp = await client.get(f"/api/uploads/{key}", headers=AUTH_HEADERS)
    assert upload_resp.status_code == 404


@patch("app.jobs.tasks.process_upscale")
async def test_should_refuse_delete_of_active_job(mock_task: object, client: AsyncClient) -> None:
    """Supprimer un job encore actif retourne 409 (annuler d'abord)."""
    key = await _upload_image(client)
    create_resp = await client.post("/api/jobs", json={"input_key": key}, headers=AUTH_HEADERS)
    job_id = create_resp.json()["id"]

    delete_resp = await client.delete(f"/api/jobs/{job_id}", headers=AUTH_HEADERS)
    assert delete_resp.status_code == 409


@patch("app.jobs.tasks.process_upscale")
async def test_should_bulk_delete_terminal_jobs_only(
    mock_task: object, client: AsyncClient
) -> None:
    """Le bulk-delete supprime les jobs terminés et ignore les actifs."""
    # Un job terminé (cancelled) + un job actif (pending).
    key1 = await _upload_image(client)
    j1 = (await client.post("/api/jobs", json={"input_key": key1}, headers=AUTH_HEADERS)).json()[
        "id"
    ]
    await client.post(f"/api/jobs/{j1}/cancel", headers=AUTH_HEADERS)
    key2 = await _upload_image(client)
    j2 = (await client.post("/api/jobs", json={"input_key": key2}, headers=AUTH_HEADERS)).json()[
        "id"
    ]

    resp = await client.post(
        "/api/jobs/bulk-delete", json={"job_ids": [j1, j2]}, headers=AUTH_HEADERS
    )
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 1  # seul j1 (terminal) supprimé

    assert (await client.get(f"/api/jobs/{j1}", headers=AUTH_HEADERS)).status_code == 404
    assert (await client.get(f"/api/jobs/{j2}", headers=AUTH_HEADERS)).status_code == 200


# ── Pré-warm ─────────────────────────────────────────────────────


async def test_should_warmup_noop_without_cloud(client: AsyncClient) -> None:
    """Sans backend cloud disponible, /api/warmup → warmed=false (no-op)."""
    with patch("app.core.gpu.factory.build_cloud_gpu_backend", return_value=None):
        resp = await client.post("/api/warmup", json={"scale_factor": 4}, headers=AUTH_HEADERS)
    assert resp.status_code == 200
    assert resp.json() == {"warmed": False}


async def test_should_warmup_require_auth(client: AsyncClient) -> None:
    """/api/warmup exige une authentification (pas de spam anonyme du GPU)."""
    resp = await client.post("/api/warmup", json={"scale_factor": 4})
    assert resp.status_code == 401


async def test_should_warmup_send_ping_with_cloud(client: AsyncClient) -> None:
    """Avec un backend cloud, /api/warmup envoie le ping (x2 → hat-l) et ferme."""
    from unittest.mock import AsyncMock, MagicMock

    fake_backend = MagicMock()
    fake_backend.warmup = AsyncMock()
    fake_backend.close = AsyncMock()

    with patch("app.core.gpu.factory.build_cloud_gpu_backend", return_value=fake_backend):
        resp = await client.post("/api/warmup", json={"scale_factor": 2}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    assert resp.json() == {"warmed": True}
    fake_backend.warmup.assert_awaited_once_with(scale_factor=2, model_name="hat-l")
    fake_backend.close.assert_awaited_once()
