from dataclasses import dataclass


@dataclass(frozen=True)
class ScoringConfig:
    threshold: int = 60
    roles: int = 35
    required_skills: int = 25
    preferred_skills: int = 10
    location: int = 10
    experience: int = 15
    employment: int = 5
    supplement_role_seed: bool = True

    def __post_init__(self) -> None:
        weights = (
            self.roles,
            self.required_skills,
            self.preferred_skills,
            self.location,
            self.experience,
            self.employment,
        )
        if any(w < 0 for w in weights) or sum(weights) != 100:
            raise ValueError("Weights must be nonnegative and sum to 100")
        if not 0 <= self.threshold <= 100:
            raise ValueError("Threshold must be between 0 and 100")
