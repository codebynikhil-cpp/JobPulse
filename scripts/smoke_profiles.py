"""Phase 2 HTTP verification through the running Next.js proxy and server pages."""

import http.cookiejar
import json
import re
import secrets
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:3000"
ORIGIN = "http://localhost:3000"


def browser():
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
    )


def request(client, path, method="GET", data=None):
    req = urllib.request.Request(
        BASE + path,
        method=method,
        data=json.dumps(data).encode() if data is not None else None,
        headers={"Origin": ORIGIN, "Content-Type": "application/json"},
    )
    try:
        with client.open(req, timeout=15) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def sign_up(client):
    assert (
        request(
            client,
            "/api/auth/signup",
            "POST",
            {
                "email": f"profiles-smoke-{secrets.token_hex(8)}@example.com",
                "password": secrets.token_urlsafe(24),
            },
        )[0]
        == 201
    )


def anonymous_page(client, path):
    status, html = request(client, path)
    assert status == 200
    assert "Log in" in html or re.search(
        r'<meta[^>]+http-equiv="refresh"[^>]+content="[01];url=/login"', html
    )
    assert "Profile basics" not in html


client = browser()
assert request(client, "/api/profiles")[0] == 401
anonymous_page(client, "/profiles")
anonymous_page(client, "/profiles/new")
sign_up(client)
assert "Create your first profile" in request(client, "/profiles")[1]
assert "Required skills" in request(client, "/profiles/new")[1]
data = {
    "name": f"Smoke Profile {secrets.token_hex(6)}",
    "description": "An account-owned search.",
    "active": False,
    "exp_min": 0,
    "exp_max": 2,
    "employment_types": ["full_time"],
    "work_modes": ["remote"],
    "roles": [{"name": "Backend Developer"}, {"name": "Software Engineer"}],
    "skills": [{"name": "Python", "kind": "required"}, {"name": "SQL", "kind": "preferred"}],
    "locations": [{"name": "India"}],
    "exclusions": [{"term": "Senior", "kind": "keyword"}],
}
status, body = request(client, "/api/profiles", "POST", data)
assert status == 201, body
profile = json.loads(body)
url = f"/api/profiles/{profile['id']}"
assert len(json.loads(request(client, "/api/profiles")[1])) == 1
assert data["name"] in request(client, "/profiles")[1]
html = request(client, f"/profiles/{profile['id']}")[1]
assert data["name"] in html and "Python" in html and "SQL" in html
assert "Excluded keywords" in request(client, f"/profiles/{profile['id']}/edit")[1]
assert request(client, url, "PATCH", {"active": True})[0] == 200
assert json.loads(request(client, url)[1])["active"] is True
assert (
    request(
        client,
        url,
        "PATCH",
        {"skills": [{"name": "Python", "kind": "preferred"}], "exclusions": []},
    )[0]
    == 200
)
assert request(client, url, "PATCH", {"exp_min": 5})[0] == 422
assert json.loads(request(client, url)[1])["exp_min"] == "0.0"
other = browser()
sign_up(other)
assert json.loads(request(other, "/api/profiles")[1]) == []
for method, payload in [("GET", None), ("PATCH", {"active": False}), ("DELETE", None)]:
    assert request(other, url, method, payload)[0] == 404
assert data["name"] not in request(other, f"/profiles/{profile['id']}")[1]
assert request(client, url, "PATCH", {"active": False})[0] == 200
assert request(client, url, "DELETE")[0] == 204
assert request(client, url)[0] == 404
assert json.loads(request(client, "/api/profiles")[1]) == []
assert request(client, "/api/auth/logout", "POST", {})[0] == 204
assert request(client, "/api/profiles")[0] == 401
anonymous_page(client, "/profiles")
print(
    "PASS: profile pages and API proxy; create/detail/edit; configuration replacement; activation/deactivation; validation; owner isolation; delete; authenticated server rendering; logout protection"
)
