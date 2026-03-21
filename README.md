# Trepan: The Architectural Seatbelt 🛡️

**100% Local. Zero Cloud Leakage. Absolute Intent Verification.**

> Most AI tools are **Yes-Men** — they help you ship spaghetti code faster with a smile.
> **Trepan is the No-Man.** It is the mandatory enforcement layer between your AI IDE and your codebase — catching **Context Drift** before it becomes architectural debt you can't pay back.

Built for developers suffering from the **Vibe Coding Hangover**: that moment you realize your AI wrote syntactically perfect, semantically wrong code — and you shipped it.

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

Trepan performs **Semantic Auditing** — using a local LLM to compare every code change against your declared architectural pillars and producing a **Deterministic Verification** verdict: `ACCEPT` or `REJECT`. No hallucinations. No gray zones.

---

## 🔒 The 100% Local Promise

Your code is your most valuable asset. **It never leaves your machine.**

- **Zero Cloud Leakage**: No AWS. No OpenAI. No metadata sent to third parties. Ever.
- **Privacy-First**: Powered by a local **Llama 3.1 (8B)** model via [Ollama](https://ollama.com/).
- **War-Room Ready**: Fully offline-capable. Your security posture is not dependent on an internet connection or a corporate API's uptime.

---

## 📋 Prerequisites — Read This First

Before installing Trepan, ensure the following are in place:

| Requirement | Details |
|---|---|
| **Ollama** | Installed and running locally. [Download here](https://ollama.com/download) |
| **Ollama Model** | `ollama pull llama3.1:8b` (or your preferred 8B-class model) |
| **Python** | Version **3.8+** |
| **VS Code** | For the extension-based audit workflow |

---

## 🚀 Installation

```bash
# 1. Clone the repository
git clone https://github.com/your-username/trepan.git
cd trepan

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Start the local audit server
python start_server.py
```

Then install the **Trepan VS Code Extension** from the Marketplace (or from the `/extension` folder). Every file save is now audited in real-time.

---

## 🎯 Switching Audit Models

Trepan supports multiple models for different use cases:

- **⚡ Fast Mode (Llama 3.1:8b)**: ~5-7s per audit. Best for active coding sessions.
- **🧠 Smart Mode (DeepSeek-R1:7b)**: ~12-18s per audit. Better reasoning for security reviews.

To switch models:
1. Press `Ctrl+Shift+P` (Windows/Linux) or `Cmd+Shift+P` (Mac)
2. Type `Trepan: Select Audit Model`
3. Choose your preferred mode

The selected model persists across VS Code sessions.

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

## 🎓 Philosophy

> *AI should be a skeptical partner, not a yes-man.*
>
> Trepan optimizes for **architectural integrity** — ensuring your project's soul isn't dissolved in the vibe of rapid AI iteration. The model that wrote your feature in 30 seconds didn't read your ADRs. Trepan did.
>
> **Your code stays on your machine. Always.**

---

## 📞 Are You One of the First 30 Cloners?

I'd love to hear if Trepan caught a drift for you. Open an issue or reach out directly:

- **LinkedIn**: [Ethan Baron](https://www.linkedin.com/in/ethan-baron-b77965374/)
- **X (Twitter)**: [@Jsaaaron91633](https://x.com/Jsaaaron91633)

---

## ⚖️ License — AGPLv3

This project is licensed under the **GNU Affero General Public License v3.0 (AGPLv3)**.

See the [LICENSE](LICENSE) file for full details.

**What this means in plain English:**
You are free to use, modify, and distribute Trepan. However, if you modify it and offer it as a networked service (SaaS), you **must** make your modified source code publicly available under the same license.

This clause exists for one reason: to prevent predatory corporate enclosure of open-source tooling. Trepan stays open. Period.
