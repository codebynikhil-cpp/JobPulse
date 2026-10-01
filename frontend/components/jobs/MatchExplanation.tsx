import type { Match } from "@/types/product";
import { ScoreBadge } from "@/components/ui/primitives";
const names: Record<string, string> = {
  role: "Role alignment",
  roles: "Role alignment",
  required_skills: "Required skills",
  preferred_skills: "Preferred skills",
  location: "Location",
  experience: "Experience",
  work_mode: "Work arrangement",
};
function readable(reason: string) {
  return reason.replace(
    /^([a-z_]+):\s*\+\d+(?:\.\d+)?;\s*(?:\1:\s*)?/,
    (_, key: string) => `${names[key] || key.replaceAll("_", " ")}: `,
  );
}
export default function MatchExplanation({ profiles }: { profiles: Match[] }) {
  return (
    <section className="detail-section">
      <h2>Why this matches</h2>
      <p className="muted">
        Evidence from your saved profiles. Scores come from JobPulse’s matching
        engine.
      </p>
      {profiles.map((profile) => (
        <div className="match-section" key={profile.profile_id}>
          <div className="section-heading">
            <h3>{profile.profile_name}</h3>
            <ScoreBadge score={profile.score} />
          </div>
          {profile.match_reasons.length ? (
            <ul>
              {profile.match_reasons.map((reason, index) => (
                <li key={index}>{readable(reason)}</li>
              ))}
            </ul>
          ) : (
            <p className="muted">
              No detailed explanation is available for this match.
            </p>
          )}
        </div>
      ))}
    </section>
  );
}
