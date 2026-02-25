import React from "react";
import "./LandingPage.css";

const LandingPage = () => {
  return (
    <div className="container">
      {/* Navigation */}
      <nav className="navbar">
        <div className="logo">
          <span className="logo-icon">🔍</span> TruthLens
        </div>
        <div className="nav-links">
          <a href="#features">Features</a>
          <a href="#community">Community</a>
          <a href="#about">About</a>
        </div>
        <div className="nav-buttons">
          <button className="btn-login">LOGIN</button>
          <button className="btn-get">GET</button>
        </div>
      </nav>

      {/* Hero Section */}
      <header className="hero">
        <div className="hero-content">
          <h1>
            See the Truth <br /> Behind the Feed.
          </h1>
          <p>AI - powered shield against misinformation</p>
          <button className="btn-download">DOWNLOAD FOR CHROME</button>
        </div>
        <div className="hero-mockup">
          <div className="laptop-frame">
            {/* Representing the UI from your wireframe */}
            <div className="mock-screen">
              <div className="mock-popup">
                <div className="popup-header">
                  <span>TruthLens</span>
                  <div className="dots">
                    <span className="dot red"></span>
                    <span className="dot yellow"></span>
                    <span className="dot green"></span>
                  </div>
                </div>
                <div className="popup-body"></div>
                <button className="popup-btn">Verify 🔍</button>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Stats Bar */}
      <section className="stats-bar">
        <span>
          <strong>12,040</strong> Images Verified
        </span>
        <span className="separator">•</span>
        <span>
          <strong>500+</strong> Active Contributors
        </span>
        <span className="separator">•</span>
        <span>
          <strong>98%</strong> Accuracy Rate
        </span>
      </section>

      {/* How It Works */}
      <section className="how-it-works">
        <h2>HOW IT WORKS?</h2>
        <div className="steps-grid">
          <div className="step">
            <div className="step-icon">✂️</div>
            <h3>(1) SNIP</h3>
            <p>Snip suspicious images directly from your feed.</p>
          </div>
          <div className="step">
            <div className="step-icon">🧠</div>
            <h3>(2) ANALYZE</h3>
            <p>AI cross-references data to detect misinformation.</p>
          </div>
          <div className="step">
            <div className="step-icon">👥</div>
            <h3>(3) RESOLVE</h3>
            <p>Crowdsourced voting settles unverified claims.</p>
          </div>
        </div>
      </section>

      {/* Recent Investigations */}
      <section className="investigations">
        <h2>Recent Investigations by the Community</h2>
        <div className="cards-grid">
          <div className="invest-card yellow-card">
            <h4>Suspicious Quote</h4>
            <p>
              User @juan_delacruz submitted a quote card regarding 'Walang
              Pasok'...
            </p>
            <div className="card-footer">
              <span className="badge unverified">⚠️ UNVERIFIED</span>
              <a href="#">Help Verify →</a>
            </div>
          </div>
          <div className="invest-card red-card">
            <h4>Phishing Scam Alert</h4>
            <p>
              Viral post claiming 'Maharlika Fund' is distributing ₱5,000 cash
              aid...
            </p>
            <div className="card-footer">
              <span className="badge fake">🚫 FAKE</span>
              <a href="#">View Debunking →</a>
            </div>
          </div>
          <div className="invest-card green-card">
            <h4>Typhoon Update</h4>
            <p>
              Infographic showing Signal No. 2 in Bicol Region has been
              cross-referenced...
            </p>
            <div className="card-footer">
              <span className="badge fact">✅ FACT</span>
              <a href="#">See Source →</a>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="footer">
        <p>
          🔍 TruthLens | © 2026 TruthLens Project. Built for Capstone Thesis.
        </p>
      </footer>
    </div>
  );
};

export default LandingPage;
