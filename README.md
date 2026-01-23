# 🛡️ Trepan - DevSecOps Enforcer & Policy Guardrails

**Trepan** is a local-first security enforcement tool that provides real-time code analysis and policy guardrails for developers. Unlike traditional linters that rely on fragile regex patterns, Trepan uses Abstract Syntax Tree (AST) analysis to understand the *structure* and *logic* of your code.

## 🚀 Features

### Core Capabilities
- **🔍 AST Security Engine** - Structural code analysis using Python's `ast` module for accurate vulnerability detection
- **🔗 Polyglot Taint Analysis** - Track data flow from untrusted sources to dangerous sinks across Python, JavaScript, and TypeScript
- **📦 Supply Chain Sentinel** - Detect typosquatting attacks and vulnerable dependencies in `requirements.txt`, `package.json`
- **🎯 Shadow Red Teamer** - On-demand AI-assisted threat modeling (manual trigger only for privacy)
- **🖥️ Hardware Sentinel** - Intelligent task routing between CPU and GPU for optimal performance
- **🎛️ System Tray Integration** - Background monitoring with minimal resource footprint

### Security Detection
- Hardcoded secrets & API keys
- SQL Injection vulnerabilities
- Cross-Site Scripting (XSS)
- Path Traversal attacks
- Remote Code Execution (RCE)
- Unsafe logging of PII
- Unvalidated user inputs

## 📋 Requirements

```bash
pip install -r requirements.txt
```

## 🏃 Quick Start

```bash
# Run Trepan
python trepan.py

# Run with specific directory watch
python trepan.py --watch /path/to/project
```

## 🏗️ Architecture

```
[ Developer Machine ]
      |
      +--- [ Local File System ] <--- (Watchdog) ---+
      |                                             |
      +--- [ AST Engine ] --------------------------+---> ( Structural Analysis )
      |    (Python 'ast' / Local Policy DB)         |
      |                                             +---> [ Policy Enforcer ]
      |                                             |     (Block/Warn/Inject Context)
      +--- [ Supply Chain Sentinel ] ---------------+
      |
      +--- [ On-Demand Bridge ] ---> (Explicit User Trigger Only)
                |
                v
      [ Secure Cloud Gateway ]
                |
                v
      [ LLM (Llama-3-70b) ] ---> ( Shadow Red Team Analysis )
```

## 📁 Project Structure

| Module | Purpose |
|--------|---------|
| `trepan.py` | Main orchestrator and file watcher |
| `taint_engine.py` | Polyglot security scanning |
| `policy_gatekeeper.py` | Policy enforcement engine |
| `policy_ui.py` | Diff view for user consent |
| `package_sentinel.py` | Supply chain security |
| `hardware_sentinel.py` | CPU/GPU task routing |
| `llm_gateway.py` | Model-agnostic AI integration |
| `system_tray.py` | Background monitoring UI |
| `red_team.py` | AI-assisted threat modeling |

## 🔒 Privacy First

Trepan is designed with privacy as a core principle:
- **Local-First**: All analysis runs locally by default
- **No Data Exfiltration**: Proprietary code never leaves your machine without explicit opt-in
- **GDPR/SOC2 Ready**: Designed for compliance-sensitive environments

## 📜 The Trepan Constitution

Immutable development laws that prevent feature regression:
1. **Law of Visible Trust** - User consent must be explicit
2. **Law of Separation** - Logic lives in modules, not the orchestrator
3. **Law of Audit** - Every Red Team action must be logged
4. **Law of Stability** - No feature removal for "simplicity"

## 🛠️ Configuration

Create a `llm_config.yaml` for AI features:

```yaml
providers:
  groq:
    api_key: ${GROQ_API_KEY}
    model: llama3-70b-8192
```

## 📄 License

MIT License

## 🤝 Contributing

Contributions welcome! Please read the `TREPAN_CONSTITUTION.md` before making changes.
