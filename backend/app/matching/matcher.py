from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol

from app.matching.config import ScoringConfig
from app.matching.experience import ExperienceRange, parse_experience
from app.matching.text import ROLE_GROUPS, contains, normalize, skill_evidence


class JobInput(Protocol):
    title: str
    description: str
    location: str
    employment_type: str | None
    experience_text: str | None
    min_exp_years: Decimal | None
    max_exp_years: Decimal | None


@dataclass(frozen=True)
class MatchingProfile:
    roles: tuple[str, ...] = ()
    # (configured role, aliases); aliases for unselected roles never participate.
    role_aliases: tuple[tuple[str, tuple[str, ...]], ...] = ()
    required_skills: tuple[str, ...] = ()
    preferred_skills: tuple[str, ...] = ()
    preferred_locations: tuple[str, ...] = ()
    excluded_locations: tuple[str, ...] = ()
    excluded_terms: tuple[str, ...] = ()
    employment_types: tuple[str, ...] = ()
    work_modes: tuple[str, ...] = ()
    exp_min: Decimal | None = None
    exp_max: Decimal | None = None
    min_score: int | None = None

    def __post_init__(self) -> None:
        if self.min_score is not None and not 0 <= self.min_score <= 100:
            raise ValueError("Profile threshold must be between 0 and 100")
        if self.exp_min is not None and self.exp_max is not None and self.exp_min > self.exp_max:
            raise ValueError("Invalid profile experience bounds")


@dataclass(frozen=True)
class HardFilterResult:
    name: str
    status: str  # passed, failed, unknown, unrestricted
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class ComponentScore:
    name: str
    score: int
    weight: int
    status: str
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class MatchResult:
    matched: bool
    score: int
    decision: str
    threshold: int
    hard_filters: tuple[HardFilterResult, ...]
    components: tuple[ComponentScore, ...]
    matched_evidence: tuple[str, ...]
    negative_evidence: tuple[str, ...]
    parsed_experience: ExperienceRange | None
    reasons: tuple[str, ...] = field(default_factory=tuple)
    negative_reasons: tuple[str, ...] = field(default_factory=tuple)


class Matcher(Protocol):
    def match(self, job: JobInput, profile: MatchingProfile) -> MatchResult: ...


class DeterministicMatcher:
    def __init__(self, config: ScoringConfig | None = None):
        self.config = config if config is not None else ScoringConfig()

    def match(self, job: JobInput, profile: MatchingProfile) -> MatchResult:
        config = self.config
        text = f"{job.title} {job.description}"
        hard: list[HardFilterResult] = []
        components: list[ComponentScore] = []
        positive: list[str] = []
        negative: list[str] = []

        def check(name: str, status: str, evidence: tuple[str, ...] = ()) -> None:
            hard.append(HardFilterResult(name, status, evidence))
            if status == "failed":
                negative.extend(f"{name}: {e}" for e in evidence)

        def component(
            name: str, terms: tuple[str, ...], hits: tuple[str, ...], status: str | None = None
        ) -> None:
            weight = getattr(config, name)
            score = weight * len(hits) // len(terms) if terms else 0
            state = status or ("matched" if hits else "unknown" if not terms else "absent")
            evidence = tuple(f"{name}: {hit}" for hit in hits)
            components.append(ComponentScore(name, score, weight, state, evidence))
            positive.extend(evidence)

        excluded = tuple(t for t in profile.excluded_terms if contains(job.title, t))
        check("excluded_terms", "failed" if excluded else "passed", excluded)
        locations = tuple(t for t in profile.excluded_locations if contains(job.location, t))
        check(
            "excluded_locations",
            "failed"
            if locations
            else "unknown"
            if profile.excluded_locations and not job.location
            else "passed",
            locations,
        )
        employment_bad = bool(
            profile.employment_types
            and job.employment_type
            and job.employment_type not in profile.employment_types
        )
        check(
            "employment",
            "failed"
            if employment_bad
            else "unrestricted"
            if not profile.employment_types
            else "unknown"
            if job.employment_type is None
            else "passed",
            (job.employment_type,) if job.employment_type else (),
        )
        required = tuple(s for s in profile.required_skills if skill_evidence(text, s))
        missing = tuple(s for s in profile.required_skills if s not in required)
        check(
            "required_skills",
            "failed" if missing else "passed" if profile.required_skills else "unrestricted",
            tuple(f"Required skill absent: {s}" for s in missing),
        )

        experience = parse_experience(
            job.experience_text or job.description,
            title=job.title,
            minimum=job.min_exp_years,
            maximum=job.max_exp_years,
        )
        too_high = bool(
            experience
            and experience.numeric_rejection_safe
            and experience.minimum is not None
            and profile.exp_max is not None
            and experience.minimum > profile.exp_max
        )
        check(
            "experience",
            "failed"
            if too_high
            else "unknown"
            if experience is None or not experience.numeric_rejection_safe
            else "passed",
            (f"Job minimum {experience.minimum} exceeds profile maximum {profile.exp_max}",)
            if too_high
            else (),
        )
        if experience and experience.ambiguous:
            negative.append("Experience evidence is ambiguous: " + "; ".join(experience.evidence))

        role_hits = tuple(r for r in profile.roles if contains(job.title, r))
        if not role_hits:
            role_hits = tuple(
                alias
                for role, aliases in profile.role_aliases
                if normalize(role) in {normalize(r) for r in profile.roles}
                for alias in aliases
                if contains(job.title, alias)
            )
        if not role_hits and config.supplement_role_seed:
            role_hits = tuple(
                alias
                for role in profile.roles
                for alias in ROLE_GROUPS.get(normalize(role), ())
                if contains(job.title, alias)
            )
        component("roles", ("Target role",), role_hits[:1])
        component("required_skills", profile.required_skills, required)
        component(
            "preferred_skills",
            profile.preferred_skills,
            tuple(s for s in profile.preferred_skills if skill_evidence(text, s)),
        )
        component(
            "location",
            profile.preferred_locations,
            tuple(s for s in profile.preferred_locations if contains(job.location, s)),
        )
        fit = bool(
            experience
            and experience.source != "title"
            and experience.minimum is not None
            and (profile.exp_min is not None or profile.exp_max is not None)
            and (profile.exp_max is None or experience.minimum <= profile.exp_max)
            and (
                profile.exp_min is None
                or experience.maximum is None
                or experience.maximum >= profile.exp_min
            )
        )
        component(
            "experience", ("Experience fit",), ("Experience range overlaps profile",) if fit else ()
        )
        component(
            "employment",
            profile.employment_types,
            (job.employment_type,) if job.employment_type in profile.employment_types else (),
        )
        # Employment alternatives are OR, rather than fractional overlap.
        if components[-1].score:
            last = components[-1]
            components[-1] = ComponentScore(
                last.name, last.weight, last.weight, last.status, last.evidence
            )
        if profile.work_modes:
            negative.append("Work mode unknown: canonical Job has no authoritative work mode")
        for item in components:
            if item.status in ("absent", "unknown"):
                negative.append(f"{item.name}: no positive evidence ({item.status})")
        failed = any(item.status == "failed" for item in hard)
        score = 0 if failed else sum(item.score for item in components)
        threshold = config.threshold if profile.min_score is None else profile.min_score
        matched = not failed and score >= threshold
        reasons = tuple(
            f"{c.name}: +{c.score}; " + "; ".join(c.evidence) for c in components if c.score
        )
        return MatchResult(
            matched,
            score,
            "matched" if matched else "rejected",
            threshold,
            tuple(hard),
            tuple(components),
            tuple(positive),
            tuple(negative),
            experience,
            reasons,
            tuple(negative),
        )
