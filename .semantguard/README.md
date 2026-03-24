# SemantGuard: The Architectural Seatbelt 🛡️

**100% Local. Zero Cloud Leakage. Absolute Intent Verification.**

Most AI tools are "Yes-Men"—they help you write spaghetti code faster. SemantGuard is the "No-Man." It is a local-first architectural linter designed to stop "Architecture Drift" before it hits your codebase. Built for developers who value integrity over just "vibes."

---

## 🔒 The 100% Local Promise

Your code is your most valuable asset. Why send it to the cloud?

- **Zero Cloud Leakage**: SemantGuard runs entirely on your hardware. No AWS, no OpenAI, no metadata sent to third parties.
- **Privacy-First**: Powered by a local Llama 3.1 (8B) model via Ollama.
- **War-Room Ready**: Designed to work offline. Your security isn't dependent on an internet connection or a corporate API's uptime.

---

## 🏎️ The Architectural Seatbelt

SemantGuard doesn't just check syntax; it enforces **Intent**.

### The Guillotine Parser
A production-hardened filter (7/7 stress tests passed) that strips away AI hallucinations and "yap," leaving only a raw ACCEPT or REJECT verdict.

### Closed-Loop Audit
Every AI decision is logged in `Walkthrough.md`. SemantGuard "looks back" at your Reference Architecture to verify the AI isn't lying about its reasoning.

### Intent-Diff Verification
Before you commit, use the Side-by-Side Review. Compare the AI's explained "Thought" against the actual code diff to ensure the "Why" matches the "What."

---

## 🛠️ Technical Specifications

To ensure SemantGuard's "Seatbelt" engages correctly, verify your local environment matches these production-tested specs.

### 1. The Core Engine (Ollama)
- **Model**: `llama3.1:8b` (Minimum)
- **Quantization**: `Q4_K_M` (Recommended for the best balance of speed and "Architectural Intelligence")
- **VRAM Requirements**: ~5.5GB to 8GB
- **Note**: If you are running on an RTX 4060 Ti or higher, ensure Ollama is utilizing the GPU for sub-100ms response times.

### 2. Python Environment
- **Version**: Python 3.10 or 3.11
- **Key Libraries**:
  - `fastapi` & `uvicorn` (For the high-speed local bridge)
  - `re` (For the production-hardened Guillotine Parser)
  - `aiohttp` (For non-blocking communication with Ollama)

### 3. IDE Integration (VS Code)
- **Extension Host**: VS Code 1.85.0+
- **Communication**: SemantGuard Server defaults to `localhost:8000`. Ensure this port is not blocked by local firewalls.

### 4. Filesystem Structure
Upon initialization, SemantGuard manages the following in your project root:
- `.semantguard/semantguard_vault/` - Holds your cryptographically-signed Architectural Pillar snapshots
- `.semantguard/Walkthrough.md` - The live Audit Ledger and Reference Architecture
- `.semantguard/.semantguard.lock` - SHA-256 signature of the vault (DO NOT EDIT)

---

## 🚀 Quick Start

### Prerequisites
- Python 3.10 or 3.11
- Ollama with llama3.1 model: `ollama pull llama3.1:8b`
- VS Code 1.85.0+

### Installation

1. **Start the SemantGuard Server**
   ```bash
   cd semantguard_server
   python -m uvicorn server:app --reload
   ```
   Wait for the "✅ SemantGuard_Model_V2 ready" message.

2. **Install VS Code Extension**
   - Open VS Code
   - Install the SemantGuard Gatekeeper extension from the marketplace
   - Or install from source: `cd extension && npm install && code --install-extension .`

3. **Initialize Your Project**
   - The `.semantguard` folder auto-creates on first server start
   - Edit `.semantguard/system_rules.md` to define your architectural rules
   - Edit `.semantguard/golden_state.md` to define your project architecture

4. **Test the Seatbelt**
   - Make a code change in your project
   - Save the file
   - Watch SemantGuard evaluate it in real-time
   - Status bar shows: `🛡️ SemantGuard ✅`

---

## 🛠️ The Developer's Audit

When SemantGuard rejects a change, don't just take its word for it:

1. **Open the Side-by-Side Review**
   - Click the ⚙️ Gear Icon in the SemantGuard Vault UI
   - Select "Review Changes vs. Walkthrough"

2. **Compare**
   - Code on the Left | Audit Trail on the Right
   - See exactly which Pillar was violated
   - Understand why the "Guillotine" dropped

3. **Verify**
   - Check if the AI's reasoning matches reality
   - Look for hallucinations or context drift
   - Override if the AI is wrong (you're in control)

---

## 📋 The Six Pillars of the SemantGuard Vault

SemantGuard enforces architectural consistency and dynamic learning through six core documents in `.semantguard/`:

1. **`golden_state.md` (The Whitelist):** Your project's mandatory blueprint.
2. **`system_rules.md` (The Blacklist):** The security gatekeeper.
3. **`done_tasks.md`:** A log of successfully completed work.
4. **`pending_tasks.md`:** The actionable TODO list for the AI or developer.
5. **`problems_and_resolutions.md`:** A record of technical roadblocks encountered and their exact solutions.
6. **`history_phases.md`:** The project's evolutionary timeline.

**🔄 The Agentic Feedback Loop:**
If a problem occurs leading to an architectural Pivot:
* The failed approach is added to `system_rules.md` (Blacklist).
* The successful solution is added to `golden_state.md` (Whitelist).

---

## 🏛️ The Cryptographic Vault
SemantGuard protects your architectural rules with a cryptographic vault in `.semantguard/semantguard_vault/`. 
- **Meta-Gate Validation**: Changes to your rules (`.semantguard/*.md`) are reviewed by a specialized Meta-Gate AI to ensure intent is preserved.
- **SHA-256 Locking**: The entire vault is signed in `.semantguard.lock` to prevent unauthorized out-of-band tampering.

---

## 🎓 Philosophy
AI should be a skeptical partner, not a yes-man. SemantGuard optimizes for **architectural integrity**, ensuring your project's soul isn't lost in the "vibe" of rapid AI iteration.

**Your code stays on your machine. Always.**

| `SemantGuard: Show Server Status` | Check if server is online |
| `SemantGuard: Toggle Airbag On/Off` | Enable/disable save blocking |
| `SemantGuard: Open SemantGuard Ledger` | View Walkthrough.md |
| `SemantGuard: Review Changes vs. Walkthrough` | Side-by-side code + audit view |
| `Ask SemantGuard` | Highlight code and ask for evaluation |

---

## ⚙️ Configuration

Edit VS Code settings (`settings.json`):

```json
{
  "semantguard.serverUrl": "http://127.0.0.1:8000",
  "semantguard.enabled": true,
  "semantguard.timeoutMs": 30000,
  "semantguard.excludePatterns": [
    "**/node_modules/**",
    "**/.git/**",
    "**/*.md",
    "**/*.json"
  ]
}
```

---

## 🐛 Troubleshooting

### Server won't start
- Check Ollama is running: `ollama list`
- Verify llama3.1 is installed: `ollama pull llama3.1:8b`
- Check port 8000 is available
- Ensure Python 3.10 or 3.11 is installed

### Extension not working
- Verify server is running (status bar shows green shield)
- Check server URL in settings matches `http://127.0.0.1:8000`
- Reload VS Code window: Click the ⚙️ Gear Icon → "Reload Window"
- Check firewall isn't blocking localhost:8000

### Saves always blocked
- Check `.semantguard/system_rules.md` for overly strict rules
- Review `Walkthrough.md` to see why saves are rejected
- Temporarily disable: Click the ⚙️ Gear Icon → "Toggle Airbag On/Off"

### Vault Compromised Error
- This means `.semantguard/semantguard_vault/` files or `.semantguard.lock` were manually edited
- To fix: Review your pillar files, then run the "Re-sign Vault" command from the SemantGuard sidebar
- Or use the API: `curl -X POST http://127.0.0.1:8000/resign_vault`

### Slow Response Times
- Check GPU utilization: `nvidia-smi` (should show Ollama using GPU)
- Verify quantization: `ollama show llama3.1:8b` (should show Q4_K_M or similar)
- Ensure VRAM isn't exhausted by other processes

---

## 📚 Documentation

- **CLOSED_LOOP_AUDIT_IMPLEMENTATION.md** - Technical implementation details
- **QUICK_START_CLOSED_LOOP.md** - User-friendly quick start guide
- **ARCHITECTURE_DIAGRAM.md** - Visual system architecture
- **Walkthrough.md** - Your live audit trail (auto-generated)

---

## 🎓 Philosophy

SemantGuard is built on the principle that **AI should be a skeptical partner, not a yes-man**. 

Most AI coding assistants optimize for speed and convenience. SemantGuard optimizes for **architectural integrity**. It's designed for:

- **Security-conscious developers** who can't afford to leak code to the cloud
- **Solo developers** who need a second pair of eyes on architectural decisions
- **Teams** who want to enforce consistent patterns across the codebase
- **High-stakes environments** where architectural drift has real consequences

---

## 🚨 Beta Status

SemantGuard is currently in a **14-day Private Beta**. As a solo developer building in a high-stakes environment, I value your technical feedback above all else.

If SemantGuard catches a drift for you, consider:
- Starring the repo
- Reporting issues on GitHub
- Sharing your use case

---

## ⚖️ License — AGPLv3

This project is licensed under the **GNU Affero General Public License v3.0 (AGPLv3)**.

See the [LICENSE](LICENSE) file for full details.

**What this means in plain English:**
You are free to use, modify, and distribute SemantGuard. However, if you modify it and offer it as a networked service (SaaS), you **must** make your modified source code publicly available under the same license.

This clause exists for one reason: to prevent predatory corporate enclosure of open-source tooling. SemantGuard stays open. Period.


---

## 🛡️ Built with Integrity

SemantGuard was built by a developer who needed it. No VC funding. No cloud dependencies. No compromises on privacy.

**Your code stays on your machine. Always.**
