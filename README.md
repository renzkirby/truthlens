# TruthLens

> An AI-driven browser extension and web community platform for misinformation verification, synthetic media detection, and collaborative fact-checking.

TruthLens helps users verify questionable online content without leaving their current browsing experience. It combines automated evidence retrieval and AI-assisted analysis with a community verification platform for claims that cannot be resolved through available online evidence.

Rather than relying solely on AI-generated judgments, TruthLens follows an **evidence-first approach** by retrieving relevant fact-checks and web sources before producing a verification result.

---

## Key Features

### Browser Extension (Manifest V3)

- **Image Snipping:** Capture suspicious content directly from a webpage and extract text using OCR for verification.
- **URL Analysis:** Analyze article links, extract their central claims, and cross-check them against available evidence.
- **Text Verification:** Submit textual claims directly for fact-checking.
- **File Analysis:** Upload supported documents for text extraction and claim verification.
- **Deepfake Detection:** Analyze images for signs of AI-generated or manipulated visual content.
- **In-Page Results:** Display verification results directly on the active webpage.

### Community Platform

- **Community Feed & Threads:** Browse verified claims, ongoing investigations, evidence, and discussions.
- **Community Escalation:** Claims with insufficient evidence can be escalated for collaborative verification.
- **Evidence Submission:** Users can contribute supporting, contradicting, or contextual evidence.
- **Trust Score System:** User reputation is adjusted based on the quality of resolved contributions.
- **Moderation Panel:** Moderators can review evidence, resolve escalated claims, and manage community activity.

---

## Verification Pipeline

TruthLens uses an evidence-first verification pipeline:

1. **Input Processing**  
   Claims are extracted from image snippets, text, URLs, or uploaded documents.

2. **Claim Matching**  
   Previously processed claims are checked using fingerprinting and semantic similarity.

3. **Verified Knowledge Retrieval**  
   TruthLens searches its internal verified information before performing external retrieval.

4. **Google Fact Check Tools API**  
   Existing professional fact-checks are prioritized when available.

5. **Tavily Web Retrieval**  
   Additional evidence is retrieved from selected online sources when relevant fact-checks are unavailable.

6. **Evidence-Grounded AI Analysis**  
   Google Gemini analyzes the claim against the retrieved evidence, with Groq-hosted Llama models available as a fallback.

The system may return:

**FACT · FAKE · MISLEADING · SATIRE · UNVERIFIED**

Claims without enough reliable evidence are intentionally classified as **UNVERIFIED** and may be escalated to the community platform.

---

## Tech Stack

### Frontend

- React
- Vite
- Chrome Extension API / Manifest V3
- Axios
- Lucide React
- Recharts

### Backend

- Django
- Django REST Framework
- PostgreSQL via Supabase
- pgvector
- Celery
- Redis

### AI & Verification

- **Google Gemini** — primary evidence-grounded AI analysis
- **Groq / Llama** — fallback AI provider
- **Google Fact Check Tools API** — professional fact-check retrieval
- **Tavily API** — live web evidence retrieval
- **Google Cloud Vision** — primary OCR
- **EasyOCR** — OCR fallback
- **Sightengine** — AI-generated image and deepfake detection
- **Sentence Transformers** — semantic claim matching

---

## Local Development Setup

### Prerequisites

- Python 3.10+
- Node.js & npm
- Redis
- PostgreSQL / Supabase development database

### 1. Clone the Repository

```powershell
git clone https://github.com/renzkirby/truthlens.git
cd truthlens
2. Backend Setup
cd backend/truthlens_backend

python -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt

python manage.py migrate
python manage.py runserver

Start Redis and run the Celery worker in a separate terminal:

celery -A truthlens_backend worker -l info --pool=solo

Configure the required API keys and database credentials in the backend .env file before running verification features.

3. Web Platform Setup
cd frontend/frontend

npm install
npm run dev
4. Browser Extension Setup
cd extension

npm install
npm run build

Then:

Open chrome://extensions/
Enable Developer mode
Click Load unpacked
Select the extension/dist/ directory
Development

TruthLens follows an iterative engineering workflow:

Inspect → Plan → Implement → Test → Fix → Polish → Lock

The project is currently under active development as part of an undergraduate capstone study at Cavite State University – Bacoor City Campus.

The Team
Brian Josh Yaiso
Keanna Nicole Montero
Lhoraine Palenzuela
Rachele Rosal
Renz Kirby Ramirez
