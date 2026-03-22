# Trepan V2.0: The Architectural Seatbelt 🛡️

**100% Local. Zero Cloud Leakage. Lightning Fast Security.**

> Most AI tools are **Yes-Men** — they help you ship spaghetti code faster with a smile.
> **Trepan is the No-Man.** It is the mandatory enforcement layer between your AI IDE and your codebase — catching **Context Drift** and **Security Violations** before they become architectural debt you can't pay back.

Built for developers suffering from the **Vibe Coding Hangover**: that moment you realize your AI wrote syntactically perfect, semantically wrong code — and you shipped it.

## 🚀 What's New in V2.0

### ⚡ Layer 1: Lightning Fast Pre-Screener
Trepan V2.0 introduces **Layer 1**, a deterministic pre-screener that catches obvious security violations **instantly** without calling the AI model:

- **< 0.1 second** response time for common violations
- **Zero GPU usage** for deterministic checks
- **20-50x faster** than model inference
- **10 security rules** covering critical vulnerabilities

**Performance Comparison:**
- V1.0: Every file requires 2-5 second model inference
- V2.0: Obvious violations caught in < 0.1 seconds
- Clean code still gets full AI analysis

### 🎨 Sleek Toast Notifications
No more intrusive modal popups! V2.0 features:
- Non-blocking toast notifications in bottom-right corner
- Professional enterprise tool UX
- Auto-dismissing messages
- Seamless integration with Trepan Vault panel

---

## 🎬 See Trepan in Action

![Trepan catching a security violation in VS Code](images/trepan_demo.gif)


---

## 🧠 The Technical "Why" — Semgrep Isn't Enough

Static analysis tools like Semgrep catch **syntax violations**. They cannot catch **intent violations**.

**Context Drift** is the gap between what you *intended* to build and what your AI *actually* built. It happens because:

- **Attention Decay**: As your AI's context window fills up, it loses grip on your architectural decisions made 10,000 tokens ago.
- **Semantic Drift**: The AI generates code that is syntactically valid and passes linting — but violates the *spirit* of your architecture (e.g., using a forbidden pattern, bypassing a security boundary, re-introducing a previously rejected approach).

**Semgrep checks for known bad patterns. Trepan checks for known good intent.**

Trepan performs **Two-Layer Defense**:

### Layer 1: Deterministic Pre-Screener (NEW in V2.0)
Catches obvious violations instantly using regex and AST pattern matching:
- Hardcoded secrets and API keys
- `eval()` with user input (RCE risk)
- `subprocess` with `shell=True` (command injection)
- SQL string concatenation (SQL injection)
- Sensitive data in logs
- And 5 more critical patterns

**Response time: < 0.1 seconds. Zero GPU usage.**

### Layer 2: AI Semantic Analysis
For complex violations that require understanding intent:
- Uses local Llama 3.1:8b or DeepSeek R1
- Compares code against your architectural pillars
- Produces deterministic verdict: `ACCEPT` or `REJECT`
- No hallucinations. No gray zones.

**Response time: 2-5 seconds. Full context understanding.**

---

## 🔒 The 100% Local Promise

Your code is your most valuable asset. **It never leaves your machine.**

- **Zero Cloud Leakage**: No AWS. No OpenAI. No metadata sent to third parties. Ever.
- **Privacy-First**: Powered by local models via [Ollama](https://ollama.com/)
  - **Llama 3.1:8b** - Fast Mode (default)
  - **DeepSeek R1:7b** - Smart Mode (deeper analysis)
- **War-Room Ready**: Fully offline-capable. Your security posture is not dependent on an internet connection or a corporate API's uptime.
- **Layer 1 Bonus**: Most violations caught without even calling the AI model

---

## 📋 Prerequisites — Read This First

Before installing Trepan, ensure the following are in place:

| Requirement | Details |
|---|---|
| **Ollama** | Installed and running locally. [Download here](https://ollama.com/download) |
| **Ollama Model** | `ollama pull llama3.1:8b` (default, recommended for speed) |
| **Optional Model** | `ollama pull deepseek-r1:latest` (for deeper analysis) |
| **Python** | Version **3.8+** |
| **VS Code** | Version **1.74.0+** |

---

## 🚀 Installation

### Option 1: Install from VSIX (Recommended)
```bash
# 1. Download trepan-gatekeeper-2.0.0.vsix from GitHub releases

# 2. Install in VS Code
code --install-extension trepan-gatekeeper-2.0.0.vsix

# Or install via VS Code UI:
# Extensions → ... → Install from VSIX
```

### Option 2: Build from Source
```bash
# 1. Clone the repository
git clone https://github.com/dsadsadsadsadas/Trepan.git
cd Trepan

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Start the local audit server
python start_server.py

# 4. Install the extension from /extension folder
cd extension
vsce package
code --install-extension trepan-gatekeeper-2.0.0.vsix
```

Every file save is now audited in real-time with Layer 1 + Layer 2 defense!

---
## 🎛️ Configuration & Commands

### 🎯 Switching Audit Models

Trepan supports multiple models for different use cases:

- **⚡ Fast Mode (Llama 3.1:8b)**: ~4-6s per audit (after Layer 1). Best for active coding sessions. **Default.**
- **🧠 Smart Mode (DeepSeek R1:7b)**: ~10-15s per audit (after Layer 1). Better reasoning for complex security reviews.
- **🚀 Power Mode (BYOK - Cloud)**: ~1.5s average per audit. Use flagship models like Claude 3.5 Sonnet or GPT-4o via your own cloud API key. **3-4x faster than local!**

**To switch models:**
1. Press `Ctrl+Shift+P` (Windows/Linux) or `Cmd+Shift+P` (Mac)
2. Type `Trepan: Select Audit Model`
3. Choose your preferred mode

The selected model persists across VS Code sessions.

### 🚀 Power Mode (BYOK) - NEW!

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
   - Groq: `llama3-70b-8192`, `mixtral-8x7b-32768`, etc.
5. Trepan tests the connection and saves your credentials securely

**Toggle Power Mode:**
- Click the "Local" button in the Trepan Vault panel to switch to "Power ⚡"
- Or use Command Palette: `Trepan: Toggle Power Mode`
- Status bar shows: `🛡️ Trepan: Power Mode ⚡ [OpenRouter]` or `[Groq]`

**Performance Tracking:**
After each audit, you'll see:
- **Cloud Audit**: `☁️ Cloud Audit: OpenRouter | ⚡ Latency: 1.45s`
- **Local Audit**: `💻 Local Audit: Layer 1 + Layer 2`

**Performance Comparison:**
- **⚡ Cloud Average**: ~1.5 seconds per audit (3-4x faster than local!)
- **OpenRouter (Claude 3.5)**: ~1-2 seconds per audit
- **Groq (Llama 70B)**: ~0.5-1 second per audit (fastest!)
- **Local (Llama 3.1:8b)**: ~4-6 seconds per audit

**Benefits:**
- ⚡ **Blazing fast**: ~1.5s average (3-4x faster than local models)
- 🧠 **Better accuracy**: Flagship models outperform local 8B models
- 💰 **Pay-as-you-go**: Only pay for what you use (~$0.01-0.05 per audit)
- 📊 **Performance tracking**: See provider name and latency in audit results
- 🔄 **Easy switching**: Toggle between Local and Power Mode anytime

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

### ⚙️ CPU/GPU Mode

Switch between GPU (fast) and CPU (battery-saving) inference:

1. Press `Ctrl+Shift+P` (Windows/Linux) or `Cmd+Shift+P` (Mac)
2. Type `Trepan: Toggle CPU/GPU Mode`
3. Choose your preferred mode

The selected mode persists across VS Code sessions.

### 🛡️ Layer 1 Pre-Screener (Automatic)

Layer 1 runs automatically on every save. No configuration needed!

**What Layer 1 Catches:**
- 🔴 **L1-001**: Hardcoded secrets, API keys, passwords
- 🔴 **L1-002**: `eval()` with user input (RCE risk)
- 🔴 **L1-003**: `subprocess` with `shell=True` (command injection)
- 🔴 **L1-008**: `pickle.load()` with user input (arbitrary code execution)
- 🟠 **L1-004**: SQL string concatenation (SQL injection)
- 🟠 **L1-005**: `console.log()` with sensitive data
- 🟠 **L1-006**: `print()` with passwords/tokens
- 🟠 **L1-007**: Error stack traces in API responses
- 🟡 **L1-009**: `assert` for security checks (stripped by optimizer)
- 🟡 **L1-010**: Bare `except:` clauses (silent failures)

**Performance:** < 0.1 seconds, zero GPU usage
---

## ⚡ Project Initialization

Starting a new project? Open the VS Code Command Palette (`Ctrl+Shift+P` / `Cmd+Shift+P`) and run **`Trepan: Initialize Project`**.

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

## 🏗️ Two-Layer Architecture

```
User saves file (Ctrl+S)
    ↓
┌─────────────────────────────────┐
│ LAYER 1: Deterministic Screener │ ← NEW in V2.0
│ • Regex pattern matching         │
│ • AST analysis (Python)          │
│ • < 0.1 second response          │
│ • Zero GPU usage                 │
│ • 10 security rules              │
└─────────────────────────────────┘
    ↓
    ├─ REJECT? → Toast notification ⚡
    │              (Save blocked instantly)
    │
    └─ ACCEPT? → Continue to Layer 2
                     ↓
              ┌──────────────────┐
              │ LAYER 2: AI Model │
              │ • Llama 3.1:8b    │
              │ • DeepSeek R1     │
              │ • Complex logic   │
              │ • 2-5 seconds     │
              │ • Full context    │
              └──────────────────┘
                     ↓
              ACCEPT or REJECT
              (Toast notification)
```

### Performance Metrics

**Example: File with hardcoded API key**
- V1.0: 3.2 seconds (model inference required)
- V2.0: 0.08 seconds (Layer 1 catches it instantly)
- **Improvement: 40x faster**

**Example: Clean code**
- V1.0: 3.2 seconds (model inference)
- V2.0: 3.2 seconds (passes through Layer 1 to model)
- **No penalty for clean code**

---

## 🎓 Philosophy

> *AI should be a skeptical partner, not a yes-man.*
>
> Trepan optimizes for **architectural integrity** — ensuring your project's soul isn't dissolved in the vibe of rapid AI iteration. The model that wrote your feature in 30 seconds didn't read your ADRs. Trepan did.
>
> **Your code stays on your machine. Always.**

---

## ⚠️ IMPORTANT!

Trepan uses local 7-8B parameter models. It catches the majority of common violations but is not perfect. It is a **seatbelt, not an autopilot**. Your judgment still matters.

**Layer 1** provides deterministic guarantees for 10 critical patterns. **Layer 2** provides semantic analysis for complex violations. Together, they form a powerful defense-in-depth strategy.

---

## 📊 What Gets Audited?

### Layer 1 (Instant, Deterministic)
- Hardcoded secrets, API keys, passwords
- Remote code execution risks (`eval()`, `pickle.load()`)
- Command injection (`subprocess` with `shell=True`)
- SQL injection (string concatenation in queries)
- Sensitive data in logs (`console.log()`, `print()`)
- Error stack traces in API responses
- Security anti-patterns (`assert` for auth, bare `except:`)

### Layer 2 (AI-Powered, Semantic)
- Architectural drift from your pillars
- Intent violations (code that works but violates design)
- Complex data flow analysis
- Context-aware security checks
- Custom rule violations from your `.trepan/` pillars

---

## 🎬 User Experience

### When Trepan Blocks a Save

**Old UX (V1.0):**
- ❌ Intrusive modal popup blocks entire screen
- ❌ Must click "OK" to dismiss
- ❌ Interrupts flow completely

**New UX (V2.0):**
- ✅ Sleek toast notification slides up from bottom-right
- ✅ Auto-dismisses after a few seconds
- ✅ Trepan Vault panel shows full violation details
- ✅ Professional enterprise tool feel

### Typical Workflow

1. Write code with your AI assistant
2. Hit `Ctrl+S` to save
3. **Layer 1 checks** (< 0.1s) - catches obvious violations
4. **Layer 2 checks** (2-5s) - semantic analysis if Layer 1 passes
5. **Toast notification** - ACCEPT (green) or REJECT (red)
6. **Vault panel** - detailed reasoning and suggested fixes
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
