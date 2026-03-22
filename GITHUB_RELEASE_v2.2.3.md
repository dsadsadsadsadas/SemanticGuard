# 🚀 Trepan v2.2.3 - Power Mode: Multi-Provider Cloud Support

## ⚡ What's New

### Multi-Provider Cloud Support
Power Mode now supports **two cloud providers** for maximum flexibility:

- **OpenRouter**: Access to Claude 3.5 Sonnet, GPT-4o, and 100+ models (~1-2s per audit)
- **Groq**: Ultra-fast inference with Llama 70B models (~0.5-1s per audit)

**Average cloud audit time: ~1.5 seconds** (3-4x faster than local models!)

### Performance Tracking UI
See exactly how fast your audits are with the new "bragging" UI:
- `☁️ Cloud Audit: OpenRouter | ⚡ Latency: 1.45s`
- `💻 Local Audit: Layer 1 + Layer 2`

Real-time performance metrics displayed after every audit.

### Enhanced Configuration
- Provider selection in settings (⚙️ gear icon)
- Separate API keys for each provider stored securely in VS Code SecretStorage
- Easy switching between Local and Power Mode with one click
- Status bar shows active provider: `🛡️ Trepan: Power Mode ⚡ [Groq]`

## 🎯 How to Use Power Mode

1. Click the ⚙️ gear icon in the Trepan Vault panel
2. Select your provider (OpenRouter or Groq)
3. Enter your API key:
   - **OpenRouter**: Get one at [openrouter.ai](https://openrouter.ai)
   - **Groq**: Get one at [groq.com](https://groq.com)
4. Choose your model:
   - OpenRouter: `anthropic/claude-3.5-sonnet`, `openai/gpt-4o-mini`, etc.
   - Groq: `llama3-70b-8192`, `mixtral-8x7b-32768`, etc.
5. Toggle between Local and Power Mode anytime!

## 📊 Performance Comparison

| Mode | Speed | Best For |
|------|-------|----------|
| **Groq (Llama 70B)** | ~0.5-1s | Maximum speed |
| **OpenRouter (Claude 3.5)** | ~1-2s | Best accuracy |
| **Local (Llama 3.1:8b)** | ~4-6s | 100% privacy |
| **Local (DeepSeek R1)** | ~10-15s | Deep reasoning |

## 🏗️ Hybrid Architecture

Power Mode uses a hybrid local+cloud architecture:

```
User saves file
    ↓
Layer 1 (Local - Python Server) - < 0.1s
    ↓
    ├─ REJECT? → Block save immediately
    │
    └─ PASS? → Check mode
              ↓
              ├─ Local Mode → Layer 2 (Local Python) - 4-6s
              │
              └─ Power Mode → Layer 2 (Cloud API) - 1.5s avg
                              ↓
                              ├─ OpenRouter (Claude 3.5)
                              └─ Groq (Llama 70B)
```

**Security**: Layer 1 always runs locally. Only Layer 2 analysis goes to cloud in Power Mode.

## 🔒 Security & Privacy

### Local Mode (Default)
- ✅ 100% privacy - code never leaves your machine
- ✅ Zero cloud dependencies
- ✅ Fully offline-capable
- ✅ War-room ready

### Power Mode (Optional - BYOK)
- ⚠️ Code sent to cloud provider for Layer 2 analysis
- 🔒 API keys stored in VS Code's encrypted SecretStorage
- 🚫 Keys NEVER touch the Python server
- ✅ All API calls happen directly from the extension
- 🛡️ Layer 1 still runs locally (catches obvious violations before cloud)
- 🔄 Toggle on/off anytime

**When to use Power Mode:**
- Prototyping and experimentation
- Non-sensitive codebases
- When speed matters more than privacy
- When you need the best possible accuracy

**When NOT to use Power Mode:**
- Proprietary/confidential code
- Regulated industries (healthcare, finance)
- Air-gapped environments
- When 100% local is required

## 📦 Installation

### Option 1: Install from VSIX
```bash
# Download trepan-gatekeeper-2.2.2.vsix from releases
code --install-extension trepan-gatekeeper-2.2.2.vsix
```

### Option 2: Install from VS Code
1. Download `trepan-gatekeeper-2.2.2.vsix`
2. Open VS Code
3. Extensions → ... → Install from VSIX
4. Select the downloaded file

### Server Setup
```bash
# Start the Trepan server
python start_server.py

# Pull required models (for Local Mode)
ollama pull llama3.1:8b
```

## 🐛 Bug Fixes & Improvements

- Improved status bar updates with provider names
- Enhanced webview UI with dynamic mode display
- Better error handling for cloud API failures
- Fixed mode persistence across VS Code sessions
- Cleaned up codebase and documentation
- Updated .gitignore to exclude build artifacts

## 🎓 Philosophy

> **Privacy-First by Default. Lightning Fast with Power Mode.**
>
> Trepan starts 100% local. Power Mode is opt-in for those who need speed.
> The choice is yours: maximum privacy or maximum speed.

## 📝 Breaking Changes

None. Fully backward compatible with v2.0.x and v2.2.x.

## 🔮 What's Next

- Additional cloud providers (Anthropic Direct, OpenAI Direct)
- Cost tracking and usage analytics
- Performance history graphs
- Custom model fine-tuning support

---

**Full Changelog**: https://github.com/dsadsadsadsadas/Trepan/compare/v2.2.2...v2.2.3

**Need Help?** Open an issue or reach out:
- 📧 jayjaygamingbaron@gmail.com
- 💼 [LinkedIn](https://www.linkedin.com/in/ethan-baron-b77965374/)
- 🐦 [@Jsaaaron91633](https://x.com/Jsaaaron91633)
