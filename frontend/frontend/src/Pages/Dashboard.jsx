import { useState, useEffect } from "react";
import { useAuth } from "../context/AuthContext.jsx";
import { useNavigate } from "react-router-dom";
import NavigationBar from "../components/NavigationBar.jsx";
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import "./Dashboard.css";
import Icons from "../components/Icons.jsx"


const VERDICT_CONFIG = {
  FACT: { color: "var(--verdict-fact-text)", bg: "var(--verdict-fact-bg)", label: "FACT" },
  FAKE: { color: "var(--verdict-fake-text)", bg: "var(--verdict-fake-bg)", label: "FAKE" },
  UNVERIFIED: {
      color: "var(--verdict-unverified-text)",
      bg: "var(--verdict-unverified-bg)",
      label: "UNVERIFIED",
   },
  SATIRE: { color: "var(--verdict-satire-text)", bg: "var(--verdict-satire-bg)", label: "SATIRE" },
  OUT_OF_SCOPE: {
      color: "var(--verdict-unverified-text)",
      bg: "var(--verdict-unverified-bg)",
      label: "OUT OF SCOPE",
   },
  MISLEADING: { color: "var(--verdict-misleading-text)", bg: "var(--verdict-misleading-bg)", label: "MISLEADING" },
};


function timeAgo(dateStr) {
  if (!dateStr) return "—";
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins  = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days  = Math.floor(diff / 86400000);
  if (mins  < 1)  return "Just now";
  if (mins  < 60) return `${mins}m ago`;
  if (hours < 24) return `${hours}h ago`;
  if (days  < 7)  return `${days}d ago`;
  return `${Math.floor(days / 7)}w ago`;
}


function Dashboard() {
  const { authFetch, user } = useAuth();
  const navigate = useNavigate();

  const [threads, setThreads] = useState([]);
  const [claims,  setClaims]  = useState([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(null);


  useEffect(() => {
    const fetchThreads = async () => {
      try {
        const data = await authFetch("http://localhost:8000/api/threads/", {
          method: "GET",
        });
        setThreads(data || []);
      } catch (err) {
        setError("Failed to load threads");
      }
    };

    const fetchClaims = async () => {
      try {
        const data = await authFetch("http://localhost:8000/api/auth/my-claims/", {
          method: "GET",
        });
        setClaims(data || []);
      } catch (err) {
        setError("Failed to load claims");
      } finally {
        // We set loading false only after both calls have had a chance to run.
        // Using finally on the last fetch is a simple approach.
        setLoading(false);
      }
    };

    fetchThreads();
    fetchClaims();
  }, []);

  
  const totalScans   = claims.length;
  const fakesStopped = claims.filter((c) => c.verdict === "FAKE").length;

  // "Needs Your Vote"
  const needsVote = threads
    .filter((t) => t.claim?.verdict === "UNVERIFIED" || !t.claim?.verdict)
    .slice(0, 3); // show max 3

  // Recent scans 
  const recentScans = [...claims]
    .sort((a, b) => new Date(b.last_updated) - new Date(a.last_updated))
    .slice(0, 4);

  // Trending threads 
  const trendingThreads = [...threads]
    .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
    .slice(0, 5);

  // Recharts data 
  const verdictTally = claims.reduce((acc, claim) => {
    const v = claim.verdict || "PENDING";
    acc[v] = (acc[v] || 0) + 1;
    return acc;
  }, {});

  // Convert the tally object into the array format Recharts expects:
  // [{ name: "FACT", value: 3 }, { name: "FAKE", value: 2 }, ...]
  const chartData = Object.entries(verdictTally).map(([name, value]) => ({
    name,
    value,
  }));

  return (
    <div className="dashboard-layout">
      <NavigationBar />

      <main className="dashboard-container">

        <div className="welcome-header">
          <div>
            <h1 className="welcome-title">
              Welcome back, <span className="welcome-name">@{user?.username}</span> 
            </h1>
            <p className="welcome-subtitle">
              Here's what's happening in the TruthLens community today.
            </p>
          </div>
          <div className="trust-pill">
            <span className="trust-pill-label">Trust Score</span>
            <span className="trust-pill-value">{user?.trust_score?.toFixed(1) || "0.0"}</span>
          </div>
        </div>

        {/* ── Stats ── */}
        <div className="stats-row">
          <div className="quick-stat-card">
            <p className="qs-label">Total Scans</p>
            <p className="qs-value">{totalScans}</p>
          </div>
          <div className="quick-stat-card">
            <p className="qs-label">Fake News Stopped</p>
            <p className="qs-value fake">{fakesStopped}</p>
          </div>
          <div className="quick-stat-card">
            <p className="qs-label">Community Threads</p>
            <p className="qs-value">{threads.length}</p>
          </div>
          <div className="quick-stat-card">
            <p className="qs-label">Needs Your Vote</p>
            <p className="qs-value warn">{needsVote.length}</p>
          </div>
        </div>

        {/* ── Middle Row: Widgets + Chart ── */}
        <div className="middle-row">

          {/* Left column: two widgets stacked */}
          <div className="widgets-column">

            {/* Needs Your Vote */}
            <div className="box-panel widget">
              <h2 className="widget-title"><Icons name="list-checks"/> Needs Your Vote</h2>
              {loading ? (
                <p className="empty-msg">Loading...</p>
              ) : needsVote.length === 0 ? (
                <p className="empty-msg">No unverified claims right now.</p>
              ) : (
                <div className="widget-list">
                  {needsVote.map((thread) => (
                    <div
                      key={thread.id}
                      className="widget-item clickable"
                      onClick={() => navigate("/community")}
                    >
                      <div className="widget-item-top">
                        <span className="widget-badge unverified">UNVERIFIED</span>
                        <span className="widget-time">{timeAgo(thread.created_at)}</span>
                      </div>
                      <p className="widget-summary">
                        {thread.claim?.ai_summary || thread.caption || "No summary available."}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* My Recent Scans */}
            <div className="box-panel widget">
              <h2 className="widget-title"><Icons name="scan-line"/>  My Recent Scans</h2>
              {loading ? (
                <p className="empty-msg">Loading...</p>
              ) : recentScans.length === 0 ? (
                <p className="empty-msg">No scans yet.</p>
              ) : (
                <div className="widget-list">
                  {recentScans.map((claim) => {
                    const v = VERDICT_CONFIG[claim.verdict] || VERDICT_CONFIG.PENDING;
                    return (
                      <div key={claim.id} className="widget-item">
                        <div className="widget-item-top">
                          <span
                            className="widget-badge"
                            style={{ backgroundColor: v.color }}
                          >
                            {v.label}
                          </span>
                          <span className="widget-time">{timeAgo(claim.last_updated)}</span>
                        </div>
                        <p className="widget-summary">
                          {claim.ai_summary || "No summary available."}
                        </p>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

          </div>

          {/* Right column: Recharts donut chart */}
          <div className="box-panel chart-panel">
            <h2 className="widget-title"><Icons name="pie-chart"/>  Your Verdict Breakdown</h2>
            {claims.length === 0 ? (
              <p className="empty-msg">No data yet. Start scanning claims!</p>
            ) : (
              <ResponsiveContainer width="100%" height={280}>
                <PieChart>
                  <Pie
                    data={chartData}
                    cx="50%"
                    cy="45%"
                    innerRadius={70}
                    outerRadius={110}
                    paddingAngle={3}
                    dataKey="value"
                  >
                    {chartData.map((entry) => (
                      <Cell
                        key={entry.name}
                        fill={VERDICT_CONFIG[entry.name]?.color || "#9ca3af"}
                      />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(value, name) => [`${value} scans`, name]}
                  />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            )}
          </div>

        </div>


        {/* ── Trending Claims Feed ── */}
        <div className="box-panel">
          <h2 className="widget-title"><Icons name="trending-up"/>  Trending in the Community</h2>
          {loading ? (
            <p className="empty-msg">Loading...</p>
          ) : trendingThreads.length === 0 ? (
            <p className="empty-msg">No threads yet.</p>
          ) : (
            <div className="trending-list">
              {trendingThreads.map((thread) => {
                const v = VERDICT_CONFIG[thread.claim?.verdict] || VERDICT_CONFIG.PENDING;
                return (
                  <div
                    key={thread.id}
                    className="trending-item clickable"
                    onClick={() => navigate("/community")}
                  >
                    <div className="trending-left">
                      <span
                        className="widget-badge"
                        style={{ backgroundColor: v.color }}
                      >
                        {v.label}
                      </span>
                      <p className="trending-summary">
                        {thread.claim?.ai_summary || thread.caption || "No summary."}
                      </p>
                    </div>
                    <div className="trending-right">
                      <span className="trending-author">@{thread.author?.username}</span>
                      <span className="widget-time">{timeAgo(thread.created_at)}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

      </main>
    </div>
  );
}

export default Dashboard;