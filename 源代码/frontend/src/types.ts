// 微博方向社交机器人检测V1.0

export type NavKey = "overview" | "collection" | "analysis" | "reports";

export interface LoginPayload {
  username: string;
  password: string;
}

export interface LoginResponse {
  token: string;
  display_name: string;
}

export interface TweetRecord {
  tweet_id: string;
  text: string;
  created_at: string;
  likes: number;
  retweets: number;
  replies: number;
  lang?: string | null;
  hashtags: string[];
  has_media: boolean;
  possibly_sensitive: boolean;
  is_repost: boolean;
}

export interface UserBundle {
  username: string;
  display_name: string;
  user_id?: string | null;
  description: string;
  created_at?: string | null;
  followers_count: number;
  following_count: number;
  tweet_count: number;
  protected: boolean;
  location: string;
  profile_image_url?: string | null;
  posts: TweetRecord[];
}

export interface FeatureSnapshot {
  account: Record<string, string | number | boolean | null>;
  behavior: Record<string, string | number | boolean | null>;
  content: Record<string, string | number | boolean | null>;
  ai: Record<string, string | number | boolean | null>;
}

export interface ScoreSnapshot {
  text_model_probability: number;
  behavior_probability: number;
  ai_content_probability: number;
  final_probability: number;
  final_label: string;
  risk_level: string;
}

export interface DetectionReport {
  report_id: string;
  created_at: string;
  username: string;
  summary: string;
  recommendation: string;
  account: UserBundle;
  features: FeatureSnapshot;
  scores: ScoreSnapshot;
}

export interface ReportListItem {
  report_id: string;
  created_at: string;
  username: string;
  final_label: string;
  risk_level: string;
  final_probability: number;
  summary: string;
}

export interface DashboardResponse {
  total_reports: number;
  high_risk_reports: number;
  average_probability: number;
  latest_reports: ReportListItem[];
}
