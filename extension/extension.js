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
const _lastSentContent = new Map(); // key: document.uri.toString(), value: string
const DIFF_CONTEXT_LINES = 10; // lines of context above and below each changed region
const LARGE_FILE_THRESHOLD = 150; // lines — files above this use diff mode
const FIRST_AUDIT_LINE_LIMIT = 200; // Files above this skip first-save audit

// Model selection state
let _selectedModel = "llama3.1:8b"; // Default to Fast mode
const MODEL_OPTIONS = [
    {
        label: "⚡ Fast Mode — Llama 3.1:8b",
        description: "~5 seconds per audit. Good accuracy. Best for active coding.",
        model: "llama3.1:8b"
    },
    {
        label: "🧠 Smart Mode — DeepSeek-R1",
        description: "~11 seconds per audit. Better reasoning. Best for security review.",
        model: "deepseek-r1:latest"
    }
];

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

    // Export context for use in other functions
    if (!global.trepanContext) {
        global.trepanContext = context;
    }

    context.subscriptions.push(
        vscode.window.registerWebviewViewProvider("trepan.explorer", trepanSidebarProvider)
    );

    // Initialize Output Channel (Global Singleton)
    outputChannel = vscode.window.createOutputChannel("Trepan Gatekeeper");
    context.subscriptions.push(outputChannel);
    
    // Status bar pill
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBarItem.command = "trepan.status";
    updateStatusBar(context);
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

    const selectModelCmd = vscode.commands.registerCommand(
        "trepan.selectModel",
        async () => {
            const picked = await vscode.window.showQuickPick(
                MODEL_OPTIONS.map(opt => ({
                    label: opt.label,
                    description: opt.description,
                    model: opt.model
                })),
                {
                    placeHolder: `Current model: ${_selectedModel}. Choose your audit mode.`,
                    title: "Trepan: Select Audit Model"
                }
            );

            if (picked) {
                _selectedModel = picked.model;
                const modeName = picked.model === "llama3.1:8b" ? "Fast Mode ⚡" : "Smart Mode 🧠";
                vscode.window.showInformationMessage(
                    `Trepan switched to ${modeName} (${picked.model})`
                );
                console.log(`[TREPAN] Model switched to: ${_selectedModel}`);
            }
        }
    );

    const auditFolderCmd = vscode.commands.registerCommand(
        "trepan.auditEntireFolder",
        async () => {
            const workspaceFolders = vscode.workspace.workspaceFolders;
            if (!workspaceFolders) {
                vscode.window.showErrorMessage("Trepan: No workspace folder open.");
                return;
            }
            
            // Step 1: Let user pick which folder to audit
            let targetFolder;
            
            if (workspaceFolders.length === 1) {
                // Only one workspace folder, use it
                targetFolder = workspaceFolders[0].uri;
            } else {
                // Multiple workspace folders, let user choose
                const folderChoice = await vscode.window.showQuickPick(
                    workspaceFolders.map(folder => ({
                        label: folder.name,
                        description: folder.uri.fsPath,
                        uri: folder.uri
                    })),
                    {
                        placeHolder: "Select folder to audit",
                        title: "🛡️ Trepan: Choose Folder for Full Audit"
                    }
                );
                
                if (!folderChoice) {
                    return; // User cancelled
                }
                
                targetFolder = folderChoice.uri;
            }
            
            // Alternatively, let user pick any subfolder
            const pickSubfolder = await vscode.window.showQuickPick([
                {
                    label: "$(folder) Audit entire workspace folder",
                    description: targetFolder.fsPath,
                    choice: "root"
                },
                {
                    label: "$(folder-opened) Pick a specific subfolder",
                    description: "Browse and select a subfolder to audit",
                    choice: "subfolder"
                }
            ], {
                placeHolder: "Audit entire folder or pick a subfolder?",
                title: "🛡️ Trepan: Folder Audit Scope"
            });
            
            if (!pickSubfolder) {
                return; // User cancelled
            }
            
            if (pickSubfolder.choice === "subfolder") {
                const selectedFolder = await vscode.window.showOpenDialog({
                    canSelectFiles: false,
                    canSelectFolders: true,
                    canSelectMany: false,
                    defaultUri: targetFolder,
                    openLabel: "Select Folder to Audit"
                });
                
                if (!selectedFolder || selectedFolder.length === 0) {
                    return; // User cancelled
                }
                
                targetFolder = selectedFolder[0];
            }
            
            const context = global.trepanContext;
            const isPowerMode = context?.globalState.get('trepan.mode') === 'cloud';
            
            // Get server URL
            const cfg = vscode.workspace.getConfiguration("trepan");
            let serverUrl = cfg.get("serverUrl") ?? "http://127.0.0.1:8001";
            
            // Try to use discovered URL if available
            const discoveredUrl = await discoverServerURL();
            if (discoveredUrl) {
                serverUrl = discoveredUrl;
            }
            
            // Get current model for latency calculation
            let currentModel = _selectedModel; // Local mode model
            if (isPowerMode) {
                const provider = context?.globalState.get('trepan.provider') || 'openrouter';
                const modelKey = provider === 'openrouter' ? 'openrouter_model' : 'groq_model';
                currentModel = context?.globalState.get(modelKey) || '';
            }
            
            // Determine latency based on model
            let interFileLatency = 3000; // Default 3 seconds for llama3
            if (currentModel.toLowerCase().includes('llama-4') || currentModel.toLowerCase().includes('llama4')) {
                interFileLatency = 1500; // 1.5 seconds for llama4
            }
            
            console.log(`[TREPAN FOLDER AUDIT] Using model: ${currentModel}, inter-file latency: ${interFileLatency}ms`);
            
            // Warn about cost if Power Mode
            if (isPowerMode) {
                const confirm = await vscode.window.showWarningMessage(
                    "🔍 Trepan: Full folder audit will send every file to the Cloud API. This may incur API costs. Continue?",
                    "Audit Entire Folder",
                    "Cancel"
                );
                if (confirm !== "Audit Entire Folder") return;
            }
            
            // File extensions to audit
            const AUDITABLE_EXTENSIONS = ['.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.go', '.rb', '.php'];
            
            // Directories to skip
            const SKIP_DIRS = new Set([
                'node_modules', '.git', 'dist', 'build', 'venv', '.venv',
                '__pycache__', '.trepan', 'trepan_vault', 'coverage', '.next'
            ]);
            
            // Collect all files in the target folder
            const relativePath = vscode.workspace.asRelativePath(targetFolder);
            const searchPattern = new vscode.RelativePattern(targetFolder, '**/*');
            const excludePattern = `{${[...SKIP_DIRS].map(d => `**/${d}/**`).join(',')}}`;
            
            const allFiles = await vscode.workspace.findFiles(searchPattern, excludePattern);
            
            const auditableFiles = allFiles.filter(f => 
                AUDITABLE_EXTENSIONS.some(ext => f.fsPath.endsWith(ext))
            );
            
            if (auditableFiles.length === 0) {
                vscode.window.showInformationMessage(`Trepan: No auditable files found in ${relativePath}.`);
                return;
            }
            
            const modeLabel = isPowerMode ? "☁️ Cloud" : "⚡ Local";
            vscode.window.showInformationMessage(
                `🛡️ Trepan: Starting folder audit of ${auditableFiles.length} files in "${relativePath}" [${modeLabel} Mode]...`
            );
            
            const violations = [];
            const errors = [];
            const errorDetails = {}; // Store detailed error info
            let processed = 0;
            let skipped = 0;
            
            // Progress notification
            await vscode.window.withProgress({
                location: vscode.ProgressLocation.Notification,
                title: "🛡️ Trepan: Auditing folder...",
                cancellable: true
            }, async (progress, token) => {
                
                for (let i = 0; i < auditableFiles.length; i++) {
                    const fileUri = auditableFiles[i];
                    
                    if (token.isCancellationRequested) {
                        console.log("[TREPAN FOLDER AUDIT] Cancelled by user");
                        break;
                    }
                    
                    const fileName = fileUri.fsPath.split(/[/\\]/).pop();
                    const fileRelativePath = vscode.workspace.asRelativePath(fileUri);
                    
                    progress.report({
                        message: `${processed + 1}/${auditableFiles.length} — ${fileRelativePath}`,
                        increment: 100 / auditableFiles.length
                    });
                    
                    try {
                        const document = await vscode.workspace.openTextDocument(fileUri);
                        const code = document.getText();
                        
                        if (!code.trim()) {
                            skipped++;
                            continue;
                        }
                        
                        // Skip very large files over 500 lines in local mode
                        const lineCount = code.split('\n').length;
                        if (!isPowerMode && lineCount > 500) {
                            console.log(`[TREPAN FOLDER AUDIT] Skipping large file: ${fileRelativePath} (${lineCount} lines)`);
                            skipped++;
                            continue;
                        }
                        
                        // Pillars are loaded server-side from project_path
                        const pillars = {};
                        const processorMode = "GPU";
                        
                        const response = await fetchWithTimeout(`${serverUrl}/evaluate`, {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({
                                filename: fileName,
                                code_snippet: code,
                                pillars: pillars,
                                project_path: vscode.workspace.workspaceFolders[0].uri.fsPath,
                                processor_mode: processorMode,
                                model_name: _selectedModel,
                                power_mode: isPowerMode
                            }),
                        }, 60000);
                        
                        if (!response.ok) {
                            const errorText = await response.text().catch(() => 'Unable to read error response');
                            const errorMsg = `HTTP ${response.status}: ${errorText}`;
                            console.error(`[TREPAN FOLDER AUDIT] Server error on ${fileRelativePath}: ${errorMsg}`);
                            errors.push(fileRelativePath);
                            errorDetails[fileRelativePath] = errorMsg;
                            processed++;
                            continue;
                        }
                        
                        const result = await response.json();
                        
                        if (result.action === "REJECT" && result.violations?.length > 0) {
                            for (const v of result.violations) {
                                violations.push({
                                    file: fileRelativePath,
                                    line: v.line_number || 0,
                                    rule: v.rule_name || v.rule_id,
                                    reason: v.violation,
                                    confidence: v.confidence
                                });
                            }
                        }
                        
                        processed++;
                        
                        // Smart token-aware latency (except for the last file)
                        if (i < auditableFiles.length - 1) {
                            // Load system rules for token estimation
                            const systemRules = await loadSystemRules();
                            const systemPrompt = systemRules || '';
                            
                            // Token estimation: ~4 characters per token
                            const estimatedTokens = (systemPrompt.length + code.length) / 4;
                            
                            // Target: 30,000 tokens per minute
                            const TARGET_TPM = 30000;
                            
                            // Calculate dynamic delay in milliseconds
                            let delayMs = (estimatedTokens / TARGET_TPM) * 60000;
                            
                            // Minimum 300ms safety net for RPM limits
                            delayMs = Math.max(delayMs, 300);
                            
                            console.log(`[TREPAN FOLDER AUDIT] Smart latency: ${Math.round(delayMs)}ms (${Math.round(estimatedTokens)} tokens)`);
                            await new Promise(resolve => setTimeout(resolve, delayMs));
                        }
                        
                    } catch (err) {
                        const errorMsg = `${err.name}: ${err.message}`;
                        console.error(`[TREPAN FOLDER AUDIT] Exception on ${fileRelativePath}:`, err);
                        console.error(`[TREPAN FOLDER AUDIT] Stack trace:`, err.stack);
                        errors.push(fileRelativePath);
                        errorDetails[fileRelativePath] = errorMsg;
                        processed++;
                    }
                }
            });
            
            // Show results in output channel
            const auditOutputChannel = vscode.window.createOutputChannel("Trepan — Folder Audit");
            auditOutputChannel.clear();
            auditOutputChannel.appendLine(`🛡️ TREPAN FOLDER AUDIT RESULTS`);
            auditOutputChannel.appendLine(`${'='.repeat(60)}`);
            auditOutputChannel.appendLine(`Folder: ${relativePath}`);
            auditOutputChannel.appendLine(`Mode: ${isPowerMode ? "☁️ Power Mode (Cloud API)" : "⚡ Local Mode (Llama)"}`);
            auditOutputChannel.appendLine(`Model: ${currentModel}`);
            auditOutputChannel.appendLine(`Inter-file latency: ${interFileLatency}ms`);
            auditOutputChannel.appendLine(`Files scanned: ${processed}`);
            auditOutputChannel.appendLine(`Files skipped: ${skipped}`);
            auditOutputChannel.appendLine(`Violations found: ${violations.length}`);
            auditOutputChannel.appendLine(`Errors: ${errors.length}`);
            auditOutputChannel.appendLine(`${'='.repeat(60)}\n`);
            
            // Group violations by file for reporting
            const byFile = {};
            for (const v of violations) {
                if (!byFile[v.file]) byFile[v.file] = [];
                byFile[v.file].push(v);
            }
            
            if (violations.length === 0) {
                auditOutputChannel.appendLine("✅ No violations found. Codebase is clean.");
            } else {
                auditOutputChannel.appendLine(`🚨 ${violations.length} VIOLATION(S) DETECTED:\n`);
                for (const [file, fileViolations] of Object.entries(byFile)) {
                    auditOutputChannel.appendLine(`📄 ${file}`);
                    for (const v of fileViolations) {
                        auditOutputChannel.appendLine(`   Line ${v.line} [${v.confidence}] ${v.rule}`);
                        auditOutputChannel.appendLine(`   → ${v.reason}`);
                    }
                    auditOutputChannel.appendLine('');
                }
            }
            
            if (errors.length > 0) {
                auditOutputChannel.appendLine(`\n⚠️ Failed to audit ${errors.length} file(s):`);
                errors.forEach(f => {
                    auditOutputChannel.appendLine(`   • ${f}`);
                    if (errorDetails[f]) {
                        auditOutputChannel.appendLine(`     Error: ${errorDetails[f]}`);
                    }
                });
            }
            
            auditOutputChannel.show();
            
            // Summary notification
            if (violations.length === 0) {
                vscode.window.showInformationMessage(
                    `✅ Trepan: Folder audit complete — ${processed} files clean`
                );
            } else {
                const fileCount = Object.keys(byFile).length;
                vscode.window.showWarningMessage(
                    `⚠️ Trepan: Found ${violations.length} violation(s) in ${fileCount} files — see Output panel`
                );
            }
        }
    );

    const configureBYOKCmd = vscode.commands.registerCommand(
        "trepan.configureBYOK",
        async () => {
            try {
                console.log("[TREPAN BYOK] Starting configuration flow...");
                
                // Step 1: Select Provider
                const providerChoice = await vscode.window.showQuickPick([
                    {
                        label: "$(cloud) OpenRouter",
                        description: "Access to Claude, GPT-4, and 100+ models",
                        detail: "Best for variety and cutting-edge models",
                        provider: "openrouter"
                    },
                    {
                        label: "$(zap) Groq",
                        description: "Ultra-fast inference with Llama models",
                        detail: "Best for speed (up to 10x faster)",
                        provider: "groq"
                    }
                ], {
                    placeHolder: "Select your cloud provider",
                    title: "🔧 Trepan Power Mode - Choose Provider"
                });
                
                if (!providerChoice) {
                    console.log("[TREPAN BYOK] Provider selection cancelled");
                    return;
                }
                
                const provider = providerChoice.provider;
                console.log(`[TREPAN BYOK] Provider selected: ${provider}`);
                
                // Save provider selection
                await context.globalState.update('trepan.provider', provider);
                
                // Provider-specific configuration
                const providerConfig = {
                    openrouter: {
                        keyName: "openrouter_api_key",
                        modelKey: "openrouter_model",
                        defaultModel: "anthropic/claude-3.5-sonnet",
                        keyPlaceholder: "sk-or-v1-...",
                        displayName: "OpenRouter"
                    },
                    groq: {
                        keyName: "groq_api_key",
                        modelKey: "groq_model",
                        defaultModel: "meta-llama/llama-4-scout-17b-16e-instruct",
                        keyPlaceholder: "gsk_...",
                        displayName: "Groq"
                    }
                };
                
                const config = providerConfig[provider];
                
                // Check for existing credentials
                const existingKey = await context.secrets.get(config.keyName);
                const existingModel = context.globalState.get(config.modelKey) || config.defaultModel;
                
                console.log(`[TREPAN BYOK] Existing credentials for ${provider}: key=${existingKey ? 'EXISTS' : 'NONE'}, model=${existingModel}`);
                
                // If credentials exist, show settings menu
                if (existingKey) {
                    const maskedKey = '•'.repeat(Math.min(existingKey.length, 32));
                    
                    const action = await vscode.window.showQuickPick([
                        {
                            label: "$(key) API Key",
                            description: maskedKey,
                            detail: `Click to update your ${config.displayName} API key`,
                            action: "editKey"
                        },
                        {
                            label: "$(symbol-namespace) Model",
                            description: existingModel,
                            detail: "Click to change the model",
                            action: "editModel"
                        },
                        {
                            label: "$(testing-passed-icon) Test Connection",
                            description: "Verify your credentials work",
                            detail: `Send a test request to ${config.displayName}`,
                            action: "test"
                        },
                        {
                            label: "$(arrow-left) Change Provider",
                            description: `Currently using ${config.displayName}`,
                            detail: "Switch to a different cloud provider",
                            action: "changeProvider"
                        }
                    ], {
                        placeHolder: `${config.displayName} Settings - Select what to edit`,
                        title: `🔧 Trepan Power Mode - ${config.displayName}`
                    });
                    
                    if (!action) {
                        console.log("[TREPAN BYOK] Settings menu cancelled");
                        return;
                    }
                    
                    if (action.action === "changeProvider") {
                        // Recursively call configureBYOK to start over
                        await vscode.commands.executeCommand('trepan.configureBYOK');
                        return;
                    }
                    
                    if (action.action === "editKey") {
                        // Edit API Key
                        const newKey = await vscode.window.showInputBox({
                            prompt: `Enter new ${config.displayName} API Key (or press Escape to cancel)`,
                            placeHolder: config.keyPlaceholder,
                            password: true,
                            ignoreFocusOut: true,
                            validateInput: (value) => {
                                if (!value || value.trim().length === 0) {
                                    return "API Key cannot be empty";
                                }
                                return null;
                            }
                        });
                        
                        if (!newKey) {
                            console.log("[TREPAN BYOK] API key update cancelled");
                            return;
                        }
                        
                        // Test new key
                        console.log(`[TREPAN BYOK] Testing new ${provider} API key...`);
                        vscode.window.showInformationMessage(`🔄 Testing ${config.displayName} connection...`);
                        
                        await testProviderConnection(provider, newKey, existingModel);
                        
                        await context.secrets.store(config.keyName, newKey);
                        vscode.window.showInformationMessage(`✅ ${config.displayName} API key updated successfully!`);
                        console.log(`[TREPAN BYOK] ${provider} API key updated`);
                        
                    } else if (action.action === "editModel") {
                        // Edit Model - Show preset list + custom option
                        const modelPresets = provider === "groq" ? [
                            {
                                label: "$(zap) Llama 4 Scout 17B",
                                description: "meta-llama/llama-4-scout-17b-16e-instruct",
                                detail: "Recommended: Fast (30K TPM), 96% accuracy on security tests",
                                modelId: "meta-llama/llama-4-scout-17b-16e-instruct"
                            },
                            {
                                label: "$(symbol-namespace) Llama 3.3 70B Versatile",
                                description: "llama-3.3-70b-versatile",
                                detail: "Slower (12K TPM) but larger model",
                                modelId: "llama-3.3-70b-versatile"
                            },
                            {
                                label: "$(edit) Custom Model ID",
                                description: "Enter a different model",
                                detail: "Specify any Groq model ID manually",
                                modelId: "custom"
                            }
                        ] : [
                            {
                                label: "$(cloud) Claude 3.5 Sonnet",
                                description: "anthropic/claude-3.5-sonnet",
                                detail: "Recommended: Best accuracy",
                                modelId: "anthropic/claude-3.5-sonnet"
                            },
                            {
                                label: "$(edit) Custom Model ID",
                                description: "Enter a different model",
                                detail: "Specify any OpenRouter model ID manually",
                                modelId: "custom"
                            }
                        ];
                        
                        const modelChoice = await vscode.window.showQuickPick(modelPresets, {
                            placeHolder: `Select ${config.displayName} model or choose custom`,
                            title: `🔧 ${config.displayName} Model Selection`
                        });
                        
                        if (!modelChoice) {
                            console.log("[TREPAN BYOK] Model selection cancelled");
                            return;
                        }
                        
                        let newModel;
                        
                        if (modelChoice.modelId === "custom") {
                            // Custom model input
                            newModel = await vscode.window.showInputBox({
                                prompt: `Enter ${config.displayName} Model ID`,
                                placeHolder: config.defaultModel,
                                value: existingModel,
                                ignoreFocusOut: true,
                                validateInput: (value) => {
                                    if (!value || value.trim().length === 0) {
                                        return "Model ID cannot be empty";
                                    }
                                    return null;
                                }
                            });
                            
                            if (!newModel) {
                                console.log("[TREPAN BYOK] Custom model input cancelled");
                                return;
                            }
                        } else {
                            // Preset model selected
                            newModel = modelChoice.modelId;
                        }
                        
                        await context.globalState.update(config.modelKey, newModel);
                        vscode.window.showInformationMessage(`✅ Model updated to: ${newModel}`);
                        console.log(`[TREPAN BYOK] ${provider} model updated to:`, newModel);
                        
                        // Refresh webview to show new model
                        trepanSidebarProvider.sendMessage({
                            type: 'updateModelBadge',
                            modelId: newModel
                        });
                        
                    } else if (action.action === "test") {
                        // Test Connection
                        console.log(`[TREPAN BYOK] Testing ${provider} connection...`);
                        vscode.window.showInformationMessage(`🔄 Testing ${config.displayName} connection...`);
                        
                        await testProviderConnection(provider, existingKey, existingModel);
                        
                        vscode.window.showInformationMessage(`✅ Connection successful! Model: ${existingModel}`);
                        console.log(`[TREPAN BYOK] ${provider} connection test passed`);
                    }
                    
                    return;
                }
                
                // First-time setup flow (no existing credentials)
                console.log(`[TREPAN BYOK] First-time setup for ${provider}`);
                
                // Step 2: Prompt for API Key
                const apiKey = await vscode.window.showInputBox({
                    prompt: `Enter your ${config.displayName} API Key`,
                    placeHolder: config.keyPlaceholder,
                    password: true,
                    ignoreFocusOut: true,
                    validateInput: (value) => {
                        if (!value || value.trim().length === 0) {
                            return "API Key cannot be empty";
                        }
                        return null;
                    }
                });

                if (!apiKey) {
                    console.log("[TREPAN BYOK] API key input cancelled");
                    vscode.window.showInformationMessage("BYOK configuration cancelled.");
                    return;
                }
                
                console.log(`[TREPAN BYOK] ${provider} API key received, length:`, apiKey.length);

                // Step 3: Select Model - Show preset list + custom option
                const modelPresets = provider === "groq" ? [
                    {
                        label: "$(zap) Llama 4 Scout 17B",
                        description: "meta-llama/llama-4-scout-17b-16e-instruct",
                        detail: "Recommended: Fast (30K TPM), 96% accuracy on security tests",
                        modelId: "meta-llama/llama-4-scout-17b-16e-instruct"
                    },
                    {
                        label: "$(symbol-namespace) Llama 3.3 70B Versatile",
                        description: "llama-3.3-70b-versatile",
                        detail: "Slower (12K TPM) but larger model",
                        modelId: "llama-3.3-70b-versatile"
                    },
                    {
                        label: "$(edit) Custom Model ID",
                        description: "Enter a different model",
                        detail: "Specify any Groq model ID manually",
                        modelId: "custom"
                    }
                ] : [
                    {
                        label: "$(cloud) Claude 3.5 Sonnet",
                        description: "anthropic/claude-3.5-sonnet",
                        detail: "Recommended: Best accuracy",
                        modelId: "anthropic/claude-3.5-sonnet"
                    },
                    {
                        label: "$(edit) Custom Model ID",
                        description: "Enter a different model",
                        detail: "Specify any OpenRouter model ID manually",
                        modelId: "custom"
                    }
                ];
                
                const modelChoice = await vscode.window.showQuickPick(modelPresets, {
                    placeHolder: `Select ${config.displayName} model or choose custom`,
                    title: `🔧 ${config.displayName} Model Selection`
                });
                
                if (!modelChoice) {
                    console.log("[TREPAN BYOK] Model selection cancelled");
                    vscode.window.showInformationMessage("BYOK configuration cancelled.");
                    return;
                }
                
                let modelId;
                
                if (modelChoice.modelId === "custom") {
                    // Custom model input
                    modelId = await vscode.window.showInputBox({
                        prompt: `Enter ${config.displayName} Model ID`,
                        placeHolder: config.defaultModel,
                        value: config.defaultModel,
                        ignoreFocusOut: true,
                        validateInput: (value) => {
                            if (!value || value.trim().length === 0) {
                                return "Model ID cannot be empty";
                            }
                            return null;
                        }
                    });
                    
                    if (!modelId) {
                        console.log("[TREPAN BYOK] Custom model input cancelled");
                        vscode.window.showInformationMessage("BYOK configuration cancelled.");
                        return;
                    }
                } else {
                    // Preset model selected
                    modelId = modelChoice.modelId;
                }
                
                console.log(`[TREPAN BYOK] ${provider} model selected:`, modelId);

                // Step 4: Test the connection
                console.log(`[TREPAN BYOK] Testing ${provider} connection...`);
                vscode.window.showInformationMessage(`🔄 Testing ${config.displayName} connection...`);

                await testProviderConnection(provider, apiKey, modelId);

                console.log(`[TREPAN BYOK] ${provider} connection test successful`);

                // Step 5: Save credentials securely
                console.log(`[TREPAN BYOK] Saving ${provider} credentials...`);
                await context.secrets.store(config.keyName, apiKey);
                await context.globalState.update(config.modelKey, modelId);
                console.log(`[TREPAN BYOK] ${provider} credentials saved successfully`);

                // Step 6: Show success message
                vscode.window.showInformationMessage(
                    `✅ ${config.displayName} configured successfully! Model: ${modelId}`
                );

                console.log(`[TREPAN BYOK] Configuration complete. Provider: ${provider}, Model: ${modelId}`);

                // Refresh webview to show new model
                trepanSidebarProvider.sendMessage({
                    type: 'updateModelBadge',
                    modelId: modelId
                });

            } catch (error) {
                console.error("[TREPAN BYOK] Configuration error:", error);
                vscode.window.showErrorMessage(
                    `❌ BYOK configuration failed: ${error.message}`
                );
            }
        }
    );
    
    // Helper function to test provider connections
    async function testProviderConnection(provider, apiKey, model) {
        const endpoints = {
            openrouter: "https://openrouter.ai/api/v1/chat/completions",
            groq: "https://api.groq.com/openai/v1/chat/completions"
        };
        
        const testResponse = await fetchWithTimeout(endpoints[provider], {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${apiKey}`,
                ...(provider === "openrouter" && {
                    "HTTP-Referer": "https://github.com/dsadsadsadsadas/Trepan",
                    "X-Title": "Trepan Gatekeeper"
                })
            },
            body: JSON.stringify({
                model: model,
                messages: [{ role: "user", content: "ACK" }],
                max_tokens: 10
            })
        }, 15000);
        
        if (!testResponse.ok) {
            const errorText = await testResponse.text();
            throw new Error(`${provider} API test failed: ${testResponse.status} - ${errorText}`);
        }
        
        return await testResponse.json();
    }

    const togglePowerModeCmd = vscode.commands.registerCommand(
        "trepan.togglePowerMode",
        async () => {
            try {
                console.log("[TREPAN POWER MODE] Toggle requested");
                
                // Get current provider (default to openrouter)
                const provider = context.globalState.get('trepan.provider') || 'openrouter';
                
                // Provider-specific key names
                const keyNames = {
                    openrouter: "openrouter_api_key",
                    groq: "groq_api_key"
                };
                
                const modelKeys = {
                    openrouter: "openrouter_model",
                    groq: "groq_model"
                };
                
                const displayNames = {
                    openrouter: "OpenRouter",
                    groq: "Groq"
                };
                
                // Check if API key exists for current provider
                const existingKey = await context.secrets.get(keyNames[provider]);
                
                if (existingKey) {
                    // Key exists, just toggle the mode
                    const currentMode = context.globalState.get('trepan.mode') || 'local';
                    const newMode = currentMode === 'cloud' ? 'local' : 'cloud';
                    
                    console.log(`[TREPAN POWER MODE] Toggling from ${currentMode} to ${newMode}`);
                    
                    await context.globalState.update('trepan.mode', newMode);
                    updateStatusBar(context);
                    
                    if (newMode === 'cloud') {
                        const model = context.globalState.get(modelKeys[provider]) || 
                                     (provider === 'openrouter' ? 'anthropic/claude-3.5-sonnet' : 'llama-3.3-70b-versatile');
                        vscode.window.showInformationMessage(
                            `✅ Trepan: Power Mode Activated (${displayNames[provider]} - ${model})`
                        );
                        console.log(`[TREPAN POWER MODE] ✅ Activated Power Mode with ${displayNames[provider]}, model: ${model}`);
                        outputChannel.appendLine(`[${new Date().toISOString()}] ✅ Power Mode Activated - Provider: ${displayNames[provider]}, Model: ${model}`);
                    } else {
                        vscode.window.showInformationMessage(
                            `✅ Trepan: Local Mode Activated`
                        );
                        console.log("[TREPAN POWER MODE] ✅ Activated Local Mode");
                        outputChannel.appendLine(`[${new Date().toISOString()}] ✅ Local Mode Activated`);
                    }
                } else {
                    // No key exists, trigger configuration flow
                    console.log("[TREPAN POWER MODE] No API key found, triggering configuration");
                    await vscode.commands.executeCommand('trepan.configureBYOK');
                    
                    // After configuration, check if key was added and activate power mode
                    const keyAfterConfig = await context.secrets.get(keyNames[provider]);
                    if (keyAfterConfig) {
                        await context.globalState.update('trepan.mode', 'cloud');
                        updateStatusBar(context);
                        console.log("[TREPAN POWER MODE] ✅ Activated Power Mode after configuration");
                        outputChannel.appendLine(`[${new Date().toISOString()}] ✅ Power Mode Activated after initial configuration`);
                    }
                }
            } catch (error) {
                console.error("[TREPAN POWER MODE] Toggle error:", error);
                vscode.window.showErrorMessage(
                    `❌ Power Mode toggle failed: ${error.message}`
                );
            }
        }
    );

    const toggleV2PromptsCmd = vscode.commands.registerCommand(
        "trepan.toggleV2Prompts",
        async () => {
            const currentMode = context.globalState.get('trepan.experimental_v2_prompts') || false;
            const newMode = !currentMode;
            
            await context.globalState.update('trepan.experimental_v2_prompts', newMode);
            
            const status = newMode ? "ENABLED" : "DISABLED";
            const emoji = newMode ? "🧪" : "📝";
            
            vscode.window.showInformationMessage(
                `${emoji} Trepan V2 Prompts: ${status} ${newMode ? '(Experimental - Reduces false positives)' : '(Using legacy prompts)'}`
            );
            
            console.log(`[TREPAN V2] Experimental V2 prompts: ${status}`);
        }
    );

    const debugReasoningCmd = vscode.commands.registerCommand(
        "trepan.debugReasoning",
        async () => {
            const currentMode = context.globalState.get('trepan.debug_reasoning') || false;
            const newMode = !currentMode;
            
            await context.globalState.update('trepan.debug_reasoning', newMode);
            
            const status = newMode ? "ENABLED" : "DISABLED";
            const emoji = newMode ? "🔍" : "🔇";
            
            vscode.window.showInformationMessage(
                `${emoji} Trepan Debug Reasoning: ${status} ${newMode ? '(Detailed logs in console)' : '(Normal logging)'}`
            );
            
            console.log(`[TREPAN DEBUG] Debug reasoning mode: ${status}`);
        }
    );

    context.subscriptions.push(askCommand, openLedgerCommand, reviewChangesCommand, initializeProjectCommand, toggleProcessorCommand, selectModelCmd, auditFolderCmd, configureBYOKCmd, togglePowerModeCmd, toggleV2PromptsCmd, debugReasoningCmd);

    // Periodic server health check
    checkServerHealth();
    const healthTimer = setInterval(checkServerHealth, 30_000);
    context.subscriptions.push({ dispose: () => clearInterval(healthTimer) });

    // ── THE AIRBAG ────────────────────────────────────────────────────────────
    const saveHook = vscode.workspace.onWillSaveTextDocument((event) => {
        // Keep this synchronous and lightweight: immediately hand off the real work
        // into a Promise passed to event.waitUntil so any synchronous exceptions
        // are avoided by design.
        // Save event triggered

        event.waitUntil((async () => {
            try {
                // Only trigger on explicit manual saves (Ctrl+S / Cmd+S). Ignore auto-saves on focus out/delay.
                if (event.reason !== vscode.TextDocumentSaveReason.Manual) {
                    // Skip auto-save events
                    return;
                }

                const cfg = vscode.workspace.getConfiguration("trepan");
                if (!cfg.get("enabled")) {
                    // Airbag disabled in settings
                    return;
                }

                // Bypass standard excludes if this is a Pillar file (Selective Pass)
                const relPath = vscode.workspace.asRelativePath(event.document.uri);
                const isPillar = relPath.startsWith(".trepan") && relPath.endsWith(".md");
                // Check if file is a pillar or excluded

                if (!isPillar) {
                    const excludes = cfg.get("excludePatterns") ?? [];
                    if (excludes.some((pat) => matchGlob(pat, relPath))) {
                        // File excluded by pattern
                        return;
                    }
                }

                // Check Server Offline
                if (!serverOnline) {
                    const enforcementMode = cfg.get("enforcementMode") ?? "Soft";
                    if (enforcementMode === "Strict") {
                        console.warn('[TREPAN] Server is OFFLINE. Strict mode enforcing BLOCK.');
                        // Sleek toast notification instead of modal
                        vscode.window.showErrorMessage(`🛑 Trepan: Server offline — Save blocked in Strict mode`);
                        throw new Error("Trepan Strict Mode: Server is offline. Save blocked.");
                    }
                    console.warn('[TREPAN] Server is OFFLINE. Airbag failing open for this save.');
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
        const key = document.uri.toString();
        _lastAuditedContent.delete(key);
        _lastSentContent.delete(key);
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

    // Skip if this exact content was already sent in a previous audit
    if (_lastSentContent.get(fileKey) === currentContent) {
        console.log('[TREPAN] No changes since last audit. Skipping.');
        return [];
    }

    // Trivial change filter — skip if entire content change is just whitespace/comments/newlines
    // This is more reliable as it catches all cosmetic changes regardless of diff mode
    const lastSent = _lastSentContent.get(fileKey);
    if (lastSent) {
        const normalize = (text) => text.split(/\r?\n/).map(l => l.trim()).filter(l => l.length > 0).join('');
        if (normalize(currentContent) === normalize(lastSent)) {
            console.log('[TREPAN] Trivial cosmetic change detected (indentation/newlines only). Skipping audit.');
            return [];
        }
    }

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
            // Sleek toast notification instead of modal
            vscode.window.showErrorMessage(`🛑 Trepan: No server available — Save blocked in Strict mode`);
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

        updateStatusBar(context, 'auditing');
        trepanSidebarProvider.sendMessage({ type: 'scanning', title: 'Meta-Gate Audit: ' + fileName }, true);
        
        try {
            // Resolve the project root for the specific file being saved (multi-root workspace support)
            const projectPath = vscode.workspace.getWorkspaceFolder(document.uri)?.uri.fsPath
                ?? vscode.workspace.workspaceFolders?.[0]?.uri.fsPath
                ?? '';
            console.log(`[TREPAN META-GATE] Resolved project_path: ${projectPath}`);
            const processorMode = vscode.workspace.getConfiguration("trepan").get("processor_mode") || "GPU";
            
            // Record what we are about to send, regardless of verdict
            _lastSentContent.set(fileKey, currentContent);

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
                updateStatusBar(context, 'idle');
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
                // Sleek toast notification instead of modal
                vscode.window.showErrorMessage(`🛑 Trepan: Save blocked — Security violation detected (Score: ${scoreDisplay})`);
                throw new Error(`Trepan Gatekeeper: architectural drift detected (score ${scoreDisplay})`);
            }

            setStatus("accepted");
            setTimeout(() => updateStatusBar(context, 'idle'), 2000);
            _lastAuditedContent.set(fileKey, currentContent);
            return [];
        } catch (err) {
            console.error("Trepan Meta-Gate error:", err);
            updateStatusBar(context, 'idle');
            return [];
        }
    } else {
        // ============================================
        // THE AIRBAG: Project File Evaluation
        // ============================================
        const fileName = path.basename(document.fileName);
        const totalLines = currentContent.split('\n').length;
        const previousContent = _lastAuditedContent.get(fileKey);

        // ── CHECK MODE EARLY: Power Mode needs full context ───────────────
        const context = global.trepanContext;
        const isPowerMode = context?.globalState.get('trepan.mode') === 'cloud';

        let codeContent;
        
        // ── POWER MODE: Always send full file (no snapshot restrictions) ──
        if (isPowerMode) {
            console.log(`[TREPAN POWER MODE] Sending full file (${totalLines} lines) for deep taint analysis`);
            codeContent = currentContent;
            
            // Still update snapshots for future reference
            if (!previousContent) {
                _lastAuditedContent.set(fileKey, currentContent);
            }
        }
        // ── LOCAL MODE: Use snapshot logic to save GPU resources ──────────
        else {
            if (!previousContent) {
                // FIRST SAVE — no snapshot exists yet
                if (totalLines > FIRST_AUDIT_LINE_LIMIT) {
                    // Large file on first save — index silently, skip audit
                    _lastAuditedContent.set(fileKey, currentContent);
                    _lastSentContent.set(fileKey, currentContent);
                    
                    // Show status bar message
                    const indexMsg = vscode.window.setStatusBarMessage(
                        `🛡️ Trepan: Indexed ${totalLines} lines — auditing changes from next save`,
                        8000
                    );
                    
                    console.log(`[TREPAN] First save of large file (${totalLines} lines). Indexing silently, skipping audit.`);
                    return [];
                } else {
                    // Small file on first save — audit normally
                    codeContent = currentContent;
                }
            } else if (totalLines <= LARGE_FILE_THRESHOLD) {
                // Small file with existing snapshot — always full audit
                codeContent = currentContent;
            } else {
                // Large file with existing snapshot — use diff engine
                codeContent = extractAuditChunk(currentContent, previousContent, DIFF_CONTEXT_LINES);
                
                if (codeContent === "") {
                    // No changes detected — skip audit entirely
                    console.log('[TREPAN] No changes detected since last audit. Skipping.');
                    return [];
                }
                
                console.log(`[TREPAN] Diff mode: sending ${codeContent.split('\n').length} lines of ${totalLines} total`);
            }
        }

        const pillars = readPillars(document);


        console.log(`[TREPAN AIRBAG] Document save detected: ${fileName}`);

        updateStatusBar(context, 'auditing');
        trepanSidebarProvider.sendMessage({ type: 'scanning', title: 'Airbag Audit: ' + fileName }, true);

        try {
            // Resolve the project root for the specific file being saved (multi-root workspace support)
            const projectPath = vscode.workspace.getWorkspaceFolder(document.uri)?.uri.fsPath
                ?? vscode.workspace.workspaceFolders?.[0]?.uri.fsPath
                ?? '';
            console.log(`[TREPAN AIRBAG] Resolved project_path: ${projectPath}`);
            const processorMode = vscode.workspace.getConfiguration("trepan").get("processor_mode") || "GPU";
            
            // Record what we are about to send, regardless of verdict
            _lastSentContent.set(fileKey, currentContent);

            // ── TRAFFIC COP: Route based on mode ──────────────────────────────
            // Note: isPowerMode already checked above for snapshot logic
            
            let data;
            
            if (isPowerMode) {
                console.log("[TREPAN TRAFFIC COP] Power Mode detected — routing through Layer 1 + Cloud");
                console.log(`[TREPAN TRAFFIC COP] Sending full file: ${totalLines} lines for deep analysis`);
                
                // Step 1: Run Layer 1 on Python server
                const layer1Response = await fetchWithTimeout(`${serverUrl}/evaluate`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        filename: fileName,
                        code_snippet: codeContent,
                        pillars: pillars,
                        project_path: projectPath,
                        processor_mode: processorMode,
                        model_name: _selectedModel,
                        power_mode: true  // Signal to run Layer 1 only
                    }),
                }, timeoutMs);

                if (!layer1Response.ok) {
                    console.warn(`Trepan: Layer 1 server returned ${layer1Response.status} — failing open`);
                    updateStatusBar(context, 'idle');
                    return [];
                }

                const layer1Data = await layer1Response.json();
                
                // Step 2: Check Layer 1 result
                if (layer1Data.action === "REJECT") {
                    // Layer 1 caught it — block immediately
                    console.log("[TREPAN TRAFFIC COP] Layer 1 REJECT — blocking save");
                    data = layer1Data;
                } else if (layer1Data.action === "L1_PASS") {
                    // Layer 1 passed — call Cloud API for Layer 2
                    console.log("[TREPAN TRAFFIC COP] Layer 1 passed — calling Cloud API");
                    
                    try {
                        const cloudResult = await callCloudAPI(context, {
                            filename: fileName,
                            code_snippet: codeContent,
                            pillars: pillars
                        });
                        
                        // ═══ REQUIREMENT 5: FALLBACK LINE NUMBER DETECTION ═══
                        // Process violations to correct line numbers using fallback logic
                        if (cloudResult.violations && Array.isArray(cloudResult.violations)) {
                            console.log(`[TREPAN FALLBACK] Processing ${cloudResult.violations.length} violations`);
                            
                            cloudResult.violations = cloudResult.violations.map(violation => {
                                const reportedLine = violation.line_number;
                                const violatingSnippet = violation.violating_snippet;
                                
                                // Apply fallback detection if violating_snippet is provided
                                if (violatingSnippet) {
                                    const correctedLine = detectCorrectLineNumber(
                                        reportedLine,
                                        violatingSnippet,
                                        document
                                    );
                                    
                                    // Update violation with corrected line number
                                    return {
                                        ...violation,
                                        line_number: correctedLine,
                                        original_line_number: reportedLine, // Keep original for debugging
                                        line_corrected: correctedLine !== reportedLine
                                    };
                                } else {
                                    console.warn(`[TREPAN FALLBACK] No violating_snippet for violation at line ${reportedLine}`);
                                    return violation;
                                }
                            });
                            
                            const correctedCount = cloudResult.violations.filter(v => v.line_corrected).length;
                            if (correctedCount > 0) {
                                console.log(`[TREPAN FALLBACK] ✓ Corrected ${correctedCount} line numbers using fallback logic`);
                            }
                        }
                        
                        data = cloudResult;
                        console.log("[TREPAN TRAFFIC COP] Cloud API result:", data.action);
                    } catch (cloudError) {
                        console.error("[TREPAN TRAFFIC COP] Cloud API failed:", cloudError);
                        vscode.window.showErrorMessage(`⚠️ Power Mode failed: ${cloudError.message}. Falling back to local.`);
                        
                        // Fallback: run full local audit
                        const fallbackResponse = await fetchWithTimeout(`${serverUrl}/evaluate`, {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({
                                filename: fileName,
                                code_snippet: codeContent,
                                pillars: pillars,
                                project_path: projectPath,
                                processor_mode: processorMode,
                                model_name: _selectedModel,
                                power_mode: false
                            }),
                        }, timeoutMs);
                        
                        if (fallbackResponse.ok) {
                            data = await fallbackResponse.json();
                        } else {
                            updateStatusBar(context, 'idle');
                            return [];
                        }
                    }
                } else {
                    // Unexpected response
                    data = layer1Data;
                }
            } else {
                // Local Mode: Standard full audit
                console.log("[TREPAN TRAFFIC COP] Local Mode — running full local audit");
                
                const res = await fetchWithTimeout(`${serverUrl}/evaluate`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        filename: fileName,
                        code_snippet: codeContent,
                        pillars: pillars,
                        project_path: projectPath,
                        processor_mode: processorMode,
                        model_name: _selectedModel,
                        power_mode: false
                    }),
                }, timeoutMs);

                if (!res.ok) {
                    console.warn(`Trepan: Airbag server returned ${res.status} — failing open`);
                    updateStatusBar(context, 'idle');
                    return [];
                }

                data = await res.json();
                
                // Add local audit metadata
                data.audit_mode = 'local';
            }
            // ── End Traffic Cop ────────────────────────────────────────────────
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
                // Performance tracking metadata
                audit_mode: data.audit_mode || 'local',
                cloud_provider: data.cloud_provider || null,
                cloud_latency: data.cloud_latency || null,
            };

            trepanSidebarProvider.sendMessage(webviewMessage, actionResult === "REJECT");
            await executeAIAssistantActions(reasoning, actionResult, driftScore);

            if (actionResult === "REJECT") {
                const scoreDisplay = driftScore.toFixed(2);
                // Sleek toast notification instead of modal
                vscode.window.showErrorMessage(`🛑 Trepan: Save blocked — Security violation detected (Score: ${scoreDisplay})`);
                throw new Error(`Trepan Airbag: architectural drift detected (score ${scoreDisplay})`);
            }

            setStatus("accepted");
            setTimeout(() => updateStatusBar(context, 'idle'), 2000);
            _lastAuditedContent.set(fileKey, currentContent);
            return [];
        } catch (err) {
            console.error("Trepan Airbag error:", err);
            updateStatusBar(context, 'idle');
            return [];
        }
    }
}


// ─── Line Number Injection Helper (Requirement 1) ───────────────────────────

/**
 * Inject line numbers into code before sending to Cloud API
 * Format: ${lineNumber} | ${lineContent}
 * @param {string} code - Raw code content
 * @returns {string} - Line-numbered code
 */
function injectLineNumbers(code) {
    if (!code || typeof code !== 'string') {
        console.warn('[TREPAN LINE INJECTION] Invalid code input, returning empty string');
        return '';
    }
    
    const lines = code.split('\n');
    const numberedLines = lines.map((line, index) => {
        const lineNumber = index + 1; // 1-based line numbers
        return `${lineNumber} | ${line}`;
    });
    
    return numberedLines.join('\n');
}

/**
 * Remove line number prefix from a code snippet
 * @param {string} snippet - Code snippet potentially with line number prefix
 * @returns {string} - Cleaned snippet
 */
function removeLineNumberPrefix(snippet) {
    if (!snippet || typeof snippet !== 'string') {
        return snippet;
    }
    
    // Remove pattern: "123 | " from the beginning
    return snippet.replace(/^\d+\s*\|\s*/, '').trim();
}

/**
 * Detect correct line number using fallback logic (Requirement 5)
 * @param {number} reportedLineNumber - Line number reported by AI
 * @param {string} violatingSnippet - The exact code snippet with violation
 * @param {vscode.TextDocument} document - VS Code document
 * @returns {number} - Corrected line number (1-based)
 */
function detectCorrectLineNumber(reportedLineNumber, violatingSnippet, document) {
    try {
        // Validate inputs
        if (!violatingSnippet || typeof violatingSnippet !== 'string') {
            console.warn('[TREPAN FALLBACK] No violating_snippet provided, using reported line number');
            return reportedLineNumber;
        }
        
        // Clean the snippet (remove line number prefix if present)
        const cleanSnippet = removeLineNumberPrefix(violatingSnippet);
        
        if (!cleanSnippet) {
            console.warn('[TREPAN FALLBACK] Empty snippet after cleaning, using reported line number');
            return reportedLineNumber;
        }
        
        // First, check if reported line number is correct
        if (reportedLineNumber >= 1 && reportedLineNumber <= document.lineCount) {
            const reportedLine = document.lineAt(reportedLineNumber - 1); // Convert to 0-based
            const reportedLineText = reportedLine.text.trim();
            const cleanSnippetTrimmed = cleanSnippet.trim();
            
            if (reportedLineText === cleanSnippetTrimmed || reportedLineText.includes(cleanSnippetTrimmed)) {
                console.log(`[TREPAN FALLBACK] ✓ Reported line ${reportedLineNumber} matches snippet`);
                return reportedLineNumber;
            }
        }
        
        // Fallback: Search for snippet in document
        console.log(`[TREPAN FALLBACK] Line ${reportedLineNumber} doesn't match, searching for snippet...`);
        const documentText = document.getText();
        const snippetIndex = documentText.indexOf(cleanSnippet);
        
        if (snippetIndex === -1) {
            console.warn(`[TREPAN FALLBACK] ⚠ Snippet not found in document: "${cleanSnippet.substring(0, 50)}..."`);
            return reportedLineNumber; // Use reported line as fallback
        }
        
        // Convert character offset to line number
        const position = document.positionAt(snippetIndex);
        const correctedLineNumber = position.line + 1; // Convert to 1-based
        
        console.log(`[TREPAN FALLBACK] ✓ Corrected line number: ${reportedLineNumber} → ${correctedLineNumber}`);
        return correctedLineNumber;
        
    } catch (error) {
        console.error('[TREPAN FALLBACK] Error in fallback detection:', error);
        return reportedLineNumber; // Safe fallback
    }
}

// ─── System Rules Loader ─────────────────────────────────────────────────────

/**
 * Load system_rules.md from the project's .trepan folder
 * @param {string} projectPath - Absolute path to project root
 * @returns {string} - Contents of system_rules.md or empty string if not found
 */
function loadSystemRules(projectPath) {
    try {
        const systemRulesPath = path.join(projectPath, '.trepan', 'system_rules.md');
        if (fs.existsSync(systemRulesPath)) {
            const content = fs.readFileSync(systemRulesPath, 'utf-8');
            console.log(`[TREPAN RULES] Loaded system_rules.md (${content.length} chars)`);
            return content;
        } else {
            console.warn(`[TREPAN RULES] system_rules.md not found at: ${systemRulesPath}`);
            return '';
        }
    } catch (error) {
        console.error(`[TREPAN RULES] Error loading system_rules.md:`, error);
        return '';
    }
}

// ─── Cloud API Call (Power Mode - Multi-Provider) ────────────────────────────

async function callCloudAPI(context, payload) {
    const startTime = Date.now(); // High-resolution performance timer
    
    try {
        // Get current provider
        const provider = context.globalState.get('trepan.provider') || 'openrouter';
        
        // Check for experimental V2 prompt mode
        const useV2Prompts = context.globalState.get('trepan.experimental_v2_prompts') || false;
        
        // Provider-specific configuration
        const providerConfig = {
            openrouter: {
                keyName: "openrouter_api_key",
                modelKey: "openrouter_model",
                endpoint: "https://openrouter.ai/api/v1/chat/completions",
                displayName: "OpenRouter"
            },
            groq: {
                keyName: "groq_api_key",
                modelKey: "groq_model",
                endpoint: "https://api.groq.com/openai/v1/chat/completions",
                displayName: "Groq"
            }
        };
        
        const config = providerConfig[provider];
        if (!config) {
            throw new Error(`Unknown provider: ${provider}`);
        }
        
        // Get API key and model
        const apiKey = await context.secrets.get(config.keyName);
        const modelId = context.globalState.get(config.modelKey) || 
                       (provider === 'openrouter' ? 'anthropic/claude-3.5-sonnet' : 'llama-3.3-70b-versatile');
        
        if (!apiKey) {
            throw new Error(`${config.displayName} API key not found. Please configure Power Mode first.`);
        }
        
        console.log(`[TREPAN POWER MODE] Calling ${config.displayName} with model: ${modelId} (V${useV2Prompts ? '2' : '1'} prompts)`);
        
        // ═══ LOAD SYSTEM RULES FROM PROJECT ═══
        const projectPath = payload.project_path || vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || '';
        const systemRules = loadSystemRules(projectPath);
        
        if (!systemRules) {
            console.warn('[TREPAN POWER MODE] No system_rules.md found - using empty ruleset');
        }
        
        // ═══ REQUIREMENT 1: LINE NUMBER INJECTION ═══
        // Inject line numbers into code before sending to Cloud API
        const originalCode = payload.code_snippet;
        const numberedCode = injectLineNumbers(originalCode);
        console.log(`[TREPAN LINE INJECTION] Injected line numbers into ${originalCode.split('\n').length} lines`);
        
        // Build the prompt based on version
        let systemPrompt, userPrompt;
        
        if (useV2Prompts) {
            // V2 Constrained Prompt System (Fixed - Production Ready)
            systemPrompt = `You are a security auditor that must minimize false positives. You ONLY flag issues that are realistically exploitable in the given context.

HARD CONSTRAINTS (CRITICAL - FOLLOW EXACTLY):
1. Do NOT assume user input unless explicitly shown
2. Do NOT assume shell=True unless explicitly present
2b. Environment variables used in SQL queries ARE a real injection risk — treat as REJECT
3. Treat hardcoded constants as SAFE unless proven otherwise
   EXCEPTION: Hardcoded credentials (API keys, passwords, tokens, secrets) are ALWAYS CRITICAL regardless of being constants
4. Prefer FALSE NEGATIVE over FALSE POSITIVE when uncertain
5. If unsure → classify as LOW, not HIGH/CRITICAL

CRITICAL SECURITY PATTERNS (ALWAYS FLAG):
- Hardcoded credentials: API keys (AWS, OpenAI, etc.), passwords, tokens, secrets
  Pattern: Strings matching [A-Z0-9]{20,} or containing "key", "secret", "password", "token" in variable name
- Sensitive data in output sinks: print(), console.log(), logger.debug(), logger.info()
  If password, credit card, SSN, or PII reaches ANY output → CRITICAL
- SQL injection: String concatenation or f-strings in SQL queries
  Includes: WHERE, FROM, LIKE, ORDER BY clauses with dynamic values

REQUIRED REASONING STEPS (MANDATORY ORDER):
1. Detect risky pattern (e.g., subprocess, eval, SQL, hardcoded credential, logging sensitive data)
2. Check for user-controlled input (YES / NO)
   NOTE: Environment variables CAN be attacker-controlled in some contexts
3. Check execution context:
   - shell=True? (YES / NO)
   - argument list vs string?
   - Is sensitive data being logged/printed?
4. Determine exploitability:
   - Can attacker influence execution? (YES / NO)
   - Is credential exposed in code? (YES / NO)
   - Is PII/password reaching output? (YES / NO)
5. Only then assign severity

If steps are skipped → response is INVALID

OUTPUT SCHEMA (STRICT JSON ONLY):
{
    "pattern_detected": "description of risky pattern found",
    "user_controlled_input": true/false,
    "uses_shell": true/false,
    "argument_type": "list/string/none",
    "exploitability": "real/theoretical/none",
    "severity": "CRITICAL/HIGH/MEDIUM/LOW/NONE",
    "confidence": 0.0-1.0,
    "reasoning": "step-by-step explanation following the 5 required steps"
}

ANTI-HALLUCINATION GUARD:
If the code does not explicitly show a vulnerability, you MUST NOT infer one.

VALIDATION RULES:
- If user_controlled_input = false BUT hardcoded credential detected → severity = CRITICAL
- If sensitive data (password, SSN, credit card) in print/log → severity = CRITICAL
- If uses_shell = false AND argument_type = "list" → severity ≤ LOW
- If exploitability = "none" AND no credential exposure → severity = NONE
- If pattern_detected = "none" → all other fields should reflect no risk`;

            userPrompt = `Analyze this code for security violations following the required reasoning steps:

Filename: ${payload.filename}

Code:
\`\`\`
${numberedCode}
\`\`\`

Follow the 5 required reasoning steps in order:
1. Pattern Detection: What risky patterns do you see?
2. Input Analysis: Is there user-controlled input?
3. Context Analysis: How is the risky pattern used?
4. Exploitability: Can an attacker actually exploit this?
5. Severity Assignment: Based on real exploitability

Provide your analysis in the required JSON format.`;
        } else {
            // ═══ REQUIREMENT 2 & 3: ENHANCED SYSTEM PROMPT ═══
            // V1 Legacy Prompt System with Line Number and Rule Name Instructions
            systemPrompt = `You are Trepan, a security-focused code auditor. Analyze the provided code for security violations and architectural drift.

IMPORTANT INSTRUCTIONS FOR LINE NUMBERS:
- The code you receive has line numbers prepended in the format: \${lineNumber} | \${lineContent}
- You MUST use the exact line numbers shown in the code
- DO NOT calculate or infer line numbers independently
- Report the line number exactly as it appears before the pipe character (|)

STRICT RULE NOMENCLATURE (CRITICAL):
- You are operating under a strict custom rulebook
- You MUST map every violation to the exact Rule ID provided in the system context
- Examples of valid rule names: 'RULE_8: PHI_PROTECTION', 'RULE_10: LOGGING_GATE', 'RULE_3: HARDCODED_SECRETS'
- Under NO circumstances are you allowed to invent, guess, or generate generic rule names
- DO NOT use generic names like 'security_violation', 'data_exposure', 'sensitive_data_exposure'
- If you're unsure which rule applies, use the closest matching rule from the provided list
- If no exact rule matches, state "RULE_UNKNOWN: [description]" rather than inventing a rule name

SINK VERIFICATION MANDATE (CRITICAL):
- You must perform rigorous End-to-End Taint Analysis
- Defining sensitive data in a variable is NOT a vulnerability
- A vulnerability ONLY exists if that exact sensitive data flows into an insecure sink
- Insecure sinks include: print(), console.log(), os.popen(), HTTP response bodies, database queries, file writes
- If an object contains sensitive data, but that specific data is stripped or unreferenced before the final output/return, YOU MUST NOT FLAG IT
- Verify the exact keys/fields being returned before claiming data exposure
- Example: If user_data = {"ssn": "123-45-6789", "name": "John"} but only {"name": "John"} is returned, this is SAFE
- You must trace the data flow from source to sink and confirm the sensitive field actually reaches the output

REQUIRED OUTPUT FORMAT:
Return ONLY valid JSON in this exact format:
{
    "action": "ACCEPT or REJECT",
    "drift_score": 0.0 to 1.0,
    "reasoning": "Brief explanation with data flow analysis",
    "violations": [
        {
            "rule_id": "string (exact rule name from instructions)",
            "line_number": number (exact line number from prepended format),
            "violation": "description with data flow path",
            "confidence": "HIGH or LOW",
            "violating_snippet": "the exact line of code containing the violation (without the line number prefix)"
        }
    ]
}

PROJECT-SPECIFIC SECURITY RULES:
${systemRules || 'No custom rules defined. Use general security best practices.'}

DATA FLOW ANALYSIS REQUIREMENTS:
1. Identify the source of sensitive data (variable definition, user input, database query)
2. Trace the data through all transformations (assignments, function calls, filtering)
3. Identify the final sink (return statement, print, log, HTTP response)
4. Verify that the sensitive field actually reaches the sink
5. Only flag if the sensitive data is present in the final output`;

            userPrompt = `Analyze this code for security violations:

Filename: ${payload.filename}

Code:
\`\`\`
${numberedCode}
\`\`\`

Provide your analysis in JSON format. Remember to:
1. Use exact line numbers from the code
2. Use exact rule names from the instructions (e.g., RULE_8: PHI_PROTECTION)
3. Perform complete data flow analysis from source to sink
4. Only flag violations where sensitive data actually reaches an insecure sink`;
        }

        // Build headers based on provider
        const headers = {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${apiKey}`
        };
        
        // OpenRouter requires additional headers
        if (provider === 'openrouter') {
            headers["HTTP-Referer"] = "https://github.com/dsadsadsadsadas/Trepan";
            headers["X-Title"] = "Trepan Gatekeeper";
        }

        const response = await fetchWithTimeout(config.endpoint, {
            method: "POST",
            headers: headers,
            body: JSON.stringify({
                model: modelId,
                messages: [
                    { role: "system", content: systemPrompt },
                    { role: "user", content: userPrompt }
                ],
                temperature: 0.1,
                max_tokens: 2000
            })
        }, 30000);

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`${config.displayName} API failed: ${response.status} - ${errorText}`);
        }

        const data = await response.json();
        const content = data.choices?.[0]?.message?.content;
        
        if (!content) {
            throw new Error(`No response content from ${config.displayName}`);
        }
        
        console.log(`[TREPAN POWER MODE] Raw response from ${config.displayName}:`, content);
        
        // Parse JSON response
        const jsonMatch = content.match(/\{[\s\S]*\}/);
        if (!jsonMatch) {
            throw new Error(`Could not extract JSON from ${config.displayName} response`);
        }
        
        let result = JSON.parse(jsonMatch[0]);
        
        // V2 Response Processing and Validation
        if (useV2Prompts) {
            result = await processV2Response(result, config.displayName, payload);
        }
        
        // Calculate performance metrics
        const duration = (Date.now() - startTime) / 1000; // Convert to seconds
        
        // Add performance metadata to result
        result.cloud_provider = config.displayName;
        result.cloud_latency = duration.toFixed(2);
        result.audit_mode = 'cloud';
        result.prompt_version = useV2Prompts ? 'v2' : 'v1';
        
        console.log(`[TREPAN POWER MODE] Parsed result from ${config.displayName}:`, result);
        console.log(`[TREPAN POWER MODE] ⚡ Performance: ${duration.toFixed(2)}s latency`);
        
        return result;
        
    } catch (error) {
        console.error("[TREPAN POWER MODE] Cloud API error:", error);
        throw error;
    }
}

// ─── V2 Response Processing and Validation ──────────────────────────────────

async function processV2Response(v2Response, providerName, payload) {
    const context = global.trepanContext;
    const debugMode = context?.globalState.get('trepan.debug_reasoning') || false;
    
    if (debugMode) {
        console.log(`[TREPAN V2 DEBUG] ═══════════════════════════════════════`);
        console.log(`[TREPAN V2 DEBUG] Processing V2 response from ${providerName}`);
        console.log(`[TREPAN V2 DEBUG] Raw V2 Response:`, JSON.stringify(v2Response, null, 2));
        console.log(`[TREPAN V2 DEBUG] ═══════════════════════════════════════`);
    } else {
        console.log(`[TREPAN V2] Processing V2 response from ${providerName}`);
    }
    
    // Validate V2 response structure
    const requiredFields = [
        "pattern_detected", "user_controlled_input", "uses_shell", 
        "argument_type", "exploitability", "severity", "confidence", "reasoning"
    ];
    
    const validationErrors = [];
    
    // Check required fields
    for (const field of requiredFields) {
        if (!(field in v2Response)) {
            validationErrors.push(`Missing required field: ${field}`);
        }
    }
    
    if (validationErrors.length > 0) {
        console.warn(`[TREPAN V2] Validation errors: ${validationErrors.join(', ')}`);
        if (debugMode) {
            console.log(`[TREPAN V2 DEBUG] Validation failed, attempting strict mode retry`);
        }
        return await retryWithStrictMode(payload, providerName);
    }
    
    // Logical consistency validation
    const correctedResponse = { ...v2Response };
    const logicalErrors = [];
    
    // Rule: If user_controlled_input = false → severity cannot be CRITICAL
    if (!v2Response.user_controlled_input && v2Response.severity === "CRITICAL") {
        logicalErrors.push("No user input but CRITICAL severity");
        correctedResponse.severity = "HIGH";
        if (debugMode) {
            console.log(`[TREPAN V2 DEBUG] Applied constraint: user_controlled_input=false → severity downgraded from CRITICAL to HIGH`);
        }
    }
    
    // Rule: If uses_shell = false AND argument_type = list → severity ≤ LOW
    if (!v2Response.uses_shell && 
        v2Response.argument_type === "list" && 
        ["CRITICAL", "HIGH", "MEDIUM"].includes(v2Response.severity)) {
        logicalErrors.push("Safe subprocess usage but high severity");
        correctedResponse.severity = "LOW";
        if (debugMode) {
            console.log(`[TREPAN V2 DEBUG] Applied constraint: uses_shell=false + argument_type=list → severity downgraded to LOW`);
        }
    }
    
    // Rule: If exploitability = none → severity must be NONE
    if (v2Response.exploitability === "none" && v2Response.severity !== "NONE") {
        logicalErrors.push("No exploitability but non-zero severity");
        correctedResponse.severity = "NONE";
        if (debugMode) {
            console.log(`[TREPAN V2 DEBUG] Applied constraint: exploitability=none → severity set to NONE`);
        }
    }
    
    // Rule: If pattern_detected indicates no risk → severity should be NONE
    const safePatterns = ["none", "no pattern", "no risk", "safe", "no issues"];
    if (safePatterns.some(pattern => v2Response.pattern_detected.toLowerCase().includes(pattern))) {
        if (v2Response.severity !== "NONE") {
            logicalErrors.push("No pattern detected but non-zero severity");
            correctedResponse.severity = "NONE";
            if (debugMode) {
                console.log(`[TREPAN V2 DEBUG] Applied constraint: safe pattern detected → severity set to NONE`);
            }
        }
    }
    
    if (logicalErrors.length > 0) {
        console.warn(`[TREPAN V2] Logical errors corrected: ${logicalErrors.join(', ')}`);
    }
    
    // Convert V2 to legacy format for compatibility
    const legacyResponse = convertV2ToLegacyFormat(correctedResponse);
    
    // Add V2 metadata for debugging
    legacyResponse.v2_metadata = {
        pattern_detected: correctedResponse.pattern_detected,
        user_controlled_input: correctedResponse.user_controlled_input,
        uses_shell: correctedResponse.uses_shell,
        argument_type: correctedResponse.argument_type,
        exploitability: correctedResponse.exploitability,
        severity: correctedResponse.severity,
        confidence: correctedResponse.confidence,
        validation_errors: validationErrors,
        logical_errors: logicalErrors,
        constraints_applied: logicalErrors.length > 0
    };
    
    if (debugMode) {
        console.log(`[TREPAN V2 DEBUG] ═══════════════════════════════════════`);
        console.log(`[TREPAN V2 DEBUG] Final V2 Analysis:`);
        console.log(`[TREPAN V2 DEBUG] - Pattern: ${correctedResponse.pattern_detected}`);
        console.log(`[TREPAN V2 DEBUG] - User Input: ${correctedResponse.user_controlled_input}`);
        console.log(`[TREPAN V2 DEBUG] - Uses Shell: ${correctedResponse.uses_shell}`);
        console.log(`[TREPAN V2 DEBUG] - Argument Type: ${correctedResponse.argument_type}`);
        console.log(`[TREPAN V2 DEBUG] - Exploitability: ${correctedResponse.exploitability}`);
        console.log(`[TREPAN V2 DEBUG] - Severity: ${correctedResponse.severity}`);
        console.log(`[TREPAN V2 DEBUG] - Confidence: ${correctedResponse.confidence}`);
        console.log(`[TREPAN V2 DEBUG] - Constraints Applied: ${logicalErrors.length}`);
        console.log(`[TREPAN V2 DEBUG] - Legacy Action: ${legacyResponse.action}`);
        console.log(`[TREPAN V2 DEBUG] - Legacy Score: ${legacyResponse.drift_score}`);
        console.log(`[TREPAN V2 DEBUG] ═══════════════════════════════════════`);
    } else {
        console.log(`[TREPAN V2] Converted to legacy format:`, legacyResponse);
    }
    
    return legacyResponse;
}

async function retryWithStrictMode(payload, providerName) {
    console.log(`[TREPAN V2] Retrying with strict mode for ${providerName}`);
    
    // For now, fall back to V1 format on validation failure
    // In a full implementation, this would retry with enhanced constraints
    const fallbackResponse = {
        action: "ACCEPT",
        drift_score: 0.0,
        reasoning: "V2 validation failed, falling back to safe default",
        violations: [],
        v2_fallback: true
    };
    
    return fallbackResponse;
}

function convertV2ToLegacyFormat(v2Response) {
    // Map severity to action
    const severity = v2Response.severity || "NONE";
    const action = ["CRITICAL", "HIGH", "MEDIUM"].includes(severity) ? "REJECT" : "ACCEPT";
    
    // Map severity to drift score
    const severityToScore = {
        "CRITICAL": 1.0,
        "HIGH": 0.8,
        "MEDIUM": 0.6,
        "LOW": 0.3,
        "NONE": 0.0
    };
    const driftScore = severityToScore[severity] || 0.0;
    
    // Create violations array if rejecting
    const violations = [];
    if (action === "REJECT") {
        violations.push({
            rule_id: "V2_ANALYSIS",
            line_number: 1,  // V2 doesn't track specific lines yet
            violation: v2Response.pattern_detected || "Security violation detected",
            confidence: (v2Response.confidence || 0.0) > 0.7 ? "HIGH" : "LOW"
        });
    }
    
    return {
        action: action,
        drift_score: driftScore,
        reasoning: v2Response.reasoning || "V2 analysis completed",
        violations: violations
    };
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
        updateStatusBar(global.trepanContext);

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
        updateStatusBar(global.trepanContext);

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
        updateStatusBar(global.trepanContext);
    }
}

// ─── Status Bar ───────────────────────────────────────────────────────────────

const STATUS_MAP = {
    online: { text: "🛡️ Trepan: Watching...", tooltip: "Trepan online — airbag armed", bg: undefined },
    loading: { text: "$(shield) Trepan ⏳", tooltip: "Trepan online — model loading…", bg: undefined },
    checking: { text: "$(sync~spin) Auditing...", tooltip: "Trepan — evaluating save…", bg: new vscode.ThemeColor("terminal.ansiYellow") },
    accepted: { text: "🛡️ Trepan: Accepted ✅", tooltip: "Trepan — save ACCEPTED", bg: new vscode.ThemeColor("statusBarItem.prominentBackground") },
    offline: { text: "$(shield) Trepan ⚫", tooltip: "Trepan offline — saves pass through", bg: undefined },
    powerMode: { text: "$(zap) Trepan: Power Mode", tooltip: "Trepan Power Mode — using cloud AI", bg: undefined }
};

function setStatus(key, customText = null, customTooltip = null) {
    if (!statusBarItem) return;
    const s = STATUS_MAP[key] ?? STATUS_MAP.offline;
    statusBarItem.text = customText || s.text;
    statusBarItem.tooltip = customTooltip || s.tooltip;
    statusBarItem.backgroundColor = s.bg;
}

async function updateStatusBar(context, state = 'idle') {
    if (!statusBarItem) return;
    const mode = context?.globalState.get('trepan.mode');
    const provider = context?.globalState.get('trepan.provider') || 'openrouter';
    
    const providerDisplayNames = {
        openrouter: "OpenRouter",
        groq: "Groq"
    };
    
    console.log(`[TREPAN STATUS] Updating status bar - mode: ${mode}, provider: ${provider}, state: ${state}, serverOnline: ${serverOnline}`);
    
    // Priority 1: If server is offline, always show offline (regardless of mode)
    if (!serverOnline) {
        setStatus('offline');
        console.log(`[TREPAN STATUS] ✅ Status bar set to offline (server down)`);
        return;
    }
    
    // Priority 2: Handle active audit state (with yellow spinner)
    if (state === 'auditing') {
        // During audit, show yellow spinner but preserve mode identity
        if (mode === 'cloud') {
            statusBarItem.text = `$(sync~spin) Auditing...`;
            statusBarItem.color = new vscode.ThemeColor('terminal.ansiYellow');
            statusBarItem.tooltip = `Trepan: Auditing code with Power Mode`;
        } else {
            setStatus('checking');
        }
        console.log(`[TREPAN STATUS] ✅ Status bar set to auditing (mode: ${mode})`);
        return;
    }
    
    // Priority 3: If server is online and Power Mode is active, show Power Mode identity
    if (mode === 'cloud') {
        const displayName = providerDisplayNames[provider];
        
        // Get the exact model name from globalState
        const modelKey = provider === 'openrouter' ? 'openrouter_model' : 'groq_model';
        const modelId = context?.globalState.get(modelKey);
        
        // Check if API key exists
        const keyName = provider === 'openrouter' ? 'openrouter_api_key' : 'groq_api_key';
        const apiKey = await context?.secrets.get(keyName);
        
        // Always show Power Mode base state with zap icon and clear any yellow color
        statusBarItem.color = undefined; // Clear yellow color from auditing state
        if (modelId && apiKey) {
            setStatus(
                'powerMode',
                `$(zap) Trepan: Power Mode`,
                `Trepan Power Mode — ${displayName}: ${modelId}`
            );
            console.log(`[TREPAN STATUS] ✅ Status bar set to Power Mode with ${displayName}: ${modelId}`);
        } else if (apiKey) {
            setStatus(
                'powerMode',
                `$(zap) Trepan: Power Mode`,
                `Trepan Power Mode — ${displayName}`
            );
            console.log(`[TREPAN STATUS] ✅ Status bar set to Power Mode with ${displayName} (no model specified)`);
        } else {
            setStatus(
                'powerMode',
                `$(zap) Trepan: Power Mode [No API Key]`,
                `Trepan Power Mode — API key not configured`
            );
            console.log(`[TREPAN STATUS] ⚠️ Status bar set to Power Mode but no API key found`);
        }
    } else {
        // Priority 4: Server online, Local Mode - clear any yellow color
        statusBarItem.color = undefined;
        setStatus('online');
        console.log(`[TREPAN STATUS] ✅ Status bar set to online (local mode)`);
    }
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
    async resolveWebviewView(webviewView) {
        this._view = webviewView;
        webviewView.webview.options = { enableScripts: true };
        webviewView.webview.html = await this._getHtmlForWebview();

        // If we have a cached message, send it immediately upon resolution
        if (this._lastMessage) {
            this.sendMessage(this._lastMessage);
        }

        // Listen for messages from the Webview (like button clicks)
        webviewView.webview.onDidReceiveMessage(async (message) => {
            console.log('[TREPAN WEBVIEW] Received message:', message);
            
            // Handle BYOK configuration request
            if (message.command === 'configure_byok') {
                console.log('[TREPAN WEBVIEW] Executing trepan.configureBYOK command');
                try {
                    await vscode.commands.executeCommand('trepan.configureBYOK');
                    console.log('[TREPAN WEBVIEW] Command executed successfully');
                } catch (error) {
                    console.error('[TREPAN WEBVIEW] Command execution failed:', error);
                    vscode.window.showErrorMessage(`Failed to open BYOK config: ${error.message}`);
                }
                return;
            }
            
            // Handle Power Mode toggle request
            if (message.command === 'toggle_power_mode') {
                console.log('[TREPAN WEBVIEW] Executing trepan.togglePowerMode command');
                try {
                    await vscode.commands.executeCommand('trepan.togglePowerMode');
                    console.log('[TREPAN WEBVIEW] Power mode toggled successfully');
                } catch (error) {
                    console.error('[TREPAN WEBVIEW] Power mode toggle failed:', error);
                    vscode.window.showErrorMessage(`Failed to toggle power mode: ${error.message}`);
                }
                return;
            }

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

            if (message.command === 'run_workspace_audit') {
                console.log('[TREPAN WEBVIEW] Executing trepan.auditEntireFolder command');
                try {
                    await vscode.commands.executeCommand('trepan.auditEntireFolder');
                    console.log('[TREPAN WEBVIEW] Workspace audit started successfully');
                } catch (error) {
                    console.error('[TREPAN WEBVIEW] Workspace audit failed:', error);
                    vscode.window.showErrorMessage(`Failed to start workspace audit: ${error.message}`);
                }
                return;
            }

            if (message.command === 'toggle_cpu_gpu') {
                console.log('[TREPAN WEBVIEW] Executing trepan.toggleProcessor command');
                try {
                    await vscode.commands.executeCommand('trepan.toggleProcessor');
                    console.log('[TREPAN WEBVIEW] CPU/GPU toggle executed successfully');
                } catch (error) {
                    console.error('[TREPAN WEBVIEW] CPU/GPU toggle failed:', error);
                    vscode.window.showErrorMessage(`Failed to toggle CPU/GPU: ${error.message}`);
                }
                return;
            }

            if (message.command === 'initialize_project') {
                console.log('[TREPAN WEBVIEW] Executing trepan.initializeProject command');
                try {
                    await vscode.commands.executeCommand('trepan.initializeProject');
                    console.log('[TREPAN WEBVIEW] Project initialization started successfully');
                } catch (error) {
                    console.error('[TREPAN WEBVIEW] Project initialization failed:', error);
                    vscode.window.showErrorMessage(`Failed to initialize project: ${error.message}`);
                }
                return;
            }

            if (message.command === 'update_model') {
                const { model } = message;
                console.log('[TREPAN WEBVIEW] Updating model to:', model);
                const context = global.trepanContext;
                const provider = context?.globalState.get('trepan.provider') || 'openrouter';
                const modelKey = provider === 'openrouter' ? 'openrouter_model' : 'groq_model';
                await context?.globalState.update(modelKey, model);
                vscode.window.showInformationMessage(`Model updated to: ${model}`);
                this.sendMessage({ type: 'updateModelBadge', modelId: model });
                return;
            }

            if (message.command === 'toggle_mode') {
                console.log('[TREPAN WEBVIEW] Executing trepan.togglePowerMode command from settings');
                try {
                    await vscode.commands.executeCommand('trepan.togglePowerMode');
                    console.log('[TREPAN WEBVIEW] Power mode toggled successfully from settings');
                } catch (error) {
                    console.error('[TREPAN WEBVIEW] Power mode toggle failed:', error);
                    vscode.window.showErrorMessage(`Failed to toggle power mode: ${error.message}`);
                }
                return;
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
    async _getHtmlForWebview() {
        // Get current mode and model information
        const context = global.trepanContext;
        const mode = context?.globalState.get('trepan.mode') || 'local';
        const provider = context?.globalState.get('trepan.provider') || 'openrouter';
        
        // Get model name
        const modelKey = provider === 'openrouter' ? 'openrouter_model' : 'groq_model';
        const modelId = context?.globalState.get(modelKey);
        
        // Check if API key exists
        const keyName = provider === 'openrouter' ? 'openrouter_api_key' : 'groq_api_key';
        const apiKey = await context?.secrets.get(keyName);
        
        // Build model badge HTML (only for Power Mode) - WITHOUT provider prefix
        let modelBadgeHtml = '';
        if (mode === 'cloud') {
            if (apiKey && modelId) {
                // Show only the model ID, no provider prefix
                modelBadgeHtml = `<span id="model-badge" style="font-size: 10px; padding: 2px 6px; border-radius: 4px; background-color: #333; color: #ccc; vertical-align: middle; margin-left: 8px;">${modelId}</span>`;
            } else if (!apiKey) {
                modelBadgeHtml = `<span id="model-badge" style="font-size: 10px; padding: 2px 6px; border-radius: 4px; color: #ff5555; border: 1px solid #ff5555; vertical-align: middle; margin-left: 8px;">No API Key Detected</span>`;
            }
        }
        
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
        
        /* BYOK Settings Gear Styling */
        .settings-gear {
            background: none;
            border: none;
            cursor: pointer;
            font-size: 20px;
            padding: 4px 8px;
            opacity: 0.7;
            transition: opacity 0.2s, transform 0.2s;
        }
        .settings-gear:hover {
            opacity: 1;
            transform: rotate(30deg);
        }
        .header-container {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }
        .header-container h2 {
            margin: 0;
        }
    </style>
</head>
<body>
    <div id="compromise-banner" class="compromise-alert">
        <h3 style="margin-top:0;">🛑 VAULT COMPROMISE DETECTED</h3>
        <p>The architectural pillars have been modified outside of Trepan's authorization. Please review the rules in your .trepan folder.</p>
        <button id="resign-btn" class="btn btn-danger">⚠️ I have reviewed the rules. Re-Sign Vault.</button>
    </div>

    <div id="content">
        <div class="header-container">
            <h2>🏛️ Trepan Vault Access${modelBadgeHtml}</h2>
            <button id="settings-gear" class="settings-gear" title="Open Settings" onclick="window.openSettings()">⚙️</button>
        </div>
        <p>Awaiting architectural changes...</p>
    </div>
    
    <div id="settings-panel" style="display: none; padding: 0; margin-top: 15px;">
        <div style="background: #1e1e1e; border-radius: 6px; overflow: hidden;">
            <div style="padding: 15px; border-bottom: 1px solid #333;">
                <h3 style="margin: 0; color: var(--vscode-editor-foreground);">⚙️ Trepan Settings</h3>
            </div>
            
            <details style="border-bottom: 1px solid #333;">
                <summary style="padding: 14px 15px; cursor: pointer; list-style: none; background: #1e1e1e; transition: background 0.2s; user-select: none;" onmouseover="this.style.background='#252525'" onmouseout="this.style.background='#1e1e1e'">
                    <span style="font-weight: 500; color: var(--vscode-editor-foreground);">🔧 API & Engine</span>
                </summary>
                <div style="padding: 15px; background: #181818; border-left: 3px solid #4ec9b0;">
                    <div style="margin-bottom: 12px;">
                        <button onclick="window.configureBYOK()" style="width: 100%; padding: 10px; background: #1a73e8; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 0.9em; font-weight: 500;">Configure API Key</button>
                    </div>
                    <div>
                        <label style="display: block; margin-bottom: 6px; font-size: 0.85em; color: #ccc;">Model Selection:</label>
                        <select id="model-select" onchange="window.updateModel()" style="width: 100%; padding: 8px; background: #252525; color: var(--vscode-input-foreground); border: 1px solid #333; border-radius: 4px; font-size: 0.9em;">
                            <option value="meta-llama/llama-4-scout-17b-16e-instruct">Llama-4-Scout (Fast)</option>
                            <option value="meta-llama/llama-3.1-70b-instruct">Llama-3-70B (Accurate)</option>
                        </select>
                    </div>
                </div>
            </details>
            
            <details style="border-bottom: 1px solid #333;">
                <summary style="padding: 14px 15px; cursor: pointer; list-style: none; background: #1e1e1e; transition: background 0.2s; user-select: none;" onmouseover="this.style.background='#252525'" onmouseout="this.style.background='#1e1e1e'">
                    <span style="font-weight: 500; color: var(--vscode-editor-foreground);">🔀 Mode Selection</span>
                </summary>
                <div style="padding: 15px; background: #181818; border-left: 3px solid #dcdcaa;">
                    <div style="display: flex; gap: 10px;">
                        <button id="mode-local-btn" onclick="window.setMode('local')" style="flex: 1; padding: 10px; background: #252525; color: white; border: 1px solid #333; border-radius: 4px; cursor: pointer; font-size: 0.9em; font-weight: 500; transition: background 0.2s;" onmouseover="this.style.background='#2d2d2d'" onmouseout="this.style.background='#252525'">Local Mode</button>
                        <button id="mode-cloud-btn" onclick="window.setMode('cloud')" style="flex: 1; padding: 10px; background: #252525; color: white; border: 1px solid #333; border-radius: 4px; cursor: pointer; font-size: 0.9em; font-weight: 500; transition: background 0.2s;" onmouseover="this.style.background='#2d2d2d'" onmouseout="this.style.background='#252525'">Cloud Power Mode</button>
                    </div>
                </div>
            </details>
            
            <details style="border-bottom: 1px solid #333;">
                <summary style="padding: 14px 15px; cursor: pointer; list-style: none; background: #1e1e1e; transition: background 0.2s; user-select: none;" onmouseover="this.style.background='#252525'" onmouseout="this.style.background='#1e1e1e'">
                    <span style="font-weight: 500; color: var(--vscode-editor-foreground);">⚡ Hardware Acceleration</span>
                </summary>
                <div style="padding: 15px; background: #181818; border-left: 3px solid #ce9178;">
                    <button id="toggle-cpu-gpu-btn" onclick="window.toggleCpuGpu()" style="width: 100%; padding: 10px; background: #252525; color: white; border: 1px solid #333; border-radius: 4px; cursor: pointer; font-size: 0.9em; font-weight: 500; transition: background 0.2s;" onmouseover="this.style.background='#2d2d2d'" onmouseout="this.style.background='#252525'">Toggle CPU/GPU</button>
                </div>
            </details>
            
            <details style="border-bottom: 1px solid #333;">
                <summary style="padding: 14px 15px; cursor: pointer; list-style: none; background: #1e1e1e; transition: background 0.2s; user-select: none;" onmouseover="this.style.background='#252525'" onmouseout="this.style.background='#1e1e1e'">
                    <span style="font-weight: 500; color: var(--vscode-editor-foreground);">📁 Project Management</span>
                </summary>
                <div style="padding: 15px; background: #181818; border-left: 3px solid #569cd6;">
                    <button id="initialize-project-btn" onclick="window.initializeProject()" style="width: 100%; padding: 10px; background: #252525; color: white; border: 1px solid #333; border-radius: 4px; cursor: pointer; font-size: 0.9em; font-weight: 500; transition: background 0.2s;" onmouseover="this.style.background='#2d2d2d'" onmouseout="this.style.background='#252525'">Initialize Trepan</button>
                </div>
            </details>
            
            <details style="border-bottom: 1px solid #333;">
                <summary style="padding: 14px 15px; cursor: pointer; list-style: none; background: #1e1e1e; transition: background 0.2s; user-select: none;" onmouseover="this.style.background='#252525'" onmouseout="this.style.background='#1e1e1e'">
                    <span style="font-weight: 500; color: var(--vscode-editor-foreground);">🚀 Workspace Actions</span>
                </summary>
                <div style="padding: 15px; background: #181818; border-left: 3px solid #f48771;">
                    <button onclick="window.runWorkspaceAudit()" style="width: 100%; padding: 10px; background: #f48771; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: 500; font-size: 0.9em; transition: background 0.2s;" onmouseover="this.style.background='#e67660'" onmouseout="this.style.background='#f48771'">Run Full Workspace Audit</button>
                </div>
            </details>
            
            <div style="padding: 15px;">
                <button onclick="window.closeSettings()" style="width: 100%; padding: 8px; background: transparent; color: #ccc; border: 1px solid #333; border-radius: 4px; cursor: pointer; font-size: 0.9em; transition: all 0.2s;" onmouseover="this.style.background='#252525'; this.style.borderColor='#555'" onmouseout="this.style.background='transparent'; this.style.borderColor='#333'">Close Settings</button>
            </div>
        </div>
    </div>
    <script>
        // Make vscode global so inline onclick handlers can access it
        window.vscode = acquireVsCodeApi();
        const vscode = window.vscode;
        const contentDiv = document.getElementById('content');
        const compromiseBanner = document.getElementById('compromise-banner');
        
        // Global function for BYOK configuration
        window.configureBYOK = function() {
            console.log('configureBYOK called');
            vscode.postMessage({ command: 'configure_byok' });
        };
        
        // Global function for opening settings panel
        window.openSettings = function() {
            const panel = document.getElementById('settings-panel');
            const content = document.getElementById('content');
            if (panel && content) {
                panel.style.display = 'block';
                content.style.display = 'none';
            }
        };
        
        // Global function for closing settings panel
        window.closeSettings = function() {
            const panel = document.getElementById('settings-panel');
            const content = document.getElementById('content');
            if (panel && content) {
                panel.style.display = 'none';
                content.style.display = 'block';
            }
        };
        
        // Global function for updating model
        window.updateModel = function() {
            const select = document.getElementById('model-select');
            if (select) {
                const model = select.value;
                console.log('updateModel called with:', model);
                vscode.postMessage({ command: 'update_model', model: model });
            }
        };
        
        // Global function for setting mode
        window.setMode = function(mode) {
            console.log('setMode called with:', mode);
            vscode.postMessage({ command: 'toggle_mode' });
        };
        
        // Global function for running workspace audit
        window.runWorkspaceAudit = function() {
            console.log('runWorkspaceAudit called');
            vscode.postMessage({ command: 'run_workspace_audit' });
        };
        
        // Global function for toggling CPU/GPU
        window.toggleCpuGpu = function() {
            console.log('toggleCpuGpu called');
            vscode.postMessage({ command: 'toggle_cpu_gpu' });
        };
        
        // Global function for initializing project
        window.initializeProject = function() {
            console.log('initializeProject called');
            vscode.postMessage({ command: 'initialize_project' });
        };
        
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
            
            // Handle model badge update
            if (message.type === 'updateModelBadge') {
                const badge = document.getElementById('model-badge');
                if (badge && message.modelId) {
                    badge.textContent = message.modelId;
                    badge.style.color = '#ccc';
                    badge.style.backgroundColor = '#333';
                    badge.style.border = 'none';
                    console.log('[WEBVIEW] Model badge updated to:', message.modelId);
                }
                return;
            }
            
            if (message.type === 'reset') {
                document.body.classList.remove('compromised');
                compromiseBanner.classList.remove('active');
                contentDiv.innerHTML = '<div class="header-container"><h2>🏛️ Trepan Vault Access</h2><div style="display: flex; gap: 8px; align-items: center;"><button id="mode-toggle" class="settings-gear" title="Toggle Local/Power Mode" style="font-size: 14px; padding: 4px 8px; color: white; background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.3);" onclick="window.toggleMode()"><span id="mode-text">Local</span></button><button class="settings-gear" title="Configure Power Mode (BYOK)" onclick="window.configureBYOK()">⚙️</button></div></div><p>Awaiting architectural changes...</p>';
                return;
            }
            
            if (message.type === 'resign_success') {
                document.body.classList.remove('compromised');
                compromiseBanner.classList.remove('active');
                contentDiv.innerHTML = '<div class="header-container"><h2>🏛️ Trepan Vault Access</h2><div style="display: flex; gap: 8px; align-items: center;"><button id="mode-toggle" class="settings-gear" title="Toggle Local/Power Mode" style="font-size: 14px; padding: 4px 8px; color: white; background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.3);" onclick="window.toggleMode()"><span id="mode-text">Local</span></button><button class="settings-gear" title="Configure Power Mode (BYOK)" onclick="window.configureBYOK()">⚙️</button></div></div><p style="color: var(--vscode-testing-iconPassed); font-weight: bold;">✅ Successfully Re-Signed Vault!</p>';
                setTimeout(() => {
                    contentDiv.innerHTML = '<div class="header-container"><h2>🏛️ Trepan Vault Access</h2><div style="display: flex; gap: 8px; align-items: center;"><button id="mode-toggle" class="settings-gear" title="Toggle Local/Power Mode" style="font-size: 14px; padding: 4px 8px; color: white; background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.3);" onclick="window.toggleMode()"><span id="mode-text">Local</span></button><button class="settings-gear" title="Configure Power Mode (BYOK)" onclick="window.configureBYOK()">⚙️</button></div></div><p>Awaiting architectural changes...</p>';
                }, 3000);
                return;
            }

            // SCANNING: show loading spinner while AI is thinking
            if (message.type === 'scanning') {
                contentDiv.innerHTML = '<div class="header-container"><h2>🏛️ Trepan Vault Access</h2><div style="display: flex; gap: 8px; align-items: center;"><button id="mode-toggle" class="settings-gear" title="Toggle Local/Power Mode" style="font-size: 14px; padding: 4px 8px; color: white; background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.3);" onclick="window.toggleMode()"><span id="mode-text">Local</span></button><button class="settings-gear" title="Configure Power Mode (BYOK)" onclick="window.configureBYOK()">⚙️</button></div></div><div class="scanning"><div class="spinner"></div><span>🛡️ Trepan is evaluating architectural drift...</span></div>';
                return;
            }

            // ERROR: show server failure while evaluating
            if (message.type === 'error') {
                contentDiv.innerHTML = '<div class="header-container"><h2>🏛️ Trepan Vault Access</h2><div style="display: flex; gap: 8px; align-items: center;"><button id="mode-toggle" class="settings-gear" title="Toggle Local/Power Mode" style="font-size: 14px; padding: 4px 8px; color: white; background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.3);" onclick="window.toggleMode()"><span id="mode-text">Local</span></button><button class="settings-gear" title="Configure Power Mode (BYOK)" onclick="window.configureBYOK()">⚙️</button></div></div><div class="action-card" style="border-left: 4px solid var(--vscode-errorForeground);"><p class="action-error">⚠️ Trepan Error</p><p style="color: var(--vscode-editor-foreground); font-size: 0.9em;">' + message.message + '</p><p style="color: var(--vscode-terminal-ansiYellow); font-style: italic; font-size: 0.85em; margin-top: 8px;">Audit failed — check server logs for details.</p></div>';
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

                // ═══════════════════════════════════════════════════════════════════
                // PERFORMANCE TRACKING: "Bragging" UI
                // ═══════════════════════════════════════════════════════════════════
                if (message.audit_mode === 'cloud' && message.cloud_provider && message.cloud_latency) {
                    html += '<div style="background: rgba(100, 200, 255, 0.1); border-left: 3px solid #64c8ff; padding: 8px 12px; margin: 10px 0; border-radius: 4px; font-size: 0.9em;">';
                    html += '<span style="color: #64c8ff;">☁️ Cloud Audit:</span> ';
                    html += '<span style="font-weight: bold; color: var(--vscode-editor-foreground);">' + escapeHtml(message.cloud_provider) + '</span>';
                    html += ' | ';
                    html += '<span style="color: #dcdcaa;">⚡ Latency:</span> ';
                    html += '<span style="font-weight: bold; color: #4ec9b0;">' + escapeHtml(message.cloud_latency) + 's</span>';
                    html += '</div>';
                } else if (message.audit_mode === 'local') {
                    html += '<div style="background: rgba(78, 201, 176, 0.1); border-left: 3px solid #4ec9b0; padding: 8px 12px; margin: 10px 0; border-radius: 4px; font-size: 0.9em;">';
                    html += '<span style="color: #4ec9b0;">💻 Local Audit:</span> ';
                    html += '<span style="font-weight: bold; color: var(--vscode-editor-foreground);">Layer 1 + Layer 2</span>';
                    html += '</div>';
                }

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
                contentDiv.innerHTML = '<div class="header-container"><h2>🏛️ Trepan Vault Access</h2><div style="display: flex; gap: 8px; align-items: center;"><button id="mode-toggle" class="settings-gear" title="Toggle Local/Power Mode" style="font-size: 14px; padding: 4px 8px; color: white; background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.3);" onclick="window.toggleMode()"><span id="mode-text">Local</span></button><button class="settings-gear" title="Configure Power Mode (BYOK)" onclick="window.configureBYOK()">⚙️</button></div></div>';
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


