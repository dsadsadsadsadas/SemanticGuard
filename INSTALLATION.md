# 🛡️ SemantGuard Installation Guide

## Quick Start

SemantGuard is **lightweight by design** - the repository contains only the code (~50MB). Models are downloaded separately based on your choice.

---

## Prerequisites

- Python 3.8+
- Node.js 16+ (for extension development)
- VS Code 1.74.0+

---

## Installation Options

### Option 1: Local Mode (Privacy-First) 🔒

**Best for:** Enterprise, sensitive codebases, offline development

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/semantguard.git
   cd semantguard
   ```

2. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Install Ollama** (handles model downloads automatically)
   ```bash
   # macOS/Linux
   curl -fsSL https://ollama.com/install.sh | sh
   
   # Windows
   # Download from: https://ollama.com/download
   ```

4. **Pull the model** (one-time, ~4.7GB)
   ```bash
   ollama pull llama3.1:8b
   # OR for better performance
   ollama pull deepseek-coder:6.7b
   ```

5. **Start the server**
   ```bash
   python start_server.py
   ```

6. **Install VS Code extension**
   ```bash
   code --install-extension extension/semantguard-gatekeeper-2.3.8.vsix
   ```

---

### Option 2: Power Mode (Cloud-Based) ⚡

**Best for:** Rapid prototyping, personal projects, speed-critical workflows

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/semantguard.git
   cd semantguard
   ```

2. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Start the server**
   ```bash
   python start_server.py
   ```

4. **Install VS Code extension**
   ```bash
   code --install-extension extension/semantguard-gatekeeper-2.3.8.vsix
   ```

5. **Configure API Key**
   - Open VS Code
   - Click the SemantGuard icon in the sidebar
   - Click ⚙️ Settings
   - Select "Configure API Key"
   - Choose provider:
     - **Groq** (fastest, free tier available)
     - **OpenRouter** (most model options)
   - Enter your API key

**Get API Keys:**
- Groq: https://console.groq.com/keys
- OpenRouter: https://openrouter.ai/keys

---

## Repository Size

- **Code only:** ~50MB
- **With Ollama model (optional):** +4.7GB (downloaded separately)
- **Total clone size:** ~50MB

**Note:** Model files are NOT included in the Git repository. They are downloaded on-demand when you choose Local Mode.

---

## What Gets Downloaded?

### Minimal Install (Power Mode)
```
semantguard/
├── extension/              # VS Code extension (~2MB)
├── semantguard_server/     # Python server (~5MB)
├── requirements.txt        # Python dependencies
└── start_server.py         # Server launcher
```
**Total:** ~50MB

### Full Install (Local Mode)
```
semantguard/
├── extension/              # VS Code extension (~2MB)
├── semantguard_server/     # Python server (~5MB)
├── requirements.txt        # Python dependencies
├── start_server.py         # Server launcher
└── ~/.ollama/models/       # Models (downloaded separately)
    └── llama3.1:8b         # ~4.7GB (one-time download)
```
**Total:** ~50MB + 4.7GB (models stored in Ollama's directory, not in repo)

---

## Verify Installation

```bash
# Check server is running
curl http://127.0.0.1:8001/health

# Expected response:
# {"status": "healthy", "mode": "local" or "cloud"}
```

---

## Troubleshooting

### "Repository too large to clone"
- The repository itself is only ~50MB
- If you see a large size, you may be cloning an old version with model files
- Use: `git clone --depth 1` for a shallow clone

### "Ollama model download is slow"
- Models are large (4-5GB) and download once
- Download happens outside the Git repository
- Stored in: `~/.ollama/models/` (Linux/Mac) or `%USERPROFILE%\.ollama\models\` (Windows)

### "Server won't start"
```bash
# Check Python version
python --version  # Should be 3.8+

# Check dependencies
pip install -r requirements.txt

# Check Ollama (Local Mode only)
ollama list  # Should show llama3.1:8b or deepseek-coder
```

---

## Uninstallation

### Remove SemantGuard
```bash
# Remove repository
rm -rf semantguard/

# Remove VS Code extension
code --uninstall-extension trepansec.semantguard-gatekeeper
```

### Remove Ollama Models (Optional)
```bash
# List models
ollama list

# Remove specific model
ollama rm llama3.1:8b

# Remove all Ollama data
rm -rf ~/.ollama/  # Linux/Mac
# OR
rmdir /s %USERPROFILE%\.ollama\  # Windows
```

---

## Next Steps

- Read the [README](README.md) for feature overview
- Check [ARCHITECTURE.md](docs/ARCHITECTURE.md) for technical details
- Join our [Discord](https://discord.gg/semantguard) for support

---

**Made with 🛡️ by developers, for developers**
