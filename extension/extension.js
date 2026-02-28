"use strict";

/**
 * 🛡️ Trepan Gatekeeper — VS Code Airbag Extension
 *
 * Hooks into onWillSaveTextDocument. When a file is about to be saved,
 * it sends the code + .trepan/ pillars to the local Trepan inference server.
 * If the server returns REJECT, the save is physically blocked in VS Code.
 *
 * Fail-open: if the server is offline or slow, the save proceeds normally.
 */

const vscode = require("vscode");
const fs = require("fs");
const path = require("path");

// ─── State ───────────────────────────────────────────────────────────────────

let statusBarItem;
let serverOnline = false;

// ─── Activation ──────────────────────────────────────────────────────────────

/**
 * @param {vscode.ExtensionContext} context
 */
function activate(context) {
    console.log("🛡️ Trepan Gatekeeper: Airbag active");

    context.subscriptions.push(
        vscode.window.registerWebviewViewProvider("trepan.explorer", trepanSidebarProvider)
    );

    // Status bar pill
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBarItem.command = "trepan.status";
    setStatus("checking");
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);

    // Commands
    context.subscriptions.push(
        vscode.commands.registerCommand("trepan.status", showStatus),
        vscode.commands.registerCommand("trepan.toggleEnabled", toggleEnabled)
    );

    let askCommand = vscode.commands.registerCommand('trepan.askGatekeeper', async () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) return;

        // Grab the text the user highlighted
        const selection = editor.selection;
        const highlightedText = editor.document.getText(selection);

        if (!highlightedText) {
            vscode.window.showInformationMessage("Please highlight a rule or code snippet first.");
            return;
        }

        vscode.window.showInformationMessage(`Asking Trepan about: "${highlightedText}"...`);

        // Send logic to the sidebar UI
        trepanSidebarProvider.sendMessage({
            type: 'log',
            title: 'User Asked',
            thought: 'Sending selection to Meta-Gate: ' + highlightedText
        });
    });

    context.subscriptions.push(askCommand);

    // Periodic server health check
    checkServerHealth();
    const healthTimer = setInterval(checkServerHealth, 30_000);
    context.subscriptions.push({ dispose: () => clearInterval(healthTimer) });

    // ── THE AIRBAG ────────────────────────────────────────────────────────────
    const saveHook = vscode.workspace.onWillSaveTextDocument((event) => {
        console.log('[TREPAN DEBUG] Save event triggered for:', event.document.fileName);
        try {
            const cfg = vscode.workspace.getConfiguration("trepan");
            if (!cfg.get("enabled")) {
                console.log('[TREPAN DEBUG] Airbag is DISABLED in settings. Skipping.');
                return;
            }

            // Bypass standard excludes if this is a Pillar file (Selective Pass)
            const relPath = vscode.workspace.asRelativePath(event.document.uri);
            const isPillar = relPath.startsWith(".trepan") && relPath.endsWith(".md");
            console.log(`[TREPAN DEBUG] relPath=${relPath} | isPillar=${isPillar} | serverOnline=${serverOnline}`);

            if (!isPillar) {
                const excludes = cfg.get("excludePatterns") ?? [];
                if (excludes.some((pat) => matchGlob(pat, relPath))) {
                    console.log('[TREPAN DEBUG] File matched exclude pattern. Skipping.');
                    return;
                }
            }

            // Skip if server is offline — fail open
            if (!serverOnline) {
                console.warn('[TREPAN DEBUG] Server is OFFLINE. Airbag failing open for this save.');
                return;
            }

            event.waitUntil(evaluateSave(event.document));
        } catch (error) {
            console.error('[TREPAN ERROR] Save listener crashed:', error);
            vscode.window.showErrorMessage(`Trepan Extension Crash: ${error.message}`);
        }
    });

    context.subscriptions.push(saveHook);
}

// ─── Core Evaluation ─────────────────────────────────────────────────────────

/**
 * @param {vscode.TextDocument} document
 * @returns {Promise<vscode.TextEdit[]>}
 */
async function evaluateSave(document) {
    const cfg = vscode.workspace.getConfiguration("trepan");
    const serverUrl = cfg.get("serverUrl") ?? "http://127.0.0.1:8000";
    const timeoutMs = cfg.get("timeoutMs") ?? 30_000;

    const relPath = vscode.workspace.asRelativePath(document.uri);
    const isPillar = relPath.startsWith(".trepan") && relPath.endsWith(".md");

    // ============================================
    // THE META-GATE: Policing the Law (.trepan/*.md)
    // ============================================
    if (isPillar) {
        const fileName = path.basename(document.fileName);
        const incomingContent = document.getText();

        setStatus("checking");
        // Action 1: Push the SCANNING state to sidebar immediately
        trepanSidebarProvider.sendMessage({ type: 'scanning', title: 'Meta-Gate Audit: ' + fileName });
        try {
            const res = await fetchWithTimeout(`${serverUrl}/evaluate_pillar`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ filename: fileName, incoming_content: incomingContent }),
            }, timeoutMs);

            if (!res.ok) {
                console.warn(`Trepan: Meta-Gate server returned ${res.status} — failing open`);
                setStatus("online");
                return [];
            }

            const data = await res.json();
            setStatus("online");

            // Send output to the reasoning sidebar
            trepanSidebarProvider.sendMessage({
                type: 'log',
                title: 'Meta-Gate Audit: ' + fileName,
                score: data.drift_score?.toFixed(2),
                action: data.action,
                thought: data.raw_output,
                filename: fileName,
                incomingContent: incomingContent,
            });

            if (data.action === "REJECT") {
                const score = (data.drift_score ?? 0).toFixed(2);
                vscode.window.showErrorMessage(`🛑 Trepan Blocked Pillar Save — Drift Score: ${score}`, { modal: true }, "See Reasoning");

                // The Revert Mechanism - forcefully overwrite user's file with vault state
                const workspaceEdit = new vscode.WorkspaceEdit();
                const vaultPath = path.join(vscode.workspace.workspaceFolders[0].uri.fsPath, ".trepan", ".vault", fileName);
                if (fs.existsSync(vaultPath)) {
                    const vaultContent = fs.readFileSync(vaultPath, "utf-8");
                    const fullRange = new vscode.Range(
                        document.positionAt(0),
                        document.positionAt(incomingContent.length)
                    );
                    workspaceEdit.replace(document.uri, fullRange, vaultContent);
                    await vscode.workspace.applyEdit(workspaceEdit);
                    vscode.window.showInformationMessage(`Vault state restored for ${fileName}.`);
                }

                throw new Error(`Trepan Meta-Gate: architectural change rejected (score ${score})`);
            }

            if (data.action === "VAULT_COMPROMISED") {
                vscode.window.showErrorMessage(`🚨 VAULT COMPROMISED: ${data.raw_output}`, { modal: true });
                throw new Error("Trepan Meta-Gate: Vault Cryptographic Signature Invalid.");
            }

            setStatus("accepted");
            setTimeout(() => setStatus("online"), 2000);
            return []; // ALLOW

        } catch (err) {
            if (err.message?.startsWith("Trepan Meta-Gate")) throw err;
            setStatus("online");
            return [];
        }
    }

    // ============================================
    // STANDARD AIRBAG: Policing the Code 
    // ============================================
    const pillars = readPillars();
    const fileName = path.basename(document.fileName);
    const codeSnippet = document.getText().substring(0, 3000);

    const payload = {
        ...pillars,
        user_command: `[SAVE INTERCEPT — ${fileName}]\n\n${codeSnippet}`,
    };

    setStatus("checking");

    try {
        const res = await fetchWithTimeout(`${serverUrl}/evaluate`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        }, timeoutMs);

        if (!res.ok) {
            console.warn(`Trepan: server returned ${res.status} — failing open`);
            setStatus("online");
            return [];
        }

        const data = await res.json();
        setStatus("online");

        // Send output to the reasoning sidebar
        trepanSidebarProvider.sendMessage({
            type: 'log',
            title: 'Airbag Audit: ' + fileName,
            score: data.drift_score?.toFixed(2),
            action: data.action,
            thought: data.raw_output,
        });

        if (data.action === "REJECT") {
            const score = (data.drift_score ?? 0).toFixed(2);
            const reason = (data.raw_output ?? "").split("\n").slice(0, 3).join(" ").substring(0, 200);

            // Block the save — showing a modal error makes it unmissable
            const choice = await vscode.window.showErrorMessage(
                `🛑 Trepan Blocked Save — Drift Score: ${score}`,
                { modal: true, detail: `Reason: ${reason}\n\nFix the architectural violation or disable Trepan to proceed.` },
                "Override & Save Anyway",
                "Open .trepan/system_rules.md"
            );

            if (choice === "Override & Save Anyway") {
                return [];
            }

            if (choice === "Open .trepan/system_rules.md") {
                openPillarFile("system_rules.md");
            }

            throw new Error(`Trepan Gatekeeper: architectural drift detected (score ${score})`);
        }

        setStatus("accepted");
        setTimeout(() => setStatus("online"), 2000);
        return [];

    } catch (err) {
        if (err.message?.startsWith("Trepan Gatekeeper")) throw err;
        console.warn("Trepan: evaluation error —", err.message, "— failing open");
        setStatus("online");
        return [];
    }
}

// ─── Pillar Reader ────────────────────────────────────────────────────────────

function readPillars() {
    const folders = vscode.workspace.workspaceFolders;
    if (!folders?.length) return emptyPillars();

    const trepanDir = path.join(folders[0].uri.fsPath, ".trepan");
    const read = (name) => {
        const filePath = path.join(trepanDir, name);
        return fs.existsSync(filePath) ? fs.readFileSync(filePath, "utf-8") : "";
    };

    return {
        golden_state: read("golden_state.md"),
        done_tasks: read("done_tasks.md"),
        pending_tasks: read("pending_tasks.md"),
        history_phases: read("history_phases.md"),
        system_rules: read("system_rules.md"),
        problems_and_resolutions: read("problems_and_resolutions.md"),
    };
}

function emptyPillars() {
    return {
        golden_state: "", done_tasks: "", pending_tasks: "",
        history_phases: "", system_rules: "", problems_and_resolutions: "",
    };
}

// ─── Health Check ─────────────────────────────────────────────────────────────

async function checkServerHealth() {
    const cfg = vscode.workspace.getConfiguration("trepan");
    const url = cfg.get("serverUrl") ?? "http://127.0.0.1:8000";
    try {
        const res = await fetchWithTimeout(`${url}/health`, {}, 4000);
        const data = await res.json();
        serverOnline = data.status === "ok";
        setStatus(serverOnline ? (data.model_loaded ? "online" : "loading") : "offline");
    } catch {
        serverOnline = false;
        setStatus("offline");
    }
}

// ─── Status Bar ───────────────────────────────────────────────────────────────

const STATUS_MAP = {
    online: { text: "$(shield) Trepan ✅", tooltip: "Trepan online — airbag armed", bg: undefined },
    loading: { text: "$(shield) Trepan ⏳", tooltip: "Trepan online — model loading…", bg: undefined },
    checking: { text: "$(shield) Trepan 🔄", tooltip: "Trepan — evaluating save…", bg: new vscode.ThemeColor("statusBarItem.warningBackground") },
    accepted: { text: "$(shield) Trepan ✅", tooltip: "Trepan — save ACCEPTED", bg: new vscode.ThemeColor("statusBarItem.prominentBackground") },
    offline: { text: "$(shield) Trepan ⚫", tooltip: "Trepan offline — saves pass through", bg: undefined },
};

function setStatus(key) {
    if (!statusBarItem) return;
    const s = STATUS_MAP[key] ?? STATUS_MAP.offline;
    statusBarItem.text = s.text;
    statusBarItem.tooltip = s.tooltip;
    statusBarItem.backgroundColor = s.bg;
}

// ─── Commands ─────────────────────────────────────────────────────────────────

async function showStatus() {
    const cfg = vscode.workspace.getConfiguration("trepan");
    const url = cfg.get("serverUrl");
    const enabled = cfg.get("enabled");
    vscode.window.showInformationMessage(
        `🛡️ Trepan Gatekeeper\n\nServer: ${url}\nAirbag: ${enabled ? "ARMED ✅" : "DISABLED ⚫"}\nServer: ${serverOnline ? "online" : "offline"}`
    );
}

async function toggleEnabled() {
    const cfg = vscode.workspace.getConfiguration("trepan");
    const current = cfg.get("enabled");
    await cfg.update("enabled", !current, vscode.ConfigurationTarget.Global);
    vscode.window.showInformationMessage(`🛡️ Trepan Airbag: ${!current ? "ARMED ✅" : "DISABLED ⚫"}`);
    setStatus(!current ? (serverOnline ? "online" : "offline") : "offline");
}

function openPillarFile(name) {
    const folders = vscode.workspace.workspaceFolders;
    if (!folders?.length) return;
    const filePath = path.join(folders[0].uri.fsPath, ".trepan", name);
    if (fs.existsSync(filePath)) {
        vscode.workspace.openTextDocument(filePath).then((doc) => vscode.window.showTextDocument(doc));
    }
}

// ─── Utilities ────────────────────────────────────────────────────────────────

function fetchWithTimeout(url, options, ms) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), ms);
    return fetch(url, { ...options, signal: controller.signal }).finally(() => clearTimeout(timer));
}

/** Minimal glob matcher — supports ** and * wildcards */
function matchGlob(pattern, filePath) {
    const regexStr = pattern
        .replace(/[.+^${}()|[\]\\]/g, "\\$&")
        .replace(/\*\*/g, "___DOUBLE___")
        .replace(/\*/g, "[^/]*")
        .replace(/___DOUBLE___/g, ".*");
    return new RegExp(`^${regexStr}$`).test(filePath);
}

// ─── Webview View Provider (Sidebar) ──────────────────────────────────────────

class TrepanSidebarProvider {
    constructor() { }
    resolveWebviewView(webviewView) {
        this._view = webviewView;
        webviewView.webview.options = { enableScripts: true };
        webviewView.webview.html = this._getHtmlForWebview();

        // Listen for messages from the Webview (like button clicks)
        webviewView.webview.onDidReceiveMessage(async (message) => {
            if (message.command === 'resign_vault') {
                const cfg = vscode.workspace.getConfiguration("trepan");
                const serverUrl = cfg.get("serverUrl") ?? "http://127.0.0.1:8000";
                try {
                    vscode.window.showInformationMessage("🛡️ Re-signing Trepan Vault...");
                    const res = await fetchWithTimeout(`${serverUrl}/resign_vault`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" }
                    }, 10000);

                    if (res.ok) {
                        const data = await res.json();
                        vscode.window.showInformationMessage(`✅ ${data.message}`);
                        this.sendMessage({ type: 'resign_success' });
                    } else {
                        vscode.window.showErrorMessage(`❌ Failed to re-sign vault: Server returned ${res.status}`);
                    }
                } catch (err) {
                    vscode.window.showErrorMessage(`❌ Failed to connect to Trepan server to re-sign: ${err.message}`);
                }
            }

            if (message.command === 'revert_save') {
                const { filename } = message;
                const folders = vscode.workspace.workspaceFolders;
                if (!folders?.length) return;
                const vaultPath = path.join(folders[0].uri.fsPath, ".trepan", "trepan_vault", filename);
                const livePath = path.join(folders[0].uri.fsPath, ".trepan", filename);
                if (fs.existsSync(vaultPath)) {
                    fs.copyFileSync(vaultPath, livePath);
                    const doc = await vscode.workspace.openTextDocument(livePath);
                    await vscode.window.showTextDocument(doc);
                    vscode.window.showInformationMessage(`🛡️ Reverted ${filename} to vault state.`);
                    this.sendMessage({ type: 'reset' });
                }
            }

            if (message.command === 'force_override') {
                vscode.window.showWarningMessage(`⚠️ Force Override acknowledged. Trepan will allow the next save for this file.`);
                this.sendMessage({ type: 'reset' });
            }
        });
    }
    sendMessage(message) {
        if (this._view) {
            this._view.webview.postMessage(message);
        } else {
            vscode.commands.executeCommand("trepan.explorer.focus").then(() => {
                if (this._view) this._view.webview.postMessage(message);
            });
        }
    }
    _getHtmlForWebview() {
        return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trepan Architect</title>
    <style>
        body { font-family: var(--vscode-font-family); padding: 10px; color: var(--vscode-editor-foreground); transition: background-color 0.3s; }
        body.compromised { background-color: rgba(255, 0, 0, 0.1); }
        .thought { color: var(--vscode-terminal-ansiBrightBlack); font-style: italic; white-space: pre-wrap; margin-bottom: 10px; font-size: 0.9em; }
        .action-accept { color: var(--vscode-testing-iconPassed); font-weight: bold; }
        .action-reject { color: var(--vscode-testing-iconFailed); font-weight: bold; }
        .action-error { color: orange; font-weight: bold; }
        .action-compromised { color: #ff4d4d; font-weight: bold; font-size: 1.2em; }
        .log-entry { margin-bottom: 20px; border-bottom: 1px solid var(--vscode-panel-border); padding-bottom: 10px; }
        .scanning { display: flex; align-items: center; gap: 8px; color: var(--vscode-terminal-ansiBrightYellow); }
        .spinner { width: 14px; height: 14px; border: 2px solid var(--vscode-terminal-ansiBrightYellow); border-top-color: transparent; border-radius: 50%; animation: spin 0.8s linear infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }
        .compromise-alert { display: none; background-color: #ffcccc; color: #990000; padding: 15px; border-left: 5px solid #cc0000; margin-bottom: 20px; border-radius: 4px; }
        .compromise-alert.active { display: block; }
        .btn { border: none; padding: 8px 14px; cursor: pointer; font-weight: bold; margin-top: 8px; margin-right: 6px; border-radius: 4px; }
        .btn-danger { background-color: #cc0000; color: white; }
        .btn-danger:hover { background-color: #990000; }
        .btn-warn { background-color: #b36b00; color: white; }
        .btn-warn:hover { background-color: #804d00; }
        .btn-revert { background-color: #1a73e8; color: white; }
        .btn-revert:hover { background-color: #1557b0; }
    </style>
</head>
<body>
    <div id="compromise-banner" class="compromise-alert">
        <h3 style="margin-top:0;">🛑 VAULT COMPROMISE DETECTED</h3>
        <p>The architectural pillars have been modified outside of Trepan's authorization. Please review the rules in your .trepan folder.</p>
        <button id="resign-btn" class="btn btn-danger">⚠️ I have reviewed the rules. Re-Sign Vault.</button>
    </div>

    <div id="content">
        <h2>🏛️ Trepan Vault Access</h2>
        <p>Awaiting architectural changes...</p>
    </div>
    <script>
        const vscode = acquireVsCodeApi();
        const contentDiv = document.getElementById('content');
        const compromiseBanner = document.getElementById('compromise-banner');
        
        document.getElementById('resign-btn').addEventListener('click', () => {
            vscode.postMessage({ command: 'resign_vault' });
        });

        window.addEventListener('message', event => {
            const message = event.data;
            
            if (message.type === 'reset') {
                document.body.classList.remove('compromised');
                compromiseBanner.classList.remove('active');
                contentDiv.innerHTML = '<h2>🏛️ Trepan Vault Access</h2><p>Awaiting architectural changes...</p>';
                return;
            }
            
            if (message.type === 'resign_success') {
                document.body.classList.remove('compromised');
                compromiseBanner.classList.remove('active');
                contentDiv.innerHTML = '<h2>🏛️ Trepan Vault Access</h2><p style="color: var(--vscode-testing-iconPassed); font-weight: bold;">✅ Successfully Re-Signed Vault!</p>';
                setTimeout(() => {
                    contentDiv.innerHTML = '<h2>🏛️ Trepan Vault Access</h2><p>Awaiting architectural changes...</p>';
                }, 3000);
                return;
            }

            // SCANNING: show loading spinner while AI is thinking
            if (message.type === 'scanning') {
                contentDiv.innerHTML = '<h2>🏛️ Trepan Vault Access</h2><div class="scanning"><div class="spinner"></div><span>🛡️ Trepan is evaluating architectural drift...</span></div>';
                return;
            }
            
            if (message.type === 'log') {
                if (message.action === 'VAULT_COMPROMISED') {
                    document.body.classList.add('compromised');
                    compromiseBanner.classList.add('active');
                }

                const entry = document.createElement('div');
                entry.className = 'log-entry';
                let html = '<h3>' + message.title + '</h3>';
                if (message.score) html += '<p>Drift Score: ' + message.score + '</p>';

                if (message.action === 'ACCEPT') {
                    html += '<p class="action-accept">✅ Verdict: ACCEPT</p>';
                    if (message.thought) {
                        html += '<button class="btn btn-revert" id="seeReasoningBtn">💭 See Reasoning</button>';
                        html += '<div id="reasoningContent" style="display:none; margin-top:10px; padding:10px; background-color:var(--vscode-editor-inactiveSelectionBackground); border-radius:4px;"><div class="thought">' + message.thought + '</div></div>';
                    }

                } else if (message.action === 'REJECT') {
                    html += '<p class="action-reject">🛑 Verdict: REJECT</p>';
                    if (message.thought) {
                        html += '<button class="btn btn-revert" id="seeReasoningBtn">💭 See Reasoning</button>';
                        html += '<div id="reasoningContent" style="display:none; margin-top:10px; padding:10px; background-color:var(--vscode-editor-inactiveSelectionBackground); border-radius:4px;"><div class="thought">' + message.thought + '</div></div>';
                    }
                    html += '<div style="margin-top:10px;">';
                    html += '<button class="btn btn-revert" id="revertBtn">↩️ Revert Save</button>';
                    html += '<button class="btn btn-warn" id="overrideBtn">⚠️ Force Override</button>';
                    html += '</div>';

                } else if (message.action === 'ERROR') {
                    html += '<p class="action-error">⚠️ Verdict: ERROR (AI hallucinated — no valid output)</p>';
                    if (message.thought) {
                        html += '<button class="btn btn-revert" id="seeReasoningBtn">💭 See Reasoning</button>';
                        html += '<div id="reasoningContent" style="display:none; margin-top:10px; padding:10px; background-color:var(--vscode-editor-inactiveSelectionBackground); border-radius:4px;"><div class="thought">' + message.thought + '</div></div>';
                    }

                } else if (message.action === 'VAULT_COMPROMISED') {
                    html += '<p class="action-compromised">🚨 VAULT COMPROMISED</p>';

                } else {
                    if (message.action) html += '<p>Verdict: ' + message.action + '</p>';
                    if (message.thought) {
                        html += '<button class="btn btn-revert" id="seeReasoningBtn">💭 See Reasoning</button>';
                        html += '<div id="reasoningContent" style="display:none; margin-top:10px; padding:10px; background-color:var(--vscode-editor-inactiveSelectionBackground); border-radius:4px;"><div class="thought">' + message.thought + '</div></div>';
                    }
                }

                entry.innerHTML = html;
                contentDiv.innerHTML = '<h2>🏛️ Trepan Vault Access</h2>';
                contentDiv.appendChild(entry);

                // Wire up buttons via event delegation on the entry element
                entry.addEventListener('click', (e) => {
                    const target = e.target;
                    if (target.id === 'seeReasoningBtn') {
                        const reasoningContent = document.getElementById('reasoningContent');
                        if (reasoningContent) {
                            const isHidden = reasoningContent.style.display === 'none';
                            reasoningContent.style.display = isHidden ? 'block' : 'none';
                            target.innerText = isHidden ? '🙈 Hide Reasoning' : '💭 See Reasoning';
                        }
                    } else if (target.id === 'revertBtn') {
                        vscode.postMessage({ command: 'revert_save', filename: message.filename });
                    } else if (target.id === 'overrideBtn') {
                        vscode.postMessage({ command: 'force_override' });
                    }
                });
            }
        });
    </script>
</body>
</html>`;
    }
}
const trepanSidebarProvider = new TrepanSidebarProvider();

// ─── Exports ─────────────────────────────────────────────────────────────────

function deactivate() { }

module.exports = { activate, deactivate };
