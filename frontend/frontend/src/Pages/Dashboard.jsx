/**
 * Dashboard Page
 * ══════════════════════════════════════════════════════════════════
 * User dashboard showing metrics, recent activity, and trending claims.
 *
 * Features:
 *   - Quick stats: total scans, fake news stopped, community threads
 *   - Widgets: claims needing votes, recent scans, verdict breakdown chart
 *   - Trending claims from the community
 *
 * State Management:
 *   - Custom hooks (useFetchThreads, useFetchClaims) handle data fetching
 *   - Verdict utility functions for consistent verdict display
 *   - Centralized constants for verdict configurations
 */

import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";
import NavigationBar from "../components/NavigationBar.jsx";
import Icons from "../components/Icons.jsx";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from "recharts";

// ── Utilities & Hooks ──
import timeAgo from "../utils/timeAgo";
import { VERDICT_CONFIG } from "../utils/constants";
import { getEffectiveVerdict } from "../utils/verdict";
import { useFetchThreads, useFetchClaims } from "../hooks";

// ── Styles ──
import "./Dashboard.css";

/**
 * Dashboard Component
 * Shows user overview with metrics, recent activity, trending claims
 */
function Dashboard() {
   const { user, authFetch, refreshUser } = useAuth();
   const navigate = useNavigate();

   useEffect(() => {
      refreshUser?.();
   }, []);

   // ── Data Fetching ──
   // Use custom hooks to eliminate boilerplate fetch logic
   const { threads, loading: threadsLoading } = useFetchThreads(authFetch);
   const { claims, loading: claimsLoading } = useFetchClaims(authFetch, "my-claims");

   // Overall loading state (true if either is loading)
   const loading = threadsLoading || claimsLoading;

   // ── Compute Dashboard Stats ──
   // Derived from claims and threads data
   const totalScans = claims.length;
   const fakesStopped = claims.filter((c) => getEffectiveVerdict(c) === "FAKE").length;

   // ── Widget Data: Needs Your Vote ──
   // Show up to 3 unverified threads
   const needsVote = threads
      .filter((t) => {
         const verdict = getEffectiveVerdict(t.claim);
         return verdict === "UNVERIFIED" || !verdict;
      })
      .slice(0, 3);

   // ── Widget Data: My Recent Scans ──
   // Show 4 most recent claims (sorted by last_updated)
   const recentScans = [...claims]
      .sort((a, b) => new Date(b.last_updated) - new Date(a.last_updated))
      .slice(0, 4);

   // ── Widget Data: Trending Threads ──
   // Show 5 most recent threads (sorted by created_at)
   const trendingThreads = [...threads]
      .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
      .slice(0, 5);

   // ── Chart Data: Verdict Breakdown ──
   // Count claims by verdict for pie chart visualization
   const verdictTally = claims.reduce((acc, claim) => {
      const v = getEffectiveVerdict(claim) || "PENDING";
      acc[v] = (acc[v] || 0) + 1;
      return acc;
   }, {});

   const chartData = Object.entries(verdictTally).map(([name, value]) => ({
      name,
      value,
   }));

   return (
      <div className="dashboard-layout">
         <NavigationBar />

         <main className="dashboard-container">
            {/* ── Welcome Header ── */}
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

            {/* ── Quick Stats Row ── */}
            {/* Shows: total scans, fake stopped, community threads, claims needing votes */}
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
            {/* Left: Stacked widgets (votes & recent scans) | Right: Verdict breakdown chart */}
            <div className="middle-row">
               <div className="widgets-column">
                  {/* Needs Your Vote */}
                  <div className="box-panel widget">
                     <h2 className="widget-title">
                        <Icons name="list-checks" /> Needs Your Vote
                     </h2>
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
                                 onClick={() => navigate("/community")}>
                                 <div className="widget-item-top">
                                    <span className="widget-badge unverified">UNVERIFIED</span>
                                    <span className="widget-time">
                                       {timeAgo(thread.created_at)}
                                    </span>
                                 </div>
                                 <p className="widget-summary">
                                    {thread.claim?.ai_summary ||
                                       thread.caption ||
                                       "No summary available."}
                                 </p>
                              </div>
                           ))}
                        </div>
                     )}
                  </div>

                  {/* My Recent Scans */}
                  <div className="box-panel widget">
                     <h2 className="widget-title">
                        <Icons name="scan-line" /> My Recent Scans
                     </h2>
                     {loading ? (
                        <p className="empty-msg">Loading...</p>
                     ) : recentScans.length === 0 ? (
                        <p className="empty-msg">No scans yet.</p>
                     ) : (
                        <div className="widget-list">
                           {recentScans.map((claim) => {
                              const verdict = getEffectiveVerdict(claim);
                              const v = VERDICT_CONFIG[verdict] || VERDICT_CONFIG.PENDING;
                              return (
                                 <div
                                    key={claim.id}
                                    className="widget-item">
                                    <div className="widget-item-top">
                                       <span
                                          className="widget-badge"
                                          style={{ backgroundColor: v.color }}>
                                          {v.label}
                                       </span>
                                       <span className="widget-time">
                                          {timeAgo(claim.last_updated)}
                                       </span>
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
                  <h2 className="widget-title">
                     <Icons name="pie-chart" /> Your Verdict Breakdown
                  </h2>
                  {claims.length === 0 ? (
                     <p className="empty-msg">No data yet. Start scanning claims!</p>
                  ) : (
                     <ResponsiveContainer
                        width="100%"
                        height={280}>
                        <PieChart>
                           <Pie
                              data={chartData}
                              cx="50%"
                              cy="45%"
                              innerRadius={70}
                              outerRadius={110}
                              paddingAngle={3}
                              dataKey="value">
                              {chartData.map((entry) => (
                                 <Cell
                                    key={entry.name}
                                    fill={VERDICT_CONFIG[entry.name]?.color || "#9ca3af"}
                                 />
                              ))}
                           </Pie>
                           <Tooltip formatter={(value, name) => [`${value} scans`, name]} />
                           <Legend />
                        </PieChart>
                     </ResponsiveContainer>
                  )}
               </div>
            </div>

            {/* ── Trending Claims Feed ── */}
            <div className="box-panel">
               <h2 className="widget-title">
                  <Icons name="trending-up" /> Trending in the Community
               </h2>
               {loading ? (
                  <p className="empty-msg">Loading...</p>
               ) : trendingThreads.length === 0 ? (
                  <p className="empty-msg">No threads yet.</p>
               ) : (
                  <div className="trending-list">
                     {trendingThreads.map((thread) => {
                        const verdict = getEffectiveVerdict(thread.claim);
                        const v = VERDICT_CONFIG[verdict] || VERDICT_CONFIG.PENDING;
                        return (
                           <div
                              key={thread.id}
                              className="trending-item clickable"
                              onClick={() => navigate("/community")}>
                              <div className="trending-left">
                                 <span
                                    className="widget-badge"
                                    style={{ backgroundColor: v.color }}>
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
