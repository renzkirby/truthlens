import { useState, useEffect } from "react";
import { useAuth } from "../context/AuthContext";
import NavigationBar from "../components/NavigationBar.jsx";
import "./UserProfile.css";

const VERDICT_CONFIG = {
  FACT: { color: "#22c55e", label: "FACT" },
  FAKE: { color: "#ef4444", label: "FAKE" },
  UNVERIFIED: { color: "#9ca3af", label: "UNVERIFIED" },
  SATIRE: { color: "#a855f7", label: "SATIRE" },
  PENDING: { color: "#6b7280", label: "PENDING" },
};

function UserProfile() {
  const { user, authFetch } = useAuth();
  const [claims, setClaims] = useState([]);
  const [activeTab, setActiveTab] = useState("scans");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchClaims = async () => {
      try {
        const data = await authFetch("http://localhost:8000/api/auth/my-claims/");
        setClaims(data || []);
      } catch (err) {
        console.error("Failed to fetch claims:", err);
      } finally {
        setLoading(false);
      }
    };
    fetchClaims();
  }, []);

  const totalScans = claims.length;
  const fakesStopped = claims.filter((c) => c.verdict === "FAKE").length;
  const verifiedClaims = claims.filter((c) => c.verdict === "FACT").length;
  const accuracyRate =
    totalScans > 0
      ? Math.round(((fakesStopped + verifiedClaims) / totalScans) * 100)
      : 0;

  const getTrustLevel = (score) => {
    if (score >= 80) return { label: "Expert", color: "#22c55e" };
    if (score >= 60) return { label: "Trusted", color: "var(--primary-blue)" };
    if (score >= 40) return { label: "Contributor", color: "#f97316" };
    return { label: "Newcomer", color: "var(--text-muted)" };
  };

  const trustLevel = getTrustLevel(user?.trust_score || 0);

  const formatDate = (dateStr) => {
    if (!dateStr) return "—";
    return new Date(dateStr).toLocaleDateString("en-US", {
      year: "numeric",
      month: "long",
      day: "numeric",
    });
  };

  const timeAgo = (dateStr) => {
    if (!dateStr) return "—";
    const diff = Date.now() - new Date(dateStr).getTime();
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    if (days === 0) return "Today";
    if (days === 1) return "Yesterday";
    if (days < 7) return `${days}d ago`;
    if (days < 30) return `${Math.floor(days / 7)}w ago`;
    return `${Math.floor(days / 30)}mo ago`;
  };

  return (
    <div className="profile-layout">
      <NavigationBar />

      <main className="profile-container">

        {/* Identity Header */}
        <div className="profile-header box-panel">
          <div className="profile-avatar">
            {user?.username?.[0]?.toUpperCase() || "?"}
          </div>
          <div className="profile-identity">
            <h1 className="profile-username">{user?.username || "—"}</h1>
            <p className="profile-email">{user?.email || "—"}</p>
            <div className="profile-meta">
              <span
                className="trust-level-badge"
                style={{ backgroundColor: trustLevel.color }}
              >
                {trustLevel.label}
              </span>
              <span className="join-date">
                Joined {formatDate(user?.date_joined)}
              </span>
            </div>
          </div>
        </div>

        {/* Reputation Dashboard */}
        <div className="box-panel">
          <h2 className="section-title">Reputation Dashboard</h2>
          <div className="stats-grid">
            <div className="stat-card">
              <p className="stat-label">Trust Score</p>
              <p className="stat-value">{user?.trust_score?.toFixed(1) || "0.0"}</p>
              <div className="trust-bar-track">
                <div
                  className="trust-bar-fill"
                  style={{
                    width: `${Math.min(user?.trust_score || 0, 100)}%`,
                    backgroundColor: trustLevel.color,
                  }}
                />
              </div>
              <p className="stat-sublabel">{trustLevel.label} Level</p>
            </div>

            <div className="stat-card">
              <p className="stat-label">Accuracy Rate</p>
              <p className="stat-value">{accuracyRate}%</p>
              <p className="stat-sublabel">of verdicts confirmed</p>
            </div>

            <div className="stat-card">
              <p className="stat-label">Fake News Stopped</p>
              <p className="stat-value">{fakesStopped}</p>
              <p className="stat-sublabel">FAKE verdicts found</p>
            </div>

            <div className="stat-card">
              <p className="stat-label">Total Scans</p>
              <p className="stat-value">{totalScans}</p>
              <p className="stat-sublabel">claims analyzed</p>
            </div>
          </div>
        </div>

        {/* Activity History */}
        <div className="box-panel">
          <div className="tabs-row">
            <button
              className={`tab-btn ${activeTab === "scans" ? "active" : ""}`}
              onClick={() => setActiveTab("scans")}
            >
              My Personal Scans
            </button>
            <button
              className={`tab-btn ${activeTab === "contributions" ? "active" : ""}`}
              onClick={() => setActiveTab("contributions")}
            >
              Community Contributions
            </button>
          </div>

          {activeTab === "scans" && (
            <div className="tab-content">
              {loading ? (
                <p className="empty-msg">Loading your scans...</p>
              ) : claims.length === 0 ? (
                <p className="empty-msg">No scans yet. Start verifying claims!</p>
              ) : (
                <div className="claims-list">
                  {claims.map((claim) => {
                    const verdict = VERDICT_CONFIG[claim.verdict] || VERDICT_CONFIG.PENDING;
                    return (
                      <div className="claim-card" key={claim.id}>
                        <div className="claim-top">
                          <span
                            className="claim-verdict-badge"
                            style={{ backgroundColor: verdict.color }}
                          >
                            {verdict.label}
                          </span>
                          <span className="claim-type-pill">{claim.claim_type}</span>
                          <span className="claim-time">{timeAgo(claim.last_updated)}</span>
                        </div>
                        <p className="claim-summary">
                          {claim.ai_summary || "No summary available."}
                        </p>
                        {claim.source_link && (
                          <a
                            href={claim.source_link}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="claim-source-link"
                          >
                            View Source →
                          </a>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {activeTab === "contributions" && (
            <div className="tab-content">
              <p className="empty-msg">Community contribution history coming soon.</p>
            </div>
          )}
        </div>

        {/* Account Settings */}
        <div className="box-panel">
          <h2 className="section-title">Account Settings</h2>
          <div className="settings-grid">
            <button className="settings-btn">Change Password</button>
            <button className="settings-btn">Change Email</button>
            <button className="settings-btn danger">Delete Account</button>
          </div>
          <div className="privacy-row">
            <span className="privacy-label">Make Community Contributions Public</span>
            <label className="toggle-switch">
              <input type="checkbox" defaultChecked />
              <span className="toggle-slider" />
            </label>
          </div>
        </div>

      </main>
    </div>
  );
}

export default UserProfile;