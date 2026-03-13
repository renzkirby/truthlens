import React from 'react';
import './LandingPage.css';
import { Link } from 'react-router';

const TruthLens = () => {
  return (
    <div className="landing-page">
      {/* Navbar */}
      <nav className="navbar">
        <div className="navbar-content">
          <div className="logo">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" className="logo-icon">
              <circle cx="11" cy="11" r="8" stroke="#10b981" strokeWidth="2.5"/>
              <line x1="16.5" y1="16.5" x2="21" y2="21" stroke="#ef4444" strokeWidth="2.5" strokeLinecap="round"/>
              <circle cx="11" cy="11" r="3" fill="#f59e0b"/>
            </svg>
            TruthLens
          </div>
          <div className="nav-links">
            <a href="#features">Features</a>
            <Link to="/community">Community</Link>
            <a href="#about">About</a>
          </div>
          <div className="nav-actions">
            <button className="login-btn">Login</button>
            <button className="get-started-btn">Get Started</button>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="hero-section">
        <div className="hero-container">
          <div className="hero-content">
            <div className="hero-badge">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
              AI-POWERED MEDIA LITERACY
            </div>
            <h1 className="hero-title">
              See the Truth <br />
              <span className="hero-highlight">Behind the Feed.</span>
            </h1>
            <p className="hero-subtitle">
              AI-powered shield against misinformation. Snip any claim, get an instant verdict, and let 10,000+ fact-checkers settle the debate.
            </p>
            
            <div className="hero-stats">
              <div className="stat-item">
                <h3>12,040+</h3>
                <p>IMAGES VERIFIED</p>
              </div>
              <div className="stat-item">
                <h3>500+</h3>
                <p>ACTIVE CONTRIBUTORS</p>
              </div>
              <div className="stat-item">
                <h3>98%</h3>
                <p>ACCURACY RATE</p>
              </div>
              <div className="stat-item">
                <h3>10k+</h3>
                <p>COMMUNITY MEMBERS</p>
              </div>
            </div>

            <div className="hero-buttons">
              <button className="download-btn">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                DOWNLOAD FOR CHROME
              </button>
              <button className="demo-btn">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                Watch Demo
              </button>
            </div>
          </div>

          <div className="hero-visual">
            <div className="mockup-container">
              <div className="mockup-bg-shape shape-1"></div>
              <div className="mockup-bg-shape shape-2"></div>
              
              {/* Foreground Floating Card */}
              <div className="floating-card">
                <div className="card-header">
                  <div className="card-logo">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
                    <span>TruthLens</span>
                  </div>
                  <div className="card-badge badge-fake">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
                    Fake / False
                  </div>
                </div>
                <p className="card-text">AI detected this photo is from a 2021 flood event, not 2024.</p>
                <div className="progress-bar">
                  <div className="progress-fill" style={{ width: '94%' }}></div>
                </div>
                <p className="card-meta">94% confidence · 15 community sources</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* How It Works Section */}
      <section className="how-it-works">
        <div className="section-header">
          <span className="section-label">HOW IT WORKS</span>
          <h2 className="section-title">Three steps to the truth</h2>
        </div>
        
        <div className="steps-grid">
          <div className="step-card">
            <div className="step-icon-wrapper">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><line x1="20" y1="4" x2="8.12" y2="15.88"/><line x1="14.47" y1="14.48" x2="20" y2="20"/><line x1="8.12" y1="8.12" x2="12" y2="12"/></svg>
            </div>
            <div className="step-number">01 — SNIP</div>
            <h3 className="step-title">Snip</h3>
            <p className="step-desc">Select any suspicious claim or image directly from your feed using our Chrome extension.</p>
          </div>
          
          <div className="step-card">
            <div className="step-icon-wrapper">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
            </div>
            <div className="step-number">02 — ANALYZE</div>
            <h3 className="step-title">Analyze</h3>
            <p className="step-desc">AI cross-references the claim against thousands of verified sources in under 3 seconds.</p>
          </div>
          
          <div className="step-card">
            <div className="step-icon-wrapper">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
            </div>
            <div className="step-number">03 — RESOLVE</div>
            <h3 className="step-title">Resolve</h3>
            <p className="step-desc">The community votes on uncertain claims. Your Trust Score grows with every accurate contribution.</p>
          </div>
        </div>
      </section>

      {/* Recent Investigations Section */}
      <section className="investigations-section">
        <div className="investigations-header">
          <div>
            <span className="section-label">LIVE FROM THE COMMUNITY</span>
            <h2 className="section-title">Recent Investigations</h2>
          </div>
          <button className="view-all-btn">View All →</button>
        </div>

        <div className="investigations-grid">
          {/* Card 1 */}
          <div className="inv-card">
            <div className="inv-image border-fake">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#9ca3af" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
              <div className="inv-badge badge-fake outline">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
                Fake / False
              </div>
            </div>
            <div className="inv-content">
              <h3>Valencia flooding photo</h3>
              <p>Aerial photo is from 2021 Hurricane Ida, not 2024 Spain floods.</p>
              <div className="ai-confidence">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
                AI Confidence: <strong>94 %</strong>
              </div>
            </div>
          </div>

          {/* Card 2 */}
          <div className="inv-card">
            <div className="inv-image border-misleading">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#9ca3af" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
              <div className="inv-badge badge-misleading outline">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                Misleading
              </div>
            </div>
            <div className="inv-content">
              <h3>Mask effectiveness study</h3>
              <p>Study cited has not been peer-reviewed and contradicts CDC guidelines.</p>
              <div className="ai-confidence">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
                AI Confidence: <strong>62 %</strong>
              </div>
            </div>
          </div>

          {/* Card 3 */}
          <div className="inv-card">
            <div className="inv-image border-fact">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#9ca3af" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
              <div className="inv-badge badge-fact outline">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
                Fact
              </div>
            </div>
            <div className="inv-content">
              <h3>Unemployment figures</h3>
              <p>BLS data confirms headline claim is accurate within margin of error.</p>
              <div className="ai-confidence">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
                AI Confidence: <strong>97 %</strong>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Trust Score CTA */}
      <section className="trust-cta">
        <div className="trust-content">
          <div className="trust-circle">
            <span className="score-number">82</span>
          </div>
          <span className="trust-label">TRUST SCORE</span>
          <h2>Build Your Trust Score</h2>
          <p>
            Every piece of evidence you submit, every vote you cast — it all builds
            your credibility score. Trusted contributors have more weight in
            community decisions.
          </p>
          <button className="join-btn">Join the Community →</button>
        </div>
      </section>

      {/* Footer */}
      <footer className="footer">
        <div className="footer-content">
          <div className="footer-left">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" className="footer-logo">
              <circle cx="11" cy="11" r="8" stroke="#ffffff" strokeWidth="2.5"/>
              <line x1="16.5" y1="16.5" x2="21" y2="21" stroke="#ffffff" strokeWidth="2.5" strokeLinecap="round"/>
            </svg>
            <span>© 2025 TruthLens. Fighting misinformation together.</span>
          </div>
          <div className="footer-links">
            <a href="#privacy">Privacy</a>
            <a href="#terms">Terms</a>
            <a href="#contact">Contact</a>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default TruthLens;