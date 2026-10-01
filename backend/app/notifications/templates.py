from __future__ import annotations

import html
from typing import Any
from urllib.parse import urlparse


def _is_safe_url(url: str | None) -> bool:
    if not url or not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def _format_experience(job_dict: dict[str, Any]) -> str | None:
    min_exp = job_dict.get("min_exp_years")
    max_exp = job_dict.get("max_exp_years")
    exp_text = job_dict.get("experience_text")

    if min_exp is not None and max_exp is not None:
        return f"{min_exp} - {max_exp} years"
    if min_exp is not None:
        return f"At least {min_exp} years"
    if max_exp is not None:
        return f"Up to {max_exp} years"
    if exp_text and isinstance(exp_text, str) and exp_text.strip():
        return exp_text.strip()
    return None


def _format_score(score: Any) -> str:
    if score is None:
        return "N/A"
    try:
        val = float(score)
        if 0.0 <= val <= 1.0:
            return f"{int(round(val * 100))}%"
        return f"{val:.1f}"
    except (ValueError, TypeError):
        return str(score)


def _extract_reasons(evidence: dict[str, Any] | None) -> list[str]:
    if not evidence or not isinstance(evidence, dict):
        return []
    reasons = []

    # Check for breakdown or direct reasons in evidence
    breakdown = evidence.get("breakdown")
    if isinstance(breakdown, dict):
        roles = breakdown.get("matched_roles")
        if roles and isinstance(roles, list):
            reasons.append(f"Matched role(s): {', '.join(str(r) for r in roles)}")
        skills = breakdown.get("matched_skills")
        if skills and isinstance(skills, list):
            reasons.append(
                f"Matched skill(s): {', '.join(str(s) for r in skills for s in (r if isinstance(r, list) else [r]))}"
            )
        loc = breakdown.get("location_match")
        if loc and isinstance(loc, (str, bool)):
            reasons.append(f"Location match: {loc}")

    raw_reasons = evidence.get("reasons")
    if isinstance(raw_reasons, list):
        for r in raw_reasons:
            if isinstance(r, str) and r.strip() and r not in reasons:
                reasons.append(r.strip())

    summary = evidence.get("summary")
    if isinstance(summary, str) and summary.strip() and summary not in reasons:
        reasons.append(summary.strip())

    return reasons


def render_notification_email(payload: dict[str, Any]) -> tuple[str, str, str]:
    """Render notification payload into (subject, text_body, html_body).

    All dynamic inputs are strictly escaped for HTML output to prevent XSS/injection.
    Unknown/missing fields are omitted without fabrication.
    """
    company = str(payload.get("company") or "").strip() or "Company"
    job = payload.get("job") or {}
    title = str(job.get("title") or "").strip() or "Open Position"
    location = str(job.get("location") or "").strip()
    employment_type = str(job.get("employment_type") or "").strip()
    exp_str = _format_experience(job)
    app_url = job.get("application_url")
    career_url = job.get("career_url")
    source_url = job.get("source_url")
    profiles = payload.get("profiles") or []

    # Subject line
    is_changed = any(k for k in ("revision", "kind") if payload.get(k) == "changed_job")
    prefix = "[JobPulse] Updated Job Match" if is_changed else "[JobPulse] New Matching Job"
    subject = f"{prefix}: {title} at {company}"

    # Plain text body
    text_lines = [
        f"{'Updated' if is_changed else 'New'} Job Match at {company}",
        "=" * 40,
        f"Company: {company}",
        f"Role: {title}",
    ]
    if location:
        text_lines.append(f"Location: {location}")
    if employment_type:
        text_lines.append(f"Employment Type: {employment_type.replace('_', ' ').title()}")
    if exp_str:
        text_lines.append(f"Experience: {exp_str}")

    text_lines.append("\nMatching Profile(s):")
    for p in profiles:
        p_name = p.get("name") or "Unnamed Profile"
        p_score = _format_score(p.get("score"))
        text_lines.append(f"- {p_name} (Score: {p_score})")
        reasons = _extract_reasons(p.get("evidence"))
        for reason in reasons:
            text_lines.append(f"    * {reason}")

    text_lines.append("\nApplication & Career Details:")
    if _is_safe_url(app_url):
        text_lines.append(f"Application URL: {app_url}")
    if _is_safe_url(career_url):
        text_lines.append(f"Career Site: {career_url}")
    elif _is_safe_url(source_url):
        text_lines.append(f"Source URL: {source_url}")

    text_lines.append(
        "\n--\nYou are receiving this alert from JobPulse based on your active search profiles."
    )
    text_body = "\n".join(text_lines)

    # HTML body with strict escaping
    escaped_company = html.escape(company, quote=True)
    escaped_title = html.escape(title, quote=True)
    escaped_location = html.escape(location, quote=True)
    escaped_emp = html.escape(employment_type.replace("_", " ").title(), quote=True)
    escaped_exp = html.escape(exp_str, quote=True) if exp_str else None

    html_parts = [
        "<!DOCTYPE html>",
        "<html>",
        "<head><meta charset='utf-8'></head>",
        "<body style='font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif; line-height: 1.5; color: #1e293b; max-width: 600px; margin: 0 auto; padding: 24px 16px;'>",
        f"<h2 style='color: #0f172a; margin-top: 0;'>{html.escape(prefix, quote=True)}</h2>",
        "<div style='background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; margin-bottom: 24px;'>",
        f"<h3 style='margin: 0 0 12px 0; color: #1e40af;'>{escaped_title}</h3>",
        f"<p style='margin: 4px 0;'><strong>Company:</strong> {escaped_company}</p>",
    ]

    if escaped_location:
        html_parts.append(
            f"<p style='margin: 4px 0;'><strong>Location:</strong> {escaped_location}</p>"
        )
    if escaped_emp:
        html_parts.append(
            f"<p style='margin: 4px 0;'><strong>Employment Type:</strong> {escaped_emp}</p>"
        )
    if escaped_exp:
        html_parts.append(
            f"<p style='margin: 4px 0;'><strong>Experience:</strong> {escaped_exp}</p>"
        )

    html_parts.append("</div>")

    # Profiles section
    html_parts.append("<h4 style='color: #334155; margin-bottom: 8px;'>Matching Profiles</h4>")
    html_parts.append("<ul style='padding-left: 20px; margin-top: 0;'>")
    for p in profiles:
        p_name = html.escape(str(p.get("name") or "Unnamed Profile"), quote=True)
        p_score = html.escape(_format_score(p.get("score")), quote=True)
        html_parts.append(
            f"<li style='margin-bottom: 8px;'><strong>{p_name}</strong> &mdash; Match Score: <span style='color: #16a34a; font-weight: 600;'>{p_score}</span>"
        )
        reasons = _extract_reasons(p.get("evidence"))
        if reasons:
            html_parts.append("<ul style='margin-top: 4px;'>")
            for r in reasons:
                html_parts.append(f"<li style='color: #64748b;'>{html.escape(r, quote=True)}</li>")
            html_parts.append("</ul>")
        html_parts.append("</li>")
    html_parts.append("</ul>")

    # Call to action link
    if _is_safe_url(app_url):
        safe_href = html.escape(app_url, quote=True)
        html_parts.append(
            f"<div style='margin-top: 24px;'><a href='{safe_href}' target='_blank' rel='noopener noreferrer' style='display: inline-block; background-color: #2563eb; color: #ffffff; text-decoration: none; padding: 10px 20px; border-radius: 6px; font-weight: 500;'>Apply Now &rarr;</a></div>"
        )
    elif _is_safe_url(career_url):
        safe_href = html.escape(career_url, quote=True)
        html_parts.append(
            f"<div style='margin-top: 24px;'><a href='{safe_href}' target='_blank' rel='noopener noreferrer' style='display: inline-block; background-color: #2563eb; color: #ffffff; text-decoration: none; padding: 10px 20px; border-radius: 6px; font-weight: 500;'>View Career Site &rarr;</a></div>"
        )

    html_parts.append(
        "<hr style='border: 0; border-top: 1px solid #e2e8f0; margin-top: 32px; margin-bottom: 16px;'>"
        "<p style='font-size: 12px; color: #94a3b8; margin: 0;'>You are receiving this automated alert from JobPulse based on your configured job monitoring profiles.</p>"
        "</body></html>"
    )
    html_body = "".join(html_parts)

    return subject, text_body, html_body
