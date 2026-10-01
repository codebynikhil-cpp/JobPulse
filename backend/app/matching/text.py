import re
import unicodedata


def normalize(text: str) -> str:
    # Preserve skill punctuation: C, C++, C# and .NET are distinct.
    text = unicodedata.normalize("NFKC", text).casefold()
    text = re.sub(r"(?<=\w)\.(?=\s|$)", " ", text)
    return " ".join(re.sub(r"[^\w+#.]", " ", text).split())


def contains(text: str, term: str) -> bool:
    term = normalize(term)
    return bool(term) and bool(
        re.search(r"(?<![\w+#.])" + re.escape(term) + r"(?![\w+#.])", normalize(text))
    )


def skill_evidence(text: str, term: str) -> bool:
    """Ignore explicit negation; positive mentions elsewhere still count."""
    for clause in re.split(r"[;!?\n]|(?<=\w)\.(?=\s)", text):
        if not contains(clause, term):
            continue
        normalized = normalize(clause)
        escaped = re.escape(normalize(term))
        if re.search(rf"\b(?:no|without)\s+{escaped}(?![\w+#.])", normalized):
            continue
        if re.search(rf"{escaped}\s+(?:is\s+)?(?:not required|not needed)", normalized):
            continue
        return True
    return False


ROLE_GROUPS = {
    "software engineer": ("software developer", "sde", "graduate software engineer"),
    "data analyst": ("analytics analyst",),
    "quality assurance engineer": ("qa engineer", "test engineer"),
}
