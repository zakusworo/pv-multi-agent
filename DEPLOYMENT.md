# GitHub Deployment Guide

## Quick Setup (5 minutes)

### Step 1: Create GitHub Repository

1. Go to https://github.com/new
2. Repository name: `pv-multi-agent`
3. Description: "Multi-Agent AI System for PV Solar Simulation with GUI and Cloud LLM Support"
4. Visibility: Public (recommended) or Private
5. **DO NOT** initialize with README/.gitignore (we already have these)
6. Click "Create repository"

### Step 2: Connect Local Repo to GitHub

```bash
cd /home/zakusworo/pv-multi-agent

# Add GitHub remote
git remote add origin https://github.com/zakusworo/pv-multi-agent.git

# Verify remote
git remote -v

# Push to GitHub
git push -u origin master
```

### Step 3: Verify on GitHub

Visit: https://github.com/zakusworo/pv-multi-agent

You should see all files committed.

---

## Alternative: SSH Authentication (Recommended for frequent pushes)

```bash
# Generate SSH key (if you don't have one)
ssh-keygen -t ed25519 -C "your.email@example.com"

# Add to GitHub
# 1. Copy the key: cat ~/.ssh/id_ed25519.pub
# 2. Go to https://github.com/settings/keys
# 3. Click "New SSH key" and paste

# Add remote with SSH
git remote add origin git@github.com:zakusworo/pv-multi-agent.git

# Push
git push -u origin master
```

---

## Deploy GUI to Cloud (Optional)

### Option A: Hugging Face Spaces (Free, Easy)

1. Go to https://huggingface.co/spaces
2. Click "Create new Space"
3. Name: `pv-multi-agent`
4. SDK: `Streamlit`
5. Visibility: Public
6. Click "Create Space"

7. In terminal:
```bash
# Install Hugging Face Hub CLI
pip install huggingface_hub

# Login
huggingface-cli login

# Clone your space
git clone https://huggingface.co/spaces/zakusworo/pv-multi-agent
cd pv-multi-agent

# Copy files from your project
cp /home/zakusworo/pv-multi-agent/gui.py .
cp /home/zakusworo/pv-multi-agent/pyproject.toml .
cp /home/zakusworo/pv-multi-agent/pv_agents_cloud.py .
# ... copy other needed files

# Add requirements
echo "streamlit
pvlib
pandas
numpy
ollama
openai
plotly
openmeteo-requests
niquests" > requirements.txt

# Commit and push
git add .
git commit -m "Deploy PV Multi-Agent GUI"
git push
```

### Option B: Streamlit Cloud (Free)

1. Go to https://streamlit.io/cloud
2. Sign in with GitHub
3. Click "New app"
4. Select your `pv-multi-agent` repository
5. Main file path: `gui.py`
6. Click "Deploy!"

### Option C: Render/Railway (Free tier)

Similar process - connect GitHub repo and deploy.

---

## Usage After Deployment

### Local GUI
```bash
cd /home/zakusworo/pv-multi-agent
streamlit run gui.py
# Opens at http://localhost:8501
```

### Cloud LLM (OpenRouter)
```bash
export OPENROUTER_API_KEY=sk-or-...
python pv_agents_cloud.py --provider openrouter --model qwen/qwen-3.6-plus
```

**Note:** `qwen/qwen-3.6-plus` is only available on OpenRouter (cloud). For local Ollama, use `gemma2:9b` or `qwen2.5:7b`.

### Local LLM (Ollama)
```bash
ollama pull gemma2:9b
python pv_agents_cloud.py --provider ollama --model gemma2:9b
```

**Note:** Ollama uses simplified model names. The cloud equivalent of `gemma2:9b` is `google/gemma-2-9b-it` on OpenRouter.

---

## Sharing Your Project

### Add to Your Resume/Portfolio

```
🌞 Multi-Agent PV System Calculator
GitHub: https://github.com/zakusworo/pv-multi-agent

- Multi-agent AI architecture with 6 specialized agents
- Hybrid AI + Physics: LLM reasoning + PVlib IEEE calculations
- Web GUI deployed on Streamlit Cloud
- Validated against industry-standard PVsyst (PR: 72.9% vs 72.8%)
- Tech stack: Python, PVlib, Streamlit, Ollama, OpenAI API
```

### Demo Video Script (for LinkedIn/Twitter)

1. Show GUI landing page
2. Select location (Bandung, Indonesia)
3. Adjust system capacity slider
4. Show real-time charts updating
5. Download report
6. Show CLI with cloud LLM output
7. Mention: "Validated against PVsyst!"

---

## Troubleshooting

### "Permission denied (publickey)"
```bash
# Test SSH connection
ssh -T git@github.com

# If fails, re-add SSH key to GitHub
```

### "Repository not found"
```bash
# Check remote URL
git remote -v

# Fix if needed
git remote set-url origin https://github.com/zakusworo/pv-multi-agent.git
```

### Large file errors
```bash
# Check file sizes
git ls-files -s | sort -rn | head

# If uv.lock is too large, add to .gitignore
echo "uv.lock" >> .gitignore
git rm --cached uv.lock
git commit -m "Remove uv.lock from tracking"
```

---

## Next Steps

1. ✅ Push to GitHub
2. ✅ Deploy GUI to Streamlit Cloud / Hugging Face
3. 📝 Add license file (MIT recommended)
4. 🏷️ Add GitHub topics: `solar`, `pv`, `multi-agent`, `ai`, `renewable-energy`
5. 📊 Add screenshot to README
6. 🔗 Share on LinkedIn, Twitter, Reddit (r/solar, r/renewableenergy)

---

**Questions?** Open an issue on GitHub or contact: your.email@example.com
