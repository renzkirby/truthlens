import React, { useState, useEffect } from "react";
import { getUserHubData } from "../utils/api";
import "./UserHub.css";
import Icons from "../components/Icons";

const VerdictBadge = ({ verdict }) => {
    const map = {
        FACT: { bg: "#d1fae5", text: "#065f46", border: "#0e9f6e", label: "Fact", Icon: "check-circle" },
        FAKE: { bg: "#fee2e2", text: "#7f1d1d", border: "#e02424", label: "Fake", Icon: "x-circle" },
        MISLEADING: { bg: "#fef3c7", text: "#78350f", border: "#d97706", label: "Misleading", Icon: "alert-triangle" },
        SATIRE: { bg: "#ede9fe", text: "#4c1d95", border: "#7c3aed", label: "Satire", Icon: "wand" },
        UNVERIFIED: { bg: "#f3f4f6", text: "#374151", border: "#6b7280", label: "Unverified", Icon: "help-circle" },
    };
    
    const normalized = verdict ? verdict.toUpperCase() : "UNVERIFIED";
    const s = map[normalized] || map.UNVERIFIED;

    return (
        <span style={{
            background: s.bg, color: s.text, border: `1.5px solid ${s.border}`,
            borderRadius: 6, padding: "3px 9px", fontSize: 11, fontWeight: 700,
            letterSpacing: "0.03em", display: "inline-flex", alignItems: "center", gap: 5
        }}>
            <Icons name={s.Icon} size={11} strokeWidth={2.5} />
            {s.label}
        </span>
    );
};

const TrustGauge = ({ score }) => {
    const color = score >= 80 ? "#0e9f6e" : score >= 50 ? "#d97706" : "#e02424";
    return (
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 2 }}>
            <svg width={64} height={64} viewBox="0 0 64 64">
                <circle cx={32} cy={32} r={26} fill="none" stroke="#e5e7eb" strokeWidth={6} />
                <circle cx={32} cy={32} r={26} fill="none" stroke={color} strokeWidth={6}
                    strokeDasharray={`${(score / 100) * 163.4} 163.4`}
                    strokeLinecap="round" transform="rotate(-90 32 32)" />
                <text x={32} y={37} textAnchor="middle" fontSize={13} fontWeight={800} fill={color}>
                    {score}
                </text>
            </svg>
            <span style={{ fontSize: 10, color: "#6b7280", fontWeight: 600, letterSpacing: "0.06em" }}>
                TRUST SCORE
            </span>
        </div>
    );
};

const Avatar = ({ iconName, bg, color, size, imgUrl }) => (
    <div style={{
        width: size, height: size, borderRadius: "50%", background: bg,
        display: "flex", alignItems: "center", justifyContent: "center", 
        flexShrink: 0, overflow: "hidden"
    }}>
        {imgUrl ? (
            <img 
                src={imgUrl} 
                alt="Profile" 
                style={{ width: "100%", height: "100%", objectFit: "cover" }} 
            />
        ) : (
            <Icons name={iconName} size={size * 0.44} color={color} strokeWidth={2} />
        )}
    </div>
);

// --- Main Page ---
const UserHub = () => {
    const [hubData, setHubData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        const loadDashboard = async () => {
            try {
                const data = await getUserHubData();
                setHubData(data);
            } catch (err) {
                setError("Failed to load your hub data. Please try again.");
            } finally {
                setLoading(false);
            }
        };
        loadDashboard();
    }, []);

    if (loading) return <div className="hub-wrapper"><p style={{textAlign: "center", color: "#6b7280"}}>Loading Dashboard...</p></div>;
    if (error) return <div className="hub-wrapper"><p style={{textAlign: "center", color: "#e02424"}}>{error}</p></div>;

    const { reputation, impact, library } = hubData;

    return (
        <div className="hub-wrapper">
            <div className="hub-container">
                
                {/* Profile Header */}
                <div className="profile-card">
                    <div className="avatar-circle" style={{ background: "transparent" }}>
                        <Avatar 
                            imgUrl={hubData.user_info.avatar_url} 
                            iconName="user-circle" 
                            size={64} 
                            bg="#ddd6fe" 
                            color="#7c3aed" 
                        />
                    </div>
                    <div className="profile-info">
                        <div className="profile-username">@{hubData.user_info.username}</div>
                        <div className="profile-meta">
                            <Icons name="badge-check" size={12} color="#0e9f6e" />
                            {reputation.current_rank}
                        </div>
                        <div className="profile-bio">
                            Points to next rank: <strong>{reputation.points_to_next_rank}</strong>
                        </div>
                    </div>
                    
                    <div className="profile-stats">
                        <TrustGauge score={reputation.trust_score || 0} />
                        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                            <div className="stat-block">
                                <div className="stat-val">{impact.total_scans || 0}</div>
                                <div className="stat-lbl"><Icons name="scan-line" size={8} /> SCANS</div>
                            </div>
                            <div className="stat-block">
                                <div className="stat-val">{impact.impact_ripple || 0}</div>
                                <div className="stat-lbl"><Icons name="thumbs-up" size={8} /> VOTES</div>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Scans Table */}
                <div className="section-label">My Saved Receipts</div>
                <div className="data-panel">
                    <table className="data-table">
                        <thead>
                            <tr>
                                <th></th>
                                <th>Claim Excerpt</th>
                                <th>AI Verdict</th>
                                <th>Date</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {library.saved_receipts && library.saved_receipts.length > 0 ? (
                                library.saved_receipts.map((claim, i) => (
                                    <tr key={i}>
                                        <td>
                                            <div className="icon-box">
                                                {claim.claim_type === 'IMAGE' ? (
                                                    <Icons name="image" size={15} color="#6b7280" />
                                                ) : (
                                                    <Icons name="globe" size={15} color="#6b7280" />
                                                )}
                                            </div>
                                        </td>
                                        <td style={{ maxWidth: 200 }}>
                                            {claim.ai_summary || "No summary available."}
                                        </td>
                                        <td>
                                            <VerdictBadge verdict={claim.final_verdict || claim.ai_verdict} />
                                        </td>
                                        <td style={{ fontSize: 11, color: "#6b7280" }}>
                                            {new Date(claim.last_updated).toLocaleDateString()}
                                        </td>
                                        <td>
                                            <div style={{ display: "flex", gap: 6 }}>
                                                <button className="action-btn">
                                                    <Icons name="eye" size={10} color="#4f46e5" /> View
                                                </button>
                                                {claim.source_link && (
                                                    <a href={claim.source_link} target="_blank" rel="noreferrer" className="action-btn" style={{ background: "#f3f4f6", color: "#6b7280" }}>
                                                        <Icons name="external-link" size={10} color="#6b7280" /> Source
                                                    </a>
                                                )}
                                            </div>
                                        </td>
                                    </tr>
                                ))
                            ) : (
                                <tr>
                                    <td colSpan="5" style={{ textAlign: "center", padding: "20px", color: "#6b7280" }}>
                                        No saved receipts found. Bookmark a claim to see it here!
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>

                {/* Contributions Grid */}
                <div className="section-label">My Contributions</div>
                <div className="contributions-grid">
                    <div className="contribution-card">
                        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                            <span style={{ fontSize: 9, fontWeight: 800, color: "#4f46e5", letterSpacing: "0.08em", display: "flex", alignItems: "center", gap: 4 }}>
                                <Icons name="message-circle" size={9} color="#4f46e5" /> THREADS STARTED
                            </span>
                        </div>
                        <div style={{ fontSize: 16, fontWeight: 900, color: "#111827" }}>
                            {impact.total_scans || 0}
                        </div>
                    </div>
                    
                    <div className="contribution-card">
                        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                            <span style={{ fontSize: 9, fontWeight: 800, color: "#4f46e5", letterSpacing: "0.08em", display: "flex", alignItems: "center", gap: 4 }}>
                                <Icons name="paperclip" size={9} color="#4f46e5" /> EVIDENCE & VOTES
                            </span>
                        </div>
                        <div style={{ fontSize: 16, fontWeight: 900, color: "#111827" }}>
                            {impact.community_contributions || 0}
                        </div>
                    </div>
                </div>

            </div>
        </div>
    );
};

export default UserHub;