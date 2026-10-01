# Phase 5 matching contract

The standalone `app.matching.matcher.Matcher` protocol accepts a canonical Job-like
value and an immutable `MatchingProfile`, and returns an immutable `MatchResult`.
The implementation imports only stdlib and its own matching modules. No database,
network, adapter, LLM, random, clock, fuzzy matching or embeddings are involved.
Inputs must be materialized before invocation; passing lazy ORM relationships is
not part of this interface. There is no orchestration or persistence in Phase 5.

## Profile configuration and precedence

User role names are evaluated first, then user aliases attached to selected roles,
then the optional small `ROLE_GROUPS` seed. The first successful tier provides the
role evidence. Aliases attached to unselected roles are ignored. A seed cannot
remove, replace or rename a configured role or alias. Disable seed supplementation
with `ScoringConfig(supplement_role_seed=False)` for explicit-only matching.
The existing profile API has role names, but no alias or threshold fields; those
features are explicit matcher input configuration only in this phase. No API,
profile persistence or UI expansion is implied. Profile skills/locations/exclusions
map to their corresponding tuple fields; both exclusion kinds filter the title.

Text normalization uses NFKC, casefold, whitespace/punctuation normalization and
whole phrase boundaries. Skill punctuation is retained: C, C++, C# and .NET are
separate. No stemming, spelling correction, synonym guessing or fuzzy expansion.
Exact role phrases may occur inside a longer title. A senior title does not itself
exclude a role unless configured as an exclusion or supported by explicit numeric
experience requirements.

## Required skills and hard filters

Required means mandatory positive lexical evidence in title or description. Every
configured required skill must appear. Missing evidence, including an empty job
text, disqualifies because the user expressly made it mandatory. Explicit simple
negations (`no Python`, `without Python`, `Python is not required/needed`) do not
satisfy it. This is lexical evidence, not a claim to understand all natural-language
negation or distinguish every skill mention from a requirements section.

Hard failures: configured excluded terms in title, excluded location phrases,
known employment mismatch, missing required skills, or an explicit job minimum
experience above profile maximum. Any failure makes `matched=False` and final
`score=0`, regardless of other components. Components still report diagnostic
pre-filter points and evidence; they do not compensate for a failure.
Unknown employment/location/experience does not fail these filters. Unknown is
neither positive evidence nor a hard rejection unless an explicit hard requirement
makes absence disqualifying (required skills). Below-threshold decisions can still
reject for insufficient positive evidence; they are distinct from hard failure.

## Scoring

All defaults reside in `ScoringConfig`, including threshold **60** and weights:
roles **35**, required skills **25**, preferred skills **10**, location **10**,
experience **15**, employment **5**. Weights must sum to 100. A matcher input
`min_score` can override the configuration threshold. No default is embedded in
matcher business logic. Threshold comparison is inclusive.

Roles earn their full weight for any target/alias match. Skills and preferred
locations earn `floor(weight * matched_count / configured_count)`; employment
alternatives are OR and earn the full weight for a known allowed type. Experience
earns its full weight for an inferred wording or explicit range overlapping the
profile bounds. A title-only inference earns no experience points. No constraint
or missing evidence earns zero for that component, without redistributing weights.
Unknown experience therefore has a soft opportunity penalty, never an invented
numeric requirement. Empty profiles cannot acquire points from empty preferences.

Work mode is recorded as unknown when a preference exists. Canonical Job has no
work-mode field; location text is not authoritative evidence of it. It has no
weight and cannot cause hard rejection in Phase 5.

## Experience parsing

`parse_experience(text, title=..., minimum=..., maximum=...)` returns a structured
range or None. Canonical structured bounds take precedence, even a single bound.
Then explicit numeric textual requirements are considered, then entry-level
wording (advisory 0-1), then cautious title signals. Senior titles never invent a
numeric bound; possible junior titles are marked ambiguous/advisory. Neither
wording nor title inference can trigger numeric hard rejection.

Numeric ranges, decimal years, minimums, plus suffixes, upper bounds and common
`yrs` spellings are supported. Bare durations without requirement/experience
context, preferred-only clauses, company-age statements and values above 100 are
ignored. Reversed ranges are ambiguous and cannot trigger rejection. Multiple
explicit requirements select the largest minimum, retain all evidence, and flag
ambiguity; the stated largest requirement can still cause hard rejection. This
conservative clause parser does not claim universal prose coverage.

## Explainability and examples

MatchResult carries decision, threshold, final score, five named hard-filter
results, all six weighted components, matched/negative evidence, parsed experience
with provenance/ambiguity/rejection safety, and point-bearing reason strings.
Unknown or absent components have zero points and explanations. Results preserve
input ordering and repeat identically for identical inputs/configuration.

Run hand-authored examples with `python -m app.matching.examples`; the ten examples
assert expected scores, decisions, repeatability and evidence. They cover a full
fit, custom alias, seed supplement, missing/negated required skills, excluded title,
explicit senior requirements, unknown fields, insufficient evidence, and a senior
title without numeric requirements. These synthetic checks are not a real-job
precision/recall evaluation.
