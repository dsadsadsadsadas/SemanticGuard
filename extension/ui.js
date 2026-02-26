/**
 * 🛡️ Trepan Gatekeeper — UI Module
 * Handles all visual feedback: ACCEPT flash, REJECT modal, checking badge.
 */

// ─── Checking State (spinner badge) ────────────────────────────────────────

export function showCheckingState(input) {
    removeExisting("trepan-badge");
    const badge = document.createElement("div");
    badge.id = "trepan-badge";
    badge.className = "trepan-badge trepan-badge--checking";
    badge.innerHTML = `<span class="trepan-spinner"></span> Trepan checking…`;
    input.closest("form, .chat-input-wrapper, .input-wrapper")
        ?.appendChild(badge) ?? document.body.appendChild(badge);
}

export function clearCheckingState(_input) {
    removeExisting("trepan-badge");
}

// ─── ACCEPT Flash ──────────────────────────────────────────────────────────

export function showAcceptState(input) {
    removeExisting("trepan-badge");
    const badge = document.createElement("div");
    badge.id = "trepan-badge";
    badge.className = "trepan-badge trepan-badge--accept";
    badge.innerHTML = `✅ Gatekeeper: ACCEPTED`;
    const container = input.closest("form, .chat-input-wrapper, .input-wrapper");
    (container ?? document.body).appendChild(badge);
    setTimeout(() => badge.remove(), 1800);
}

// ─── REJECT Modal ──────────────────────────────────────────────────────────

export function showRejectState(decision, input, originalPrompt) {
    removeExisting("trepan-modal-overlay");

    const scorePercent = Math.round(decision.drift_score * 100);
    const scoreColor = decision.drift_score >= 0.7 ? "#ff4f4f"
        : decision.drift_score >= 0.4 ? "#ffaa00"
            : "#4ade80";

    const overlay = document.createElement("div");
    overlay.id = "trepan-modal-overlay";
    overlay.innerHTML = `
    <div class="trepan-modal" role="dialog" aria-modal="true" aria-label="Trepan Drift Warning">
      <div class="trepan-modal__header">
        <span class="trepan-modal__icon">🚨</span>
        <h2 class="trepan-modal__title">Context Drift Detected</h2>
      </div>

      <div class="trepan-modal__score-row">
        <span class="trepan-modal__score-label">Drift Score</span>
        <div class="trepan-modal__score-bar-wrap">
          <div class="trepan-modal__score-bar"
               style="width: ${scorePercent}%; background: ${scoreColor};"
               title="${decision.drift_score}"></div>
        </div>
        <span class="trepan-modal__score-value" style="color:${scoreColor}">
          ${scorePercent}%
        </span>
      </div>

      <div class="trepan-modal__section">
        <h3>Your Prompt</h3>
        <pre class="trepan-modal__code trepan-modal__code--prompt">${escHtml(originalPrompt)}</pre>
      </div>

      <div class="trepan-modal__section">
        <h3>Gatekeeper Reasoning</h3>
        <pre class="trepan-modal__code">${escHtml(decision.raw_output)}</pre>
      </div>

      <div class="trepan-modal__footer">
        <button id="trepan-btn-dismiss"  class="trepan-btn trepan-btn--secondary">
          ✏️ Modify Prompt
        </button>
        <button id="trepan-btn-rules"    class="trepan-btn trepan-btn--secondary">
          📋 Update .trepan/ Rules
        </button>
        <button id="trepan-btn-override" class="trepan-btn trepan-btn--danger">
          ⚠️ Override & Send Anyway
        </button>
      </div>
    </div>
  `;

    document.body.appendChild(overlay);
    overlay.querySelector(".trepan-modal").classList.add("trepan-modal--enter");

    // Dismiss — let user retype
    overlay.querySelector("#trepan-btn-dismiss").addEventListener("click", () => {
        overlay.remove();
        input.focus();
    });

    // Open the rules file via Antigravity API (best-effort)
    overlay.querySelector("#trepan-btn-rules").addEventListener("click", () => {
        try {
            window.__antigravity?.openFile?.(".trepan/system_rules.md");
            window.__antigravity?.openFile?.(".trepan/golden_state.md");
        } catch { }
        overlay.remove();
        input.focus();
    });

    // Override — send the prompt regardless (user's explicit choice)
    overlay.querySelector("#trepan-btn-override").addEventListener("click", () => {
        overlay.remove();
        input.dispatchEvent(
            new KeyboardEvent("keydown", { key: "Enter", code: "Enter", bubbles: true, cancelable: false })
        );
    });

    // Close on overlay click outside modal
    overlay.addEventListener("click", (e) => {
        if (e.target === overlay) { overlay.remove(); input.focus(); }
    });

    // ESC to dismiss
    document.addEventListener("keydown", function escHandler(e) {
        if (e.key === "Escape") { overlay.remove(); input.focus(); document.removeEventListener("keydown", escHandler); }
    });
}

// ─── Helpers ───────────────────────────────────────────────────────────────

function removeExisting(id) {
    document.getElementById(id)?.remove();
}

function escHtml(str) {
    return str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}
