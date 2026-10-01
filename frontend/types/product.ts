export type Match = {
  profile_id: string;
  profile_name: string;
  score: number;
  match_reasons: string[];
  evidence: Record<string, unknown>;
};
export type Job = {
  id: string;
  company_id: string;
  company_name: string;
  title: string;
  description: string;
  location: string;
  employment_type: string | null;
  experience_text: string | null;
  posted_at: string | null;
  first_seen_at: string;
  application_url: string;
  status: string;
  user_status: string;
  best_score: number;
  matched_profiles: Match[];
  match_reasons: string[];
};
export type Feed = {
  items: Job[];
  total: number;
  page: number;
  total_pages: number;
};
export type Notice = {
  id: string;
  job_id: string;
  company_name: string;
  job_title: string;
  kind: string;
  match_score: number;
  matching_profiles: string[];
  delivery_status: string;
  is_read: boolean;
  created_at: string;
  apply_url: string | null;
};
export type Company = {
  company_id: string;
  company_name: string;
  career_url: string | null;
  is_subscribed: boolean;
  source_health: string | null;
  last_checked_at: string | null;
  last_success_at: string | null;
  recent_matches_count: number;
  subscribed_profile_ids: string[];
  subscribed_profile_names: string[];
};
export type Overview = {
  stats: {
    active_profiles_count: number;
    monitored_companies_count: number;
    new_jobs_count: number;
    saved_jobs_count: number;
    applied_jobs_count: number;
    ignored_jobs_count: number;
    unread_notifications_count: number;
  };
  source_health_summary: Record<string, number>;
  recent_jobs: Job[];
  recent_notifications: Notice[];
  monitored_companies: Company[];
};
