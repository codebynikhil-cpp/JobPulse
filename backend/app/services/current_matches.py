"""One visibility contract for current profile-owned match evidence."""

import uuid

from sqlalchemy import select

from app.models.job import Job
from app.models.monitoring import JobMatch, ProfileCompany
from app.models.profile import Profile


def current_matches(user_id: uuid.UUID):
    # Closed jobs remain eligible for saved/applied history; callers choose lifecycle.
    return (
        select(JobMatch)
        .join(Profile, Profile.id == JobMatch.profile_id)
        .join(Job, Job.id == JobMatch.job_id)
        .join(
            ProfileCompany,
            (ProfileCompany.profile_id == Profile.id)
            & (ProfileCompany.company_id == Job.company_id),
        )
        .where(
            Profile.user_id == user_id,
            Profile.active.is_(True),
            JobMatch.matched.is_(True),
            JobMatch.status == "evaluated",
            JobMatch.content_hash.is_not_distinct_from(Job.content_hash),
            JobMatch.updated_at >= Profile.updated_at,
        )
    )
