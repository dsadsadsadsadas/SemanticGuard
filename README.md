# Trepan: The Architectural Seatbelt 🛡️

**100% Local. Zero Cloud Leakage. Absolute Intent Verification.**

Most AI tools are "Yes-Men"—they help you write spaghetti code faster. Trepan is the "No-Man." It is a local-first architectural linter designed to stop "Architecture Drift" before it hits your codebase. Built for developers who value integrity over just "vibes."

---

## 🔒 The 100% Local Promise

Your code is your most valuable asset. Why send it to the cloud?

- **Zero Cloud Leakage**: Trepan runs entirely on your hardware. No AWS, no OpenAI, no metadata sent to third parties.
- **Privacy-First**: Powered by a local Llama 3.1 (8B) model via Ollama.
- **War-Room Ready**: Designed to work offline. Your security isn't dependent on an internet connection or a corporate API's uptime.

---
## See Trepan in Action
![Trepan catching a security violation in VS Code](images/trepan_demo.gif)
## 🏎️ The Architectural Seatbelt

Trepan doesn't just check syntax; it enforces **Intent**.

### The Guillotine Parser
A production-hardened filter (7/7 stress tests passed) that strips away AI hallucinations and "yap," leaving only a raw ACCEPT or REJECT verdict.

### Closed-Loop Audit
Every AI decision is logged in `Walkthrough.md`. Trepan "looks back" at your Reference Architecture to verify the AI isn't lying about its reasoning.

---

## 📋 The Six Pillars of the Trepan Vault

Trepan enforces architectural consistency and dynamic learning through six core documents in `.trepan/`:

1. **`golden_state.md` (The Whitelist):** Your project's mandatory blueprint. It strictly defines the *only* allowed tech stack and approved structural templates.
2. **`system_rules.md` (The Blacklist):** The security gatekeeper. It strictly defines what is *forbidden* (e.g., vulnerable functions, banned libraries).
3. **`done_tasks.md`:** A log of successfully completed work.
4. **`pending_tasks.md`:** The actionable TODO list for the AI or developer.
5. **`problems_and_resolutions.md`:** A record of technical roadblocks encountered and their exact solutions.
6. **`history_phases.md`:** The project's evolutionary timeline.

**🔄 The Agentic Feedback Loop:**
If a problem occurs leading to an architectural Pivot:
* The failed approach is added to `system_rules.md` (Blacklist).
* The successful solution is added to `golden_state.md` (Whitelist).

---

## 🚀 Quick Start

1. **Start the Server**
   ```bash
   python start_server.py
   ```
2. **Setup Rules**
   - Edit `.trepan/system_rules.md` to define your project's "No-Go" zones.
   - Edit `.trepan/golden_state.md` to define your high-level architecture.
3. **Save and Secure**
   - Every file save is automatically audited against your pillars.
   - Use the VS Code extension to review rejections and apply suggested fixes.

---

## 🏛️ The Cryptographic Vault
Trepan protects your architectural rules with a cryptographic vault in `.trepan/trepan_vault/`. 
- **Meta-Gate Validation**: Changes to your rules (`.trepan/*.md`) are reviewed by a specialized Meta-Gate AI to ensure intent is preserved.
- **SHA-256 Locking**: The entire vault is signed in `.trepan.lock` to prevent unauthorized out-of-band tampering.

---

## 🎓 Philosophy
AI should be a skeptical partner, not a yes-man. Trepan optimizes for **architectural integrity**, ensuring your project's soul isn't lost in the "vibe" of rapid AI iteration.

**Your code stays on your machine. Always.**

## ⚖️ License
This project is licensed under the GNU Affero General Public License v3.0 (AGPLv3).

See the [LICENSE](LICENSE) file for details.

What does this mean?
You are free to use, modify, and distribute this software. However, if you modify this software and offer it as a service over a network (SaaS), you must make your modified source code publicly available under the same license. This protects the open-source nature of Trepan and prevents predatory corporate enclosure.
