# 📋 PENDING_TASKS.md — Trepan Project

## 🛡️ VS Code Airbag Extension (Updated 2026-02-26)

### Server
- [ ] Fix model loading — resolve PEFT/transformers version conflict in conda env
- [ ] Upload `Trepan_Model_V2` to HuggingFace for remote download support
- [ ] Add `/metrics` endpoint (token latency, request count, hit/reject ratio)

### Extension (VS Code — onWillSaveTextDocument approach)
- [x] `extension/package.json` — VS Code extension manifest (2026-02-26)
- [x] `extension/extension.js` — Airbag save interceptor (2026-02-26)
- [x] Added "Ask Trepan" context menu command to extension (2026-02-26)
- [x] Registered "Trepan Architect" sidebar in `package.json` (2026-02-26)
- [x] Implemented Shadow Vault & Meta-Gate `/evaluate_pillar` routing (2026-02-26)
- [x] Implemented "Trepan Architect" sidebar UI logic in `extension.js` (2026-02-26)
- [x] Fixed dead "See Reasoning" button — now toggles AI thought hidden/visible in sidebar (2026-02-27)
- [ ] Test install: `Extensions: Install from VSIX` or press F5 in extension dev host
- [ ] Create `.trepan/problems_and_resolutions.md` pillar file
- [ ] Implement REJECT history log → `.trepan/drift_log.jsonl`
- [x] Add an icon set (16x16, 48x48, 128x128 PNG) (2026-02-26)

### Dataset & Model
- [ ] Expand training dataset with more ACCEPT edge cases (currently biased toward REJECT)
- [ ] Fine-tune a second epoch with the expanded dataset
- [ ] Benchmark: measure P50/P95 inference latency on GPU vs CPU fallback

## 🔮 Polyglot Expansion (Phase 5 — Ongoing)
- [ ] Full AST support for Rust via `tree-sitter`
- [ ] Full AST support for Go via `tree-sitter`
- [ ] Full AST support for Java via `tree-sitter`

## 🏢 Enterprise Edition
- [ ] Centralized policy management server (team-wide golden state)
- [ ] Fleet Learning: propagate confirmed vulnerability fixes across projects

---

## ✅ Recently Completed
- [x] Generated extension icons via `generate_icons.py` — 4 sizes in `extension/icons/` (2026-02-26)
- [x] Built `trepan_server/` FastAPI inference backend (2026-02-26)
- [x] Built `extension/` Antigravity IDE interceptor (2026-02-26)
- [x] Built `trepan_workspace_init.py` workspace bootstrapper (2026-02-26)
- [x] Built `start_server.py` convenience launcher (2026-02-26)
- [x] `.trepan/` Workspace initialized with 4 pillar files (2026-02-26)
- [x] Made Shadow Vault physically visible at project root (`trepan_vault`) and auto-sync on start (2026-02-26)
- [x] Trained `Trepan_Model_V2` LoRA adapter (2026-02-25)
- [x] Implemented `drift_engine.py` architecture drift detector (Phase TR-02)
- [x] Implemented `taint_engine.py` polyglot taint analysis (Phase 5)
- [x] Implemented `package_sentinel.py` supply chain security (Phase 9)
- [x] Built `llm_gateway.py` multi-provider LLM adapter
