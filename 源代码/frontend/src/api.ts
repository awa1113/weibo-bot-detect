// 微博方向社交机器人检测V1.0

import type { DashboardResponse, DetectionReport, LoginPayload, LoginResponse } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: "请求失败" }));
    throw new Error(payload.detail ?? "请求失败");
  }

  return response.json() as Promise<T>;
}

export function login(payload: LoginPayload) {
  return request<LoginResponse>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function fetchDashboard() {
  return request<DashboardResponse>("/api/dashboard");
}

export function analyzeAccount(username: string, maxPosts: number) {
  return request<DetectionReport>("/api/analyze", {
    method: "POST",
    body: JSON.stringify({ username, max_posts: maxPosts }),
  });
}

export function fetchReports() {
  return request<DetectionReport[]>("/api/reports");
}
