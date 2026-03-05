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

// ─── WSL Bridge Auto-Discovery ──────────────────────────────────────────────

/**
 * Get WSL IP address by running `wsl.exe hostname -I` from Windows
 * Returns null if not running on Windows or if command fails
 */
async function getWSLIP() {
    try {
        const { exec } = require('child_process');
        const { promisify } = require('util');
        const execAsync = promisify(exec);

        // Only try this on Windows
        if (process.platform !== 'win32') {
            return null;
        }

        const { stdout } = await execAsync('wsl.exe hostname -I', { timeout: 5000 });
        const ips = stdout.trim().split(/\s+/);

        // Return the first valid IP (usually the WSL bridge IP)
        for (const ip of ips) {
            if (ip.match(/^\d+\.\d+\.\d+\.\d+$/)) {
                return ip;
            }
        }

        return null;
    } catch (error) {
        console.log(`[TREPAN WSL] Could not get WSL IP: ${error.message}`);
        return null;
    }
}

/**
 * Try connecting to server with multiple URLs (localhost + WSL IP)
 * Returns the first successful connection URL or null if all fail
 */
async function discoverServerURL(basePort = 8001) {
    // Return cached URL if available and still working
    if (discoveredServerUrl) {
        try {
            const res = await fetchWithTimeout(`${discoveredServerUrl}/health`, {}, 2000);
            if (res.ok) {
                console.log(`[TREPAN WSL] ✅ Using cached URL: ${discoveredServerUrl}`);
                return discoveredServerUrl;
            }
        } catch (error) {
            console.log(`[TREPAN WSL] ❌ Cached URL failed: ${discoveredServerUrl}, rediscovering...`);
            discoveredServerUrl = null;
        }
    }

    const cfg = vscode.workspace.getConfiguration("trepan");
    const configuredUrl = cfg.get("serverUrl");

    let targetPorts = [basePort]; // Try basePort (8001) first

    // Extract port from configured URL if present
    if (configuredUrl) {
        const urlMatch = configuredUrl.match(/:(\d+)/);
        if (urlMatch) {
            const configPort = parseInt(urlMatch[1]);
            // Prioritize configured port
            targetPorts = [configPort, basePort];
        }
    }

    // Remove duplicates
    targetPorts = [...new Set(targetPorts)];

    // Print the primary port in the diagnostic run
    console.log(`[TREPAN WSL] Target Port: ${targetPorts[0]}`);

    const candidateURLs = [];

    // Add WSL IP if available
    const wslIP = await getWSLIP();
    if (wslIP) {
        console.log(`[TREPAN WSL] Discovered WSL IP: ${wslIP}`);
    }

    // Generate candidates for all target ports
    for (const port of targetPorts) {
        candidateURLs.push(`http://127.0.0.1:${port}`);
        candidateURLs.push(`http://localhost:${port}`);
        if (wslIP) {
            candidateURLs.push(`http://${wslIP}:${port}`);
        }
    }

    console.log(`[TREPAN WSL] Testing connection URLs: ${candidateURLs.join(', ')}`);

    // Test each URL
    for (const url of candidateURLs) {
        try {
            console.log(`[TREPAN WSL] Testing: ${url}`);
            const res = await fetchWithTimeout(`${url}/health`, {}, 3000);

            if (res.ok) {
                const data = await res.json();
                console.log(`[TREPAN WSL] ✅ Connected to: ${url}`);
                console.log(`[TREPAN WSL] Server status: ${JSON.stringify(data)}`);

                // Cache the successful URL
                discoveredServerUrl = url;
                return url;
            }
        } catch (error) {
            // SILENCE NOISE: Only log if we are desperate or if it's an unexpected error
            // console.log(`[TREPAN WSL] ❌ Failed ${url}: ${error.code || error.message}`);
        }
    }

    console.log(`[TREPAN WSL] ❌ All connection attempts failed (Tested ports: ${targetPorts.join(', ')})`);
    return null;
}

// ─── State ───────────────────────────────────────────────────────────────────

let statusBarItem;
let serverOnline = false;
let discoveredServerUrl = null; // Cache the working server URL

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

    let openLedgerCommand = vscode.commands.registerCommand('trepan.openLedger', async () => {
        const folders = vscode.workspace.workspaceFolders;
        if (!folders?.length) {
            vscode.window.showErrorMessage("Trepan: No workspace open.");
            return;
        }

        const trepanDir = path.join(folders[0].uri.fsPath, ".trepan");
        let ledgerPath = null;

        if (fs.existsSync(trepanDir)) {
            const files = fs.readdirSync(trepanDir);
            const walkthroughFile = files.find(f => f.toLowerCase().startsWith("walkthrough"));
            if (walkthroughFile) {
                ledgerPath = path.join(trepanDir, walkthroughFile);
            }
        }

        if (ledgerPath && fs.existsSync(ledgerPath)) {
            const doc = await vscode.workspace.openTextDocument(ledgerPath);
            await vscode.window.showTextDocument(doc, { viewColumn: vscode.ViewColumn.Beside });
        } else {
            vscode.window.showInformationMessage("Trepan: Walkthrough ledger not found yet. It will be generated on your next save.");
        }
    });

    let reviewChangesCommand = vscode.commands.registerCommand('trepan.reviewWithLedger', async () => {
        const folders = vscode.workspace.workspaceFolders;
        if (!folders?.length) {
            vscode.window.showErrorMessage("Trepan: No workspace open.");
            return;
        }

        const activeEditor = vscode.window.activeTextEditor;
        if (!activeEditor) {
            vscode.window.showInformationMessage("Trepan: Open a file first to review changes.");
            return;
        }

        const trepanDir = path.join(folders[0].uri.fsPath, ".trepan");
        let ledgerPath = null;

        if (fs.existsSync(trepanDir)) {
            const files = fs.readdirSync(trepanDir);
            const walkthroughFile = files.find(f => f.toLowerCase().startsWith("walkthrough"));
            if (walkthroughFile) {
                ledgerPath = path.join(trepanDir, walkthroughFile);
            }
        }

        if (!ledgerPath || !fs.existsSync(ledgerPath)) {
            vscode.window.showInformationMessage("Trepan: Walkthrough ledger not found yet. It will be generated on your next save.");
            return;
        }

        // Split editor: Code on left, Ledger on right
        await vscode.commands.executeCommand('workbench.action.splitEditorRight');

        const ledgerDoc = await vscode.workspace.openTextDocument(ledgerPath);
        const ledgerEditor = await vscode.window.showTextDocument(ledgerDoc, {
            viewColumn: vscode.ViewColumn.Two,
            preserveFocus: false
        });

        // Auto-scroll to the most recent entry (bottom of file)
        const lastLine = ledgerDoc.lineCount - 1;
        const lastChar = ledgerDoc.lineAt(lastLine).text.length;
        const bottomPosition = new vscode.Position(lastLine, lastChar);
        ledgerEditor.selection = new vscode.Selection(bottomPosition, bottomPosition);
        ledgerEditor.revealRange(
            new vscode.Range(bottomPosition, bottomPosition),
            vscode.TextEditorRevealType.InCenter
        );

        // Return focus to the code editor
        await vscode.window.showTextDocument(activeEditor.document, {
            viewColumn: vscode.ViewColumn.One,
            preserveFocus: false
        });

        vscode.window.showInformationMessage("📋 Trepan: Code (left) | Audit Ledger (right)");
    });

    let initializeProjectCommand = vscode.commands.registerCommand('trepan.initializeProject', async () => {
        const folders = vscode.workspace.workspaceFolders;
        if (!folders?.length) {
            vscode.window.showErrorMessage("Trepan: No workspace open. Please open a folder first.");
            return;
        }

        const projectPath = folders[0].uri.fsPath;
        const trepanDir = path.join(projectPath, ".trepan");

        // Check if already initialized
        if (fs.existsSync(trepanDir)) {
            const choice = await vscode.window.showWarningMessage(
                "Trepan is already initialized in this project. Reinitialize?",
                { modal: true },
                "Yes, Reinitialize",
                "Cancel"
            );
            if (choice !== "Yes, Reinitialize") {
                return;
            }
        }

        // Show template selection
        const templates = [
            {
                label: "$(zap) Solo-Indie (The Speedster)",
                description: "Simple, readable code for solo developers",
                detail: "Focus: Function size limits, nesting depth, clear naming, DRY principle",
                id: "solo-indie"
            },
            {
                label: "$(layers) Clean-Layers (The Architect)",
                description: "Strict separation of concerns for long-term projects",
                detail: "Focus: Layer separation, dependency injection, interface contracts, SRP",
                id: "clean-layers"
            },
            {
                label: "$(shield) Secure-Stateless (The Fortress)",
                description: "Maximum security with zero-trust architecture",
                detail: "Focus: Input sanitization, stateless sessions, encryption, audit logging",
                id: "secure-stateless"
            }
        ];

        const selected = await vscode.window.showQuickPick(templates, {
            placeHolder: "Choose your architectural style",
            title: "Trepan: Golden Template Selection"
        });

        if (!selected) {
            return;
        }

        // Show progress
        await vscode.window.withProgress({
            location: vscode.ProgressLocation.Notification,
            title: "Trepan: Initializing Project",
            cancellable: false
        }, async (progress) => {
            progress.report({ message: "Creating .trepan directory..." });

            const cfg = vscode.workspace.getConfiguration("trepan");
            const serverUrl = cfg.get("serverUrl") ?? "http://127.0.0.1:8001";

            try {
                progress.report({ message: "Generating golden template..." });

                const response = await fetchWithTimeout(`${serverUrl}/initialize_project`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        mode: selected.id,
                        project_path: projectPath
                    })
                }, 60000); // 60 second timeout for LLM generation

                if (!response.ok) {
                    const error = await response.text();
                    throw new Error(`Server returned ${response.status}: ${error}`);
                }

                const result = await response.json();

                progress.report({ message: "Opening generated files..." });

                // Open system_rules.md and golden_state.md
                const rulesPath = path.join(trepanDir, "system_rules.md");
                const goldenPath = path.join(trepanDir, "golden_state.md");

                if (fs.existsSync(rulesPath)) {
                    const rulesDoc = await vscode.workspace.openTextDocument(rulesPath);
                    await vscode.window.showTextDocument(rulesDoc, { viewColumn: vscode.ViewColumn.One });
                }

                if (fs.existsSync(goldenPath)) {
                    const goldenDoc = await vscode.workspace.openTextDocument(goldenPath);
                    await vscode.window.showTextDocument(goldenDoc, { viewColumn: vscode.ViewColumn.Two });
                }

                vscode.window.showInformationMessage(
                    `✅ Trepan initialized with ${selected.label}! Review your system_rules.md and golden_state.md.`
                );

            } catch (error) {
                vscode.window.showErrorMessage(`Trepan initialization failed: ${error.message}`);
                console.error("Trepan initialization error:", error);
            }
        });
    });

    context.subscriptions.push(askCommand, openLedgerCommand, reviewChangesCommand, initializeProjectCommand);

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

    const saveDoneHandler = vscode.workspace.onDidSaveTextDocument((document) => {
        console.log('[TREPAN] Document Saved:', document.fileName);
    });

    context.subscriptions.push(saveHook, saveDoneHandler);
}

// ─── Core Evaluation ─────────────────────────────────────────────────────────

/**
 * @param {vscode.TextDocument} document
 * @returns {Promise<vscode.TextEdit[]>}
 */
async function evaluateSave(document) {
    const cfg = vscode.workspace.getConfiguration("trepan");
    let serverUrl = cfg.get("serverUrl") ?? "http://127.0.0.1:8001";
    const timeoutMs = cfg.get("timeoutMs") ?? 30_000;

    // Use auto-discovery if the configured URL doesn't work
    const discoveredUrl = await discoverServerURL();
    if (discoveredUrl && discoveredUrl !== serverUrl) {
        console.log(`[TREPAN EVAL] Using discovered URL: ${discoveredUrl} instead of configured: ${serverUrl}`);
        serverUrl = discoveredUrl;
        // Update config for future use
        await cfg.update("serverUrl", discoveredUrl, vscode.ConfigurationTarget.Workspace);
    } else if (!discoveredUrl) {
        console.log(`[TREPAN EVAL] ❌ No server available for evaluation`);
        return []; // Fail-open: allow save to proceed
    }

    const relPath = vscode.workspace.asRelativePath(document.uri);
    const isPillar = relPath.startsWith(".trepan") && relPath.endsWith(".md");

    // ============================================
    // THE META-GATE: Policing the Law (.trepan/*.md)
    // ============================================
    if (isPillar) {
        const fileName = path.basename(document.fileName);
        const incomingContent = document.getText();

        // ============================================
        // THE META-GATE: Policing the Law (.trepan/*.md)
        // ============================================
        console.log(`[TREPAN META-GATE] Pillar file save detected: ${fileName}`);

        setStatus("checking");
        // Action 1: Push the SCANNING state to sidebar immediately
        trepanSidebarProvider.sendMessage({ type: 'scanning', title: 'Meta-Gate Audit: ' + fileName });
        try {
            const projectPath = vscode.workspace.workspaceFolders?.[0]?.uri?.fsPath || '';
            const res = await fetchWithTimeout(`${serverUrl}/evaluate_pillar`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ filename: fileName, incoming_content: incomingContent, project_path: projectPath }),
            }, timeoutMs);

            if (!res.ok) {
                console.warn(`Trepan: Meta-Gate server returned ${res.status} — failing open`);
                setStatus("online");
                return [];
            }

            const data = await res.json();
            setStatus("online");

            // Parse the score correctly, preferring the specific Guillotine parser key if present
            const driftScore = data.score ?? data.drift_score ?? 0;
            const actionResult = data.verdict ?? data.action;
            const thoughtReasoning = data.reasoning ?? data.raw_output;

            // ═══════════════════════════════════════════════════════════════════
            // AI ASSISTANT AUTONOMY: Parse and execute [AI_ASSISTANT_ACTIONS]
            // ═══════════════════════════════════════════════════════════════════
            await executeAIAssistantActions(thoughtReasoning, actionResult, driftScore);

            // Send output to the reasoning sidebar
            trepanSidebarProvider.sendMessage({
                type: 'log',
                title: 'Meta-Gate Audit: ' + fileName,
                score: driftScore.toFixed(2),
                action: actionResult,
                thought: thoughtReasoning,
                filename: fileName,
                incomingContent: incomingContent,
            });

            if (actionResult === "REJECT") {
                const scoreDisplay = driftScore.toFixed(2);
                vscode.window.showErrorMessage(`🛑 Trepan Blocked Pillar Save — Drift Score: ${scoreDisplay}`, { modal: true }, "See Reasoning");

                // The Revert Mechanism - forcefully overwrite user's file with vault state
                const workspaceEdit = new vscode.WorkspaceEdit();
                const vaultPath = path.join(vscode.workspace.workspaceFolders[0].uri.fsPath, ".trepan", "trepan_vault", fileName);
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

                throw new Error(`Trepan Meta-Gate: architectural change rejected (score ${scoreDisplay})`);
            }

            if (actionResult === "VAULT_COMPROMISED") {
                vscode.window.showErrorMessage(`🚨 VAULT COMPROMISED: ${thoughtReasoning}`, { modal: true });
                throw new Error("Trepan Meta-Gate: Vault Cryptographic Signature Invalid.");
            }

            setStatus("accepted");
            setTimeout(() => setStatus("online"), 2000);
            return []; // ALLOW

        } catch (err) {
            if (err.message?.startsWith("Trepan Meta-Gate")) throw err;

            // ── LIVE RELOAD FALLBACK: If /evaluate_pillar failed (e.g. 500, 503, model not ready),
            // force a direct vault sync from live files via /trigger_sync ──
            console.log(`[TREPAN FALLBACK] /evaluate_pillar failed — attempting /trigger_sync live reload...`);
            try {
                const syncRes = await fetchWithTimeout(`${serverUrl}/trigger_sync`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                }, 10000);
                if (syncRes.ok) {
                    const syncData = await syncRes.json();
                    console.log(`[TREPAN FALLBACK] /trigger_sync result: ${syncData.message}`);
                    if (syncData.synced_files && syncData.synced_files.length > 0) {
                        vscode.window.showInformationMessage(`Trepan: Vault force-synced ${syncData.synced_files.length} file(s)`);
                    }
                } else {
                    console.warn(`[TREPAN FALLBACK] /trigger_sync returned ${syncRes.status}`);
                }
            } catch (syncErr) {
                console.error(`[TREPAN FALLBACK] /trigger_sync also failed:`, syncErr.message);
            }

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

        // Parse the score correctly, preferring the specific Guillotine parser key if present
        const driftScore = data.score ?? data.drift_score ?? 0;
        const actionResult = data.verdict ?? data.action;
        const thoughtReasoning = data.reasoning ?? data.raw_output ?? "";

        // ═══════════════════════════════════════════════════════════════════
        // AI ASSISTANT AUTONOMY: Parse and execute [AI_ASSISTANT_ACTIONS]
        // ═══════════════════════════════════════════════════════════════════
        await executeAIAssistantActions(thoughtReasoning, actionResult, driftScore);

        // Send output to the reasoning sidebar
        trepanSidebarProvider.sendMessage({
            type: 'log',
            title: 'Airbag Audit: ' + fileName,
            score: driftScore.toFixed(2),
            action: actionResult,
            thought: thoughtReasoning,
        });

        if (actionResult === "REJECT") {
            const scoreDisplay = driftScore.toFixed(2);
            const reason = thoughtReasoning.split("\n").slice(0, 3).join(" ").substring(0, 200);

            // Block the save — showing a modal error makes it unmissable
            const choice = await vscode.window.showErrorMessage(
                `🛑 Trepan Blocked Save — Drift Score: ${scoreDisplay}`,
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

            throw new Error(`Trepan Gatekeeper: architectural drift detected (score ${scoreDisplay})`);
        }

        // Handle WARN verdict (parser failed but we don't want to block)
        if (actionResult === "WARN") {
            console.warn('[TREPAN WARNING] Parser returned WARN - model output was malformed');
            vscode.window.showWarningMessage(
                `⚠️ Trepan: Model output was malformed, save allowed (fail-open)`,
                { modal: false }
            );
            // Allow save to proceed (fail-open)
            setStatus("online");
            return [];
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
    console.log(`[TREPAN HEALTH] Starting health check...`);

    // Use auto-discovery to find the correct server URL
    const discoveredUrl = await discoverServerURL();

    if (!discoveredUrl) {
        console.log(`[TREPAN HEALTH] ❌ No server found via auto-discovery`);
        serverOnline = false;
        setStatus("offline");

        // Output detailed diagnostics to VS Code channel
        const outputChannel = vscode.window.createOutputChannel("Trepan Gatekeeper");
        outputChannel.appendLine(`[${new Date().toISOString()}] Health Check Failed`);
        outputChannel.appendLine(`  Reason: No server responded to health checks`);
        outputChannel.appendLine(`  Tested URLs: 127.0.0.1:8001, localhost:8001${await getWSLIP() ? `, WSL IP` : ''} (and fallback 8000)`);
        outputChannel.appendLine(`  Solution: Start server with 'python start_server.py --host 0.0.0.0'`);
        outputChannel.show(true);

        return;
    }

    try {
        console.log(`[TREPAN HEALTH] Using discovered URL: ${discoveredUrl}`);
        const res = await fetchWithTimeout(`${discoveredUrl}/health`, {}, 4000);
        const data = await res.json();

        console.log(`[TREPAN HEALTH] ✅ Server response: ${JSON.stringify(data)}`);

        // Update configuration with working URL for future requests
        const cfg = vscode.workspace.getConfiguration("trepan");
        if (cfg.get("serverUrl") !== discoveredUrl) {
            console.log(`[TREPAN HEALTH] Updating serverUrl config to: ${discoveredUrl}`);
            await cfg.update("serverUrl", discoveredUrl, vscode.ConfigurationTarget.Workspace);
        }

        serverOnline = data.status === "ok";
        setStatus(serverOnline ? (data.model_loaded ? "online" : "loading") : "offline");

    } catch (error) {
        console.log(`[TREPAN HEALTH] ❌ Health check failed: ${error.message}`);

        // Enhanced error logging with Node.js error codes
        const outputChannel = vscode.window.createOutputChannel("Trepan Gatekeeper");
        outputChannel.appendLine(`[${new Date().toISOString()}] Health Check Error`);
        outputChannel.appendLine(`  URL: ${discoveredUrl}`);
        outputChannel.appendLine(`  Error Code: ${error.code || 'UNKNOWN'}`);
        outputChannel.appendLine(`  Error Message: ${error.message}`);

        if (error.code) {
            const troubleshooting = {
                'ECONNREFUSED': 'Server is not running. Start with: python start_server.py --host 0.0.0.0',
                'ETIMEDOUT': 'Server is slow to respond. Check server logs or increase timeout.',
                'EHOSTUNREACH': 'Network routing issue. Check WSL2 networking or firewall.',
                'ENOTFOUND': 'DNS resolution failed. Use IP address instead of hostname.',
                'ECONNRESET': 'Server closed connection. Check server stability.'
            };

            const solution = troubleshooting[error.code] || 'Unknown network error. Check server logs.';
            outputChannel.appendLine(`  Troubleshooting: ${solution}`);
        }

        outputChannel.show(true);
        serverOnline = false;
        setStatus("offline");
    }
}

// ─── Status Bar ───────────────────────────────────────────────────────────────

const STATUS_MAP = {
    online: { text: "🛡️ Trepan: Watching...", tooltip: "Trepan online — airbag armed", bg: undefined },
    loading: { text: "$(shield) Trepan ⏳", tooltip: "Trepan online — model loading…", bg: undefined },
    checking: { text: "🛡️ Trepan: Auditing...", tooltip: "Trepan — evaluating save…", bg: new vscode.ThemeColor("statusBarItem.warningBackground") },
    accepted: { text: "🛡️ Trepan: Accepted ✅", tooltip: "Trepan — save ACCEPTED", bg: new vscode.ThemeColor("statusBarItem.prominentBackground") },
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

// ─── AI Assistant Autonomy: Action Executor ──────────────────────────────────

/**
 * Parses [AI_ASSISTANT_ACTIONS] from LLM response OR uses fallback heuristics.
 * This makes the AI assistant autonomous - it maintains the 5 Pillars automatically.
 * 
 * FALLBACK STRATEGY: If model wasn't fine-tuned on [AI_ASSISTANT_ACTIONS],
 * we analyze the [THOUGHT] section for keywords and generate actions automatically.
 * 
 * @param {string} llmResponse - The full LLM response text
 * @param {string} verdict - The verdict (ACCEPT/REJECT)
 * @param {number} score - The drift score
 */
async function executeAIAssistantActions(llmResponse, verdict, score) {
    if (!llmResponse) return;

    const folders = vscode.workspace.workspaceFolders;
    if (!folders?.length) {
        console.warn('[TREPAN AI AUTONOMY] No workspace folder open - cannot execute file operations');
        return;
    }

    const projectRoot = folders[0].uri.fsPath;
    let executedCount = 0;

    // ═══════════════════════════════════════════════════════════════════
    // STRATEGY 1: Try to parse [AI_ASSISTANT_ACTIONS] section (if model was fine-tuned)
    // Also accept [ACTIONS] as fallback format
    // NOTE: We specifically look for [AI_ASSISTANT_ACTIONS] or [ACTIONS], NOT [ACTION]
    // because [ACTION] is used for the verdict (ACCEPT/REJECT) at the end of responses
    // ═══════════════════════════════════════════════════════════════════
    const actionsMatch = llmResponse.match(/\[(AI_ASSISTANT_ACTIONS|ACTIONS)\]([\s\S]*?)(?:\[|$)/);

    if (actionsMatch) {
        const sectionName = actionsMatch[1];
        const actionsSection = actionsMatch[2].trim();
        console.log(`[TREPAN AI AUTONOMY] Found [${sectionName}] section - using explicit actions`);

        // Parse APPEND_TO_FILE commands
        const appendCommands = actionsSection.matchAll(/APPEND_TO_FILE:\s*(.+?)\nCONTENT:\s*\|?\n([\s\S]*?)(?=\n\nAPPEND_TO_FILE:|$)/g);

        for (const match of appendCommands) {
            const filePath = match[1].trim();
            const content = match[2].trim();

            if (await appendToFile(projectRoot, filePath, content)) {
                executedCount++;
            }
        }
    } else {
        // ═══════════════════════════════════════════════════════════════════
        // STRATEGY 2: FALLBACK - Analyze [THOUGHT] section for patterns
        // ═══════════════════════════════════════════════════════════════════
        console.log('[TREPAN AI AUTONOMY] No [AI_ASSISTANT_ACTIONS] found - using fallback heuristics');

        const thoughtMatch = llmResponse.match(/\[THOUGHT\]([\s\S]*?)(?:\[|$)/);
        if (!thoughtMatch) {
            console.log('[TREPAN AI AUTONOMY] No [THOUGHT] section found - skipping');
            return;
        }

        const thought = thoughtMatch[1].trim().toLowerCase();
        const timestamp = new Date().toISOString().split('T')[0];

        // HEURISTIC 1: Detect rule violations (high drift score + REJECT)
        if (verdict === 'REJECT' && score >= 0.40) {
            const violationKeywords = ['violates', 'breaks', 'forbidden', 'not allowed', 'against rule'];
            if (violationKeywords.some(kw => thought.includes(kw))) {
                console.log('[TREPAN AI AUTONOMY] Detected rule violation - recording in problems');

                const content = `## Problem: Rule Violation Detected (${timestamp})
**Status**: UNRESOLVED
**Drift Score**: ${score.toFixed(2)}
**Description**: Code violates architectural rules
**AI Analysis**: ${thoughtMatch[1].trim().substring(0, 200)}...
`;
                if (await appendToFile(projectRoot, '.trepan/problems_and_resolutions.md', content)) {
                    executedCount++;
                }
            }
        }

        // HEURISTIC 2: Detect errors/failures
        const errorKeywords = ['error', 'failed', 'doesn\'t work', 'broken', 'issue', 'problem'];
        if (errorKeywords.some(kw => thought.includes(kw))) {
            console.log('[TREPAN AI AUTONOMY] Detected error pattern - recording in problems');

            const content = `## Problem: Error Detected (${timestamp})
**Status**: UNRESOLVED
**Description**: AI detected potential error in code
**AI Analysis**: ${thoughtMatch[1].trim().substring(0, 200)}...
`;
            if (await appendToFile(projectRoot, '.trepan/problems_and_resolutions.md', content)) {
                executedCount++;
            }
        }

        // HEURISTIC 3: Detect pattern compliance (low drift score + ACCEPT)
        if (verdict === 'ACCEPT' && score <= 0.15) {
            const patternKeywords = ['follows pattern', 'correct approach', 'good practice', 'recommended', 'aligns with'];
            if (patternKeywords.some(kw => thought.includes(kw))) {
                console.log('[TREPAN AI AUTONOMY] Detected pattern compliance - noting success');

                const content = `## Success: Pattern Followed (${timestamp})
**Drift Score**: ${score.toFixed(2)}
**Description**: Code follows architectural patterns correctly
**AI Analysis**: ${thoughtMatch[1].trim().substring(0, 200)}...
`;
                if (await appendToFile(projectRoot, '.trepan/history_phases.md', content)) {
                    executedCount++;
                }
            }
        }
    }

    // Show notification if any actions were executed
    if (executedCount > 0) {
        vscode.window.showInformationMessage(
            `🤖 Trepan AI Autonomy: Executed ${executedCount} pillar update(s)`,
            'View Changes'
        ).then(choice => {
            if (choice === 'View Changes') {
                vscode.commands.executeCommand('workbench.view.scm');
            }
        });
    }
}

/**
 * Helper function to append content to a file
 * @param {string} projectRoot - Project root path
 * @param {string} filePath - Relative file path
 * @param {string} content - Content to append
 * @returns {Promise<boolean>} - True if successful
 */
async function appendToFile(projectRoot, filePath, content) {
    try {
        const fullPath = path.join(projectRoot, filePath);

        if (!fs.existsSync(fullPath)) {
            console.warn(`[TREPAN AI AUTONOMY] File not found: ${fullPath} - skipping`);
            return false;
        }

        const existingContent = fs.readFileSync(fullPath, 'utf-8');
        const needsNewline = existingContent.length > 0 && !existingContent.endsWith('\n');
        const contentToAppend = (needsNewline ? '\n' : '') + content + '\n';

        fs.appendFileSync(fullPath, contentToAppend, 'utf-8');
        console.log(`[TREPAN AI AUTONOMY] ✅ Successfully appended to ${filePath}`);
        return true;

    } catch (error) {
        console.error(`[TREPAN AI AUTONOMY] ❌ Failed to append to ${filePath}:`, error);
        return false;
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
