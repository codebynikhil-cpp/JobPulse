import re
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ExperienceRange:
    minimum: Decimal | None
    maximum: Decimal | None
    source: str
    ambiguous: bool = False
    numeric_rejection_safe: bool = False
    evidence: tuple[str, ...] = ()


NUMBER = r"\d{1,3}(?:\.\d+)?"
PATTERN = re.compile(
    rf"(?<![\d.])(?:(?:at least|minimum(?: of)?|up to|maximum(?: of)?)\s+)?"
    rf"{NUMBER}\s*(?:(?:-|–|—|to)\s*{NUMBER}\s*)?"
    r"\+?\s*(?:years?|yrs?)\b(?:\s+or more)?",
    re.I,
)


def parse_experience(
    text: str | None,
    *,
    title: str = "",
    minimum: Decimal | None = None,
    maximum: Decimal | None = None,
) -> ExperienceRange | None:
    if minimum is not None or maximum is not None:
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError("Invalid structured experience bounds")
        return ExperienceRange(
            minimum, maximum, "structured", False, True, ("Canonical structured bounds",)
        )
    candidates = []
    for clause in re.split(r"[;.!?\n](?!\d)", (text or "").casefold()):
        if re.search(r"preferred|nice to have|desirable|company|founded|in business", clause):
            continue
        for match in PATTERN.finditer(clause):
            value = match.group()
            # A duration is not by itself an experience requirement.
            context = clause[max(0, match.start() - 35) : match.end() + 60]
            if (
                not re.search(
                    r"experience|exp\b|required|minimum|at least|must|\+|or more", context
                )
                and clause.strip() != value.strip()
            ):
                continue
            numbers = [Decimal(n) for n in re.findall(NUMBER, value)]
            if any(n > 100 for n in numbers):
                continue
            lo, hi = numbers[0], None
            if len(numbers) == 2:
                hi = numbers[1]
                if lo > hi:
                    return ExperienceRange(None, None, "text", True, False, (value,))
            elif value.startswith(("up to", "maximum")):
                lo, hi = Decimal(0), lo
            candidates.append((lo, hi, value))
    if candidates:
        chosen = max(candidates, key=lambda c: c[0])
        ambiguous = len(candidates) > 1
        return ExperienceRange(
            chosen[0], chosen[1], "text", ambiguous, True, tuple(c[2] for c in candidates)
        )
    combined = (text or "").casefold()
    if re.search(
        r"\b(fresher|new grad|recent graduate|entry[ -]level|campus|graduate program|early career)\b",
        combined,
    ):
        return ExperienceRange(
            Decimal(0), Decimal(1), "wording", False, False, ("Entry-level wording (advisory)",)
        )
    if re.search(r"\b(intern|associate|junior)\b|\bengineer i$", title.casefold()):
        return ExperienceRange(
            Decimal(0), Decimal(1), "title", True, False, ("Possible entry-level title (advisory)",)
        )
    if re.search(r"\b(senior|staff|principal|lead)\b", title.casefold()):
        return ExperienceRange(
            None, None, "title", True, False, ("Possible senior title; no numeric inference",)
        )
    return None
