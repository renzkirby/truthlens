import React from 'react';
import './CommunityFeed.css';
import LogoImage from '../assets/truthlens-logo.png';

const CommunityFeed = () => {
  const posts = [
    {
      id: 1,
      author: "@brian_023",
      time: "2h ago",
      avatarBg: "#fee2e2",
      avatarColor: "#ef4444",
      claim: "Shocking aerial photo shows the aftermath of the 2024 flooding in Valencia, Spain.",
      status: "Misleading",
      statusClass: "misleading",
      confidence: "94 %",
      actionBtnText: "Needs Evidence",
      comments: 89,
      evidenceCount: 15,
    },
    {
      id: 2,
      author: "@Luffy56",
      time: "2h ago",
      avatarBg: "#e0e7ff",
      avatarColor: "#4f46e5",
      claim: "Shocking aerial photo shows the aftermath of the 2024 flooding in Valencia, Spain.",
      status: "Unverified",
      statusClass: "unverified",
      confidence: "94 %",
      actionBtnText: "Pending",
      comments: 12,
      evidenceCount: 3,
    }
  ];

  return (
    <div className="feed-layout">
      {/* Navbar */}
      <nav className="top-navbar">
        <div className="nav-left">
          <div className="logo-section">
           <div className="logo-section">
 <img src={LogoImage} alt="TruthLens Logo" style={{ height: '40px', width: 'auto' }} />
              <circle cx="11" cy="11" r="8" stroke="#10b981" strokeWidth="2.5"/>
              <line x1="16.5" y1="16.5" x2="21" y2="21" stroke="#ef4444" strokeWidth="2.5" strokeLinecap="round"/>
              <circle cx="11" cy="11" r="3" fill="#f59e0b"/>
         </div>
            <span className="logo-text">TruthLens</span>
          </div>
          
          <div className="nav-tabs">
            <div className="nav-tab active">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
              Community Feed
            </div>
            <div className="nav-tab">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
              Dashboard
            </div>
            <div className="nav-tab">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
              Notifications
            </div>
            <div className="nav-tab">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
              Settings
            </div>
          </div>
        </div>

        <div className="nav-right">
          <div className="user-profile-pill">
            <div className="user-icon-sm">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
            </div>
            <span className="username">@RenzPogi</span>
            <span className="trust-score">82</span>
          </div>
        </div>
      </nav>

      {/* Main Feed Area */}
      <main className="feed-container">
        
        {/* Filter Bar */}
        <div className="filter-bar box-panel">
          <div className="filter-left">
            <span className="filter-label">Filter:</span>
            <button className="filter-btn active">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></svg>
              Trending
            </button>
            <button className="filter-btn">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="20 6 9 17 4 12"/></svg>
              Recently Verified
            </button>
            <button className="filter-btn">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
              Needs Evidence
            </button>
          </div>
          <div className="search-box">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#9ca3af" strokeWidth="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            <input type="text" placeholder="Search claims..." />
          </div>
        </div>

        {/* Input Bar */}
        <div className="input-bar box-panel">
          <div className="avatar-icon">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
          </div>
          <input type="text" placeholder="Flag a new claim for the community.." className="claim-input" />
          <button className="snip-btn">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><line x1="20" y1="4" x2="8.12" y2="15.88"/><line x1="14.47" y1="14.48" x2="20" y2="20"/><line x1="8.12" y1="8.12" x2="12" y2="12"/></svg>
            Snip
          </button>
        </div>

        {/* Posts List */}
        <div className="posts-list">
          {posts.map(post => (
            <div key={post.id} className="post-card">
              
              {/* Card Header */}
              <div className="card-header">
                <div className="post-author-info">
                  <div className="author-avatar" style={{ backgroundColor: post.avatarBg, color: post.avatarColor }}>
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                  </div>
                  <div className="author-meta">
                    <span className="author-name">{post.author}</span>
                    <div className="author-time">
                      {post.time} · <span className="via-link"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg> via TruthLens</span>
                    </div>
                  </div>
                </div>
                <div className="header-actions">
                  <div className={`status-badge badge-${post.statusClass}`}>
                    {post.statusClass === 'misleading' && (
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                    )}
                    {post.statusClass === 'unverified' && (
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                    )}
                    {post.status}
                  </div>
                  <button className="more-btn">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/></svg>
                  </button>
                </div>
              </div>

              {/* Card Claim Text */}
              <div className="card-claim">
                <strong>Flagged claim:</strong> "{post.claim}"
              </div>

              {/* Media Placeholder */}
              <div className="card-media">
                <div className="media-icon">
                  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#6b7280" strokeWidth="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
                </div>
                <span className="media-source">Snipped from Twitter / X</span>
              </div>

              {/* AI Analysis Bar */}
              <div className={`ai-analysis-bar bar-${post.statusClass}`}>
                <div className="ai-info">
                  <div className={`status-badge solid badge-${post.statusClass}`}>
                    {post.statusClass === 'misleading' && (
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                    )}
                    {post.statusClass === 'unverified' && (
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                    )}
                    {post.status}
                  </div>
                  <span className="ai-confidence-text">AI Confidence: <strong>{post.confidence}</strong></span>
                </div>
                <button className="needs-evidence-btn">{post.actionBtnText}</button>
              </div>

              {/* Card Footer actions */}
              <div className="card-footer">
                <button className="action-item">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                  Comment
                  <span className="count-pill">{post.comments}</span>
                </button>
                
                <button className="action-item primary-action">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg>
                  Add Evidence
                </button>
                
                <button className="action-item">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
                  Evidence
                  <span className="count-pill">{post.evidenceCount}</span>
                </button>
              </div>
            </div>
          ))}
        </div>

      </main>
    </div>
  );
};

export default CommunityFeed;