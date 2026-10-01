from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.matching.config import ScoringConfig
from app.matching.experience import parse_experience
from app.matching.matcher import DeterministicMatcher, MatchingProfile


@pytest.mark.parametrize(
    "text,lo,hi",
    [
        ("0-2 years of experience", "0", "2"),
        ("0 to 2 yrs experience", "0", "2"),
        ("1-3 years of experience", "1", "3"),
        ("3+ years experience", "3", None),
        ("at least 5 years", "5", None),
        ("minimum 2 years", "2", None),
        ("5 years or more", "5", None),
        ("Requires 2 years experience", "2", None),
        ("Must have 4 years experience", "4", None),
        ("2.5 years experience required", "2.5", None),
        ("Minimum of 3 years experience", "3", None),
        ("up to 2 years experience", "0", "2"),
        ("maximum 4 years experience", "0", "4"),
        ("8–10 years experience", "8", "10"),
        ("6—8 years experience", "6", "8"),
        ("1 year experience", "1", None),
        ("10 yrs experience", "10", None),
        ("Required: 5 years Java, 2 years AWS", "5", None),
        ("Experience: 2 years AWS; minimum 5 years Java", "5", None),
        ("fresher welcome", "0", "1"),
        ("new grad", "0", "1"),
        ("recent graduate", "0", "1"),
        ("entry level", "0", "1"),
        ("entry-level", "0", "1"),
        ("campus recruitment", "0", "1"),
        ("graduate program", "0", "1"),
        ("early career", "0", "1"),
        ("Required experience: 0 years", "0", None),
        ("7+ yrs of experience", "7", None),
        ("At least 12 years of relevant experience", "12", None),
        ("3 years experience required; 5 years preferred", "3", None),
    ],
)
def test_realistic_experience(text, lo, hi):
    result = parse_experience(text)
    assert result is not None
    assert result.minimum == Decimal(lo)
    assert result.maximum == (Decimal(hi) if hi else None)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Competitive salary",
        "Company founded 20 years ago",
        "2 years preferred",
        "3 years nice to have",
        "Project lasts 2 years",
        "1000 years experience",
        "We have been in business for 10 years",
    ],
)
def test_unknown_experience(text):
    assert parse_experience(text) is None


@pytest.mark.parametrize(
    "title",
    [
        "Intern",
        "Associate Engineer",
        "Junior Developer",
        "Software Engineer I",
        "Senior Engineer",
        "Staff Engineer",
        "Principal Engineer",
        "Technical Lead",
    ],
)
def test_titles_cannot_hard_reject(title):
    result = parse_experience("", title=title)
    assert result and not result.numeric_rejection_safe
    assert result.ambiguous


def test_structured_precedence():
    result = parse_experience("10+ years", minimum=Decimal(1), maximum=Decimal(2))
    assert result.source == "structured"
    assert result.minimum == 1


def test_ambiguous_requirements_and_reversed_range():
    assert parse_experience("Required 5 years Java, 2 years AWS").ambiguous
    result = parse_experience("5-2 years experience")
    assert result.ambiguous and not result.numeric_rejection_safe


def job(**changes):
    values = dict(
        title="Software Engineer",
        description="Python SQL",
        location="Bengaluru",
        employment_type="full_time",
        experience_text="0-2 years experience",
        min_exp_years=None,
        max_exp_years=None,
    )
    return SimpleNamespace(**(values | changes))


def profile(**changes):
    values = dict(
        roles=("Software Engineer",),
        required_skills=("Python",),
        preferred_skills=("SQL",),
        preferred_locations=("Bengaluru",),
        employment_types=("full_time",),
        exp_max=Decimal(2),
    )
    return MatchingProfile(**(values | changes))


def test_all_components_and_determinism():
    matcher = DeterministicMatcher()
    result = matcher.match(job(), profile())
    assert result.matched and result.score == 100
    assert [c.score for c in result.components] == [35, 25, 10, 10, 15, 5]
    assert all(c.evidence for c in result.components if c.score)
    assert len(result.reasons) == 6
    assert result == matcher.match(job(), profile())


@pytest.mark.parametrize(
    "changes,preferences,filter_name",
    [
        (
            {"title": "Senior Software Engineer"},
            {"excluded_terms": ("Senior",)},
            "excluded_terms",
        ),
        (
            {"location": "London"},
            {"excluded_locations": ("London",)},
            "excluded_locations",
        ),
        ({"employment_type": "contract"}, {}, "employment"),
        ({"experience_text": "5+ years experience"}, {}, "experience"),
        ({"description": "Java SQL"}, {}, "required_skills"),
    ],
)
def test_hard_filters_zero_score(changes, preferences, filter_name):
    result = DeterministicMatcher().match(job(**changes), profile(**preferences))
    assert not result.matched and result.score == 0
    assert any(h.name == filter_name and h.status == "failed" for h in result.hard_filters)
    assert result.negative_evidence


def test_unknown_not_hard_rejection_or_positive_evidence():
    result = DeterministicMatcher().match(
        job(location="", employment_type=None, experience_text=None), profile()
    )
    assert result.score == 70 and result.matched
    assert not any(h.status == "failed" for h in result.hard_filters)
    assert result.parsed_experience is None
    assert [c.score for c in result.components][-3:] == [0, 0, 0]


def test_required_absence_even_with_empty_text():
    result = DeterministicMatcher().match(job(description=""), profile())
    assert result.score == 0 and not result.matched


def test_threshold_configuration_and_profile_override():
    matcher = DeterministicMatcher(ScoringConfig(threshold=90))
    partial = job(location="", employment_type=None, experience_text=None)
    assert not matcher.match(partial, profile()).matched
    assert matcher.match(partial, profile(min_score=70)).matched


def test_alias_precedence_and_seed_opt_out():
    matcher = DeterministicMatcher()
    p = profile(role_aliases=(("Software Engineer", ("Platform Builder",)),))
    result = matcher.match(job(title="Platform Builder"), p)
    assert result.components[0].score == 35
    assert "Platform Builder" in result.components[0].evidence[0]
    assert matcher.match(job(title="SDE"), p).components[0].score == 35
    assert (
        DeterministicMatcher(ScoringConfig(supplement_role_seed=False))
        .match(job(title="SDE"), p)
        .components[0]
        .score
        == 0
    )
    assert matcher.match(job(title="Software Engineer SDE"), p).components[0].evidence == (
        "roles: Software Engineer",
    )


def test_unselected_role_alias_ignored():
    p = profile(role_aliases=(("Doctor", ("Platform Builder",)),))
    assert DeterministicMatcher().match(job(title="Platform Builder"), p).components[0].score == 0


@pytest.mark.parametrize(
    "skill,text,hit",
    [
        ("Java", "JavaScript", False),
        ("C", "C++", False),
        ("C++", "C++", True),
        ("C#", "C#", True),
        (".NET", ".NET", True),
        ("SQL", "NoSQL", False),
        ("Python", "Ｐｙｔｈｏｎ", True),
    ],
)
def test_exact_skill_boundaries(skill, text, hit):
    result = DeterministicMatcher().match(job(description=text), profile(required_skills=(skill,)))
    assert (result.score > 0) == hit


def test_preferred_partial_overlap_and_employment_alternatives():
    result = DeterministicMatcher().match(
        job(),
        profile(preferred_skills=("SQL", "Rust"), employment_types=("full_time", "contract")),
    )
    assert result.components[2].score == 5
    assert result.components[-1].score == 5


def test_work_mode_is_unknown_and_schema_unchanged():
    from app.schemas.job import JobCreate

    assert "work_mode" not in JobCreate.model_fields
    result = DeterministicMatcher().match(job(), profile(work_modes=("remote",)))
    assert result.score == 100
    assert any("Work mode unknown" in e for e in result.negative_evidence)


def test_uncertain_senior_title_never_numeric_rejects():
    result = DeterministicMatcher().match(
        job(
            title="Senior Software Engineer",
            experience_text="",
            description="Python SQL",
        ),
        profile(),
    )
    assert not any(h.status == "failed" for h in result.hard_filters)


@pytest.mark.parametrize("kwargs", [{"threshold": 101}, {"roles": -1}, {"roles": 50}])
def test_invalid_config(kwargs):
    with pytest.raises(ValueError):
        ScoringConfig(**kwargs)


@pytest.mark.parametrize(
    "description",
    [
        "Python not required",
        "Python is not needed",
        "No Python experience needed",
        "Work without Python",
    ],
)
def test_negated_skill_does_not_satisfy_required(description):
    result = DeterministicMatcher().match(job(description=description), profile())
    assert not result.matched and result.score == 0


def test_title_unknown_has_no_experience_points():
    result = DeterministicMatcher().match(
        job(
            title="Junior Software Engineer",
            description="Python SQL",
            experience_text=None,
        ),
        profile(),
    )
    assert result.components[4].score == 0


def test_strong_signals_cannot_compensate_multiple_required_skills():
    result = DeterministicMatcher().match(job(), profile(required_skills=("Python", "Rust")))
    assert result.components[1].score == 12
    assert result.score == 0 and not result.matched


def test_below_profile_minimum_is_soft_only():
    result = DeterministicMatcher().match(job(), profile(exp_min=Decimal(3), exp_max=Decimal(5)))
    assert result.components[4].score == 0
    assert not any(h.status == "failed" for h in result.hard_filters)


def test_structured_job_overrides_text_in_matcher():
    result = DeterministicMatcher().match(
        job(
            experience_text="10+ years",
            min_exp_years=Decimal(1),
            max_exp_years=Decimal(2),
        ),
        profile(),
    )
    assert result.score == 100


def test_hand_authored_acceptance_examples():
    from app.matching.examples import verify_examples

    assert len(verify_examples()) == 10


def test_matching_imports_are_pure():
    import ast
    from pathlib import Path

    import app.matching

    directory = Path(app.matching.__file__).parent
    assert len(list(directory.glob("*.py"))) >= 6
    allowed = {
        "dataclasses",
        "decimal",
        "typing",
        "re",
        "unicodedata",
        "json",
        "app.matching",
    }
    for path in directory.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                imports = [node.module or ""]
            else:
                continue
            assert all(any(n == a or n.startswith(a + ".") for a in allowed) for n in imports)


@pytest.mark.parametrize(
    "text,lo,hi", [("0-2 years", 0, 2), ("0 to 2 yrs", 0, 2), ("5 years", 5, None)]
)
def test_standalone_explicit_bounds(text, lo, hi):
    result = parse_experience(text)
    assert result.minimum == lo and result.maximum == hi
