"""Hand-authored acceptance examples: python -m app.matching.examples."""

from dataclasses import asdict, dataclass
from decimal import Decimal

from app.matching.matcher import DeterministicMatcher, MatchingProfile


@dataclass(frozen=True)
class ExampleJob:
    title: str
    description: str
    location: str = "Bengaluru"
    employment_type: str | None = "full_time"
    experience_text: str | None = "0-2 years experience"
    min_exp_years: Decimal | None = None
    max_exp_years: Decimal | None = None


PROFILE = MatchingProfile(
    roles=("Software Engineer",),
    role_aliases=(("Software Engineer", ("Platform Developer",)),),
    required_skills=("Python",),
    preferred_skills=("SQL",),
    preferred_locations=("Bengaluru",),
    employment_types=("full_time",),
    excluded_terms=("Principal",),
    exp_max=Decimal(2),
)
EXAMPLES = (
    ("graduate fit", ExampleJob("Software Engineer", "Python SQL"), 100, True),
    ("custom alias", ExampleJob("Platform Developer", "Python SQL"), 100, True),
    ("seed supplement", ExampleJob("SDE", "Python SQL"), 100, True),
    ("missing required", ExampleJob("Software Engineer", "Java SQL"), 0, False),
    (
        "explicit skill negation",
        ExampleJob("Software Engineer", "Python not required; SQL"),
        0,
        False,
    ),
    ("excluded seniority", ExampleJob("Principal Software Engineer", "Python SQL"), 0, False),
    (
        "explicit senior experience",
        ExampleJob("Software Engineer", "Python SQL", experience_text="5+ years experience"),
        0,
        False,
    ),
    (
        "unknown fields",
        ExampleJob(
            "Software Engineer",
            "Python SQL",
            location="",
            employment_type=None,
            experience_text=None,
        ),
        70,
        True,
    ),
    (
        "unknown role below threshold",
        ExampleJob(
            "Business Analyst", "Python", location="", employment_type=None, experience_text=None
        ),
        25,
        False,
    ),
    (
        "uncertain title",
        ExampleJob("Senior Software Engineer", "Python SQL", experience_text=None),
        85,
        True,
    ),
)


def verify_examples() -> list[dict]:
    matcher = DeterministicMatcher()
    results = []
    for name, job, score, matched in EXAMPLES:
        result = matcher.match(job, PROFILE)
        assert (result.score, result.matched) == (score, matched), name
        assert result == matcher.match(job, PROFILE), name
        assert all(c.evidence for c in result.components if c.score), name
        results.append({"example": name, **asdict(result)})
    return results


if __name__ == "__main__":
    import json

    print(json.dumps(verify_examples(), default=str, indent=2))
