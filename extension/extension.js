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

    // We implement a robust retry mechanism (hammering localhost) to wake up sleeping WSL network adapters.
    const MAX_RETRIES = 3;

    for (const url of candidateURLs) {
        for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
            try {
                console.log(`[TREPAN WSL] Testing (Attempt ${attempt}/${MAX_RETRIES}): ${url}`);
                // Increased timeout to 5000ms to tolerate slow WSL bridge wake-ups
                const res = await fetchWithTimeout(`${url}/health`, {}, 5000);

                if (res.ok) {
                    const data = await res.json();
                    console.log(`[TREPAN WSL] ✅ Connected to: ${url}`);
                    console.log(`[TREPAN WSL] Server status: ${JSON.stringify(data)}`);

                    // Cache the successful URL
                    discoveredServerUrl = url;
                    return url;
                }
            } catch (error) {
                // Wait briefly before retrying this specific URL
                if (attempt < MAX_RETRIES) {
                    console.log(`[TREPAN WSL] ⚠️ Attempt ${attempt} failed on ${url}, retrying in 500ms...`);
                    await new Promise(resolve => setTimeout(resolve, 500));
                }
            }
        }
    }

    console.log(`[TREPAN WSL] ❌ All connection attempts failed after ${MAX_RETRIES} retries. (Tested ports: ${targetPorts.join(', ')})`);
    return null;
}

// ─── State ───────────────────────────────────────────────────────────────────

let statusBarItem;
let serverOnline = false;
let discoveredServerUrl = null; // Cache the working server URL
let outputChannel; // Global diagnostic output channel

// Diff-based audit cache: stores last audited content per file URI
const _lastAuditedContent = new Map(); // key: document.uri.toString(), value: string
const DIFF_CONTEXT_LINES = 10; // lines of context above and below each changed region
const LARGE_FILE_THRESHOLD = 150; // lines — files above this use diff mode

// ─── Evaluation Queue ────────────────────────────────────────────────────────
// Serializes saves to prevent shotgun POST requests & Ollama bottlenecking.
class SaveQueue {
    constructor() {
        this.promise = Promise.resolve();
    }

    enqueue(task) {
        return new Promise((resolve, reject) => {
            this.promise = this.promise
                .then(() => task().then(resolve).catch(reject))
                .catch(() => task().then(resolve).catch(reject));
        });
    }
}
const saveEvaluationQueue = new SaveQueue();

// ─── Pivot Detection (Evolutionary Intelligence) ─────────────────────────────

/**
 * Detect if code removal represents a pivot away from a failed technology
 * @param {vscode.TextDocument} document - The saved document
 * @param {string} projectRoot - Workspace root path
 */
async function detectPivot(document, projectRoot) {
    try {
        console.log('[TREPAN PIVOT] Checking for pivots in:', document.fileName);

        // 1. Get git diff for this file
        const diff = await getGitDiff(document.fileName, projectRoot);
        if (!diff) {
            console.log('[TREPAN PIVOT] No git diff available');
            return;
        }

        // 2. Detect removed technologies
        const removedTechs = detectRemovedTechs(diff);
        if (removedTechs.length === 0) {
            console.log('[TREPAN PIVOT] No technologies removed');
            return;
        }

        console.log('[TREPAN PIVOT] Removed technologies:', removedTechs);

        // 3. Read problems_and_resolutions.md
        const problems = await readProblemsFile(projectRoot);
        const unresolvedProblems = problems.filter(p => p.status === 'UNRESOLVED');

        if (unresolvedProblems.length === 0) {
            console.log('[TREPAN PIVOT] No unresolved problems found');
            return;
        }

        // 4. Match removed techs to unresolved problems
        const pivots = [];
        for (const tech of removedTechs) {
            for (const problem of unresolvedProblems) {
                if (problem.description.toLowerCase().includes(tech.toLowerCase())) {
                    pivots.push({ tech, problem });
                }
            }
        }

        // 5. If pivots detected, trigger evolution
        if (pivots.length > 0) {
            for (const pivot of pivots) {
                console.log(`[TREPAN PIVOT] 🔄 PIVOT DETECTED: Removed ${pivot.tech} after problem`);

                // Call /evolve_memory
                await triggerEvolution(projectRoot, pivot.tech);
            }
        }
    } catch (error) {
        console.error('[TREPAN PIVOT] Error detecting pivot:', error);
    }
}

/**
 * Get git diff for a file
 * @param {string} fileName - Full path to file
 * @param {string} projectRoot - Workspace root
 * @returns {Promise<string|null>} - Git diff output or null
 */
async function getGitDiff(fileName, projectRoot) {
    try {
        const { exec } = require('child_process');
        const { promisify } = require('util');
        const execAsync = promisify(exec);

        const relativePath = path.relative(projectRoot, fileName);
        const { stdout } = await execAsync(`git diff HEAD "${relativePath}"`, {
            cwd: projectRoot,
            timeout: 5000
        });

        return stdout;
    } catch (error) {
        console.log('[TREPAN PIVOT] Git diff failed:', error.message);
        return null;
    }
}

/**
 * Detect removed technologies from git diff
 * @param {string} diff - Git diff output
 * @returns {string[]} - Array of removed technology names
 */
function detectRemovedTechs(diff) {
    const removedLines = diff.split('\n')
        .filter(line => line.startsWith('-') && !line.startsWith('---'))
        .map(line => line.substring(1).trim());

    const techs = [];
    const patterns = [
        /import\s+(\w+)/,                    // Python: import torch
        /from\s+(\w+)\s+import/,             // Python: from cuda import
        /require\(['"](\w+)['"]\)/,          // JS: require('mongodb')
        /import.*from\s+['"](\w+)['"]/,      // JS: import x from 'react'
        /import\s+['"](\w+)['"]/,            // JS: import 'cuda'
    ];

    for (const line of removedLines) {
        for (const pattern of patterns) {
            const match = line.match(pattern);
            if (match) {
                techs.push(match[1].toLowerCase());
            }
        }
    }

    return [...new Set(techs)]; // Remove duplicates
}

/**
 * Read and parse problems_and_resolutions.md
 * @param {string} projectRoot - Workspace root
 * @returns {Promise<Array>} - Array of problem objects
 */
async function readProblemsFile(projectRoot) {
    try {
        const problemsPath = path.join(projectRoot, '.trepan', 'problems_and_resolutions.md');
        const content = fs.readFileSync(problemsPath, 'utf-8');
        return parseProblems(content);
    } catch (error) {
        console.log('[TREPAN PIVOT] Could not read problems file:', error.message);
        return [];
    }
}

/**
 * Parse problems from markdown content
 * @param {string} content - Markdown content
 * @returns {Array} - Array of problem objects
 */
function parseProblems(content) {
    const problems = [];
    const problemBlocks = content.split(/##\s+Problem\s+#\d+:/);

    for (const block of problemBlocks.slice(1)) {
        const statusMatch = block.match(/\*\*Status\*\*:\s*(\w+)/);
        const status = statusMatch ? statusMatch[1] : 'UNKNOWN';

        problems.push({
            description: block,
            status: status
        });
    }

    return problems;
}

/**
 * Trigger evolutionary memory update
 * @param {string} projectRoot - Workspace root
 * @param {string} tech - Technology that was pivoted away from
 */
async function triggerEvolution(projectRoot, tech) {
    try {
        const cfg = vscode.workspace.getConfiguration("trepan");
        let serverUrl = cfg.get("serverUrl") ?? "http://127.0.0.1:8001";

        // Try to use discovered URL
        const discoveredUrl = await discoverServerURL();
        if (discoveredUrl) {
            serverUrl = discoveredUrl;
        }

        console.log(`[TREPAN PIVOT] Calling /evolve_memory at ${serverUrl}`);

        const response = await fetchWithTimeout(`${serverUrl}/evolve_memory`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ project_path: projectRoot })
        }, 60000); // 60 second timeout for Ollama processing

        if (response.ok) {
            const result = await response.json();
            console.log('[TREPAN PIVOT] ✅ Evolution triggered successfully:', result);

            // Show notification to user
            vscode.window.showInformationMessage(
                `✅ Trepan learned from pivot: Added rule "DO NOT USE ${tech.toUpperCase()}"`
            );
        } else {
            console.error('[TREPAN PIVOT] Evolution failed:', response.status, response.statusText);
        }
    } catch (error) {
        console.error('[TREPAN PIVOT] Error triggering evolution:', error);
    }
}

// ─── Activation ──────────────────────────────────────────────────────────────

/**
 * @param {vscode.ExtensionContext} context
 */
function activate(context) {
    console.log("🛡️ Trepan Gatekeeper: Airbag active");

    context.subscriptions.push(
        vscode.window.registerWebviewViewProvider("trepan.explorer", trepanSidebarProvider)
    );

    // Initialize Output Channel (Global Singleton)
    outputChannel = vscode.window.createOutputChannel("Trepan Gatekeeper");
    context.subscriptions.push(outputChannel);
    
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

                const processorMode = vscode.workspace.getConfiguration("trepan").get("processor_mode") || "GPU";
                const response = await fetchWithTimeout(`${serverUrl}/initialize_project`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        mode: selected.id,
                        project_path: projectPath,
                        processor_mode: processorMode
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

    let toggleProcessorCommand = vscode.commands.registerCommand('trepan.toggleProcessor', async () => {
        const cfg = vscode.workspace.getConfiguration("trepan");
        const currentMode = cfg.get("processor_mode") ?? "GPU";
        
        const selection = await vscode.window.showQuickPick([
            { label: "GPU", description: "Use Ollama/HuggingFace GPU Acceleration (Default)", picked: currentMode === "GPU" },
            { label: "CPU", description: "Use Local CPU Inference (Lower performance)", picked: currentMode === "CPU" }
        ], {
            placeHolder: `Select Trepan Inference Processor (Current: ${currentMode})`,
            title: "🛡️ Trepan: Processor Configuration"
        });

        if (selection) {
            const newMode = selection.label;
            await cfg.update("processor_mode", newMode, vscode.ConfigurationTarget.Global);
            vscode.window.showInformationMessage(
                `🛡️ Trepan: Switched to ${newMode} mode. This setting will be applied to your next audit.`
            );
        }
    });

    context.subscriptions.push(askCommand, openLedgerCommand, reviewChangesCommand, initializeProjectCommand, toggleProcessorCommand);

    // Periodic server health check
    checkServerHealth();
    const healthTimer = setInterval(checkServerHealth, 30_000);
    context.subscriptions.push({ dispose: () => clearInterval(healthTimer) });

    // ── THE AIRBAG ────────────────────────────────────────────────────────────
    const saveHook = vscode.workspace.onWillSaveTextDocument((event) => {
        // Keep this synchronous and lightweight: immediately hand off the real work
        // into a Promise passed to event.waitUntil so any synchronous exceptions
        // are avoided by design.
        console.log('[TREPAN DEBUG] Save event triggered for:', event.document.fileName, 'Reason:', event.reason);

        event.waitUntil((async () => {
            try {
                // Only trigger on explicit manual saves (Ctrl+S / Cmd+S). Ignore auto-saves on focus out/delay.
                if (event.reason !== vscode.TextDocumentSaveReason.Manual) {
                    console.log('[TREPAN DEBUG] Skipping auto-save event. Reason != Manual.');
                    return;
                }

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

                // Check Server Offline
                if (!serverOnline) {
                    const enforcementMode = cfg.get("enforcementMode") ?? "Soft";
                    if (enforcementMode === "Strict") {
                        console.warn('[TREPAN DEBUG] Server is OFFLINE. Strict mode enforcing BLOCK.');
                        vscode.window.showErrorMessage(`🛑 Trepan Strict Mode: Server is OFFLINE. Save blocked.`, { modal: true });
                        throw new Error("Trepan Strict Mode: Server is offline. Save blocked.");
                    }
                    console.warn('[TREPAN DEBUG] Server is OFFLINE. Airbag failing open for this save.');
                    return;
                }

                // Queue the evaluation sequentially to protect the GPU
                await saveEvaluationQueue.enqueue(() => evaluateSave(event.document));
            } catch (error) {
                console.error('[TREPAN ERROR] Save listener async task failed:', error);
                try { vscode.window.showErrorMessage(`Trepan Extension Crash: ${error.message}`); } catch (e) { /* swallow */ }
                // Re-throw to let VS Code know the save participant failed (preserves previous behavior)
                throw error;
            }
        })());
    });

    const saveDoneHandler = vscode.workspace.onDidSaveTextDocument(async (document) => {
        console.log('[TREPAN] Document Saved:', document.fileName);

        // Check for pivots (evolutionary intelligence)
        const workspaceFolder = vscode.workspace.getWorkspaceFolder(document.uri);
        if (workspaceFolder && serverOnline) {
            const projectRoot = workspaceFolder.uri.fsPath;
            await detectPivot(document, projectRoot);
        }
    });

    // Clear snapshot when file is closed to free memory
    const closeHandler = vscode.workspace.onDidCloseTextDocument((document) => {
        _lastAuditedContent.delete(document.uri.toString());
    });

    context.subscriptions.push(saveHook, saveDoneHandler, closeHandler);
}

// ─── Core Evaluation ─────────────────────────────────────────────────────────

/**
 * Rule Sanctuary: Detects if a document is within the .trepan/ folder
 * Returns true if the file should be auto-accepted without audit
 */
function isRuleSanctuaryPath(document) {
    const relPath = vscode.workspace.asRelativePath(document.uri);
    // Normalize path separators for cross-platform compatibility
    const normalizedPath = relPath.replace(/\\/g, '/');

    // Check if path contains .trepan/ folder
    return normalizedPath.includes('.trepan/') || normalizedPath.startsWith('.trepan/');
}

/**
 * @param {vscode.TextDocument} document
 * @returns {Promise<vscode.TextEdit[]>}
 */
async function evaluateSave(document) {
    const currentContent = document.getText();
    const fileKey = document.uri.toString();

    const cfg = vscode.workspace.getConfiguration("trepan");
    let serverUrl = cfg.get("serverUrl") ?? "http://127.0.0.1:8001";
    const timeoutMs = cfg.get("timeoutMs") ?? 300_000;

    // Use auto-discovery if the configured URL doesn't work
    const discoveredUrl = await discoverServerURL();
    if (discoveredUrl && discoveredUrl !== serverUrl) {
        console.log(`[TREPAN EVAL] Using discovered URL: ${discoveredUrl} instead of configured: ${serverUrl}`);
        serverUrl = discoveredUrl;
        // Update config for future use
        await cfg.update("serverUrl", discoveredUrl, vscode.ConfigurationTarget.Workspace);
    } else if (!discoveredUrl) {
        console.log(`[TREPAN EVAL] ❌ No server available for evaluation`);
        if (cfg.get("enforcementMode") === "Strict") {
            vscode.window.showErrorMessage(`🛑 Trepan Strict Mode: No server available. Save blocked.`, { modal: true });
            throw new Error("Trepan Strict Mode: No server available.");
        }
        return []; // Fail-open: allow save to proceed
    }

    const relPath = vscode.workspace.asRelativePath(document.uri);
    const isPillar = relPath.startsWith(".trepan") && relPath.endsWith(".md");

    // ============================================
    // THE META-GATE: Policing the Law (.trepan/*.md)
    // ============================================
    if (isPillar) {
        const fileName = path.basename(document.fileName);
        const incomingContent = currentContent;

        console.log(`[TREPAN META-GATE] Pillar file save detected: ${fileName}`);

        setStatus("checking");
        trepanSidebarProvider.sendMessage({ type: 'scanning', title: 'Meta-Gate Audit: ' + fileName }, true);
        
        try {
            // Resolve the project root for the specific file being saved (multi-root workspace support)
            const projectPath = vscode.workspace.getWorkspaceFolder(document.uri)?.uri.fsPath
                ?? vscode.workspace.workspaceFolders?.[0]?.uri.fsPath
                ?? '';
            console.log(`[TREPAN META-GATE] Resolved project_path: ${projectPath}`);
            const processorMode = vscode.workspace.getConfiguration("trepan").get("processor_mode") || "GPU";
            const res = await fetchWithTimeout(`${serverUrl}/evaluate_pillar`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ 
                    filename: fileName, 
                    incoming_content: incomingContent, 
                    project_path: projectPath,
                    processor_mode: processorMode
                }),
            }, timeoutMs);

            if (!res.ok) {
                console.warn(`Trepan: Meta-Gate server returned ${res.status} — failing open`);
                setStatus("online");
                return [];
            }

            const data = await res.json();
            const driftScore = data.drift_score ?? 0;
            const actionResult = data.action;
            const reasoning = data.reasoning || "[No reasoning provided by server]";

            const webviewMessage = {
                type: 'log',
                title: 'Meta-Gate Audit: ' + fileName,
                score: driftScore.toFixed(2),
                action: actionResult,
                reasoning: reasoning,
                filename: fileName,
                fullPath: document.uri.fsPath,
                violations: data.violations || [],
            };
            trepanSidebarProvider.sendMessage(webviewMessage, actionResult === "REJECT");
            await executeAIAssistantActions(reasoning, actionResult, driftScore);

            if (actionResult === "REJECT") {
                const scoreDisplay = driftScore.toFixed(2);
                vscode.window.showErrorMessage(`🛑 Trepan Blocked Save — Context Drift detected (Score: ${scoreDisplay})`, { modal: true });
                throw new Error(`Trepan Gatekeeper: architectural drift detected (score ${scoreDisplay})`);
            }

            setStatus("accepted");
            setTimeout(() => setStatus("online"), 2000);
            _lastAuditedContent.set(fileKey, currentContent);
            return [];
        } catch (err) {
            console.error("Trepan Meta-Gate error:", err);
            setStatus("online");
            return [];
        }
    } else {
        // ============================================
        // THE AIRBAG: Project File Evaluation
        // ============================================
        const fileName = path.basename(document.fileName);
        const totalLines = currentContent.split('\n').length;
        const previousContent = _lastAuditedContent.get(fileKey);

        let codeContent;
        if (!previousContent || totalLines <= LARGE_FILE_THRESHOLD) {
            // First audit or small file — send full content
            codeContent = currentContent;
        } else {
            // Large file with existing snapshot — send diff chunk only
            codeContent = extractAuditChunk(currentContent, previousContent, DIFF_CONTEXT_LINES);
            
            if (codeContent === "") {
                // No changes detected — skip audit entirely
                console.log('[TREPAN] No changes detected since last audit. Skipping.');
                return [];
            }
            
            console.log(`[TREPAN] Diff mode: sending ${codeContent.split('\n').length} lines of ${totalLines} total`);
        }

        const pillars = readPillars(document);

        console.log(`[TREPAN AIRBAG] Document save detected: ${fileName}`);

        setStatus("checking");
        trepanSidebarProvider.sendMessage({ type: 'scanning', title: 'Airbag Audit: ' + fileName }, true);

        try {
            // Resolve the project root for the specific file being saved (multi-root workspace support)
            const projectPath = vscode.workspace.getWorkspaceFolder(document.uri)?.uri.fsPath
                ?? vscode.workspace.workspaceFolders?.[0]?.uri.fsPath
                ?? '';
            console.log(`[TREPAN AIRBAG] Resolved project_path: ${projectPath}`);
            const processorMode = vscode.workspace.getConfiguration("trepan").get("processor_mode") || "GPU";
            const res = await fetchWithTimeout(`${serverUrl}/evaluate`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    filename: fileName,
                    code_snippet: codeContent,
                    pillars: pillars,
                    project_path: projectPath,
                    processor_mode: processorMode
                }),
            }, timeoutMs);

            if (!res.ok) {
                console.warn(`Trepan: Airbag server returned ${res.status} — failing open`);
                setStatus("online");
                return [];
            }

            const data = await res.json();
            const driftScore = data.drift_score ?? 0;
            const actionResult = data.action;
            const reasoning = data.reasoning || "[No reasoning provided by server]";

            const webviewMessage = {
                type: 'log',
                title: 'Airbag Audit: ' + fileName,
                score: driftScore.toFixed(2),
                action: actionResult,
                reasoning: reasoning,
                filename: fileName,
                fullPath: document.uri.fsPath,
                violations: data.violations || [],
            };

            trepanSidebarProvider.sendMessage(webviewMessage, actionResult === "REJECT");
            await executeAIAssistantActions(reasoning, actionResult, driftScore);

            if (actionResult === "REJECT") {
                const scoreDisplay = driftScore.toFixed(2);
                vscode.window.showErrorMessage(`🛑 Trepan Blocked Save — Context Drift detected (Score: ${scoreDisplay})`, { modal: true });
                throw new Error(`Trepan Airbag: architectural drift detected (score ${scoreDisplay})`);
            }

            setStatus("accepted");
            setTimeout(() => setStatus("online"), 2000);
            _lastAuditedContent.set(fileKey, currentContent);
            return [];
        } catch (err) {
            console.error("Trepan Airbag error:", err);
            setStatus("online");
            return [];
        }
    }
}


// ─── Pillar Reader ────────────────────────────────────────────────────────────

function readPillars(document) {
    // Resolve the correct workspace folder for the given document (multi-root support)
    const workspaceFolder = document
        ? vscode.workspace.getWorkspaceFolder(document.uri)
        : vscode.workspace.workspaceFolders?.[0];

    if (!workspaceFolder) return emptyPillars();

    const trepanDir = path.join(workspaceFolder.uri.fsPath, ".trepan");
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
        outputChannel.appendLine(`[${new Date().toISOString()}] Health Check Status: Failed (Auto-Discovery)`);
        outputChannel.appendLine(`  Solution: Start server with 'python start_server.py --host 0.0.0.0'`);
        
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

        // Enhanced error logging using the global channel
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

        let thoughtMatch = llmResponse.match(/\[THOUGHT\]([\s\S]*?)(?:\[|$)/);
        if (!thoughtMatch) {
            console.log('[TREPAN AI AUTONOMY] No [THOUGHT] section found - continuing without thought heuristics');
            // Continue without returning so this autonomy code cannot block the save/fetch flow.
            thoughtMatch = ['', ''];
        }

        const thought = (thoughtMatch[1] || '').trim().toLowerCase();
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

function fetchWithTimeout(urlStr, options = {}, ms) {
    return new Promise((resolve, reject) => {
        const http = require('http');
        const https = require('https');
        let parsedUrl;

        try {
            parsedUrl = new URL(urlStr);
        } catch (e) {
            return reject(e);
        }

        const client = parsedUrl.protocol === 'https:' ? https : http;
        const reqOptions = {
            hostname: parsedUrl.hostname,
            port: parsedUrl.port,
            path: parsedUrl.pathname + parsedUrl.search,
            method: options.method || 'GET',
            headers: options.headers || {},
            timeout: ms
        };

        const req = client.request(reqOptions, (res) => {
            let data = '';
            res.on('data', chunk => data += chunk);
            res.on('end', () => {
                resolve({
                    ok: res.statusCode >= 200 && res.statusCode < 300,
                    status: res.statusCode,
                    json: async () => JSON.parse(data),
                    text: async () => data
                });
            });
        });

        req.on('timeout', () => {
            req.destroy();
            reject(new Error(`Timeout after ${ms}ms`));
        });

        req.on('error', err => reject(err));

        if (options.body) {
            req.write(typeof options.body === 'string' ? options.body : JSON.stringify(options.body));
        }
        req.end();
    });
}

/**
 * Extracts the changed chunk from a document compared to its last audited snapshot.
 * Returns the changed lines plus DIFF_CONTEXT_LINES of surrounding context.
 * If no snapshot exists or the file is small, returns the full content.
 */
function extractAuditChunk(currentContent, previousContent, contextLines) {
    const currentLines = currentContent.split('\n');
    const previousLines = previousContent.split('\n');

    // Find changed line indices
    const changedIndices = new Set();
    const maxLen = Math.max(currentLines.length, previousLines.length);

    for (let i = 0; i < maxLen; i++) {
        if (currentLines[i] !== previousLines[i]) {
            // Add the changed line plus context window
            for (let c = Math.max(0, i - contextLines); c <= Math.min(currentLines.length - 1, i + contextLines); c++) {
                changedIndices.add(c);
            }
        }
    }

    if (changedIndices.size === 0) {
        // No changes detected — return empty string to skip audit
        return "";
    }

    // Extract the chunk as contiguous numbered lines
    const sortedIndices = Array.from(changedIndices).sort((a, b) => a - b);
    const chunkLines = sortedIndices.map(i => `${i + 1} | ${currentLines[i] || ''}`);
    return chunkLines.join('\n');
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
    constructor() {
        this._lastMessage = null;
    }
    resolveWebviewView(webviewView) {
        this._view = webviewView;
        webviewView.webview.options = { enableScripts: true };
        webviewView.webview.html = this._getHtmlForWebview();

        // If we have a cached message, send it immediately upon resolution
        if (this._lastMessage) {
            this.sendMessage(this._lastMessage);
        }

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

            if (message.command === 'apply_fix') {
                const { line, text, ruleId, reason, filePath } = message;
                
                const relativePath = vscode.workspace.asRelativePath(filePath || '');
                const prompt = `Trepan detected a Rule ${ruleId} violation in file '${relativePath}' on line ${line}.\nReason: ${reason}\nSuggested fix: ${text}\n\nPlease apply this fix.`;
                
                vscode.env.clipboard.writeText(prompt);
                vscode.window.showInformationMessage(`📋 Fix prompt for '${relativePath}' copied to clipboard! Paste it to your IDE Agent.`);
            }
        });
    }
    sendMessage(message, forceFocus = false) {
        this._lastMessage = message;

        if (forceFocus) {
            // Focus the sidebar but PRESERVE focus in the editor so typing isn't interrupted
            vscode.commands.executeCommand("trepan.explorer.focus", { preserveFocus: true });
        }

        // Attempt to send immediately (works if view was already mounted)
        if (this._view) {
            try { this._view.webview.postMessage(message); } catch (e) { console.error(e); }
        }

        // Fire a delayed duplicate message 500ms later to guarantee it catches freshly mounted Webviews.
        setTimeout(() => {
            if (this._view) {
                try { this._view.webview.postMessage(message); } catch (e) { console.error(e); }
            }
        }, 500);
    }
    _getHtmlForWebview() {
        return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline';">
    <title>Trepan Architect</title>
    <style>
        body { font-family: var(--vscode-font-family); padding: 10px; color: var(--vscode-editor-foreground); transition: background-color 0.3s; }
        body.compromised { background-color: rgba(255, 0, 0, 0.1); }
        .thought { color: var(--vscode-terminal-ansiBrightBlack); font-style: italic; white-space: pre-wrap; margin-bottom: 10px; font-size: 0.9em; }
        /* FIX 3: High-density bulletpoint styling */
        .thought-bullets { margin: 0; padding-left: 20px; line-height: 1.4; list-style-type: disc; }
        .thought-bullets li { margin: 2px 0; font-size: 0.9em; color: var(--vscode-terminal-ansiBrightBlack); }
        
        /* FIX 2: DRIFT METER STYLING (Distance-Based Color Coding) */
        .drift-meter { margin: 10px 0; padding: 8px; background-color: var(--vscode-editor-inactiveSelectionBackground); border-radius: 4px; font-size: 0.95em; }
        .drift-label { font-weight: bold; color: var(--vscode-editor-foreground); }
        .drift-score { font-weight: bold; font-size: 1.1em; padding: 2px 6px; border-radius: 3px; }
        .drift-status { font-weight: bold; margin-left: 4px; }
        
        /* Color coding: 0.0 = Green (Healthy), 0.3-0.6 = Yellow (Warning), 0.6+ = Red (Critical) */
        .drift-healthy { color: #4ec9b0; background-color: rgba(78, 201, 176, 0.15); }
        .drift-warning { color: #dcdcaa; background-color: rgba(220, 220, 170, 0.15); }
        .drift-critical { color: #f48771; background-color: rgba(244, 135, 113, 0.15); }
        
        /* Confidence Badges */
        .confidence-high { 
            color: #f48771; 
            background: rgba(244, 135, 113, 0.1);
            border: 1px solid rgba(244, 135, 113, 0.3);
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 0.8em;
            font-weight: bold;
        }
        .confidence-low { 
            color: #dcdcaa; 
            background: rgba(220, 220, 170, 0.1);
            border: 1px solid rgba(220, 220, 170, 0.3);
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 0.8em;
            font-weight: bold;
        }
        
        .action-accept { color: var(--vscode-testing-iconPassed); font-weight: bold; }
        .action-reject { color: var(--vscode-testing-iconFailed); font-weight: bold; }
        .action-error { color: orange; font-weight: bold; }
        .action-warn { color: var(--vscode-terminal-ansiYellow); font-weight: bold; }
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
        
        /* VIOLATION CARD STYLING */
        .violation-card {
            background-color: var(--vscode-editor-inactiveSelectionBackground);
            border-left: 4px solid #f48771;
            border-radius: 4px;
            padding: 12px;
            margin: 10px 0;
            font-size: 0.9em;
        }
        .violation-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
            font-weight: bold;
        }
        .violation-file { color: #4ec9b0; }
        .violation-line { color: #ce9178; font-family: var(--vscode-editor-font-family); }
        .violation-rule { 
            background: rgba(255, 255, 255, 0.1);
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 0.85em;
            color: #dcdcaa;
        }
        .violation-desc {
            margin-top: 6px;
            line-height: 1.4;
            color: var(--vscode-editor-foreground);
        }
        .violation-icon { margin-right: 4px; }
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

        function escapeHtml(unsafe) {
            return (unsafe || '')
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;")
                .replace(/'/g, "&#039;");
        }


        function renderViolations(violations, filePath) {
            try {
                if (!violations) return '';
                
                // Ensure array format (LLM might sometimes output object-wrapped array)
                const list = Array.isArray(violations) ? violations : [];
                if (list.length === 0) return '';
                
                let html = '<div class="violations-container">';
                html += '<h4 style="margin-bottom: 10px;">⚠️ Architectural Violations</h4>';
                
                list.forEach(v => {
                    if (!v) return;
                    const confClass = (v.confidence || '').toUpperCase() === 'LOW' ? 'confidence-low' : 'confidence-high';
                    
                    html += '<div class="violation-card" style="border-left: 3px solid var(--vscode-errorForeground); margin-bottom: 12px; padding: 10px; background: rgba(255, 255, 255, 0.05);">';
                    html += '    <div class="violation-header" style="margin-bottom: 6px; display: flex; justify-content: space-between;">';
                    html += '        <span class="violation-file">📍 Line: ' + (v.line_number || '?') + '</span>';
                    html += '        <span class="' + confClass + '">' + (v.confidence || 'HIGH') + ' CONFIDENCE</span>';
                    html += '    </div>';
                    html += '    <div class="violation-rule" style="font-weight: bold; margin-bottom: 4px; color: #dcdcaa;">📋 Rule: ' + escapeHtml(v.rule_id || 'Rule') + '</div>';
                    html += '    <div class="violation-desc" style="font-style: italic; color: var(--vscode-editor-foreground); margin-bottom: 8px;">🚫 Reason: ' + escapeHtml(v.violation || 'Check server logs') + '</div>';
                    
                    if (v.data_flow) {
                        html += '    <div style="font-size: 0.85em; background: rgba(0,0,0,0.2); padding: 4px 8px; border-radius: 4px; margin: 8px 0; font-family: monospace;">';
                        html += '        <span style="color: #569cd6;">Flow:</span> ' + escapeHtml(v.data_flow);
                        html += '    </div>';
                    }
                    
                    if (v.suggested_fix) {
                        html += '    <div style="margin-top: 10px;">';
                        html += '        <button class="btn btn-warn apply-fix-btn" data-line="' + (v.line_number || 0) + '" data-rule-id="' + escapeHtml(v.rule_id || 'Rule') + '" data-reason="' + escapeHtml(v.violation || 'Architectural Drift') + '" data-fix="' + escapeHtml(v.suggested_fix) + '" data-file-path="' + (filePath || '') + '">🪄 Apply Fix</button>';
                        html += '    </div>';
                    }
                    html += '</div>';
                });
                
                html += '</div>';
                return html;
            } catch (err) {
                console.error('[WEBVIEW ERROR] renderViolations failed:', err);
                return '<p style="color: var(--vscode-errorForeground);">⚠️ Error rendering violations. See developer console.</p>';
            }
        }

        window.addEventListener('message', event => {
            const message = event.data;
            console.log("WEBVIEW RECEIVED:", message);
            // ENHANCED DEBUG LOGGING
            console.log('[WEBVIEW DEBUG] ═══════════════════════════════════════');
            console.log('[WEBVIEW DEBUG] Message received!');
            console.log('[WEBVIEW DEBUG] Message type:', message.type);
            console.log('[WEBVIEW DEBUG] Message keys:', Object.keys(message));
            console.log('[WEBVIEW DEBUG] Action:', message.action);
            console.log('[WEBVIEW DEBUG] Score:', message.score);
            console.log('[WEBVIEW DEBUG] Reasoning exists?', !!message.reasoning);
            console.log('[WEBVIEW DEBUG] Violations count:', message.violations ? message.violations.length : 0);
            console.log('[WEBVIEW DEBUG] Reasoning preview:', (message.reasoning || '').substring(0, 150));
            console.log('[WEBVIEW DEBUG] ═══════════════════════════════════════');
            
            // Debug logging: show what webview receives
            if (message.type === 'log') {
                console.log('[WEBVIEW DEBUG] Received log message details:', {
                    action: message.action,
                    score: message.score,
                    reasoning_length: (message.reasoning || '').length,
                    violations_count: message.violations ? message.violations.length : 0
                });
            }
            
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

            // ERROR: show server failure while evaluating
            if (message.type === 'error') {
                contentDiv.innerHTML = '<h2>🏛️ Trepan Vault Access</h2><div class="action-card" style="border-left: 4px solid var(--vscode-errorForeground);"><p class="action-error">⚠️ Trepan Error</p><p style="color: var(--vscode-editor-foreground); font-size: 0.9em;">' + message.message + '</p><p style="color: var(--vscode-terminal-ansiYellow); font-style: italic; font-size: 0.85em; margin-top: 8px;">Audit failed — check server logs for details.</p></div>';
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
                
                // FIX 2: DRIFT METER WITH COLOR CODING (Distance-Based)
                // 0.0 = Perfect (Green), 0.3-0.6 = Warning (Yellow), 0.6+ = Critical (Red)
                if (message.score) {
                    const score = parseFloat(message.score);
                    let scoreClass = 'drift-healthy';  // Default green
                    let scoreLabel = 'Healthy';
                    
                    if (score >= 0.6) {
                        scoreClass = 'drift-critical';
                        scoreLabel = 'Critical';
                    } else if (score >= 0.3) {
                        scoreClass = 'drift-warning';
                        scoreLabel = 'Warning';
                    }
                    
                    html += '<div class="drift-meter">';
                    html += '<span class="drift-label">Architectural Distance:</span> ';
                    html += '<span class="drift-score ' + scoreClass + '">' + message.score + '</span> ';
                    html += '<div style="margin-top: 5px; font-size: 0.85em; opacity: 0.8;">';
                    html += 'Violation occurred after rule was previously satisfied → <b>Context Drift detected</b>';
                    html += '</div>';
                    html += '</div>';
                }

                // THOUGHT sequestered for terminal review (UI remains lean)
/*
                const reasoningText = message.reasoning;
                if (reasoningText) {
                    html += '<div class="thought">' + escapeHtml(reasoningText) + '</div>';
                }
*/

                if (message.action === 'ACCEPT') {
                    html += '<p class="action-accept">✅ Verdict: ACCEPT</p>';
                    // Only show violations on ACCEPT if there is actual drift (score > 0)
                    if (message.violations && message.violations.length > 0 && parseFloat(message.score || 0) > 0) {
                        html += renderViolations(message.violations, message.fullPath);
                    }

                } else if (message.action === 'REJECT') {
                    html += '<p class="action-reject">🛑 Verdict: REJECT</p>';
                    if (message.violations && message.violations.length > 0) {
                        html += renderViolations(message.violations, message.fullPath);
                    } else {
                        html += '<p style="color: var(--vscode-terminal-ansiYellow); font-style: italic; margin-top: 8px;">⚠️ Violation data missing (Check server logs)</p>';
                    }
                    html += '<div style="margin-top:10px;">';
                    html += '<button class="btn btn-revert" id="revertBtn">↩️ Revert Save</button>';
                    html += '<button class="btn btn-warn" id="overrideBtn">⚠️ Force Override</button>';
                    html += '</div>';

                } else if (message.action === 'ERROR') {
                    html += '<p class="action-error">⚠️ Verdict: ERROR (AI hallucinated — no valid output)</p>';
                    if (message.violations && message.violations.length > 0) {
                        html += renderViolations(message.violations, message.fullPath);
                    } else {
                        html += '<p style="color: var(--vscode-terminal-ansiYellow); font-style: italic; margin-top: 8px;">⚠️ Evaluation failed (AI output malformed)</p>';
                    }

                } else if (message.action === 'VAULT_COMPROMISED') {
                    html += '<p class="action-compromised">🚨 VAULT COMPROMISED</p>';

                } else if (message.action === 'WARN') {
                    // FIX 4: Handle partial audits (missing [ACTION] tag)
                    html += '<p class="action-warn">⚠️ Verdict: INCOMPLETE AUDIT</p>';
                    html += '<p style="color: var(--vscode-terminal-ansiYellow); font-size: 0.9em; margin-top: 4px;">Parser detected truncated output - [ACTION] tag missing</p>';
                    if (message.violations && message.violations.length > 0) {
                        html += renderViolations(message.violations, message.fullPath);
                    } else {
                         html += '<p style="color: var(--vscode-terminal-ansiYellow); font-style: italic; margin-top: 8px;">⚠️ Truncated output: No violations extracted</p>';
                    }
                    // Buttons are disabled for incomplete audits
                    html += '<div style="margin-top:10px;">';
                    html += '<button class="btn btn-revert" disabled style="opacity: 0.5; cursor: not-allowed;">↩️ Revert Save (Disabled)</button>';
                    html += '<button class="btn btn-warn" disabled style="opacity: 0.5; cursor: not-allowed;">⚠️ Force Override (Disabled)</button>';
                    html += '<p style="color: var(--vscode-terminal-ansiRed); font-size: 0.85em; margin-top: 8px;">⚠️ Accept/Reject buttons disabled - audit incomplete</p>';
                    html += '</div>';

                } else {
                    if (message.action) html += '<p>Verdict: ' + message.action + '</p>';
                    if (message.violations && message.violations.length > 0) {
                        html += renderViolations(message.violations, message.fullPath);
                    }
                }

                entry.innerHTML = html;
                contentDiv.innerHTML = '<h2>🏛️ Trepan Vault Access</h2>';
                contentDiv.appendChild(entry);

                // Wire up buttons via event delegation on the entry element
                entry.addEventListener('click', (e) => {
                    const target = e.target;
                    if (target.id === 'revertBtn') {
                        vscode.postMessage({ command: 'revert_save', filename: message.filename });
                    } else if (target.id === 'overrideBtn') {
                        vscode.postMessage({ command: 'force_override' });
                    } else if (target.classList.contains('apply-fix-btn')) {
                        const line = parseInt(target.getAttribute('data-line'));
                        const text = target.getAttribute('data-fix');
                        const ruleId = target.getAttribute('data-rule-id');
                        const reason = target.getAttribute('data-reason');
                        const filePath = target.getAttribute('data-file-path');
                        vscode.postMessage({ command: 'apply_fix', line, text, ruleId, reason, filePath });
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

/**
 * Hands off an AI-suggested fix to the Antigravity IDE Agent.
 * @param {number} line - The 1-indexed line number
 * @param {string} text - The replacement text (or whole code)
 */
// application logic end

// ─── Exports ─────────────────────────────────────────────────────────────────

function deactivate() { }

module.exports = { activate, deactivate };


