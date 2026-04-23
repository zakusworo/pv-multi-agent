# Deployment Guide

## Local Installation

### Step 1: Prerequisites

- **Python 3.12+** (check: `python3 --version`)
- **uv** package manager (`pip install uv` or see https://docs.astral.sh/uv/)
- **Ollama** (optional, for local AI): https://ollama.com/download

### Step 2: Clone Repository

```bash
git clone https://github.com/zakusworo/pv-multi-agent.git
cd pv-multi-agent
```

### Step 3: Install Dependencies

**With uv (recommended):**
```bash
uv sync
```

**With pip:**
```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e .
```

### Step 4: Run the Application

**Streamlit GUI (Recommended):**
```bash
.venv/bin/streamlit run gui.py --server.port 8501
# Open http://localhost:8501
```

**CLI Mode (Ollama required):**
```bash
ollama serve  # In a separate terminal
.venv/bin/python3 -m src.pv_agents
```

---

## Ollama Setup (Optional — for AI Insights)

### Install Ollama
```bash
# Linux/WSL
curl -fsSL https://ollama.com/install.sh | sh

# Start server
ollama serve
```

### Pull Models
```bash
# Lightweight model (1B params, fast)
ollama pull llama3.2:1b

# Better quality model (4B params)
ollama pull gemma4:e4b
```

### Verify
```bash
ollama list
# Should show: llama3.2:1b, gemma4:e4b
```

---

## Cloud Deployment

### Streamlit Cloud (Free Tier)

1. Push your repo to GitHub
2. Go to https://share.streamlit.io
3. Connect repository:
   - **Repo:** `zakusworo/pv-multi-agent`
   - **Branch:** `master`
   - **Main file:** `gui.py`
4. **Add secrets** (Secrets button):
   ```toml
   OPENROUTER_API_KEY = "sk-..."
   ```
5. Click **Deploy** — live in ~2 minutes

### Hugging Face Spaces

1. Go to https://huggingface.co/spaces
2. Click "Create new Space"
3. SDK: **Streamlit**
4. Connect your GitHub repo
5. Add secrets for `OPENROUTER_API_KEY`

### Docker

```bash
# Build
docker build -t sunnyside-ai .

# Run
docker run -p 8501:8501 sunnyside-ai
```

**Dockerfile** (create in project root):
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install -e .
EXPOSE 8501
CMD ["streamlit", "run", "gui.py", "--server.address=0.0.0.0"]
```

---

## Environment Variables

| Variable | Required For | Example |
|----------|-------------|---------|
| `OLLAMA_HOST` | Local Ollama | `http://localhost:11434` |
| `OPENROUTER_API_KEY` | Cloud LLM via OpenRouter | `sk-or-v1-...` |
| `OPENAI_API_KEY` | Cloud LLM via OpenAI | `sk-...` |

---

## Troubleshooting

### "module not found" errors
```bash
# Ensure you're in the project root and venv is active
cd /path/to/pv-multi-agent
source .venv/bin/activate
uv sync
```

### "PDF module not available" in GUI
```bash
# Reinstall fpdf2 and Pillow
uv add fpdf2 pillow
# Or: pip install fpdf2 Pillow
```

### Fonts missing in PDF
The PDF generator automatically searches system font directories. If no DejaVu fonts are found, it falls back to Helvetica. Install DejaVu fonts for best Unicode support:
```bash
# Ubuntu/Debian/WSL
sudo apt-get install fonts-dejavu
```

### "Ollama not running"
```bash
# Check Ollama status
ollama list

# If error, start it:
ollama serve
```

---

## Next Steps After Deployment

1. **Add GitHub topics:** `solar`, `pv`, `multi-agent`, `ai`, `renewable-energy`
2. **Pin the live demo URL** in your README
3. **Share:** LinkedIn, Twitter, r/solar, r/renewableenergy
4. **Add a demo video** (30 seconds showing location select → module pick → PDF download)

---

**Questions?** Open an issue at https://github.com/zakusworo/pv-multi-agent/issues
