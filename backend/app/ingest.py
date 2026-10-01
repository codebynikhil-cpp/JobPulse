"""Explicit manual live ingestion: python -m app.ingest SOURCE_UUID."""

import argparse
import asyncio
import json
import uuid
from dataclasses import asdict

from app.db.session import SessionLocal
from app.models import auth, catalog, job, profile  # noqa: F401
from app.services.ingestion import ingest_source


def main():
    parser = argparse.ArgumentParser(description="Manually fetch a configured Greenhouse source")
    parser.add_argument("source_id", type=uuid.UUID)
    args = parser.parse_args()
    result = asyncio.run(ingest_source(SessionLocal, args.source_id))
    print(json.dumps(asdict(result)))


if __name__ == "__main__":
    main()
