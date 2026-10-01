"""Exercise the running Compose stack over HTTP; no browser automation."""

import http.cookiejar
import json
import re
import secrets
import urllib.error
import urllib.request

BASE = "http://localhost:3000"
jar = http.cookiejar.CookieJar()
client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def request(path, body=None):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Origin": BASE, "Content-Type": "application/json"},
    )
    try:
        with client.open(req, timeout=15) as response:
            return response.status, response.geturl(), response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.geturl(), error.read().decode()


def assert_login_redirect():
    status, url, html = request("/dashboard")
    # Next.js emits a meta refresh when redirecting after a streamed loading shell.
    assert status == 200
    assert url.endswith("/login") or re.search(
        r'<meta[^>]+http-equiv="refresh"[^>]+content="[01];url=/login"', html
    )
    assert "Your account is ready" not in html


for path in ["/", "/login", "/signup"]:
    assert request(path)[0] == 200, path
assert_login_redirect()
account = {
    "email": f"smoke-{secrets.token_hex(8)}@example.com",
    "password": secrets.token_urlsafe(24),
}
assert request("/api/auth/signup", account)[0] == 201
status, url, html = request("/dashboard")
assert status == 200 and url.endswith("/dashboard") and account["email"] in html
assert request("/api/auth/logout", {})[0] == 204
assert_login_redirect()
assert request("/api/auth/login", {**account, "password": "incorrect password"})[0] == 401
assert request("/api/auth/login", account)[0] == 200
assert request("/dashboard")[1].endswith("/dashboard")
assert request("/api/auth/logout", {})[0] == 204
print(
    "PASS: home/login/signup pages; anonymous redirect; signup; server-authenticated dashboard; logout; wrong password; login; revoked dashboard access"
)
