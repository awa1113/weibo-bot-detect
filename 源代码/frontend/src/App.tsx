// 微博方向社交机器人检测V1.0

import { startTransition, useEffect, useMemo, useState, type ReactNode } from "react";

import { analyzeAccount, fetchDashboard, fetchReports, login } from "./api";
import "./App.css";
import type { DashboardResponse, DetectionReport, FeatureSnapshot, LoginResponse, NavKey } from "./types";

type FieldValue = string | number | boolean | null | undefined;
type FieldEntry = { label: string; value: string };
type FeatureGroupKey = keyof FeatureSnapshot;

const navItems: Array<{ key: NavKey; label: string; hint: string }> = [
  { key: "overview", label: "概览", hint: "系统总览" },
  { key: "collection", label: "数据采集", hint: "来源说明" },
  { key: "analysis", label: "检测分析", hint: "执行检测" },
  { key: "reports", label: "检测记录", hint: "历史报告" },
];

const featureLabels: Record<FeatureGroupKey, Record<string, string>> = {
  account: {
    username_length: "用户名长度",
    description_length: "简介长度",
    account_age_days: "可观测时长",
    followers_count: "粉丝数",
    following_count: "关注数",
    tweet_count: "累计发博数",
    followers_following_ratio: "粉丝关注比",
    posts_per_day: "日均发博频次",
    is_protected: "是否受保护",
    has_location: "是否填写地区",
  },
  behavior: {
    mean_likes: "平均点赞数",
    var_likes: "点赞方差",
    mean_retweets: "平均转发数",
    var_retweets: "转发方差",
    mean_replies: "平均评论数",
    var_replies: "评论方差",
    mean_post_interval_hours: "平均发博间隔",
    var_post_interval_hours: "发博间隔方差",
    dominant_posting_hour: "主要发博时段",
    media_ratio: "图文/视频占比",
  },
  content: {
    original_post_ratio: "原创微博占比",
    mean_text_length: "平均文本长度",
    var_text_length: "文本长度方差",
    mean_mentions: "平均提及数",
    var_mentions: "提及数方差",
    mean_urls: "平均链接数",
    var_urls: "链接数方差",
    mean_hashtags: "平均话题标签数",
    var_hashtags: "话题标签方差",
    mean_punctuation: "平均标点数",
    var_punctuation: "标点数方差",
  },
  ai: {
    mean_sentiment: "平均情感极性",
    var_sentiment: "情感极性方差",
    mean_perplexity: "平均困惑度",
    var_perplexity: "困惑度方差",
    mean_lexical_diversity: "平均词汇多样性",
    var_lexical_diversity: "词汇多样性方差",
    tweet_similarity_sum: "微博内容相似度",
  },
};

const featureGroupMeta: Record<FeatureGroupKey, { title: string; subtitle: string }> = {
  account: {
    title: "账户特征",
    subtitle: "反映账号画像与基础规模",
  },
  behavior: {
    title: "行为特征",
    subtitle: "反映互动表现与发帖节奏",
  },
  content: {
    title: "内容特征",
    subtitle: "反映文本形式与结构组成",
  },
  ai: {
    title: "AI特征",
    subtitle: "反映语言风格与生成痕迹",
  },
};

const percentKeys = new Set(["media_ratio", "original_post_ratio"]);
const dayKeys = new Set(["account_age_days"]);
const hourKeys = new Set(["mean_post_interval_hours"]);
const varianceKeys = new Set([
  "var_likes",
  "var_retweets",
  "var_replies",
  "var_post_interval_hours",
  "var_text_length",
  "var_mentions",
  "var_urls",
  "var_hashtags",
  "var_punctuation",
  "var_sentiment",
  "var_perplexity",
  "var_lexical_diversity",
]);

const languageLabels: Record<string, string> = {
  ar: "阿拉伯语",
  de: "德语",
  en: "英语",
  es: "西班牙语",
  fr: "法语",
  hi: "印地语",
  ja: "日语",
  ko: "韩语",
  pt: "葡萄牙语",
  ru: "俄语",
  zh: "中文",
};

function formatDate(value?: string | null) {
  if (!value) return "未记录";
  const date = new Date(value);
  return date.toLocaleString("zh-CN", { hour12: false });
}

function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function formatNumber(value: number, digits = 2) {
  return new Intl.NumberFormat("zh-CN", {
    maximumFractionDigits: digits,
    minimumFractionDigits: Number.isInteger(value) ? 0 : Math.min(digits, 1),
  }).format(value);
}

function formatFieldValue(key: string, value: FieldValue) {
  if (value === null || value === undefined || value === "") {
    return "未提供";
  }

  if (typeof value === "boolean") {
    return value ? "是" : "否";
  }

  if (typeof value === "number") {
    if (percentKeys.has(key)) {
      return formatPercent(value);
    }

    if (key === "dominant_posting_hour") {
      return `${value}点`;
    }

    if (dayKeys.has(key)) {
      return `${formatNumber(value, 2)}天`;
    }

    if (hourKeys.has(key)) {
      return `${formatNumber(value, 2)}小时`;
    }

    if (varianceKeys.has(key)) {
      return formatNumber(value, 4);
    }

    if (Number.isInteger(value)) {
      return formatNumber(value, 0);
    }

    return formatNumber(value, 4);
  }

  return String(value);
}

function mapFeatureItems(group: Record<string, FieldValue>, groupKey: FeatureGroupKey) {
  return Object.entries(group).map(([key, value]) => ({
    label: featureLabels[groupKey][key] ?? key,
    value: formatFieldValue(key, value),
  }));
}

function buildFieldEntries(data: Record<string, FieldValue>) {
  return Object.entries(data).map(([label, value]) => ({
    label,
    value: formatFieldValue(label, value),
  }));
}

function getLanguageSummary(report: DetectionReport | null) {
  if (!report) {
    return "未采集";
  }

  const languages = Array.from(
    new Set(report.account.posts.map((post) => post.lang).filter((lang): lang is string => Boolean(lang))),
  );

  if (languages.length === 0) {
    return "未识别";
  }

  return languages.map((item) => languageLabels[item] ?? item.toUpperCase()).join("、");
}

function countFeatureItems(report: DetectionReport | null) {
  if (!report) {
    return 0;
  }

  return Object.values(report.features).reduce((total, group) => total + Object.keys(group).length, 0);
}

function getFirstUsefulReportId(reports: DetectionReport[]) {
  return reports.find((item) => item.account.posts.length > 0)?.report_id ?? reports[0]?.report_id ?? null;
}

function riskTone(label: string) {
  if (label === "高风险") return "danger";
  if (label === "中风险") return "warn";
  return "safe";
}

function buildSourceNotes(report: DetectionReport) {
  return [
    {
      title: "数据来源",
      text: "检测数据取自微博公开页面及m.weibo.cn公开接口。",
    },
    {
      title: "采集内容",
      text:
        report.account.posts.length > 0
          ? `本次采集包含账号公开资料及${report.account.posts.length}条近期公开微博。`
          : "本次仅采集到账号公开资料，未获取到可用的近期微博文本。",
    },
    {
      title: "结果生成",
      text: `${countFeatureItems(report)}项结构化特征及风险评分均由系统基于微博公开数据自动计算生成。`,
    },
  ];
}

function SectionCard({
  title,
  subtitle,
  actions,
  children,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="panel">
      <header className="panel-header">
        <div>
          <h2>{title}</h2>
          {subtitle ? <p>{subtitle}</p> : null}
        </div>
        {actions}
      </header>
      {children}
    </section>
  );
}

function MetricCard({ label, value, helper }: { label: string; value: string; helper: string }) {
  return (
    <article className="metric-card">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{helper}</small>
    </article>
  );
}

function FieldGrid({ items }: { items: FieldEntry[] }) {
  return (
    <div className="field-grid">
      {items.map((item) => (
        <div key={item.label} className="field-item">
          <span>{item.label}</span>
          <strong>{item.value}</strong>
        </div>
      ))}
    </div>
  );
}

function FeatureSection({ report }: { report: DetectionReport }) {
  const groups: FeatureGroupKey[] = ["account", "behavior", "content", "ai"];

  return (
    <div className="feature-stack">
      {groups.map((groupKey) => (
        <article key={groupKey} className="feature-section">
          <div className="feature-section-header">
            <div>
              <h4>{featureGroupMeta[groupKey].title}</h4>
              <p>{featureGroupMeta[groupKey].subtitle}</p>
            </div>
          </div>
          <FieldGrid items={mapFeatureItems(report.features[groupKey], groupKey)} />
        </article>
      ))}
    </div>
  );
}

function ReportDetail({ report }: { report: DetectionReport | null }) {
  if (!report) {
    return <div className="empty-state">暂无检测结果，执行一次检测后这里会展示完整报告。</div>;
  }

  return (
    <div className="report-detail">
      <div className="report-hero">
        <div>
          <p className="eyebrow">账号报告</p>
          <h3>@{report.username}</h3>
          <p>{report.summary}</p>
        </div>
        <div className={`risk-badge ${riskTone(report.scores.risk_level)}`}>
          <span>{report.scores.risk_level}</span>
          <strong>{formatPercent(report.scores.final_probability)}</strong>
        </div>
      </div>

      <div className="score-grid">
        <MetricCard label="文本模型" value={formatPercent(report.scores.text_model_probability)} helper="根据账号简介与微博文本判断" />
        <MetricCard label="行为信号" value={formatPercent(report.scores.behavior_probability)} helper="根据发博节奏与互动数据判断" />
        <MetricCard label="AI内容信号" value={formatPercent(report.scores.ai_content_probability)} helper="根据困惑度和重复性判断" />
      </div>

      <SectionCard title="账号画像" subtitle="本次抓取到的核心信息">
        <FieldGrid
          items={buildFieldEntries({
            显示名称: report.account.display_name,
            粉丝数: report.account.followers_count,
            关注数: report.account.following_count,
            累计发博数: report.account.tweet_count,
            所在地区: report.account.location || "未公开",
            采集时间: formatDate(report.created_at),
          })}
        />
      </SectionCard>

      <SectionCard title="结构化特征" subtitle="按账户、行为、内容与AI信号分组展示">
        <FeatureSection report={report} />
      </SectionCard>

      <SectionCard title="处置建议" subtitle="系统根据本次检测结果生成的后续建议">
        <div className="info-card">
          <h3>建议说明</h3>
          <p>{report.recommendation}</p>
        </div>
      </SectionCard>

      <SectionCard title="近期微博" subtitle="用于本次分析的近期微博样本">
        {report.account.posts.length > 0 ? (
          <div className="tweet-list">
            {report.account.posts.map((post) => (
              <article key={post.tweet_id} className="tweet-card">
                <p>{post.text}</p>
                <div className="tweet-meta">
                  <span>{formatDate(post.created_at)}</span>
                  <span>点赞{formatNumber(post.likes, 0)}</span>
                  <span>转发{formatNumber(post.retweets, 0)}</span>
                  <span>评论{formatNumber(post.replies, 0)}</span>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="empty-state">本次检测仅采集到账号资料，暂未抓取到可用的近期微博。</div>
        )}
      </SectionCard>
    </div>
  );
}

function App() {
  const [session, setSession] = useState<LoginResponse | null>(null);
  const [activeNav, setActiveNav] = useState<NavKey>("overview");
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null);
  const [reports, setReports] = useState<DetectionReport[]>([]);
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null);
  const [loginForm, setLoginForm] = useState({ username: "admin", password: "Admin@123" });
  const [analysisForm, setAnalysisForm] = useState({ username: "人民日报", maxPosts: 6 });
  const [loading, setLoading] = useState(false);
  const [errorText, setErrorText] = useState("");
  const [infoText, setInfoText] = useState("");

  const selectedReport = useMemo(
    () => reports.find((item) => item.report_id === selectedReportId) ?? reports[0] ?? null,
    [reports, selectedReportId],
  );

  async function loadWorkspace() {
    setLoading(true);
    setErrorText("");
    try {
      const [dashboardPayload, reportsPayload] = await Promise.all([fetchDashboard(), fetchReports()]);
      startTransition(() => {
        setDashboard(dashboardPayload);
        setReports(reportsPayload);
        setSelectedReportId((current) => {
          if (current && reportsPayload.some((item) => item.report_id === current)) {
            return current;
          }
          return getFirstUsefulReportId(reportsPayload);
        });
      });
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : "系统初始化失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!session) return;
    void loadWorkspace();
  }, [session]);

  async function handleLogin(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setErrorText("");
    try {
      const nextSession = await login(loginForm);
      setSession(nextSession);
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : "登录失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleAnalyze(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setErrorText("");
    setInfoText("");
    try {
      const report = await analyzeAccount(analysisForm.username, Number(analysisForm.maxPosts));
      const [reportsPayload, dashboardPayload] = await Promise.all([fetchReports(), fetchDashboard()]);
      startTransition(() => {
        setReports(reportsPayload);
        setDashboard(dashboardPayload);
        setSelectedReportId(report.report_id);
        setActiveNav("reports");
      });
      setInfoText("检测任务已完成，系统已生成最新报告。");
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : "检测失败");
    } finally {
      setLoading(false);
    }
  }

  if (!session) {
    return (
      <main className="login-shell">
        <form className="login-card" onSubmit={handleLogin}>
          <div className="login-brand">
            <div className="logo-mark">SB</div>
            <h1>社交机器人检测系统</h1>
            <p>基于微博公开资料、多维文本信号与分类检测的轻量化分析平台</p>
          </div>

          <label>
            用户名
            <input value={loginForm.username} onChange={(event) => setLoginForm((current) => ({ ...current, username: event.target.value }))} />
          </label>
          <label>
            密码
            <input
              type="password"
              value={loginForm.password}
              onChange={(event) => setLoginForm((current) => ({ ...current, password: event.target.value }))}
            />
          </label>
          <button type="submit" disabled={loading}>
            {loading ? "登录中..." : "登录系统"}
          </button>
          <a href="#forgot">忘记密码</a>
          {errorText ? <p className="form-error">{errorText}</p> : null}
        </form>
      </main>
    );
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-block">
          <div className="logo-mark">SB</div>
          <div>
            <strong>社交机器人检测</strong>
            <span>微博公开账号多维检测平台</span>
          </div>
        </div>

        <nav className="nav-list">
          {navItems.map((item) => (
            <button
              key={item.key}
              type="button"
              className={item.key === activeNav ? "nav-item active" : "nav-item"}
              onClick={() => setActiveNav(item.key)}
            >
              <strong>{item.label}</strong>
              <span>{item.hint}</span>
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div>
            <strong>{session.display_name}</strong>
            <span>管理员账号</span>
          </div>
          <button type="button" className="ghost-button" onClick={() => setSession(null)}>
            退出
          </button>
        </div>
      </aside>

      <main className="content-shell">
        <header className="topbar">
          <div>
            <p className="eyebrow">当前模块</p>
            <h1>{navItems.find((item) => item.key === activeNav)?.label}</h1>
          </div>
          <div className="status-line">
            <span>{loading ? "正在处理..." : "系统就绪"}</span>
            <button type="button" className="ghost-button" onClick={() => void loadWorkspace()}>
              刷新数据
            </button>
          </div>
        </header>

        {errorText ? <div className="notice error">{errorText}</div> : null}
        {infoText ? <div className="notice success">{infoText}</div> : null}

        {activeNav === "overview" && (
          <>
            <div className="metric-grid">
              <MetricCard label="累计报告" value={String(dashboard?.total_reports ?? 0)} helper="系统已保存的检测结果" />
              <MetricCard label="高风险账号" value={String(dashboard?.high_risk_reports ?? 0)} helper="历史报告中的高风险数量" />
              <MetricCard label="平均风险" value={formatPercent(dashboard?.average_probability ?? 0)} helper="全部报告平均风险值" />
            </div>
            <SectionCard title="近期检测" subtitle="最近生成的检测记录">
              <div className="report-list">
                {(dashboard?.latest_reports ?? []).map((item) => (
                  <button
                    key={item.report_id}
                    type="button"
                    className="report-row"
                    onClick={() => {
                      setSelectedReportId(item.report_id);
                      setActiveNav("reports");
                    }}
                  >
                    <div>
                      <strong>@{item.username}</strong>
                      <p>{item.summary}</p>
                    </div>
                    <div className={`pill ${riskTone(item.risk_level)}`}>
                      {item.risk_level} {formatPercent(item.final_probability)}
                    </div>
                  </button>
                ))}
              </div>
            </SectionCard>
          </>
        )}

        {activeNav === "collection" && (
          <>
            <SectionCard title="数据来源" subtitle="当前检测基于微博公开数据">
              {selectedReport ? (
                <div className="content-columns">
                  {buildSourceNotes(selectedReport).map((item) => (
                    <article key={item.title} className="info-card">
                      <h3>{item.title}</h3>
                      <p>{item.text}</p>
                    </article>
                  ))}
                </div>
              ) : (
                <div className="empty-state">暂无可说明的数据来源，请先完成一次账号检测。</div>
              )}
            </SectionCard>

            <SectionCard title="采集批次" subtitle="选择一个已完成抓取的账号查看原始采集结果">
              {reports.length > 0 ? (
                <div className="report-list">
                  {reports.map((item) => (
                    <button
                      key={item.report_id}
                      type="button"
                      className={item.report_id === selectedReport?.report_id ? "report-row active" : "report-row"}
                      onClick={() => setSelectedReportId(item.report_id)}
                    >
                      <div>
                        <strong>@{item.username}</strong>
                        <p>{formatDate(item.created_at)}</p>
                      </div>
                      <div className={`pill ${riskTone(item.scores.risk_level)}`}>
                        {item.scores.risk_level} {formatPercent(item.scores.final_probability)}
                      </div>
                    </button>
                  ))}
                </div>
              ) : (
                <div className="empty-state">暂无采集数据，请先在“检测分析”中执行一次账号检测。</div>
              )}
            </SectionCard>

            {selectedReport ? (
              <>
                <div className="metric-grid">
                  <MetricCard label="采集账号" value={`@${selectedReport.username}`} helper="当前查看的数据批次" />
                  <MetricCard label="采集到微博" value={`${selectedReport.account.posts.length}条`} helper="本次抓到的公开微博数" />
                  <MetricCard label="结构化字段" value={`${countFeatureItems(selectedReport)}项`} helper="由系统自动计算生成" />
                </div>

                <div className="metric-grid">
                  <MetricCard label="主要语言" value={getLanguageSummary(selectedReport)} helper="基于近期微博语言字段汇总" />
                  <MetricCard label="采集时间" value={formatDate(selectedReport.created_at)} helper="本次报告生成时间" />
                  <MetricCard
                    label="图文/视频占比"
                    value={formatFieldValue("media_ratio", selectedReport.features.behavior.media_ratio)}
                    helper="公开微博中带图文或视频的比例"
                  />
                </div>

                <SectionCard title="账号原始资料" subtitle="直接来自微博公开页面和m.weibo.cn公开接口">
                  <FieldGrid
                    items={buildFieldEntries({
                      用户名: `@${selectedReport.account.username}`,
                      显示名称: selectedReport.account.display_name,
                      微博UID: selectedReport.account.user_id ?? "未提供",
                      账号简介: selectedReport.account.description || "未填写",
                      所在地区: selectedReport.account.location || "未公开",
                      粉丝数: selectedReport.account.followers_count,
                      关注数: selectedReport.account.following_count,
                      累计发博数: selectedReport.account.tweet_count,
                      本次采集时间: formatDate(selectedReport.created_at),
                    })}
                  />
                </SectionCard>

                <SectionCard title="结构化特征" subtitle="由微博公开数据自动计算得到，已尽量使用中文标签展示">
                  <FeatureSection report={selectedReport} />
                </SectionCard>

                <SectionCard title="近期采集微博" subtitle="来自微博公开页面和m.weibo.cn公开接口">
                  {selectedReport.account.posts.length > 0 ? (
                    <div className="tweet-list">
                      {selectedReport.account.posts.map((post) => (
                        <article key={post.tweet_id} className="tweet-card">
                          <p>{post.text}</p>
                          <div className="tweet-meta">
                            <span>发布时间：{formatDate(post.created_at)}</span>
                            <span>点赞：{formatNumber(post.likes, 0)}</span>
                            <span>转发：{formatNumber(post.retweets, 0)}</span>
                            <span>评论：{formatNumber(post.replies, 0)}</span>
                            <span>语言：{post.lang ? languageLabels[post.lang] ?? post.lang.toUpperCase() : "未识别"}</span>
                          </div>
                        </article>
                      ))}
                    </div>
                  ) : (
                    <div className="empty-state">该账号本次只采集到账号资料，暂无可展示的近期微博文本。</div>
                  )}
                </SectionCard>
              </>
            ) : null}
          </>
        )}

        {activeNav === "analysis" && (
          <>
            <SectionCard title="执行检测" subtitle="输入微博公开账号名称，系统会抓取公开资料和近期微博后生成报告">
              <form className="analysis-form" onSubmit={handleAnalyze}>
                <label>
                  账号名称
                  <input
                    value={analysisForm.username}
                    onChange={(event) => setAnalysisForm((current) => ({ ...current, username: event.target.value }))}
                    placeholder="例如人民日报"
                  />
                </label>
                <label>
                  近期微博数量
                  <input
                    type="number"
                    min={3}
                    max={12}
                    value={analysisForm.maxPosts}
                    onChange={(event) => setAnalysisForm((current) => ({ ...current, maxPosts: Number(event.target.value) }))}
                  />
                </label>
                <button type="submit" disabled={loading}>
                  {loading ? "检测中..." : "开始检测"}
                </button>
              </form>
            </SectionCard>

            <SectionCard title="检测数据说明" subtitle="当前检测仅使用微博公开数据">
              <div className="content-columns">
                <article className="info-card">
                  <h3>微博公开数据</h3>
                  <p>账号资料和近期微博内容取自微博公开页面及m.weibo.cn公开接口。</p>
                </article>
                <article className="info-card">
                  <h3>系统计算结果</h3>
                  <p>结构化特征和风险评分由系统基于采集数据自动计算生成。</p>
                </article>
              </div>
            </SectionCard>

            <ReportDetail report={selectedReport} />
          </>
        )}

        {activeNav === "reports" && (
          <div className="reports-layout">
            <SectionCard title="报告列表" subtitle="按时间倒序展示全部检测记录">
              <div className="report-list">
                {reports.map((item) => (
                  <button
                    key={item.report_id}
                    type="button"
                    className={item.report_id === selectedReport?.report_id ? "report-row active" : "report-row"}
                    onClick={() => setSelectedReportId(item.report_id)}
                  >
                    <div>
                      <strong>@{item.username}</strong>
                      <p>{formatDate(item.created_at)}</p>
                    </div>
                    <div className={`pill ${riskTone(item.scores.risk_level)}`}>
                      {item.scores.risk_level} {formatPercent(item.scores.final_probability)}
                    </div>
                  </button>
                ))}
              </div>
            </SectionCard>
            <ReportDetail report={selectedReport} />
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
