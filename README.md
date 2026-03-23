# Trepan: The Architectural Seatbelt 🛡️

**Privacy-First by Default. Lightning Fast with Power Mode. Absolute Intent Verification.**

> Most AI tools are **Yes-Men** — they help you ship spaghetti code faster with a smile.
> **Trepan is the No-Man.** It is the mandatory enforcement layer between your AI IDE and your codebase — catching **Context Drift** before it becomes architectural debt you can't pay back.
>
> **Your Choice**: 100% local privacy (default) or 3-4x faster cloud audits with your own API key (Power Mode).

Built for developers suffering from the **Vibe Coding Hangover**: that moment you realize your AI wrote syntactically perfect, semantically wrong code — and you shipped it.

---

## 🎉 What's New in v2.3.0

**Power Mode Enhancements - Production Ready**

- **🎯 V2 Prompt System**: 96% accuracy on adversarial security tests (up from 77%)
  - Zero false positives on safe code patterns
  - Catches hardcoded credentials (AWS keys, API tokens, passwords)
  - Detects sensitive data in logs (passwords, PII, credit cards)
  - Identifies SQL injection via environment variables
  
- **⚡ Llama 4 Scout 17B** (on POWER Mode): Now the default Groq model
  - 2.5x faster than Llama 3.3 70B (30K vs 12K tokens/minute)
  - Same 96% accuracy in security analysis
  - 0.7s average response time
  
- **🎨 Improved Model Selection UI**: 
  - Quick-pick menu with recommended models
  - Custom model input for power users
  - Clear speed/accuracy tradeoffs displayed

- **📁 Full Folder Audit** (v2.3.1): Scan your entire codebase in one command
  - Click the ⚙️ Gear Icon in Trepan Vault UI → "Run Full Workspace Audit"
  - Works in both Local and Power Mode
  - Results displayed in dedicated Output panel

**Upgrade**: Install `trepan-gatekeeper-2.3.1.vsix` and enjoy faster, more accurate security audits.

---

## 🎬 See Trepan in Action (Local Mode)

![Trepan catching a security violation in VS Code](images/trepan_demo.gif)


---

## 🧠 The Technical "Why" — Semgrep Isn't Enough

Static analysis tools like Semgrep catch **syntax violations**. They cannot catch **intent violations**.

**Context Drift** is the gap between what you *intended* to build and what your AI *actually* built. It happens because:

- **Attention Decay**: As your AI's context window fills up, it loses grip on your architectural decisions made 10,000 tokens ago.
- **Semantic Drift**: The AI generates code that is syntactically valid and passes linting — but violates the *spirit* of your architecture (e.g., using a forbidden pattern, bypassing a security boundary, re-introducing a previously rejected approach).

**Semgrep checks for known bad patterns. Trepan checks for known good intent.**

Trepan performs **Semantic Auditing** — using a local LLM to compare every code change against your declared architectural pillars and producing a **Deterministic Verification** verdict: `ACCEPT` or `REJECT`. No hallucinations. No gray zones.

---

## 🔒 Privacy-First Architecture

Your code is your most valuable asset. **You choose where it goes.**

### 🏠 Local Mode (Default)
- **Zero Cloud Leakage**: No AWS. No OpenAI. No metadata sent to third parties. Ever.
- **100% Privacy**: Powered by local **Llama 3.1 (8B)** model via [Ollama](https://ollama.com/)
- **War-Room Ready**: Fully offline-capable. Your security posture is not dependent on an internet connection
- **Audit Time**: ~4-6 seconds per save

### ⚡ Power Mode (Optional - BYOK)
- **Blazing Fast**: ~1.5s average audit time (3-4x faster!)
- **Your API Key**: Bring your own OpenRouter or Groq key
- **Your Control**: Toggle on/off anytime. Keys stored securely in VS Code
- **Trade-off**: Code sent to cloud provider for faster analysis
- **Best For**: Non-sensitive projects, prototyping, when speed matters

**The Choice is Yours**: Maximum privacy or maximum speed. Trepan works both ways.

---

## 📋 Prerequisites

### For Power Mode (Cloud) - Minimal Setup
If you're using Power Mode exclusively, you only need:

| Requirement | Details |
|---|---|
| **VS Code** | For the extension-based audit workflow |
| **Cloud API Key** | OpenRouter or Groq account |

**That's it!** No Ollama, no Python server, no local models. Just install the extension and configure your API key.

### For Local Mode - Full Setup
If you want 100% local privacy, you'll need:

| Requirement | Details |
|---|---|
| **Ollama** | Installed and running locally. [Download here](https://ollama.com/download) |
| **Ollama Model** | `ollama pull llama3.1:8b` (or your preferred 8B-class model) |
| **Python** | Version **3.8+** |
| **VS Code** | For the extension-based audit workflow |

**Note**: Ollama is only required if you want to use Local Mode. Power Mode works without any local setup.
| **Extension** |[Here](https://marketplace.visualstudio.com/items?itemName=trepansec.trepan-gatekeeper#review-details)| 

---

## 🚀 Installation

### Quick Start: Power Mode Only (No Local Setup)

Want to get started in 60 seconds? Use Power Mode:

```bash
# 1. Clone the repository
git clone https://github.com/dsadsadsadsadas/Trepan
cd trepan

# 2. Install the VS Code Extension
cd extension
code --install-extension trepan-gatekeeper-2.3.1.vsix
```

**That's it!** Configure your cloud API key in the extension and start auditing. No Ollama, no Python server needed.

### Full Setup: Local Mode (100% Privacy)

Want 100% local privacy? Follow the complete setup:

```bash
# 1. Clone the repository
git clone https://github.com/dsadsadsadsadas/Trepan
cd trepan

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Start the local audit server
python start_server.py

# 4. Install the VS Code Extension
cd extension
code --install-extension trepan-gatekeeper-2.2.3.vsix
```

Then install the **Trepan VS Code Extension** from the Marketplace (or from the `/extension` folder). Every file save is now audited in real-time.

---
## Buttons !

**🎯 Local Mode - Switching Audit Models**

For Local Mode (100% privacy), switch between different local models:

- **⚡ Fast Mode (Llama 3.1:8b)**: ~4-6s per audit. Best for active coding sessions.
- **🧠 Smart Mode (DeepSeek-R1:7b)**: ~10-15s per audit. Better reasoning for security reviews.

To switch local models:
1. Click the ⚙️ Gear Icon in the Trepan Vault UI
2. Select your preferred model from the dropdown in the "Engine & API" section

The selected model persists across VS Code sessions.

**Note:** All configuration is now centralized in the Settings UI (⚙️ Gear Icon).

---

**🚀 Power Mode - Cloud API Configuration (UI Panel)**

For Power Mode (cloud-based, 3-4x faster), configure through the Trepan UI panel:

**Setup via UI Panel:**
1. Open the **Trepan Vault panel** in VS Code sidebar
2. Click the **⚙️ gear icon** to configure Power Mode
3. Select your provider (OpenRouter or Groq)
4. Enter your API key and choose a model
5. Click the **"Local"** button to toggle to **"Power ⚡"** mode

**Switching Models in Power Mode:**
- Click the **⚙️ gear icon** again to change provider or model
- Select "Model" from the settings menu
- Choose from preset models or enter a custom model ID

**Supported Providers:**
- **OpenRouter**: Access to Claude 3.5 Sonnet, GPT-4o, and 100+ models
- **Groq**: Ultra-fast inference with Llama models (up to 10x faster)

**Performance:**
- **⚡ Cloud Average**: ~1.5 seconds per audit (3-4x faster than local!)
- **OpenRouter (Claude 3.5)**: ~1-2 seconds per audit
- **Groq (Llama4 Scout)**: ~0.5-1 second per audit (fastest!)
- **Local (Llama 3.1:8b)**: ~4-6 seconds per audit

**Note:** All configuration is now centralized in the Settings UI (⚙️ Gear Icon).

**🚀 Power Mode (BYOK) - Bring Your Own Key**

Want maximum speed without sacrificing accuracy? Configure Power Mode with your own cloud API key:

**Supported Providers:**
- **OpenRouter**: Access to Claude 3.5 Sonnet, GPT-4o, and 100+ models
- **Groq**: Ultra-fast inference with Llama models (up to 10x faster)

**Setup:**
1. Click the ⚙️ gear icon in the Trepan Vault panel (VS Code sidebar)
2. Select your provider (OpenRouter or Groq)
3. Enter your API key:
   - OpenRouter: Get one at [openrouter.ai](https://openrouter.ai)
   - Groq: Get one at [groq.com](https://groq.com)
4. Choose a model:
   - OpenRouter: `anthropic/claude-3.5-sonnet`, `openai/gpt-4o-mini`, etc.
   - Groq: `meta-llama/llama-4-scout-17b-16e-instruct`, `llama-3.3-70b-versatile`, etc.
5. Trepan tests the connection and saves your credentials securely

**Toggle Power Mode:**
- Click the ⚙️ Gear Icon in the Trepan Vault panel
- Use the "Mode Selection" section to switch between Local and Cloud Power Mode

**Performance:**
- **⚡ Cloud Average**: ~1.5 seconds per audit (3-4x faster than local!)
- **OpenRouter (Claude 3.5)**: ~1-2 seconds per audit
- **Groq (Llama 70B)**: ~0.5-1 second per audit (fastest!)
- **Local (Llama 3.1:8b)**: ~4-6 seconds per audit

**Benefits:**
- ⚡ **Blazing fast**: ~1.5s average (3-4x faster than local models)
- 🧠 **Better accuracy**: Flagship models outperform local 8B models
- 💰 **Pay-as-you-go**: Only pay for what you use (~$0.01-0.05 per audit)
- 📊 **Performance tracking**: See provider name and latency in audit results

**Security Note:**
- ⚠️ Your code is sent to the cloud provider's API
- 🔒 API keys stored securely in VS Code's encrypted SecretStorage
- 🚫 Keys NEVER touch the Python server
- ✅ All API calls happen directly from the extension
- 🛡️ Layer 1 still runs locally (catches obvious violations before cloud)

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

**Switch CPU/GPU**

To switch between CPU and GPU modes:
1. Click the ⚙️ Gear Icon in the Trepan Vault UI
2. Select "Switch CPU/GPU" from the settings menu
3. Choose your preferred mode

The selected mode persists across VS Code sessions.
---

## ⚡ Project Initialization

Starting a new project? Click the ⚙️ Gear Icon in the Trepan Vault UI and select **"Initialize Project"**.

Choose a mode that matches your context:

| Mode | Target | Enforces |
|---|---|---|
| 🚀 **Solo-Indie (The Speedster)** | Rapid solo development | Function size, nesting depth, clean naming |
| 🏗️ **Clean-Layers (The Architect)** | Long-term scalability | Separation of concerns, DI, interface-driven design |
| 🛡️ **Secure-Stateless (The Fortress)** | Mission-critical security | Input sanitization, stateless ops, encryption-at-rest, audit logging |

---

## 📁 The Six Pillars of the Trepan Vault

All architectural state lives in the **`.trepan/`** directory — a living, versioned brain for your project:

| Pillar | Role |
|---|---|
| **`golden_state.md`** (The Whitelist) | Your mandatory blueprint. Defines the *only* allowed tech stack and approved structural patterns. |
| **`system_rules.md`** (The Blacklist) | The security gatekeeper. Defines what is *forbidden*: vulnerable functions, banned libraries, rejected patterns. |
| **`done_tasks.md`** | A log of successfully completed work. The AI's memory of what's done. |
| **`pending_tasks.md`** | The active TODO list for the AI or developer. |
| **`problems_and_resolutions.md`** | A record of every technical roadblock and its exact resolution. |
| **`history_phases.md`** | The project's evolutionary timeline. |

> **🔄 The Agentic Feedback Loop**
>
> When a problem causes an architectural pivot, Trepan drives the learning:
> - The **failed approach** is written into `system_rules.md` (Blacklist).
> - The **successful solution** is written into `golden_state.md` (Whitelist).
>
> Your AI never makes the same architectural mistake twice.

---

## 🏛️ The Cryptographic Vault

Trepan protects your pillars with a cryptographic enforcement layer stored in `.trepan/trepan_vault/`.

- **Meta-Gate Validation**: Any change to your rules (`.trepan/*.md`) is reviewed by a specialized Meta-Gate AI to ensure that intent — not just syntax — is preserved. Rules cannot be silently weakened.
- **SHA-256 Locking**: The entire vault is signed in `.trepan.lock`. Unauthorized out-of-band tampering is detectable immediately.

Your architectural decisions are as immutable as you want them to be.

---

## 🎓 Philosophy

> *AI should be a skeptical partner, not a yes-man.*
>
> Trepan optimizes for **architectural integrity** — ensuring your project's soul isn't dissolved in the vibe of rapid AI iteration. The model that wrote your feature in 30 seconds didn't read your ADRs. Trepan did.
>
> **Your code stays on your machine. Always.**

---
## IMPORTANT !
Trepan uses a local 7-8B parameter model. It catches the majority of common violations but is not perfect. It is a seatbelt, not an autopilot. Your judgment still matters.
## 📞 Are You One of the First 100 Users?

I'd love to hear if Trepan caught a drift for you. Open an issue or reach out directly:
- **Gmail**: jayjaygamingbaron@gmail.com
- **LinkedIn**: [Ethan Baron](https://www.linkedin.com/in/ethan-baron-b77965374/)
- **X (Twitter)**: [@Jsaaaron91633](https://x.com/Jsaaaron91633)

---

## ⚖️ License — AGPLv3

This project is licensed under the **GNU Affero General Public License v3.0 (AGPLv3)**.

See the [LICENSE](LICENSE) file for full details.

**What this means in plain English:**
You are free to use, modify, and distribute Trepan. However, if you modify it and offer it as a networked service (SaaS), you **must** make your modified source code publicly available under the same license.

This clause exists for one reason: to prevent predatory corporate enclosure of open-source tooling. Trepan stays open. Period.
