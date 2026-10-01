import uuid
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.main import app
from app.models.profile import Profile, ProfileExclusion, ProfileLocation, ProfileRole, ProfileSkill

TABLES = (ProfileRole, ProfileSkill, ProfileLocation, ProfileExclusion)
FULL = {
    "name": "Early Career Engineer",
    "description": "Build useful software.",
    "active": True,
    "exp_min": 0,
    "exp_max": 2.5,
    "employment_types": ["full_time", "internship"],
    "work_modes": ["remote", "hybrid"],
    "roles": [{"name": "Software Engineer"}, {"name": "Backend Developer"}],
    "skills": [{"name": "Python", "kind": "required"}, {"name": "PostgreSQL", "kind": "preferred"}],
    "locations": [{"name": "Bengaluru"}, {"name": "London", "excluded": True}],
    "exclusions": [
        {"term": "Senior", "kind": "keyword"},
        {"term": "Engineering Manager", "kind": "role"},
    ],
}


def signup(client, email="owner@example.com"):
    response = client.post(
        "/api/auth/signup", json={"email": email, "password": "a strong password 123"}
    )
    assert response.status_code == 201
    return response.json()["id"]


@pytest.fixture
def owner(client):
    signup(client)
    return client


def create(client, data=None):
    response = client.post("/api/profiles", json=FULL if data is None else data)
    assert response.status_code == 201, response.text
    return response.json()


def test_profile_crud(owner):
    assert owner.get("/api/profiles").json() == []
    profile = create(owner)
    other = create(owner, {"name": "Another search"})
    assert {item["id"] for item in owner.get("/api/profiles").json()} == {
        profile["id"],
        other["id"],
    }
    assert owner.get(f"/api/profiles/{profile['id']}").json()["name"] == FULL["name"]
    assert profile["exp_max"] == "2.5"
    assert "user_id" not in profile
    patch = owner.patch(
        f"/api/profiles/{profile['id']}",
        json={"name": "Graduate search", "description": "Updated", "exp_min": 0.5},
    )
    assert patch.status_code == 200
    assert patch.json()["name"] == "Graduate search"
    assert patch.json()["description"] == "Updated"
    assert patch.json()["roles"] == profile["roles"]
    assert patch.json()["updated_at"] > profile["updated_at"]
    assert owner.delete(f"/api/profiles/{profile['id']}").status_code == 204
    assert owner.get(f"/api/profiles/{profile['id']}").status_code == 404
    assert len(owner.get("/api/profiles").json()) == 1


def test_owner_isolation_and_related_records(owner, migrated_database):
    profile = create(owner)
    url = f"/api/profiles/{profile['id']}"
    with TestClient(app, headers={"Origin": settings.app_origin}) as attacker:
        signup(attacker, "other@example.com")
        assert attacker.get("/api/profiles").json() == []
        assert attacker.get(url).status_code == 404
        assert (
            attacker.patch(
                url,
                json={
                    "roles": [{"name": "Hijack"}],
                    "skills": [],
                    "locations": [],
                    "exclusions": [],
                },
            ).status_code
            == 404
        )
        assert attacker.patch(url, json={"active": False}).status_code == 404
        assert attacker.delete(url).status_code == 404
        # Names are unique per owner, not globally.
        assert create(attacker)["id"] != profile["id"]
    assert owner.get(url).json() == profile
    with Session(migrated_database) as db:
        for model in TABLES:
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(model)
                    .where(model.profile_id == uuid.UUID(profile["id"]))
                )
                == 2
            )


def test_related_replacement_and_cascade(owner, migrated_database):
    profile = create(owner)
    url = f"/api/profiles/{profile['id']}"
    # Replacing with the same normalized key must not produce a transient UNIQUE error.
    response = owner.patch(
        url,
        json={
            "skills": [{"name": "python", "kind": "preferred"}],
            "roles": [{"name": "Software Engineer"}],
            "locations": [{"name": "Remote - India"}],
            "exclusions": [],
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["skills"] == [{"name": "python", "kind": "preferred"}]
    with Session(migrated_database) as db:
        for model, count in zip(TABLES, (1, 1, 1, 0), strict=True):
            assert db.scalar(select(func.count()).select_from(model)) == count
    assert (
        owner.patch(
            url, json={"active": False, "roles": [], "skills": [], "locations": []}
        ).status_code
        == 200
    )
    assert owner.get(url).json()["skills"] == []
    assert owner.delete(url).status_code == 204
    with Session(migrated_database) as db:
        assert db.scalar(select(func.count()).select_from(Profile)) == 0
        for model in TABLES:
            assert db.scalar(select(func.count()).select_from(model)) == 0


def test_database_user_delete_cascades(owner, migrated_database):
    create(owner)
    with migrated_database.begin() as conn:
        conn.execute(text("DELETE FROM users"))
    with Session(migrated_database) as db:
        for model in (Profile, *TABLES):
            assert db.scalar(select(func.count()).select_from(model)) == 0


@pytest.mark.parametrize(
    "change",
    [
        {"name": "   "},
        {"description": "Invalid" + chr(0)},
        {"roles": [{"name": "Developer" + chr(0)}]},
        {"name": "x" * 101},
        {"description": "x" * 2001},
        {"exp_min": -1},
        {"exp_max": 61},
        {"exp_min": 3, "exp_max": 2},
        {"exp_min": 0.01},
        {"employment_types": ["volunteer"]},
        {"work_modes": ["unknown"]},
        {"employment_types": ["full_time", "full_time"]},
        {"work_modes": ["remote", "remote"]},
        {"roles": [{"name": "Python Dev"}, {"name": " python   dev "}]},
        {
            "skills": [
                {"name": "Python", "kind": "required"},
                {"name": "python", "kind": "preferred"},
            ]
        },
        {"skills": [{"name": "Python", "kind": "excluded"}]},
        {"locations": [{"name": "India"}, {"name": " india ", "excluded": True}]},
        {
            "exclusions": [
                {"term": "Senior", "kind": "keyword"},
                {"term": " senior ", "kind": "role"},
            ]
        },
        {"roles": [{"name": " "}]},
        {"skills": [{"name": "", "kind": "required"}]},
        {"locations": [{"name": " "}]},
        {"exclusions": [{"term": ""}]},
        {"exclusions": [{"term": "Software Engineer", "kind": "role"}]},
        {"roles": [], "active": True},
        {"roles": [{"name": "Role"}] * 51},
        {"user_id": str(uuid.uuid4())},
        {"roles": [{"name": "Developer", "profile_id": str(uuid.uuid4())}]},
    ],
)
def test_create_validation(owner, change):
    assert owner.post("/api/profiles", json={**deepcopy(FULL), **change}).status_code == 422
    assert owner.get("/api/profiles").json() == []


@pytest.mark.parametrize(
    "field",
    [
        "name",
        "description",
        "active",
        "roles",
        "skills",
        "locations",
        "exclusions",
        "employment_types",
        "work_modes",
    ],
)
def test_patch_null_rejected(owner, field):
    profile = create(owner)
    assert owner.patch(f"/api/profiles/{profile['id']}", json={field: None}).status_code == 422
    assert owner.get(f"/api/profiles/{profile['id']}").json() == profile


def test_partial_patch_merged_validation_and_atomicity(owner):
    profile = create(owner)
    url = f"/api/profiles/{profile['id']}"
    assert owner.patch(url, json={"exp_min": 3}).status_code == 422
    assert owner.patch(url, json={"roles": [], "skills": []}).status_code == 422
    assert owner.patch(url, json={"roles": [{"name": "Senior"}]}).status_code == 422
    assert owner.get(url).json() == profile
    assert owner.patch(url, json={"exp_max": None}).status_code == 200
    assert owner.get(url).json()["exp_max"] is None
    assert owner.patch(url, json={}).status_code == 200


def test_name_normalization_and_unique_conflicts(owner):
    wide = "".join(chr(ord(c) + 0xFEE0) if c.isalpha() else c for c in "EARLY CAREER ENGINEER")
    first = create(owner, {"name": "  " + wide + "  "})
    assert first["name"] == "EARLY CAREER ENGINEER"
    assert owner.post("/api/profiles", json={"name": "early   career engineer"}).status_code == 409
    second = create(owner, {"name": "Second"})
    assert (
        owner.patch(
            f"/api/profiles/{second['id']}",
            json={"name": FULL["name"], "roles": [{"name": "Uncommitted"}]},
        ).status_code
        == 409
    )
    assert owner.get(f"/api/profiles/{second['id']}").json() == second


def test_activation_deactivation(owner):
    profile = create(owner, {"name": "Draft"})
    url = f"/api/profiles/{profile['id']}"
    assert profile["active"] is False
    assert owner.patch(url, json={"active": True}).status_code == 422
    assert (
        owner.patch(url, json={"active": True, "roles": [{"name": "Developer"}]}).json()["active"]
        is True
    )
    assert owner.patch(url, json={"active": False}).json()["active"] is False
    assert len(owner.get(url).json()["roles"]) == 1


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("get", "/api/profiles", None),
        ("post", "/api/profiles", {"name": "Test"}),
        ("get", "/api/profiles/00000000-0000-0000-0000-000000000001", None),
        ("patch", "/api/profiles/00000000-0000-0000-0000-000000000001", {"active": False}),
        ("delete", "/api/profiles/00000000-0000-0000-0000-000000000001", None),
    ],
)
def test_authentication_required(client, method, path, payload):
    assert (
        getattr(client, method)(
            path, **({"json": payload} if payload is not None else {})
        ).status_code
        == 401
    )


def test_profile_origin_guard(owner):
    profile = create(owner)
    headers = {"Origin": "https://evil.example"}
    assert owner.post("/api/profiles", json={"name": "Bad"}, headers=headers).status_code == 403
    assert (
        owner.patch(
            f"/api/profiles/{profile['id']}", json={"active": False}, headers=headers
        ).status_code
        == 403
    )
    assert owner.delete(f"/api/profiles/{profile['id']}", headers=headers).status_code == 403


def test_missing_and_invalid_ids(owner):
    url = f"/api/profiles/{uuid.uuid4()}"
    assert owner.get(url).status_code == 404
    assert owner.patch(url, json={"active": False}).status_code == 404
    assert owner.delete(url).status_code == 404
    assert owner.get("/api/profiles/not-a-uuid").status_code == 422


def test_pagination(owner):
    ids = {create(owner, {"name": f"Search {index}"})["id"] for index in range(4)}
    first = owner.get("/api/profiles?limit=2&offset=0").json()
    second = owner.get("/api/profiles?limit=2&offset=2").json()
    assert {item["id"] for item in first + second} == ids
    assert len(first) == len(second) == 2
    assert owner.get("/api/profiles?limit=101").status_code == 422
    assert owner.get("/api/profiles?offset=-1").status_code == 422


def test_database_constraints_and_cascades(owner, migrated_database):
    profile = create(owner)
    inspector = inspect(migrated_database)
    assert {
        "alembic_version",
        "users",
        "auth_sessions",
        "auth_rate_limits",
        "profiles",
        "profile_roles",
        "profile_skills",
        "profile_locations",
        "profile_exclusions",
    } <= set(inspector.get_table_names())
    assert any(
        index["column_names"] == ["user_id", "created_at", "id"]
        for index in inspector.get_indexes("profiles")
    )
    for model in TABLES:
        fk = inspector.get_foreign_keys(model.__tablename__)[0]
        assert fk["referred_table"] == "profiles"
        assert fk["options"]["ondelete"] == "CASCADE"
        with Session(migrated_database) as db:
            existing = db.scalar(select(model))
            field = "term" if model is ProfileExclusion else "name"
            values = {
                field: getattr(existing, field),
                f"normalized_{field}": getattr(existing, f"normalized_{field}"),
            }
            if hasattr(existing, "kind"):
                values["kind"] = existing.kind
            if hasattr(existing, "excluded"):
                values["excluded"] = existing.excluded
            db.add(model(profile_id=uuid.UUID(profile["id"]), **values))
            with pytest.raises(IntegrityError):
                db.commit()
            db.rollback()
    with Session(migrated_database) as db:
        record = db.get(Profile, uuid.UUID(profile["id"]))
        record.exp_min = 50
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    # Exercise PostgreSQL cascades without relying on the ORM's delete-orphan behavior.
    with migrated_database.begin() as conn:
        conn.execute(text("DELETE FROM profiles WHERE id = :id"), {"id": profile["id"]})
    with Session(migrated_database) as db:
        for model in TABLES:
            assert db.scalar(select(func.count()).select_from(model)) == 0


def test_concurrent_duplicate_name(owner):
    cookie = owner.cookies.get(settings.cookie_name)

    def attempt(_):
        with TestClient(
            app,
            headers={"Origin": settings.app_origin, "Cookie": f"{settings.cookie_name}={cookie}"},
        ) as c:
            return c.post("/api/profiles", json=FULL).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, range(2)))
    assert sorted(results) == [201, 409]
    assert len(owner.get("/api/profiles").json()) == 1


def test_migration_round_trip_preserves_auth(owner, migrated_database):
    import os
    import subprocess

    env = dict(os.environ, DATABASE_URL=migrated_database.url.render_as_string(hide_password=False))
    create(owner)
    subprocess.run(["alembic", "downgrade", "0002"], env=env, check=True)
    try:
        assert "profiles" not in inspect(migrated_database).get_table_names()
        assert owner.get("/api/auth/me").status_code == 200
    finally:
        subprocess.run(["alembic", "upgrade", "head"], env=env, check=True)
    assert owner.get("/api/profiles").json() == []
    assert owner.get("/api/auth/me").status_code == 200


def test_concurrent_partial_updates_preserve_other_fields(owner):
    profile = create(owner)
    cookie = owner.cookies.get(settings.cookie_name)
    url = f"/api/profiles/{profile['id']}"

    def change(payload):
        with TestClient(
            app,
            headers={"Origin": settings.app_origin, "Cookie": f"{settings.cookie_name}={cookie}"},
        ) as c:
            return c.patch(url, json=payload).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(
            pool.map(
                change, [{"description": "Concurrent description"}, {"work_modes": ["onsite"]}]
            )
        )
    assert statuses == [200, 200]
    result = owner.get(url).json()
    assert result["description"] == "Concurrent description"
    assert result["work_modes"] == ["onsite"]
