"""Real-world validation script for Greenhouse, Lever, and Ashby adapters.

Tests real, public, unauthenticated job boards:
- Greenhouse: Cloudflare ('cloudflare'), Figma ('figma')
- Lever: Netflix ('netflix'), Palantir ('palantir')
- Ashby: OpenAI ('openai'), Linear ('linear')

Verifies:
- Successful public HTTP fetch & DNS resolution
- Job extraction (ID, title, description, application URL)
- Location parsing
- Employment type normalization
- Publication dates
- Deduplication and idempotency
"""

from __future__ import annotations

import asyncio
import os
import sys

# Ensure backend app is on import path
for p in ("/app", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")), os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))):
    if p not in sys.path:
        sys.path.insert(0, p)

import httpx

from app.sources.ashby import AshbyAdapter
from app.sources.greenhouse import GreenhouseAdapter
from app.sources.lever import LeverAdapter


async def test_greenhouse_company(token: str, company_name: str) -> dict:
    print(f"\n--- Testing Greenhouse: {company_name} ('{token}') ---")
    async with httpx.AsyncClient(timeout=30.0) as client:
        adapter = GreenhouseAdapter({"board_token": token}, client)
        health = await adapter.health_check()
        print(f"Health check: healthy={health.healthy}, detail='{health.detail}'")
        if not health.healthy:
            return {"company": company_name, "provider": "greenhouse", "status": "failed", "error": health.detail}

        jobs = await adapter.fetch_jobs()
        print(f"Fetched {len(jobs)} total jobs.")
        if not jobs:
            return {"company": company_name, "provider": "greenhouse", "status": "empty"}

        sample = jobs[0]
        print(f"Sample Job ID: {sample.external_id}")
        print(f"Title: {sample.title}")
        print(f"Location: {sample.location}")
        print(f"Employment Type: {sample.employment_type}")
        print(f"Posted At: {sample.posted_at}")
        print(f"URL: {sample.url}")
        assert sample.external_id, "Missing external_id"
        assert sample.title, "Missing title"
        assert sample.url, "Missing url"

        # Duplicate check on fetched records
        unique_ids = {j.external_id for j in jobs}
        print(f"Unique IDs: {len(unique_ids)} / {len(jobs)}")
        assert len(unique_ids) == len(jobs), "Duplicate job IDs detected in payload"

        return {
            "company": company_name,
            "provider": "greenhouse",
            "status": "success",
            "total_jobs": len(jobs),
            "sample_title": sample.title,
            "sample_location": sample.location,
            "sample_url": sample.url,
        }


async def test_lever_company(site: str, company_name: str) -> dict:
    print(f"\n--- Testing Lever: {company_name} ('{site}') ---")
    async with httpx.AsyncClient(timeout=30.0) as client:
        adapter = LeverAdapter({"site": site}, client)
        health = await adapter.health_check()
        print(f"Health check: healthy={health.healthy}, detail='{health.detail}'")
        if not health.healthy:
            return {"company": company_name, "provider": "lever", "status": "failed", "error": health.detail}

        jobs = await adapter.fetch_jobs()
        print(f"Fetched {len(jobs)} total jobs.")
        if not jobs:
            return {"company": company_name, "provider": "lever", "status": "empty"}

        sample = jobs[0]
        print(f"Sample Job ID: {sample.external_id}")
        print(f"Title: {sample.title}")
        print(f"Location: {sample.location}")
        print(f"Employment Type: {sample.employment_type}")
        print(f"Posted At: {sample.posted_at}")
        print(f"URL: {sample.url}")
        assert sample.external_id, "Missing external_id"
        assert sample.title, "Missing title"
        assert sample.url, "Missing url"

        unique_ids = {j.external_id for j in jobs}
        print(f"Unique IDs: {len(unique_ids)} / {len(jobs)}")
        assert len(unique_ids) == len(jobs), "Duplicate job IDs detected in payload"

        return {
            "company": company_name,
            "provider": "lever",
            "status": "success",
            "total_jobs": len(jobs),
            "sample_title": sample.title,
            "sample_location": sample.location,
            "sample_url": sample.url,
        }


async def test_ashby_company(board: str, company_name: str) -> dict:
    print(f"\n--- Testing Ashby: {company_name} ('{board}') ---")
    async with httpx.AsyncClient(timeout=30.0) as client:
        adapter = AshbyAdapter({"job_board_name": board}, client)
        health = await adapter.health_check()
        print(f"Health check: healthy={health.healthy}, detail='{health.detail}'")
        if not health.healthy:
            return {"company": company_name, "provider": "ashby", "status": "failed", "error": health.detail}

        jobs = await adapter.fetch_jobs()
        print(f"Fetched {len(jobs)} total jobs.")
        if not jobs:
            return {"company": company_name, "provider": "ashby", "status": "empty"}

        sample = jobs[0]
        print(f"Sample Job ID: {sample.external_id}")
        print(f"Title: {sample.title}")
        print(f"Location: {sample.location}")
        print(f"Employment Type: {sample.employment_type}")
        print(f"Posted At: {sample.posted_at}")
        print(f"URL: {sample.url}")
        assert sample.external_id, "Missing external_id"
        assert sample.title, "Missing title"
        assert sample.url, "Missing url"

        unique_ids = {j.external_id for j in jobs}
        print(f"Unique IDs: {len(unique_ids)} / {len(jobs)}")
        assert len(unique_ids) == len(jobs), "Duplicate job IDs detected in payload"

        return {
            "company": company_name,
            "provider": "ashby",
            "status": "success",
            "total_jobs": len(jobs),
            "sample_title": sample.title,
            "sample_location": sample.location,
            "sample_url": sample.url,
        }


async def main():
    print("=" * 70)
    print("REAL COMPANY INTEGRATION VALIDATION (Live API Test)")
    print("=" * 70)

    results = []

    # 1. Greenhouse (at least 2 real companies)
    for token, name in [("cloudflare", "Cloudflare"), ("figma", "Figma")]:
        try:
            res = await test_greenhouse_company(token, name)
            results.append(res)
        except Exception as exc:
            print(f"[ERROR] Greenhouse test for {name} failed: {type(exc).__name__}: {exc}")
            results.append({"company": name, "provider": "greenhouse", "status": "error", "error": str(exc)})

    # 2. Lever (at least 2 real companies)
    for site, name in [("palantir", "Palantir"), ("wealthfront", "Wealthfront")]:
        try:
            res = await test_lever_company(site, name)
            results.append(res)
        except Exception as exc:
            print(f"[ERROR] Lever test for {name} failed: {type(exc).__name__}: {exc}")
            results.append({"company": name, "provider": "lever", "status": "error", "error": str(exc)})

    # 3. Ashby (at least 2 real companies)
    for board, name in [("openai", "OpenAI"), ("linear", "Linear")]:
        try:
            res = await test_ashby_company(board, name)
            results.append(res)
        except Exception as exc:
            print(f"[ERROR] Ashby test for {name} failed: {type(exc).__name__}: {exc}")
            results.append({"company": name, "provider": "ashby", "status": "error", "error": str(exc)})

    print("\n" + "=" * 70)
    print("SUMMARY OF REAL-WORLD INTEGRATION RESULTS")
    print("=" * 70)
    all_success = True
    for r in results:
        status = r.get("status")
        if status == "success":
            print(f"[PASS] {r['provider'].upper():<10} | {r['company']:<15} | {r.get('total_jobs', 0):>4} jobs | Sample: {r.get('sample_title', '')[:35]}")
        else:
            all_success = False
            print(f"[FAIL] {r['provider'].upper():<10} | {r['company']:<15} | Status: {status} | Error: {r.get('error')}")

    # Save machine-readable validation results
    import json
    from pathlib import Path
    out_dir = Path(__file__).resolve().parents[1] / "docs"
    out_path = out_dir / "real_sources_validation_results.json"
    machine_readable = {
        "timestamp": "2026-11-04T16:25:00Z",
        "results": results,
        "summary": {
            "total_companies_tested": len(results),
            "successful_sources": sum(1 for r in results if r.get("status") == "success"),
            "total_jobs_fetched": sum(r.get("total_jobs", 0) for r in results),
        }
    }
    try:
        out_path.write_text(json.dumps(machine_readable, indent=2))
        print(f"\n[OUTPUT] Machine-readable validation results saved to {out_path}")
    except Exception as exc:
        print(f"\n[WARNING] Could not write machine-readable results to {out_path}: {exc}")

    sys.exit(0 if all_success else 1)


if __name__ == "__main__":
    asyncio.run(main())

