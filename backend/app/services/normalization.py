import hashlib
import html
import json
import unicodedata
import uuid
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.schemas.job import JobCreate
from app.sources.base import RawJob


def clean_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        if not self.hidden:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.hidden:
            self.hidden -= 1
        self.parts.append(" ")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def description_text(value: str) -> str:
    # Greenhouse descriptions may encode markup more than once. Bounded decoding.
    for _ in range(2):
        value = html.unescape(value)
    parser = TextExtractor()
    parser.feed(value)
    return clean_text("".join(parser.parts))


def normalize_url(value: str) -> str:
    parts = urlsplit(value)
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in {"gclid", "fbclid"}
    ]
    # Keep identity-bearing parameters such as gh_jid; never fetch this URL.
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path.rstrip("/") or "/",
            urlencode(sorted(query)),
            "",
        )
    )


def normalize_job(
    raw: RawJob, *, company_id: uuid.UUID, source_id: uuid.UUID, seen_at: datetime
) -> JobCreate:
    values = dict(
        title=clean_text(raw.title),
        description=description_text(raw.description),
        location=clean_text(raw.location),
        employment_type=raw.employment_type,
        experience_text=None,
        application_url=normalize_url(raw.url),
    )
    encoded = json.dumps(values, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    return JobCreate(
        company_id=company_id,
        source_id=source_id,
        external_job_id=raw.external_id,
        **values,
        source_url=normalize_url(raw.url),
        posted_at=raw.posted_at,
        first_seen_at=seen_at,
        last_seen_at=seen_at,
        raw_data=raw.raw,
        content_hash=hashlib.sha256(encoded).hexdigest(),
    )
