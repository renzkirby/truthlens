import React from "react";
import "./LandingPage.css";
import snippetWireframe from "../assets/snippet_wireframe.png";
const LandingPage = () => {
  const investigations = [
    {
      title: "Suspicious Quote",
      description:
        "User @juan_delacruz submitted a quote card regarding 'Walang Pasok' on Monday attributed to DepEd. No official memo found yet.",
      status: "UNVERIFIED",
      statusClass: "unverified",
      linkText: "Help Verify →",
    },
    {
      title: "Phishing Scam Alert",
      description:
        "Viral post claiming 'Maharlika Fund' is distributing ₱5,000 cash aid via Google Form. Official sources confirm this is a scam.",
      status: "FAKE",
      statusClass: "fake",
      linkText: "View Debunking →",
    },
    {
      title: "Typhoon Update",
      description:
        "Infographic showing Signal No. 2 in Bicol Region has been cross-referenced with the latest 2:00 PM PAGASA Bulletin.",
      status: "FACT",
      statusClass: "fact",
      linkText: "See Source →",
    },
  ];

  return (
    <div className="landing-container">
      {/* Navbar */}
      <nav className="navbar">
        <div className="logo">
          <span className="logo-icon">🔍</span> TruthLens
        </div>
        <div className="nav-links">
          <a href="#features">Features</a>
          <a href="#community">Community</a>
          <a href="#about">About</a>
        </div>
        <div className="nav-auth">
          <button className="login-btn">LOGIN</button>
          <button className="get-btn">GET</button>
        </div>
      </nav>

      {/* Hero Section */}
      <header className="hero">
        <div className="hero-text">
          <h1>
            See the Truth <br /> Behind the Feed.
          </h1>
          <p>AI - powered shield against misinformation</p>
          <button className="download-btn">DOWNLOAD FOR CHROME</button>
        </div>
        <div className="hero-image">
          <div className="laptop-mockup">
            <div className="screen">
              {/* Add your image source here */}
              <img
                src={snippetWireframe}
                alt="TruthLens Interface"
                className="screen-image"
              />
            </div>
            <div className="base"></div>
          </div>
        </div>
      </header>

      {/* Stats Bar */}
      <div className="stats-bar">
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
      </div>

      {/* How it Works */}
      <section className="how-it-works">
        <h2>HOW IT WORKS?</h2>
        <div className="steps-grid">
          <div className="step">
            <div className="icon">✂️</div>
            <h3>(1) SNIP</h3>
            <p>Snip suspicious images directly from your feed.</p>
          </div>
          <div className="step">
            <div className="icon">🧠</div>
            <h3>(2) ANALYZE</h3>
            <p>AI cross-references data to detect misinformation.</p>
          </div>
          <div className="step">
            <div className="icon">👥</div>
            <h3>(3) RESOLVE</h3>
            <p>Crowdsourced voting settles unverified claims.</p>
          </div>
        </div>
      </section>

      {/* Recent Investigations */}
      <section className="investigations">
        <h2>Recent Investigations by the Community</h2>
        <div className="cards-grid">
          {investigations.map((item, index) => (
            <div key={index} className={`card ${item.statusClass}`}>
              <h3>{item.title}</h3>
              <p>{item.description}</p>
              <div className="card-footer">
                <span className={`badge ${item.statusClass}`}>
                  {item.status}
                </span>
                <span className="link">{item.linkText}</span>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
};

export default LandingPage;
