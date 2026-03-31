# TruthLens

> An AI-driven browser extension and community platform for real-time misinformation filtering, synthetic media detection, and collaborative fact-checking.

TruthLens bridges the gap between automated AI analysis and human consensus. By integrating directly into the browser, it removes the friction of traditional fact-checking, allowing users to verify claims, scan articles, and detect AI-generated media with a single click.

---

## Key Features

### The Browser Extension (Manifest V3)

- **Action Snip:** Activate the built-in snipping tool to capture claims from social media feeds or videos. Extracts text via OCR for rapid AI verification.
- **URL Scanner:** Paste any article link to instantly extract the central narrative and cross-reference it against live web data.
- **Forensic File Upload:** A dedicated drag-and-drop pipeline for downloaded images and PDFs to detect deepfakes, synthetic generation, and manipulated metadata.

### The Community Dashboard

- **Community Feed & Threads:** Users can view recent investigations, read AI summaries, and dive into specific claim threads.
- **Collaborative Verification:** A human-in-the-loop system where users submit evidence to prove or disprove claims.
- **Trust Score Economy:** Users earn reputation points through highly upvoted, credible evidence submissions, creating a self-regulating community.
- **Moderation Panel:** Enterprise-grade tools for admins to manage flagged content, override AI verdicts, and monitor the async verification queue.

---

## System Architecture

TruthLens utilizes a **Dual-Pipeline Architecture** to balance speed with deep forensic accuracy:

1. **The High-Velocity Pipeline (Snippets & URLs):** Prioritizes rapid OCR text extraction (EasyOCR) and live web context retrieval (Tavily). The data is orchestrated through Groq's LLaMA models to produce strict, JSON-formatted verdicts (Fact, Fake, Misleading, Unverified, Satire).
2. **The Deep Forensic Pipeline (File Uploads):** Bypasses browser compression to analyze raw file data. This pipeline processes physical files through dedicated synthetic media detection APIs to flag AI-generated images before running standard text verification.

---

## Tech Stack

**Frontend (Web & Extension)**

- React & Vite
- Tailwind CSS (Custom Semantic Design Tokens)
- Lucide React (Iconography)

**Backend & API**

- Django & Django REST Framework (DRF)
- PostgreSQL
- Django Channels (WebSockets)

**Asynchronous Pipeline & Infrastructure**

- Celery
- Redis (via Memurai)
- pHash (Semantic Claim Caching & Deduplication)

**AI & Orchestration**

- **Groq API:** Ultra-low latency LLM inference (LLaMA-3) for prompt orchestration and JSON extraction.
- **Tavily API:** Real-time web search optimized for LLM context retrieval.
- **EasyOCR / OpenCV:** Optical Character Recognition for the Snipping Tool.

---

## Local Development Setup

### Prerequisites

- Python 3.10+
- Node.js & npm
- PostgreSQL
- Redis (Memurai if running on Windows 10)

### 1. Backend Setup

```powershell
# Clone the repository
git clone https://github.com/renzkirby/truthlens-capstone.git
cd TruthLens/backend/truthlens_backend/

# Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Set up the database
python manage.py makemigrations
python manage.py migrate

# Start the Celery worker (in a separate terminal)
celery -A truthlens_backend worker -l info --pool=solo

# Start the Django development server
python manage.py runserver
```

### 2. Frontend Dashboard Setup

```powershell
cd ../../frontend/dashboard/
npm install
npm run dev
```

### 3. Chrome Extension Setup

1. Open Chrome and navigate to chrome://extensions/
2. Enable Developer mode in the top right corner.
3. Click Load unpacked and select the truthlens-capstone/extension/dist/ directory (after running npm run build in your extension folder).

## THE TEAM

> Brian Josh Yaiso
> Keanna Nicole Montero
> Lhoraine Palenzuela
> Rachele Rosal
> Renz Kirby Ramirez

### Developed for academic project — targeting a cleaner, safer, and more verifiable internet.
