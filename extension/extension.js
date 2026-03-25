"use strict";

/**
 * 🛡️ SemanticGuard Gatekeeper — VS Code Airbag Extension
 *
 * Hooks into onWillSaveTextDocument. When a file is about to be saved,
 * it sends the code + .semanticguard/ pillars to the local SemanticGuard inference server.
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
        console.log(`[SEMANTICGUARD WSL] Could not get WSL IP: ${error.message}`);
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
                console.log(`[SEMANTICGUARD WSL] ✅ Using cached URL: ${discoveredServerUrl}`);
                return discoveredServerUrl;
            }
        } catch (error) {
            console.log(`[SEMANTICGUARD WSL] ❌ Cached URL failed: ${discoveredServerUrl}, rediscovering...`);
            discoveredServerUrl = null;
        }
    }

    const cfg = vscode.workspace.getConfiguration("semanticguard");
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
    console.log(`[SEMANTICGUARD WSL] Target Port: ${targetPorts[0]}`);

    const candidateURLs = [];

    // Add WSL IP if available
    const wslIP = await getWSLIP();
    if (wslIP) {
        console.log(`[SEMANTICGUARD WSL] Discovered WSL IP: ${wslIP}`);
    }

    // Generate candidates for all target ports
    for (const port of targetPorts) {
        candidateURLs.push(`http://127.0.0.1:${port}`);
        candidateURLs.push(`http://localhost:${port}`);
        if (wslIP) {
            candidateURLs.push(`http://${wslIP}:${port}`);
        }
    }

    console.log(`[SEMANTICGUARD WSL] Testing connection URLs: ${candidateURLs.join(', ')}`);

    // We implement a robust retry mechanism (hammering localhost) to wake up sleeping WSL network adapters.
    const MAX_RETRIES = 3;

    for (const url of candidateURLs) {
        for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
            try {
                console.log(`[SEMANTICGUARD WSL] Testing (Attempt ${attempt}/${MAX_RETRIES}): ${url}`);
                // Increased timeout to 5000ms to tolerate slow WSL bridge wake-ups
                const res = await fetchWithTimeout(`${url}/health`, {}, 5000);

                if (res.ok) {
                    const data = await res.json();
                    console.log(`[SEMANTICGUARD WSL] ✅ Connected to: ${url}`);
                    console.log(`[SEMANTICGUARD WSL] Server status: ${JSON.stringify(data)}`);

                    // Cache the successful URL
                    discoveredServerUrl = url;
                    return url;
                }
            } catch (error) {
                // Wait briefly before retrying this specific URL
                if (attempt < MAX_RETRIES) {
                    console.log(`[SEMANTICGUARD WSL] ⚠️ Attempt ${attempt} failed on ${url}, retrying in 500ms...`);
                    await new Promise(resolve => setTimeout(resolve, 500));
                }
            }
        }
    }

    console.log(`[SEMANTICGUARD WSL] ❌ All connection attempts failed after ${MAX_RETRIES} retries. (Tested ports: ${targetPorts.join(', ')})`);
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
        console.log('[SEMANTICGUARD PIVOT] Checking for pivots in:', document.fileName);

        // 1. Get git diff for this file
        const diff = await getGitDiff(document.fileName, projectRoot);
        if (!diff) {
            console.log('[SEMANTICGUARD PIVOT] No git diff available');
            return;
        }

        // 2. Detect removed technologies
        const removedTechs = detectRemovedTechs(diff);
        if (removedTechs.length === 0) {
            console.log('[SEMANTICGUARD PIVOT] No technologies removed');
            return;
        }

        console.log('[SEMANTICGUARD PIVOT] Removed technologies:', removedTechs);

        // 3. Read problems_and_resolutions.md
        const problems = await readProblemsFile(projectRoot);
        const unresolvedProblems = problems.filter(p => p.status === 'UNRESOLVED');

        if (unresolvedProblems.length === 0) {
            console.log('[SEMANTICGUARD PIVOT] No unresolved problems found');
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
                console.log(`[SEMANTICGUARD PIVOT] 🔄 PIVOT DETECTED: Removed ${pivot.tech} after problem`);

                // Call /evolve_memory
                await triggerEvolution(projectRoot, pivot.tech);
            }
        }
    } catch (error) {
        console.error('[SEMANTICGUARD PIVOT] Error detecting pivot:', error);
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
        console.log('[SEMANTICGUARD PIVOT] Git diff failed:', error.message);
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
        const problemsPath = path.join(projectRoot, '.semanticguard', 'problems_and_resolutions.md');
        const content = fs.readFileSync(problemsPath, 'utf-8');
        return parseProblems(content);
    } catch (error) {
        console.log('[SEMANTICGUARD PIVOT] Could not read problems file:', error.message);
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
        const cfg = vscode.workspace.getConfiguration("semanticguard");
        let serverUrl = cfg.get("serverUrl") ?? "http://127.0.0.1:8001";

        // Try to use discovered URL
        const discoveredUrl = await discoverServerURL();
        if (discoveredUrl) {
            serverUrl = discoveredUrl;
        }

        console.log(`[SEMANTICGUARD PIVOT] Calling /evolve_memory at ${serverUrl}`);

        const response = await fetchWithTimeout(`${serverUrl}/evolve_memory`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ project_path: projectRoot })
        }, 60000); // 60 second timeout for Ollama processing

        if (response.ok) {
            const result = await response.json();
            console.log('[SEMANTICGUARD PIVOT] ✅ Evolution triggered successfully:', result);

            // Show notification to user
            vscode.window.showInformationMessage(
                `✅ SemanticGuard learned from pivot: Added rule "DO NOT USE ${tech.toUpperCase()}"`
            );
        } else {
            console.error('[SEMANTICGUARD PIVOT] Evolution failed:', response.status, response.statusText);
        }
    } catch (error) {
        console.error('[SEMANTICGUARD PIVOT] Error triggering evolution:', error);
    }
}

// ─── Activation ──────────────────────────────────────────────────────────────

/**
 * @param {vscode.ExtensionContext} context
 */
function activate(context) {
    console.log("🛡️ SemanticGuard Gatekeeper: Airbag active");

    // Export context for use in other functions
    if (!global.semanticguardContext) {
        global.semanticguardContext = context;
    }

    context.subscriptions.push(
        vscode.window.registerWebviewViewProvider("semanticguard.explorer", semanticguardSidebarProvider)
    );

    // Initialize Output Channel (Global Singleton)
    outputChannel = vscode.window.createOutputChannel("SemanticGuard Gatekeeper");
    context.subscriptions.push(outputChannel);
    
    // Status bar pill
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBarItem.command = "semanticguard.status";
    updateStatusBar(context);
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);

    // Commands
    context.subscriptions.push(
        vscode.commands.registerCommand("semanticguard.status", showStatus),
        vscode.commands.registerCommand("semanticguard.toggleEnabled", toggleEnabled)
    );

    let askCommand = vscode.commands.registerCommand('semanticguard.askGatekeeper', async () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) return;

        // Grab the text the user highlighted
        const selection = editor.selection;
        const highlightedText = editor.document.getText(selection);

        if (!highlightedText) {
            vscode.window.showInformationMessage("Please highlight a rule or code snippet first.");
            return;
        }

        vscode.window.showInformationMessage(`Asking SemanticGuard about: "${highlightedText}"...`);

        // Send logic to the sidebar UI
        semanticguardSidebarProvider.sendMessage({
            type: 'log',
            title: 'User Asked',
            thought: 'Sending selection to Meta-Gate: ' + highlightedText
        });
    });

    let openLedgerCommand = vscode.commands.registerCommand('semanticguard.openLedger', async () => {
        const folders = vscode.workspace.workspaceFolders;
        if (!folders?.length) {
            vscode.window.showErrorMessage("SemanticGuard: No workspace open.");
            return;
        }

        const semanticguardDir = path.join(folders[0].uri.fsPath, ".semanticguard");
        let ledgerPath = null;

        if (fs.existsSync(semanticguardDir)) {
            const files = fs.readdirSync(semanticguardDir);
            const walkthroughFile = files.find(f => f.toLowerCase().startsWith("walkthrough"));
            if (walkthroughFile) {
                ledgerPath = path.join(semanticguardDir, walkthroughFile);
            }
        }

        if (ledgerPath && fs.existsSync(ledgerPath)) {
            const doc = await vscode.workspace.openTextDocument(ledgerPath);
            await vscode.window.showTextDocument(doc, { viewColumn: vscode.ViewColumn.Beside });
        } else {
            vscode.window.showInformationMessage("SemanticGuard: Walkthrough ledger not found yet. It will be generated on your next save.");
        }
    });

    let reviewChangesCommand = vscode.commands.registerCommand('semanticguard.reviewWithLedger', async () => {
        const folders = vscode.workspace.workspaceFolders;
        if (!folders?.length) {
            vscode.window.showErrorMessage("SemanticGuard: No workspace open.");
            return;
        }

        const activeEditor = vscode.window.activeTextEditor;
        if (!activeEditor) {
            vscode.window.showInformationMessage("SemanticGuard: Open a file first to review changes.");
            return;
        }

        const semanticguardDir = path.join(folders[0].uri.fsPath, ".semanticguard");
        let ledgerPath = null;

        if (fs.existsSync(semanticguardDir)) {
            const files = fs.readdirSync(semanticguardDir);
            const walkthroughFile = files.find(f => f.toLowerCase().startsWith("walkthrough"));
            if (walkthroughFile) {
                ledgerPath = path.join(semanticguardDir, walkthroughFile);
            }
        }

        if (!ledgerPath || !fs.existsSync(ledgerPath)) {
            vscode.window.showInformationMessage("SemanticGuard: Walkthrough ledger not found yet. It will be generated on your next save.");
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

        vscode.window.showInformationMessage("📋 SemanticGuard: Code (left) | Audit Ledger (right)");
    });

    let initializeProjectCommand = vscode.commands.registerCommand('semanticguard.initializeProject', async () => {
        const folders = vscode.workspace.workspaceFolders;
        if (!folders?.length) {
            vscode.window.showErrorMessage("SemanticGuard: No workspace open. Please open a folder first.");
            return;
        }

        const projectPath = folders[0].uri.fsPath;
        const semanticguardDir = path.join(projectPath, ".semanticguard");

        // Check if already initialized
        if (fs.existsSync(semanticguardDir)) {
            const choice = await vscode.window.showWarningMessage(
                "SemanticGuard is already initialized in this project. Reinitialize?",
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
            title: "SemanticGuard: Golden Template Selection"
        });

        if (!selected) {
            return;
        }

        // Show progress
        await vscode.window.withProgress({
            location: vscode.ProgressLocation.Notification,
            title: "SemanticGuard: Initializing Project",
            cancellable: false
        }, async (progress) => {
            progress.report({ message: "Creating .semanticguard directory..." });

            const cfg = vscode.workspace.getConfiguration("semanticguard");
            const serverUrl = cfg.get("serverUrl") ?? "http://127.0.0.1:8001";

            try {
                progress.report({ message: "Generating golden template..." });

                const processorMode = vscode.workspace.getConfiguration("semanticguard").get("processor_mode") || "GPU";
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
                const rulesPath = path.join(semanticguardDir, "system_rules.md");
                const goldenPath = path.join(semanticguardDir, "golden_state.md");

                if (fs.existsSync(rulesPath)) {
                    const rulesDoc = await vscode.workspace.openTextDocument(rulesPath);
                    await vscode.window.showTextDocument(rulesDoc, { viewColumn: vscode.ViewColumn.One });
                }

                if (fs.existsSync(goldenPath)) {
                    const goldenDoc = await vscode.workspace.openTextDocument(goldenPath);
                    await vscode.window.showTextDocument(goldenDoc, { viewColumn: vscode.ViewColumn.Two });
                }

                vscode.window.showInformationMessage(
                    `✅ SemanticGuard initialized with ${selected.label}! Review your system_rules.md and golden_state.md.`
                );

            } catch (error) {
                vscode.window.showErrorMessage(`SemanticGuard initialization failed: ${error.message}`);
                console.error("SemanticGuard initialization error:", error);
            }
        });
    });

    let toggleProcessorCommand = vscode.commands.registerCommand('semanticguard.toggleProcessor', async () => {
        const cfg = vscode.workspace.getConfiguration("semanticguard");
        const currentMode = cfg.get("processor_mode") ?? "GPU";
        
        const selection = await vscode.window.showQuickPick([
            { label: "GPU", description: "Use Ollama/HuggingFace GPU Acceleration (Default)", picked: currentMode === "GPU" },
            { label: "CPU", description: "Use Local CPU Inference (Lower performance)", picked: currentMode === "CPU" }
        ], {
            placeHolder: `Select SemanticGuard Inference Processor (Current: ${currentMode})`,
            title: "🛡️ SemanticGuard: Processor Configuration"
        });

        if (selection) {
            const newMode = selection.label;
            await cfg.update("processor_mode", newMode, vscode.ConfigurationTarget.Global);
            vscode.window.showInformationMessage(
                `🛡️ SemanticGuard: Switched to ${newMode} mode. This setting will be applied to your next audit.`
            );
        }
    });

    const selectModelCmd = vscode.commands.registerCommand(
        "semanticguard.selectModel",
        async () => {
            const picked = await vscode.window.showQuickPick(
                MODEL_OPTIONS.map(opt => ({
                    label: opt.label,
                    description: opt.description,
                    model: opt.model
                })),
                {
                    placeHolder: `Current model: ${_selectedModel}. Choose your audit mode.`,
                    title: "SemanticGuard: Select Audit Model"
                }
            );

            if (picked) {
                _selectedModel = picked.model;
                const modeName = picked.model === "llama3.1:8b" ? "Fast Mode ⚡" : "Smart Mode 🧠";
                vscode.window.showInformationMessage(
                    `SemanticGuard switched to ${modeName} (${picked.model})`
                );
                console.log(`[SEMANTICGUARD] Model switched to: ${_selectedModel}`);
            }
        }
    );

    const auditFolderCmd = vscode.commands.registerCommand(
        "semanticguard.auditEntireFolder",
        async () => {
            const workspaceFolders = vscode.workspace.workspaceFolders;
            if (!workspaceFolders) {
                vscode.window.showErrorMessage("SemanticGuard: No workspace folder open.");
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
                        title: "🛡️ SemanticGuard: Choose Folder for Full Audit"
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
                title: "🛡️ SemanticGuard: Folder Audit Scope"
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
            
            const extensionContext = global.semanticguardContext;
            if (!extensionContext) {
                vscode.window.showErrorMessage("SemanticGuard: Extension context not available. Please reload VS Code.");
                return;
            }
            const isPowerMode = extensionContext.globalState.get('semanticguard.mode') === 'cloud';
            
            // Get server URL
            const cfg = vscode.workspace.getConfiguration("semanticguard");
            let serverUrl = cfg.get("serverUrl") ?? "http://127.0.0.1:8001";
            
            // Try to use discovered URL if available
            const discoveredUrl = await discoverServerURL();
            if (discoveredUrl) {
                serverUrl = discoveredUrl;
            }
            
            // Get current model for latency calculation
            let currentModel = _selectedModel; // Local mode model
            if (isPowerMode) {
                const provider = extensionContext.globalState.get('semanticguard.provider') || 'openrouter';
                const modelKey = provider === 'openrouter' ? 'openrouter_model' : 'groq_model';
                currentModel = extensionContext.globalState.get(modelKey) || '';
            }
            
            console.log(`[SEMANTICGUARD FOLDER AUDIT] Using model: ${currentModel}`);
            
            // Warn about cost if Power Mode
            if (isPowerMode) {
                // Detect TPM before showing confirmation
                const provider = context.globalState.get('semanticguard.provider') || 'groq';
                const keyName = provider === 'openrouter' ? 'openrouter_api_key' : 'groq_api_key';
                const apiKey = await context.secrets.get(keyName);
                const modelKey = provider === 'openrouter' ? 'openrouter_model' : 'groq_model';
                const cloudModelName = context.globalState.get(modelKey) || 'meta-llama/llama-4-scout-17b-16e-instruct';
                
                let tpmMessage = "";
                if (apiKey) {
                    const { TokenBucket, detectModelLimits } = require(path.join(context.extensionPath, 'token-bucket.js'));
                    const { maxRpm, maxTpm } = await detectModelLimits(apiKey, cloudModelName);
                    tpmMessage = `\n\nDetected Rate Limits: ${maxTpm.toLocaleString()} TPM, ~${maxRpm} RPM (estimated)`;
                    if (maxTpm >= 500000) {
                        tpmMessage += `\n🎉 Upgraded Account Detected!`;
                    }
                }
                
                const confirm = await vscode.window.showWarningMessage(
                    `🔍 SemanticGuard: Full folder audit will send every file to the Cloud API. This may incur API costs.${tpmMessage}\n\nContinue?`,
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
                '__pycache__', '.semanticguard', 'semanticguard_vault', 'coverage', '.next'
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
                vscode.window.showInformationMessage(`SemanticGuard: No auditable files found in ${relativePath}.`);
                return;
            }
            
            const modeLabel = isPowerMode ? "☁️ Cloud" : "⚡ Local";
            vscode.window.showInformationMessage(
                `🛡️ SemanticGuard: Starting folder audit of ${auditableFiles.length} files in "${relativePath}" [${modeLabel} Mode]...`
            );
            
            // ═══ START TIMER ═══
            const auditStartTime = Date.now();
            
            const violations = [];
            const errors = [];
            const errorDetails = {}; // Store detailed error info
            let processed = 0;
            let skipped = 0;
            let layer1Blocked = 0; // Track files blocked by Layer 1
            let layer2Analyzed = 0; // Track files that went to Layer 2
            
            // Store detected TPM for output display
            let detectedTPM = 30000; // Default
            let detectedRPM = 30; // Default
            
            // ═══ INTELLIGENT RATE LIMITING: Token Bucket ═══
            const { TokenBucket, detectModelLimits } = require(path.join(context.extensionPath, 'token-bucket.js'));
            
            // Detect actual TPM limits from API
            const provider = context.globalState.get('semanticguard.provider') || 'groq';
            const keyName = provider === 'openrouter' ? 'openrouter_api_key' : 'groq_api_key';
            const apiKey = await context.secrets.get(keyName);
            
            // CRITICAL FIX: Use CLOUD model, not local model
            const modelKey = provider === 'openrouter' ? 'openrouter_model' : 'groq_model';
            const cloudModelName = context.globalState.get(modelKey) || 'meta-llama/llama-4-scout-17b-16e-instruct';
            
            let rateLimiter;
            if (apiKey && isPowerMode) {
                console.log(`[SEMANTICGUARD FOLDER AUDIT] Detecting rate limits from API for model: ${cloudModelName}...`);
                const { maxRpm, maxTpm } = await detectModelLimits(apiKey, cloudModelName);
                detectedTPM = maxTpm;
                detectedRPM = maxRpm;
                rateLimiter = new TokenBucket(maxRpm, maxTpm);
                console.log(`[SEMANTICGUARD FOLDER AUDIT] Rate limiter initialized: ${maxTpm.toLocaleString()} TPM`);
                console.log(`[SEMANTICGUARD FOLDER AUDIT] Token Bucket starts FULL — first ~${Math.floor(maxTpm / 5000)} files will be instant, then throttling begins`);
            } else {
                // Fallback to default limits
                rateLimiter = new TokenBucket(30, 30000);
            }
            
            // Progress notification
            await vscode.window.withProgress({
                location: vscode.ProgressLocation.Notification,
                title: "🛡️ SemanticGuard: Auditing folder...",
                cancellable: true
            }, async (progress, token) => {
                
                for (let i = 0; i < auditableFiles.length; i++) {
                    const fileUri = auditableFiles[i];
                    
                    if (token.isCancellationRequested) {
                        console.log("[SEMANTICGUARD FOLDER AUDIT] Cancelled by user");
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
                            console.log(`[SEMANTICGUARD FOLDER AUDIT] Skipping large file: ${fileRelativePath} (${lineCount} lines)`);
                            skipped++;
                            continue;
                        }
                        
                        // Pillars are loaded server-side from project_path
                        const pillars = {};
                        const processorMode = "GPU";
                        
                        // Strip comments while preserving line numbers for Power Mode
                        const auditCode = isPowerMode ? stripCommentsPreserveLines(code) : code;
                        
                        const response = await fetchWithTimeout(`${serverUrl}/evaluate`, {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({
                                filename: fileName,
                                code_snippet: auditCode,
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
                            console.error(`[SEMANTICGUARD FOLDER AUDIT] Server error on ${fileRelativePath}: ${errorMsg}`);
                            errors.push(fileRelativePath);
                            errorDetails[fileRelativePath] = errorMsg;
                            processed++;
                            continue;
                        }
                        
                        const result = await response.json();
                        
                        // ═══ LAYER 1 TRACKING ═══
                        if (result.action === "REJECT" && result.layer === "layer1") {
                            layer1Blocked++;
                            console.log(`[SEMANTICGUARD FOLDER AUDIT] Layer 1 BLOCKED: ${fileRelativePath}`);
                        }
                        
                        // ═══ CRITICAL FIX: Handle L1_PASS in Power Mode ═══
                        // When power_mode=true, backend returns L1_PASS if Layer 1 passes
                        // We must then call Cloud API for Layer 2 analysis
                        let finalResult = result;
                        
                        if (isPowerMode && result.action === "L1_PASS") {
                            layer2Analyzed++;
                            console.log(`[SEMANTICGUARD FOLDER AUDIT] L1_PASS received for ${fileRelativePath} — calling Cloud API for Layer 2`);
                            
                            try {
                                // Call Cloud API directly (same as single-file save)
                                const cloudResult = await callCloudAPI(context, {
                                    filename: fileName,
                                    code_snippet: code,
                                    pillars: pillars,
                                    project_path: vscode.workspace.workspaceFolders[0].uri.fsPath
                                });
                                
                                finalResult = cloudResult;
                                console.log(`[SEMANTICGUARD FOLDER AUDIT] Cloud API returned: ${cloudResult.action} with ${cloudResult.findings?.length || 0} findings`);
                            } catch (cloudError) {
                                console.error(`[SEMANTICGUARD FOLDER AUDIT] Cloud API failed for ${fileRelativePath}:`, cloudError);
                                
                                // Check for 429 rate limit error
                                if (cloudError.message && cloudError.message.includes('429')) {
                                    console.log(`[SEMANTICGUARD FOLDER AUDIT] 429 Rate Limit detected — setting global pause`);
                                    await rateLimiter.setGlobalPause(30);
                                }
                                
                                // Fall back to L1_PASS result (treat as safe)
                                finalResult = result;
                            }
                        }
                        
                        // Handle both old violations format and new findings format
                        if (finalResult.action === "REJECT") {
                            if (finalResult.findings?.length > 0) {
                                // New V2 findings format
                                for (const f of finalResult.findings) {
                                    violations.push({
                                        file: fileRelativePath,
                                        line: f.line_number || 0,
                                        rule: f.rule_id || f.vulnerability_type || "Security Issue",
                                        reason: f.description || "Security vulnerability detected",
                                        confidence: "HIGH",
                                        severity: f.severity || "MEDIUM"
                                    });
                                }
                            } else if (finalResult.violations?.length > 0) {
                                // Old violations format
                                for (const v of finalResult.violations) {
                                    violations.push({
                                        file: fileRelativePath,
                                        line: v.line_number || 0,
                                        rule: v.rule_name || v.rule_id,
                                        reason: v.violation,
                                        confidence: v.confidence
                                    });
                                }
                            }
                        }
                        
                        processed++;
                        
                        // ═══ INTELLIGENT RATE LIMITING: Token Bucket ═══
                        if (i < auditableFiles.length - 1 && isPowerMode) {
                            // Load system rules for token estimation
                            const systemRules = loadSystemRules(vscode.workspace.workspaceFolders[0].uri.fsPath);
                            const systemPrompt = systemRules || '';
                            
                            // Token estimation: ~4 characters per token
                            // Account for: system prompt + code + response (2000 tokens)
                            const estimatedTokens = Math.floor((systemPrompt.length + code.length) / 4) + 2000;
                            
                            // Use Token Bucket for precise rate limiting
                            const waitTime = await rateLimiter.consumeWithWait(estimatedTokens);
                            
                            if (waitTime === -1) {
                                // File too large, skip it
                                console.log(`[SEMANTICGUARD FOLDER AUDIT] File too large (${estimatedTokens.toLocaleString()} tokens), skipping: ${fileRelativePath}`);
                                skipped++;
                                continue;
                            } else if (waitTime > 0) {
                                console.log(`[SEMANTICGUARD FOLDER AUDIT] Token bucket wait: ${waitTime.toFixed(2)}s for ${estimatedTokens.toLocaleString()} tokens (bucket state: ${rateLimiter.getState().tokens.toLocaleString()}/${rateLimiter.getState().capacity.toLocaleString()})`);
                            } else {
                                // Log instant processing (bucket has tokens)
                                const state = rateLimiter.getState();
                                console.log(`[SEMANTICGUARD FOLDER AUDIT] Instant processing (${estimatedTokens.toLocaleString()} tokens, bucket: ${state.tokens.toLocaleString()}/${state.capacity.toLocaleString()})`);
                            }
                        } else if (i < auditableFiles.length - 1) {
                            // Local mode: simple delay
                            await new Promise(resolve => setTimeout(resolve, 300));
                        }
                        
                    } catch (err) {
                        const errorMsg = `${err.name}: ${err.message}`;
                        console.error(`[SEMANTICGUARD FOLDER AUDIT] Exception on ${fileRelativePath}:`, err);
                        console.error(`[SEMANTICGUARD FOLDER AUDIT] Stack trace:`, err.stack);
                        errors.push(fileRelativePath);
                        errorDetails[fileRelativePath] = errorMsg;
                        processed++;
                    }
                }
            });
            
            // ═══ END TIMER ═══
            const auditEndTime = Date.now();
            const totalTimeSeconds = (auditEndTime - auditStartTime) / 1000;
            const avgTimePerFile = processed > 0 ? (totalTimeSeconds / processed).toFixed(2) : 0;
            
            // Show results in output channel
            const auditOutputChannel = vscode.window.createOutputChannel("SemanticGuard — Folder Audit");
            auditOutputChannel.clear();
            auditOutputChannel.appendLine(`🛡️ SEMANTICGUARD FOLDER AUDIT RESULTS`);
            auditOutputChannel.appendLine(`${'='.repeat(60)}`);
            auditOutputChannel.appendLine(`Folder: ${relativePath}`);
            auditOutputChannel.appendLine(`Mode: ${isPowerMode ? "☁️ Power Mode (Cloud API)" : "⚡ Local Mode (Llama)"}`);
            auditOutputChannel.appendLine(`Model: ${currentModel}`);
            if (isPowerMode) {
                auditOutputChannel.appendLine(`Rate Limits: ${detectedTPM.toLocaleString()} TPM, ${detectedRPM} RPM`);
                if (detectedTPM >= 500000) {
                    auditOutputChannel.appendLine(`>>> UPGRADED ACCOUNT DETECTED! You have ${detectedTPM.toLocaleString()} TPM`);
                }
            }
            auditOutputChannel.appendLine(`Files scanned: ${processed}`);
            auditOutputChannel.appendLine(`Files skipped: ${skipped}`);
            if (isPowerMode) {
                auditOutputChannel.appendLine(`Layer 1 blocked: ${layer1Blocked} files (regex pre-filter)`);
                auditOutputChannel.appendLine(`Layer 2 analyzed: ${layer2Analyzed} files (LLM deep scan)`);
            }
            auditOutputChannel.appendLine(`Violations found: ${violations.length}`);
            auditOutputChannel.appendLine(`Errors: ${errors.length}`);
            auditOutputChannel.appendLine(`${'='.repeat(60)}`);
            auditOutputChannel.appendLine(`⏱️  Total Time: ${totalTimeSeconds.toFixed(2)}s (avg ${avgTimePerFile}s per file)`);
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
                    `✅ SemanticGuard: Folder audit complete — ${processed} files clean`
                );
            } else {
                const fileCount = Object.keys(byFile).length;
                vscode.window.showWarningMessage(
                    `⚠️ SemanticGuard: Found ${violations.length} violation(s) in ${fileCount} files — see Output panel`
                );
            }
        }
    );

    const configureBYOKCmd = vscode.commands.registerCommand(
        "semanticguard.configureBYOK",
        async () => {
            try {
                console.log("[SEMANTICGUARD BYOK] Starting configuration flow...");
                
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
                    title: "🔧 SemanticGuard Power Mode - Choose Provider"
                });
                
                if (!providerChoice) {
                    console.log("[SEMANTICGUARD BYOK] Provider selection cancelled");
                    return;
                }
                
                const provider = providerChoice.provider;
                console.log(`[SEMANTICGUARD BYOK] Provider selected: ${provider}`);
                
                // Save provider selection
                await context.globalState.update('semanticguard.provider', provider);
                
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
                
                console.log(`[SEMANTICGUARD BYOK] Existing credentials for ${provider}: key=${existingKey ? 'EXISTS' : 'NONE'}, model=${existingModel}`);
                
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
                        title: `🔧 SemanticGuard Power Mode - ${config.displayName}`
                    });
                    
                    if (!action) {
                        console.log("[SEMANTICGUARD BYOK] Settings menu cancelled");
                        return;
                    }
                    
                    if (action.action === "changeProvider") {
                        // Recursively call configureBYOK to start over
                        await vscode.commands.executeCommand('semanticguard.configureBYOK');
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
                            console.log("[SEMANTICGUARD BYOK] API key update cancelled");
                            return;
                        }
                        
                        // Test new key
                        console.log(`[SEMANTICGUARD BYOK] Testing new ${provider} API key...`);
                        vscode.window.showInformationMessage(`🔄 Testing ${config.displayName} connection...`);
                        
                        const testResult = await testProviderConnection(provider, newKey, existingModel);
                        
                        await context.secrets.store(config.keyName, newKey);
                        
                        let successMsg = `✅ ${config.displayName} API key updated successfully!`;
                        if (testResult.detectedTPM) {
                            successMsg += `\n\nDetected Rate Limits: ${testResult.detectedTPM.toLocaleString()} TPM, ~${testResult.detectedRPM} RPM (estimated)`;
                            if (testResult.detectedTPM >= 500000) {
                                successMsg += `\n🎉 Upgraded Account!`;
                            }
                        }
                        vscode.window.showInformationMessage(successMsg);
                        console.log(`[SEMANTICGUARD BYOK] ${provider} API key updated`);
                        
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
                            console.log("[SEMANTICGUARD BYOK] Model selection cancelled");
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
                                console.log("[SEMANTICGUARD BYOK] Custom model input cancelled");
                                return;
                            }
                        } else {
                            // Preset model selected
                            newModel = modelChoice.modelId;
                        }
                        
                        await context.globalState.update(config.modelKey, newModel);
                        vscode.window.showInformationMessage(`✅ Model updated to: ${newModel}`);
                        console.log(`[SEMANTICGUARD BYOK] ${provider} model updated to:`, newModel);
                        
                        // Refresh webview to show new model
                        semanticguardSidebarProvider.sendMessage({
                            type: 'updateModelBadge',
                            modelId: newModel
                        });
                        
                    } else if (action.action === "test") {
                        // Test Connection
                        console.log(`[SEMANTICGUARD BYOK] Testing ${provider} connection...`);
                        vscode.window.showInformationMessage(`🔄 Testing ${config.displayName} connection...`);
                        
                        const testResult = await testProviderConnection(provider, existingKey, existingModel);
                        
                        let successMsg = `✅ Connection successful! Model: ${existingModel}`;
                        if (testResult.detectedTPM) {
                            successMsg += `\n\nDetected Rate Limits: ${testResult.detectedTPM.toLocaleString()} TPM, ~${testResult.detectedRPM} RPM (estimated)`;
                            if (testResult.detectedTPM >= 500000) {
                                successMsg += `\n🎉 Upgraded Account!`;
                            }
                        }
                        vscode.window.showInformationMessage(successMsg);
                        console.log(`[SEMANTICGUARD BYOK] ${provider} connection test passed`);
                    }
                    
                    return;
                }
                
                // First-time setup flow (no existing credentials)
                console.log(`[SEMANTICGUARD BYOK] First-time setup for ${provider}`);
                
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
                    console.log("[SEMANTICGUARD BYOK] API key input cancelled");
                    vscode.window.showInformationMessage("BYOK configuration cancelled.");
                    return;
                }
                
                console.log(`[SEMANTICGUARD BYOK] ${provider} API key received, length:`, apiKey.length);

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
                    console.log("[SEMANTICGUARD BYOK] Model selection cancelled");
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
                        console.log("[SEMANTICGUARD BYOK] Custom model input cancelled");
                        vscode.window.showInformationMessage("BYOK configuration cancelled.");
                        return;
                    }
                } else {
                    // Preset model selected
                    modelId = modelChoice.modelId;
                }
                
                console.log(`[SEMANTICGUARD BYOK] ${provider} model selected:`, modelId);

                // Step 4: Test the connection
                console.log(`[SEMANTICGUARD BYOK] Testing ${provider} connection...`);
                vscode.window.showInformationMessage(`🔄 Testing ${config.displayName} connection...`);

                const testResult = await testProviderConnection(provider, apiKey, modelId);

                console.log(`[SEMANTICGUARD BYOK] ${provider} connection test successful`);

                // Step 5: Save credentials securely
                console.log(`[SEMANTICGUARD BYOK] Saving ${provider} credentials...`);
                await context.secrets.store(config.keyName, apiKey);
                await context.globalState.update(config.modelKey, modelId);
                console.log(`[SEMANTICGUARD BYOK] ${provider} credentials saved successfully`);

                // Step 6: Show success message with TPM info
                let successMsg = `✅ ${config.displayName} configured successfully! Model: ${modelId}`;
                if (testResult.detectedTPM) {
                    successMsg += `\n\nDetected Rate Limits: ${testResult.detectedTPM.toLocaleString()} TPM, ~${testResult.detectedRPM} RPM (estimated)`;
                    if (testResult.detectedTPM >= 500000) {
                        successMsg += `\n🎉 Upgraded Account!`;
                    }
                }
                vscode.window.showInformationMessage(successMsg);

                console.log(`[SEMANTICGUARD BYOK] Configuration complete. Provider: ${provider}, Model: ${modelId}`);

                // Refresh webview to show new model
                semanticguardSidebarProvider.sendMessage({
                    type: 'updateModelBadge',
                    modelId: modelId
                });

            } catch (error) {
                console.error("[SEMANTICGUARD BYOK] Configuration error:", error);
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
                    "HTTP-Referer": "https://github.com/dsadsadsadsadas/SemanticGuard",
                    "X-Title": "SemanticGuard Gatekeeper"
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
        
        // Detect TPM limits from response headers
        const { detectModelLimits } = require(path.join(context.extensionPath, 'token-bucket.js'));
        const { maxRpm, maxTpm } = await detectModelLimits(apiKey, model);
        
        const result = await testResponse.json();
        result.detectedTPM = maxTpm;
        result.detectedRPM = maxRpm;
        
        return result;
    }

    const togglePowerModeCmd = vscode.commands.registerCommand(
        "semanticguard.togglePowerMode",
        async () => {
            try {
                console.log("[SEMANTICGUARD POWER MODE] Toggle requested");
                
                // Get current provider (default to openrouter)
                const provider = context.globalState.get('semanticguard.provider') || 'openrouter';
                
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
                    const currentMode = context.globalState.get('semanticguard.mode') || 'local';
                    const newMode = currentMode === 'cloud' ? 'local' : 'cloud';
                    
                    console.log(`[SEMANTICGUARD POWER MODE] Toggling from ${currentMode} to ${newMode}`);
                    
                    await context.globalState.update('semanticguard.mode', newMode);
                    updateStatusBar(context);
                    
                    if (newMode === 'cloud') {
                        const model = context.globalState.get(modelKeys[provider]) || 
                                     (provider === 'openrouter' ? 'anthropic/claude-3.5-sonnet' : 'meta-llama/llama-4-scout-17b-16e-instruct');
                        vscode.window.showInformationMessage(
                            `✅ SemanticGuard: Power Mode Activated (${displayNames[provider]} - ${model})`
                        );
                        console.log(`[SEMANTICGUARD POWER MODE] ✅ Activated Power Mode with ${displayNames[provider]}, model: ${model}`);
                        outputChannel.appendLine(`[${new Date().toISOString()}] ✅ Power Mode Activated - Provider: ${displayNames[provider]}, Model: ${model}`);
                    } else {
                        vscode.window.showInformationMessage(
                            `✅ SemanticGuard: Local Mode Activated`
                        );
                        console.log("[SEMANTICGUARD POWER MODE] ✅ Activated Local Mode");
                        outputChannel.appendLine(`[${new Date().toISOString()}] ✅ Local Mode Activated`);
                    }
                } else {
                    // No key exists, trigger configuration flow
                    console.log("[SEMANTICGUARD POWER MODE] No API key found, triggering configuration");
                    await vscode.commands.executeCommand('semanticguard.configureBYOK');
                    
                    // After configuration, check if key was added and activate power mode
                    const keyAfterConfig = await context.secrets.get(keyNames[provider]);
                    if (keyAfterConfig) {
                        await context.globalState.update('semanticguard.mode', 'cloud');
                        updateStatusBar(context);
                        console.log("[SEMANTICGUARD POWER MODE] ✅ Activated Power Mode after configuration");
                        outputChannel.appendLine(`[${new Date().toISOString()}] ✅ Power Mode Activated after initial configuration`);
                    }
                }
            } catch (error) {
                console.error("[SEMANTICGUARD POWER MODE] Toggle error:", error);
                vscode.window.showErrorMessage(
                    `❌ Power Mode toggle failed: ${error.message}`
                );
            }
        }
    );

    const toggleV2PromptsCmd = vscode.commands.registerCommand(
        "semanticguard.toggleV2Prompts",
        async () => {
            const currentMode = context.globalState.get('semanticguard.experimental_v2_prompts') || false;
            const newMode = !currentMode;
            
            await context.globalState.update('semanticguard.experimental_v2_prompts', newMode);
            
            const status = newMode ? "ENABLED" : "DISABLED";
            const emoji = newMode ? "🧪" : "📝";
            
            vscode.window.showInformationMessage(
                `${emoji} SemanticGuard V2 Prompts: ${status} ${newMode ? '(Experimental - Reduces false positives)' : '(Using legacy prompts)'}`
            );
            
            console.log(`[SEMANTICGUARD V2] Experimental V2 prompts: ${status}`);
        }
    );

    const debugReasoningCmd = vscode.commands.registerCommand(
        "semanticguard.debugReasoning",
        async () => {
            const currentMode = context.globalState.get('semanticguard.debug_reasoning') || false;
            const newMode = !currentMode;
            
            await context.globalState.update('semanticguard.debug_reasoning', newMode);
            
            const status = newMode ? "ENABLED" : "DISABLED";
            const emoji = newMode ? "🔍" : "🔇";
            
            vscode.window.showInformationMessage(
                `${emoji} SemanticGuard Debug Reasoning: ${status} ${newMode ? '(Detailed logs in console)' : '(Normal logging)'}`
            );
            
            console.log(`[SEMANTICGUARD DEBUG] Debug reasoning mode: ${status}`);
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

                const cfg = vscode.workspace.getConfiguration("semanticguard");
                if (!cfg.get("enabled")) {
                    // Airbag disabled in settings
                    return;
                }

                // Bypass standard excludes if this is a Pillar file (Selective Pass)
                const relPath = vscode.workspace.asRelativePath(event.document.uri);
                const isPillar = relPath.startsWith(".semanticguard") && relPath.endsWith(".md");
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
                        console.warn('[SEMANTICGUARD] Server is OFFLINE. Strict mode enforcing BLOCK.');
                        // Sleek toast notification instead of modal
                        vscode.window.showErrorMessage(`🛑 SemanticGuard: Server offline — Save blocked in Strict mode`);
                        throw new Error("SemanticGuard Strict Mode: Server is offline. Save blocked.");
                    }
                    console.warn('[SEMANTICGUARD] Server is OFFLINE. Airbag failing open for this save.');
                    return;
                }

                // Queue the evaluation sequentially to protect the GPU
                await saveEvaluationQueue.enqueue(() => evaluateSave(event.document));
            } catch (error) {
                console.error('[SEMANTICGUARD ERROR] Save listener async task failed:', error);
                try { vscode.window.showErrorMessage(`SemanticGuard Extension Crash: ${error.message}`); } catch (e) { /* swallow */ }
                // Re-throw to let VS Code know the save participant failed (preserves previous behavior)
                throw error;
            }
        })());
    });

    const saveDoneHandler = vscode.workspace.onDidSaveTextDocument(async (document) => {
        console.log('[SEMANTICGUARD] Document Saved:', document.fileName);

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
 * Rule Sanctuary: Detects if a document is within the .semanticguard/ folder
 * Returns true if the file should be auto-accepted without audit
 */
function isRuleSanctuaryPath(document) {
    const relPath = vscode.workspace.asRelativePath(document.uri);
    // Normalize path separators for cross-platform compatibility
    const normalizedPath = relPath.replace(/\\/g, '/');

    // Check if path contains .semanticguard/ folder
    return normalizedPath.includes('.semanticguard/') || normalizedPath.startsWith('.semanticguard/');
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
        console.log('[SEMANTICGUARD] No changes since last audit. Skipping.');
        return [];
    }

    // Trivial change filter — skip if entire content change is just whitespace/comments/newlines
    // This is more reliable as it catches all cosmetic changes regardless of diff mode
    const lastSent = _lastSentContent.get(fileKey);
    if (lastSent) {
        const normalize = (text) => text.split(/\r?\n/).map(l => l.trim()).filter(l => l.length > 0).join('');
        if (normalize(currentContent) === normalize(lastSent)) {
            console.log('[SEMANTICGUARD] Trivial cosmetic change detected (indentation/newlines only). Skipping audit.');
            return [];
        }
    }

    const cfg = vscode.workspace.getConfiguration("semanticguard");
    let serverUrl = cfg.get("serverUrl") ?? "http://127.0.0.1:8001";
    const timeoutMs = cfg.get("timeoutMs") ?? 300_000;

    // Use auto-discovery if the configured URL doesn't work
    const discoveredUrl = await discoverServerURL();
    if (discoveredUrl && discoveredUrl !== serverUrl) {
        console.log(`[SEMANTICGUARD EVAL] Using discovered URL: ${discoveredUrl} instead of configured: ${serverUrl}`);
        serverUrl = discoveredUrl;
        // Update config for future use
        await cfg.update("serverUrl", discoveredUrl, vscode.ConfigurationTarget.Workspace);
    } else if (!discoveredUrl) {
        console.log(`[SEMANTICGUARD EVAL] ❌ No server available for evaluation`);
        if (cfg.get("enforcementMode") === "Strict") {
            // Sleek toast notification instead of modal
            vscode.window.showErrorMessage(`🛑 SemanticGuard: No server available — Save blocked in Strict mode`);
            throw new Error("SemanticGuard Strict Mode: No server available.");
        }
        return []; // Fail-open: allow save to proceed
    }

    const relPath = vscode.workspace.asRelativePath(document.uri);
    const isPillar = relPath.startsWith(".semanticguard") && relPath.endsWith(".md");

    // ============================================
    // THE META-GATE: Policing the Law (.semanticguard/*.md)
    // ============================================
    if (isPillar) {
        const fileName = path.basename(document.fileName);
        const incomingContent = currentContent;

        console.log(`[SEMANTICGUARD META-GATE] Pillar file save detected: ${fileName}`);

        updateStatusBar(extensionContext, 'auditing');
        semanticguardSidebarProvider.sendMessage({ type: 'scanning', title: 'Analysis: ' + fileName }, true);
        
        try {
            // Resolve the project root for the specific file being saved (multi-root workspace support)
            const projectPath = vscode.workspace.getWorkspaceFolder(document.uri)?.uri.fsPath
                ?? vscode.workspace.workspaceFolders?.[0]?.uri.fsPath
                ?? '';
            console.log(`[SEMANTICGUARD META-GATE] Resolved project_path: ${projectPath}`);
            const processorMode = vscode.workspace.getConfiguration("semanticguard").get("processor_mode") || "GPU";
            
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
                console.warn(`SemanticGuard: Meta-Gate server returned ${res.status} — failing open`);
                updateStatusBar(extensionContext, 'idle');
                return [];
            }

            const data = await res.json();
            const driftScore = data.drift_score ?? 0;
            const actionResult = data.action;
            const reasoning = data.reasoning || "[No reasoning provided by server]";

            const webviewMessage = {
                type: 'log',
                title: 'Analysis: ' + fileName,
                score: driftScore.toFixed(2),
                action: actionResult,
                reasoning: reasoning,
                filename: fileName,
                fullPath: document.uri.fsPath,
                findings: data.findings || [],  // V2: Use findings array
                violations: data.violations || [],  // Legacy support
            };
            semanticguardSidebarProvider.sendMessage(webviewMessage, actionResult === "REJECT");
            await executeAIAssistantActions(reasoning, actionResult, driftScore);

            if (actionResult === "REJECT") {
                const scoreDisplay = driftScore.toFixed(2);
                // Sleek toast notification instead of modal
                vscode.window.showErrorMessage(`🛑 SemanticGuard: Save blocked — Security violation detected (Score: ${scoreDisplay})`);
                throw new Error(`SemanticGuard Gatekeeper: architectural drift detected (score ${scoreDisplay})`);
            }

            setStatus("accepted");
            setTimeout(() => updateStatusBar(extensionContext, 'idle'), 2000);
            _lastAuditedContent.set(fileKey, currentContent);
            return [];
        } catch (err) {
            console.error("SemanticGuard Meta-Gate error:", err);
            updateStatusBar(extensionContext, 'idle');
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
        const extensionContext = global.semanticguardContext;
        if (!extensionContext) {
            console.error('[SEMANTICGUARD] Extension context not available');
            return; // Fail-open: allow save if context unavailable
        }
        const isPowerMode = extensionContext.globalState.get('semanticguard.mode') === 'cloud';

        let codeContent;
        
        // ── POWER MODE: Always send full file (no snapshot restrictions) ──
        if (isPowerMode) {
            console.log(`[SEMANTICGUARD POWER MODE] Sending full file (${totalLines} lines) for deep taint analysis`);
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
                        `🛡️ SemanticGuard: Indexed ${totalLines} lines — auditing changes from next save`,
                        8000
                    );
                    
                    console.log(`[SEMANTICGUARD] First save of large file (${totalLines} lines). Indexing silently, skipping audit.`);
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
                    console.log('[SEMANTICGUARD] No changes detected since last audit. Skipping.');
                    return [];
                }
                
                console.log(`[SEMANTICGUARD] Diff mode: sending ${codeContent.split('\n').length} lines of ${totalLines} total`);
            }
        }

        const pillars = readPillars(document);


        console.log(`[SEMANTICGUARD AIRBAG] Document save detected: ${fileName}`);

        updateStatusBar(extensionContext, 'auditing');
        semanticguardSidebarProvider.sendMessage({ type: 'scanning', title: 'Analysis: ' + fileName }, true);

        try {
            // Resolve the project root for the specific file being saved (multi-root workspace support)
            const projectPath = vscode.workspace.getWorkspaceFolder(document.uri)?.uri.fsPath
                ?? vscode.workspace.workspaceFolders?.[0]?.uri.fsPath
                ?? '';
            console.log(`[SEMANTICGUARD AIRBAG] Resolved project_path: ${projectPath}`);
            const processorMode = vscode.workspace.getConfiguration("semanticguard").get("processor_mode") || "GPU";
            
            // Record what we are about to send, regardless of verdict
            _lastSentContent.set(fileKey, currentContent);

            // ── TRAFFIC COP: Route based on mode ──────────────────────────────
            // Note: isPowerMode already checked above for snapshot logic
            
            let data;
            
            if (isPowerMode) {
                console.log("[SEMANTICGUARD TRAFFIC COP] Power Mode detected — routing through Layer 1 + Cloud");
                console.log(`[SEMANTICGUARD TRAFFIC COP] Sending full file: ${totalLines} lines for deep analysis`);
                
                // Strip comments to protect Layer 1 Regex from false positives
                const strippedCodeContent = stripCommentsPreserveLines(codeContent);
                
                // Step 1: Run Layer 1 on Python server
                const layer1Response = await fetchWithTimeout(`${serverUrl}/evaluate`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        filename: fileName,
                        code_snippet: strippedCodeContent,
                        pillars: pillars,
                        project_path: projectPath,
                        processor_mode: processorMode,
                        model_name: _selectedModel,
                        power_mode: true  // Signal to run Layer 1 only
                    }),
                }, timeoutMs);

                if (!layer1Response.ok) {
                    console.warn(`SemanticGuard: Layer 1 server returned ${layer1Response.status} — failing open`);
                    updateStatusBar(extensionContext, 'idle');
                    return [];
                }

                const layer1Data = await layer1Response.json();
                
                // Step 2: Check Layer 1 result
                if (layer1Data.action === "REJECT") {
                    // Layer 1 caught it — block immediately
                    console.log("[SEMANTICGUARD TRAFFIC COP] Layer 1 REJECT — blocking save");
                    data = layer1Data;
                } else if (layer1Data.action === "L1_PASS") {
                    // Layer 1 passed — call Cloud API for Layer 2
                    console.log("[SEMANTICGUARD TRAFFIC COP] Layer 1 passed — calling Cloud API");
                    
                    try {
                        const cloudResult = await callCloudAPI(extensionContext, {
                            filename: fileName,
                            code_snippet: codeContent,
                            pillars: pillars
                        });
                        
                        // ═══ REQUIREMENT 5: FALLBACK LINE NUMBER DETECTION ═══
                        // Process violations to correct line numbers using fallback logic
                        if (cloudResult.violations && Array.isArray(cloudResult.violations)) {
                            console.log(`[SEMANTICGUARD FALLBACK] Processing ${cloudResult.violations.length} violations`);
                            
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
                                    console.warn(`[SEMANTICGUARD FALLBACK] No violating_snippet for violation at line ${reportedLine}`);
                                    return violation;
                                }
                            });
                            
                            const correctedCount = cloudResult.violations.filter(v => v.line_corrected).length;
                            if (correctedCount > 0) {
                                console.log(`[SEMANTICGUARD FALLBACK] ✓ Corrected ${correctedCount} line numbers using fallback logic`);
                            }
                        }
                        
                        data = cloudResult;
                        console.log("[SEMANTICGUARD TRAFFIC COP] Cloud API result:", data.action);
                    } catch (cloudError) {
                        console.error("[SEMANTICGUARD TRAFFIC COP] Cloud API failed:", cloudError);
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
                            updateStatusBar(extensionContext, 'idle');
                            return [];
                        }
                    }
                } else {
                    // Unexpected response
                    data = layer1Data;
                }
            } else {
                // Local Mode: Standard full audit
                console.log("[SEMANTICGUARD TRAFFIC COP] Local Mode — running full local audit");
                
                // Strip comments to protect Layer 1 Regex from false positives
                const strippedCodeContent = stripCommentsPreserveLines(codeContent);
                
                const localStartTime = Date.now();
                const res = await fetchWithTimeout(`${serverUrl}/evaluate`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        filename: fileName,
                        code_snippet: strippedCodeContent,
                        pillars: pillars,
                        project_path: projectPath,
                        processor_mode: processorMode,
                        model_name: _selectedModel,
                        power_mode: false
                    }),
                }, timeoutMs);
                const localEndTime = Date.now();
                const localLatency = ((localEndTime - localStartTime) / 1000).toFixed(2);

                if (!res.ok) {
                    console.warn(`SemanticGuard: Airbag server returned ${res.status} — failing open`);
                    updateStatusBar(extensionContext, 'idle');
                    return [];
                }

                data = await res.json();
                
                // Add local audit metadata
                data.audit_mode = 'local';
                data.local_latency = localLatency;
            }
            // ── End Traffic Cop ────────────────────────────────────────────────
            const driftScore = data.drift_score ?? 0;
            const actionResult = data.action;
            const reasoning = data.reasoning || "[No reasoning provided by server]";

            const webviewMessage = {
                type: 'log',
                title: 'Analysis: ' + fileName,
                score: driftScore.toFixed(2),
                action: actionResult,
                reasoning: reasoning,
                filename: fileName,
                fullPath: document.uri.fsPath,
                findings: data.findings || [],  // V2: Use findings array
                violations: data.violations || [],  // Legacy support
                // Performance tracking metadata
                audit_mode: data.audit_mode || 'local',
                cloud_provider: data.cloud_provider || null,
                cloud_latency: data.cloud_latency || null,
                local_latency: data.local_latency || null,
            };

            semanticguardSidebarProvider.sendMessage(webviewMessage, actionResult === "REJECT");
            await executeAIAssistantActions(reasoning, actionResult, driftScore);

            if (actionResult === "REJECT") {
                const scoreDisplay = driftScore.toFixed(2);
                // Sleek toast notification instead of modal
                vscode.window.showErrorMessage(`🛑 SemanticGuard: Save blocked — Security violation detected (Score: ${scoreDisplay})`);
                throw new Error(`SemanticGuard Airbag: architectural drift detected (score ${scoreDisplay})`);
            }

            setStatus("accepted");
            setTimeout(() => updateStatusBar(extensionContext, 'idle'), 2000);
            _lastAuditedContent.set(fileKey, currentContent);
            return [];
        } catch (err) {
            console.error("SemanticGuard Airbag error:", err);
            updateStatusBar(extensionContext, 'idle');
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
        console.warn('[SEMANTICGUARD LINE INJECTION] Invalid code input, returning empty string');
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
            console.warn('[SEMANTICGUARD FALLBACK] No violating_snippet provided, using reported line number');
            return reportedLineNumber;
        }
        
        // Clean the snippet (remove line number prefix if present)
        const cleanSnippet = removeLineNumberPrefix(violatingSnippet);
        
        if (!cleanSnippet) {
            console.warn('[SEMANTICGUARD FALLBACK] Empty snippet after cleaning, using reported line number');
            return reportedLineNumber;
        }
        
        // First, check if reported line number is correct
        if (reportedLineNumber >= 1 && reportedLineNumber <= document.lineCount) {
            const reportedLine = document.lineAt(reportedLineNumber - 1); // Convert to 0-based
            const reportedLineText = reportedLine.text.trim();
            const cleanSnippetTrimmed = cleanSnippet.trim();
            
            if (reportedLineText === cleanSnippetTrimmed || reportedLineText.includes(cleanSnippetTrimmed)) {
                console.log(`[SEMANTICGUARD FALLBACK] ✓ Reported line ${reportedLineNumber} matches snippet`);
                return reportedLineNumber;
            }
        }
        
        // Fallback: Search for snippet in document
        console.log(`[SEMANTICGUARD FALLBACK] Line ${reportedLineNumber} doesn't match, searching for snippet...`);
        const documentText = document.getText();
        const snippetIndex = documentText.indexOf(cleanSnippet);
        
        if (snippetIndex === -1) {
            console.warn(`[SEMANTICGUARD FALLBACK] ⚠ Snippet not found in document: "${cleanSnippet.substring(0, 50)}..."`);
            return reportedLineNumber; // Use reported line as fallback
        }
        
        // Convert character offset to line number
        const position = document.positionAt(snippetIndex);
        const correctedLineNumber = position.line + 1; // Convert to 1-based
        
        console.log(`[SEMANTICGUARD FALLBACK] ✓ Corrected line number: ${reportedLineNumber} → ${correctedLineNumber}`);
        return correctedLineNumber;
        
    } catch (error) {
        console.error('[SEMANTICGUARD FALLBACK] Error in fallback detection:', error);
        return reportedLineNumber; // Safe fallback
    }
}

// ─── System Rules Loader ─────────────────────────────────────────────────────

/**
 * Load system_rules.md from the project's .semanticguard folder
 * @param {string} projectPath - Absolute path to project root
 * @returns {string} - Contents of system_rules.md or empty string if not found
 */
function loadSystemRules(projectPath) {
    try {
        const systemRulesPath = path.join(projectPath, '.semanticguard', 'system_rules.md');
        if (fs.existsSync(systemRulesPath)) {
            const content = fs.readFileSync(systemRulesPath, 'utf-8');
            console.log(`[SEMANTICGUARD RULES] Loaded system_rules.md (${content.length} chars)`);
            return content;
        } else {
            console.warn(`[SEMANTICGUARD RULES] system_rules.md not found at: ${systemRulesPath}`);
            return '';
        }
    } catch (error) {
        console.error(`[SEMANTICGUARD RULES] Error loading system_rules.md:`, error);
        return '';
    }
}

// ─── Ghost Stripper: Strip Comments While Preserving Line Numbers ──────────

/**
 * Remove full-line Python comments while preserving exact line count.
 * Replaces comment lines with blank lines to maintain line number alignment.
 * @param {string} code - Source code
 * @returns {string} - Code with comments stripped, line count preserved
 */
function stripCommentsPreserveLines(code) {
    return code.split('\n').map(line => {
        const trimmed = line.trim();
        // If line is a full-line comment, replace with blank line
        if (trimmed.startsWith('#')) {
            return '';
        }
        return line;
    }).join('\n');
}

// ─── Cloud API Call (Power Mode - Multi-Provider) ────────────────────────────

async function callCloudAPI(context, payload) {
    const startTime = Date.now(); // High-resolution performance timer
    
    try {
        // Get current provider
        const provider = context.globalState.get('semanticguard.provider') || 'openrouter';
        
        // Check for experimental V2 prompt mode
        const useV2Prompts = context.globalState.get('semanticguard.experimental_v2_prompts') || false;
        
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
                       (provider === 'openrouter' ? 'anthropic/claude-3.5-sonnet' : 'meta-llama/llama-4-scout-17b-16e-instruct');
        
        if (!apiKey) {
            throw new Error(`${config.displayName} API key not found. Please configure Power Mode first.`);
        }
        
        console.log(`[SEMANTICGUARD POWER MODE] Calling ${config.displayName} with model: ${modelId} (V${useV2Prompts ? '2' : '1'} prompts)`);
        
        // ═══ LOAD SYSTEM RULES FROM PROJECT ═══
        const projectPath = payload.project_path || vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || '';
        const systemRules = loadSystemRules(projectPath);
        
        if (!systemRules) {
            console.warn('[SEMANTICGUARD POWER MODE] No system_rules.md found - using empty ruleset');
        }
        
        // ═══ GHOST STRIPPER: Remove Comments While Preserving Line Numbers ═══
        const originalCode = payload.code_snippet;
        const strippedCode = stripCommentsPreserveLines(originalCode);
        console.log(`[SEMANTICGUARD GHOST STRIPPER] Stripped comments from ${originalCode.split('\n').length} lines`);
        
        // ═══ REQUIREMENT 1: LINE NUMBER INJECTION ═══
        // Inject line numbers into code before sending to Cloud API
        const numberedCode = injectLineNumbers(strippedCode);
        console.log(`[SEMANTICGUARD LINE INJECTION] Injected line numbers into ${strippedCode.split('\n').length} lines`);
        
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
            // V1 PURGED - Now using V2 Taint Analysis System
            // MERGE STEP 1: Inject system_rules.md
            const rulesBlock = systemRules ? `
===============================================================================

PROJECT-SPECIFIC SECURITY RULES (from system_rules.md):

${systemRules}

===============================================================================
` : '';
            
            if (systemRules) {
                console.log(`[SEMANTICGUARD RULES] Injected ${systemRules.length} chars into prompt`);
            }
            
            systemPrompt = `You are an AGGRESSIVE AppSec auditor focused on EXPLOITABILITY, not patterns.

Your job is to find REAL, EXPLOITABLE security issues. Avoid false positives.

${rulesBlock}
ZERO-TOLERANCE FOR HARDCODED FALSE POSITIVES:
- Hardcoded strings are SAFE unless they are actual secrets/credentials
- Model names, file paths, configuration values are NOT vulnerabilities
- Only flag hardcoded API keys, passwords, tokens, or secrets

TAINT ANALYSIS RULES (STRICT):
1. SOURCE: Only user-controlled input is dangerous

Untrusted sources — trace these:
- HTTP: request.json(), req.query, req.body, req.params, form data
- Browser: document.cookie, localStorage, sessionStorage, window.location, location.href, location.hash, location.search, URLSearchParams, window.name
- Runtime: sys.argv[1+], os.environ (when user-influenced), file uploads, user session values, WebSocket messages
- DOM: innerHTML reads, textContent reads, getAttribute()

CRITICAL: Unvalidated Input Deserialization
- request.json or req.body used WITHOUT validation/sanitization is a vulnerability
- Look for missing jsonschema, validate_json, pydantic, marshmallow, joi, yup, zod
- Flag if user data reaches application logic without schema validation

Trusted sources — do NOT flag:
- Hardcoded string literals (unless they ARE the dangerous payload)
- Script constants defined in-file
- os.environ["KEY"] = "literal" (assigning literal)
- os.environ.copy() (copying full env, not user-controlled key)

2. SINK: Dangerous sinks — flag if untrusted input reaches these:

Code Execution:
- eval(), exec(), compile(), Function() constructor
- subprocess with shell=True, os.system(), os.popen()
- spawn() with shell mode or user-controlled binary

CRITICAL SUBPROCESS RULE:
- subprocess.run(['command', 'arg']) with list arguments and NO shell=True is SAFE
- subprocess.run('command', shell=True) with string and shell=True is DANGEROUS
- If you see subprocess with list arguments and no shell=True → DO NOT FLAG IT

DOM/XSS:
- innerHTML, outerHTML, document.write(), document.writeln()
- insertAdjacentHTML(), srcdoc attribute
- setTimeout(string), setInterval(string)

Injection:
- SQL: string concatenation in queries (not parameterized)
- Template: Jinja2 render with user input, EJS with user input
- Path: path.join() / os.path.join() with user-controlled segments without realpath() + startswith() validation

Deserialization:
- pickle.loads(), yaml.load() (not safe_load), unserialize()

Network:
- fetch(), requests.get/post() with user-controlled URLs (SSRF)
- XMLHttpRequest with user-controlled target

3. FLOW: Vulnerability exists ONLY if dangerous user input reaches dangerous sink
   - Trace the exact data flow from source to sink
   - If user input is sanitized, validated, or hardcoded → SAFE

CRITICAL SECURITY PATTERNS (ALWAYS FLAG):
- Hardcoded credentials: API keys, passwords, tokens, secrets
- User input in eval(), exec(), os.system()
- User input in SQL string concatenation
- User input in file paths without validation
- Hardcoded XSS payloads in innerHTML, document.write()
- Hardcoded dangerous strings in eval()

RULE_ID MAPPING (MANDATORY - NEVER USE "NONE"):

**For XSS/DOM Issues**:
- "RULE_11_STEP0: Static Dangerous Content" (hardcoded XSS, innerHTML with <script>)

**For Command Injection**:
- "RULE_102: Shell Injection" (subprocess with shell=True, os.system)

**For Code Injection**:
- "RULE_101: Eval Injection" (eval(), exec(), compile())

**For SQL Injection**:
- "RULE_103: SQL Injection" (string concatenation in SQL)

**For Hardcoded Secrets**:
- "RULE_100: Hardcoded Secrets" (API keys, passwords, tokens)

**For Data Leaks**:
- "RULE_105: Logging Gate" (sensitive data in logs)
- "RULE_104: PHI Protection" (PII/PHI in insecure sinks)

**For Custom Rules** (if system_rules.md has RULE_8, RULE_9, etc.):
- Use exact format: "RULE_8: PHI_PROTECTION"

**Default Fallbacks** (if no specific rule matches):
- "RULE_11_STEP0: Static Dangerous Content" (for hardcoded dangerous strings)
- "RULE_11: Multi-Hop Taint Analysis" (for dynamic taint flows)

REQUIRED JSON OUTPUT (STRICT SCHEMA):
{
  "findings": [
    {
      "severity": "CRITICAL|HIGH|MEDIUM|LOW",
      "rule_id": "<use exact format from RULE_ID MAPPING above - NEVER use NONE>",
      "vulnerability_type": "Hardcoded Secrets|Code Injection|SQL Injection|Path Traversal|DOM-based XSS|etc",
      "line_number": <exact_line_number>,
      "description": "Brief description of the actual vulnerability"
    }
  ]
}

FEW-SHOT EXAMPLES:

Example 1 (Hardcoded XSS):
{"findings": [{"severity": "CRITICAL", "rule_id": "RULE_11_STEP0: Static Dangerous Content", "vulnerability_type": "DOM-based XSS", "line_number": 4, "description": "Hardcoded XSS payload in innerHTML"}]}

Example 2 (eval with hardcoded string):
{"findings": [{"severity": "CRITICAL", "rule_id": "RULE_101: Eval Injection", "vulnerability_type": "Code Injection", "line_number": 1, "description": "eval() with dangerous hardcoded string"}]}

Example 3 (Safe code):
{"findings": []}

If safe: {"findings": []}

ANTI-HALLUCINATION MANDATE:
- If no user input reaches dangerous sinks → {"findings": []}
- If only hardcoded values are used → {"findings": []} (unless credentials or dangerous strings)
- If input is properly sanitized → {"findings": []}
- NO false positives for safe patterns

ZERO-TOLERANCE NO-WEASEL MANDATE:
You are FORBIDDEN from creating a finding if your own reasoning contains ANY of these phrases:
- "Although hardcoded"
- "Despite being an array"
- "Although the arguments are hardcoded"
- "Although the binary is hardcoded"
- "Could potentially"
- "An attacker could potentially"
- "Might be"
- "If an attacker"

These phrases prove you already know the code is SAFE.
If you catch yourself writing them, DISCARD the finding.
A finding that admits inputs are hardcoded is a LOGIC FAILURE.

Exception: Step 0 static dangerous content (hardcoded XSS payloads, hardcoded eval strings) — these are flagged regardless.

===============================================================================

PHASE 5 – PRE-FLIGHT CHECKLIST (mandatory before writing any JSON):

For EVERY potential finding:
  Q1: Can an attacker change this value without already having shell access? NO → REMOVE IT.
  Q2: Does my reasoning use a weasel phrase from above?                    YES → REMOVE IT.
  Q3: Is the "secret" a model name, port, host, or local URL?              YES → REMOVE IT.

After the checklist – if zero findings remain, output: {"findings": []}

===============================================================================

FINAL RULE: Pattern matching = noise. Proven taint path = finding. When in doubt, return {"findings": []}.
False negatives are recoverable. False positives destroy trust.`;

            userPrompt = `Analyze this code for REAL security vulnerabilities using strict taint analysis:

Filename: ${payload.filename}

Code:
\`\`\`
${numberedCode}
\`\`\`

Apply taint analysis:
1. Identify user-controlled sources (if any)
2. Trace data flow to dangerous sinks
3. Only flag if user input reaches dangerous sink

Return JSON with findings array. If safe, return {"findings": []}.`;
        }

        // Build headers based on provider
        const headers = {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${apiKey}`
        };
        
        // OpenRouter requires additional headers
        if (provider === 'openrouter') {
            headers["HTTP-Referer"] = "https://github.com/dsadsadsadsadas/SemanticGuard";
            headers["X-Title"] = "SemanticGuard Gatekeeper";
        }

        // 🔍 DEBUG INSTRUMENTATION: Capture raw payload before API call
        const DEBUG_PAYLOAD = {
            "system_prompt": systemPrompt,
            "user_prompt": userPrompt,
            "model": modelId,
            "temperature": 0.3,
            "max_tokens": 2000,
            "response_format": { type: "json_object" },
            "post_ghost_strip_content": strippedCode,
            "post_line_injection_content": numberedCode,
            "provider": config.displayName,
            "use_v2_prompts": useV2Prompts
        };
        const fs = require('fs');
        fs.writeFileSync("debug_extension_payload.json", JSON.stringify(DEBUG_PAYLOAD, null, 2), 'utf-8');
        console.log('[SEMANTICGUARD DEBUG] Raw payload written to debug_extension_payload.json');

        const response = await fetchWithTimeout(config.endpoint, {
            method: "POST",
            headers: headers,
            body: JSON.stringify({
                model: modelId,
                messages: [
                    { role: "system", content: systemPrompt },
                    { role: "user", content: userPrompt }
                ],
                temperature: 0.3,  // Aligned with stress_test.py for consistency
                max_tokens: 2000,
                response_format: { type: "json_object" }  // Force strict JSON mode
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
        
        console.log(`[SEMANTICGUARD POWER MODE] Raw response from ${config.displayName}:`, content);
        
        // 🛠️ BULLETPROOF JSON EXTRACTOR - Handles nested braces correctly
        // 1. Strip out markdown code blocks if the LLM hallucinated them
        let cleanResponse = content.replace(/```json/gi, '').replace(/```/g, '').trim();
        
        // 2. Find the boundaries of the outermost JSON object using string indices
        const firstBrace = cleanResponse.indexOf('{');
        if (firstBrace === -1) {
            throw new Error(`No JSON object found in ${config.displayName} response`);
        }
        
        // 3. Find the matching closing brace by counting nested braces
        let braceCount = 0;
        let lastBrace = -1;
        
        for (let i = firstBrace; i < cleanResponse.length; i++) {
            if (cleanResponse[i] === '{') {
                braceCount++;
            } else if (cleanResponse[i] === '}') {
                braceCount--;
                if (braceCount === 0) {
                    lastBrace = i;
                    break; // Found the matching closing brace
                }
            }
        }
        
        if (lastBrace === -1) {
            throw new Error(`Incomplete JSON object in ${config.displayName} response`);
        }
        
        // 4. Extract the complete JSON object from first { to matching }
        const jsonString = cleanResponse.substring(firstBrace, lastBrace + 1);
        
        // 5. Parse the safely extracted string
        let result;
        try {
            result = JSON.parse(jsonString);
            console.log(`[SEMANTICGUARD POWER MODE] ✅ Successfully parsed JSON from ${config.displayName}`);
        } catch (parseError) {
            console.error(`[SEMANTICGUARD POWER MODE] JSON parse failed:`, parseError);
            console.error(`[SEMANTICGUARD POWER MODE] Attempted to parse:`, jsonString);
            throw new Error(`Invalid JSON from ${config.displayName}: ${parseError.message}`);
        }
        
        // V2 Response Processing and Validation
        // ALWAYS process findings format (both V1 and V2 use it now)
        result = await processV2Response(result, config.displayName, payload);
        
        // Calculate performance metrics
        const duration = (Date.now() - startTime) / 1000; // Convert to seconds
        
        // Add performance metadata to result
        result.cloud_provider = config.displayName;
        result.cloud_latency = duration.toFixed(2);
        result.audit_mode = 'cloud';
        result.prompt_version = useV2Prompts ? 'v2' : 'v1';
        
        console.log(`[SEMANTICGUARD POWER MODE] Parsed result from ${config.displayName}:`, result);
        console.log(`[SEMANTICGUARD POWER MODE] ⚡ Performance: ${duration.toFixed(2)}s latency`);
        
        return result;
        
    } catch (error) {
        console.error("[SEMANTICGUARD POWER MODE] Cloud API error:", error);
        throw error;
    }
}

// ─── V2 Response Processing and Validation ──────────────────────────────────

async function processV2Response(v2Response, providerName, payload) {
    const extensionContext = global.semanticguardContext;
    const debugMode = extensionContext?.globalState.get('semanticguard.debug_reasoning') || false;
    
    if (debugMode) {
        console.log(`[SEMANTICGUARD V2 DEBUG] ═══════════════════════════════════════`);
        console.log(`[SEMANTICGUARD V2 DEBUG] Processing V2 findings from ${providerName}`);
        console.log(`[SEMANTICGUARD V2 DEBUG] Raw V2 Response:`, JSON.stringify(v2Response, null, 2));
        console.log(`[SEMANTICGUARD V2 DEBUG] ═══════════════════════════════════════`);
    } else {
        console.log(`[SEMANTICGUARD V2] Processing V2 findings from ${providerName}`);
    }
    
    // V2 FINDINGS FORMAT: {"findings": [...]}
    const findings = v2Response.findings || [];
    
    if (debugMode) {
        console.log(`[SEMANTICGUARD V2 DEBUG] Extracted ${findings.length} findings`);
        findings.forEach((finding, index) => {
            console.log(`[SEMANTICGUARD V2 DEBUG] Finding ${index + 1}:`, finding);
        });
    }
    
    // Convert V2 findings to legacy format for compatibility with existing UI
    const legacyResponse = convertFindingsToLegacyFormat(findings, v2Response);
    
    if (debugMode) {
        console.log(`[SEMANTICGUARD V2 DEBUG] ═══════════════════════════════════════`);
        console.log(`[SEMANTICGUARD V2 DEBUG] Final V2 Analysis:`);
        console.log(`[SEMANTICGUARD V2 DEBUG] - Findings Count: ${findings.length}`);
        console.log(`[SEMANTICGUARD V2 DEBUG] - Legacy Action: ${legacyResponse.action}`);
        console.log(`[SEMANTICGUARD V2 DEBUG] - Legacy Score: ${legacyResponse.drift_score}`);
        console.log(`[SEMANTICGUARD V2 DEBUG] ═══════════════════════════════════════`);
    } else {
        console.log(`[SEMANTICGUARD V2] Converted to legacy format:`, legacyResponse);
    }
    
    return legacyResponse;
}

// V2 PURGE: Legacy retry function removed - V2 findings format is simpler and more reliable

function convertFindingsToLegacyFormat(findings, rawResponse) {
    // V2 FINDINGS FORMAT: Convert {"findings": [...]} to legacy format
    
    if (!findings || findings.length === 0) {
        // SAFE: No findings
        return {
            action: "ACCEPT",
            drift_score: 0.0,
            reasoning: "No security vulnerabilities detected.",
            violations: [],
            findings: [] // Include V2 findings for new UI
        };
    }
    
    // VULNERABLE: Has findings
    const maxSeverity = getMaxSeverity(findings);
    const driftScore = severityToScore(maxSeverity);
    
    // Convert findings to legacy violations format for backward compatibility
    const violations = findings.map((finding, index) => ({
        rule_id: finding.rule_id || `SECURITY_VIOLATION_${index + 1}`,
        rule_name: finding.vulnerability_type || "Security Issue",
        line_number: finding.line_number || 0,
        violation: finding.description || "Security vulnerability detected.",
        confidence: "HIGH", // V2 doesn't use confidence
        severity: finding.severity || "MEDIUM"
    }));
    
    const reasoning = findings.length === 1 
        ? `Security vulnerability: ${findings[0].description}`
        : `${findings.length} security vulnerabilities detected.`;
    
    return {
        action: "REJECT",
        drift_score: driftScore,
        reasoning: reasoning,
        violations: violations,
        findings: findings // Include V2 findings for new UI
    };
}

function getMaxSeverity(findings) {
    const severityOrder = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];
    for (const severity of severityOrder) {
        if (findings.some(f => f.severity === severity)) {
            return severity;
        }
    }
    return "LOW";
}

function severityToScore(severity) {
    const severityToScore = {
        "CRITICAL": 1.0,
        "HIGH": 0.8,
        "MEDIUM": 0.6,
        "LOW": 0.3
    };
    return severityToScore[severity] || 0.3;
}

// ─── Pillar Reader ────────────────────────────────────────────────────────────

function readPillars(document) {
    // Resolve the correct workspace folder for the given document (multi-root support)
    const workspaceFolder = document
        ? vscode.workspace.getWorkspaceFolder(document.uri)
        : vscode.workspace.workspaceFolders?.[0];

    if (!workspaceFolder) return emptyPillars();

    const semanticguardDir = path.join(workspaceFolder.uri.fsPath, ".semanticguard");
    const read = (name) => {
        const filePath = path.join(semanticguardDir, name);
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
    console.log(`[SEMANTICGUARD HEALTH] Starting health check...`);

    // Use auto-discovery to find the correct server URL
    const discoveredUrl = await discoverServerURL();

    if (!discoveredUrl) {
        console.log(`[SEMANTICGUARD HEALTH] ❌ No server found via auto-discovery`);
        serverOnline = false;
        updateStatusBar(global.semanticguardContext);

        // Output detailed diagnostics to VS Code channel
        outputChannel.appendLine(`[${new Date().toISOString()}] Health Check Status: Failed (Auto-Discovery)`);
        outputChannel.appendLine(`  Solution: Start server with 'python start_server.py --host 0.0.0.0'`);
        
        return;
    }

    try {
        console.log(`[SEMANTICGUARD HEALTH] Using discovered URL: ${discoveredUrl}`);
        const res = await fetchWithTimeout(`${discoveredUrl}/health`, {}, 4000);
        const data = await res.json();

        console.log(`[SEMANTICGUARD HEALTH] ✅ Server response: ${JSON.stringify(data)}`);

        // Update configuration with working URL for future requests
        const cfg = vscode.workspace.getConfiguration("semanticguard");
        if (cfg.get("serverUrl") !== discoveredUrl) {
            console.log(`[SEMANTICGUARD HEALTH] Updating serverUrl config to: ${discoveredUrl}`);
            await cfg.update("serverUrl", discoveredUrl, vscode.ConfigurationTarget.Workspace);
        }

        serverOnline = data.status === "ok";
        updateStatusBar(global.semanticguardContext);

    } catch (error) {
        console.log(`[SEMANTICGUARD HEALTH] ❌ Health check failed: ${error.message}`);

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
        updateStatusBar(global.semanticguardContext);
    }
}

// ─── Status Bar ───────────────────────────────────────────────────────────────

const STATUS_MAP = {
    online: { text: "🛡️ SemanticGuard: Watching...", tooltip: "SemanticGuard online — airbag armed", bg: undefined },
    loading: { text: "$(shield) SemanticGuard ⏳", tooltip: "SemanticGuard online — model loading…", bg: undefined },
    checking: { text: "$(sync~spin) Auditing...", tooltip: "SemanticGuard — evaluating save…", bg: new vscode.ThemeColor("terminal.ansiYellow") },
    accepted: { text: "🛡️ SemanticGuard: Accepted ✅", tooltip: "SemanticGuard — save ACCEPTED", bg: new vscode.ThemeColor("statusBarItem.prominentBackground") },
    offline: { text: "$(shield) SemanticGuard ⚫", tooltip: "SemanticGuard offline — saves pass through", bg: undefined },
    powerMode: { text: "$(zap) SemanticGuard: Power Mode", tooltip: "SemanticGuard Power Mode — using cloud AI", bg: undefined }
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
    const mode = context?.globalState.get('semanticguard.mode');
    const provider = context?.globalState.get('semanticguard.provider') || 'openrouter';
    
    const providerDisplayNames = {
        openrouter: "OpenRouter",
        groq: "Groq"
    };
    
    console.log(`[SEMANTICGUARD STATUS] Updating status bar - mode: ${mode}, provider: ${provider}, state: ${state}, serverOnline: ${serverOnline}`);
    
    // Priority 1: If server is offline, always show offline (regardless of mode)
    if (!serverOnline) {
        setStatus('offline');
        console.log(`[SEMANTICGUARD STATUS] ✅ Status bar set to offline (server down)`);
        return;
    }
    
    // Priority 2: Handle active audit state (with yellow spinner)
    if (state === 'auditing') {
        // During audit, show yellow spinner but preserve mode identity
        if (mode === 'cloud') {
            statusBarItem.text = `$(sync~spin) Auditing...`;
            statusBarItem.color = new vscode.ThemeColor('terminal.ansiYellow');
            statusBarItem.tooltip = `SemanticGuard: Auditing code with Power Mode`;
        } else {
            setStatus('checking');
        }
        console.log(`[SEMANTICGUARD STATUS] ✅ Status bar set to auditing (mode: ${mode})`);
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
                `$(zap) SemanticGuard: Power Mode`,
                `SemanticGuard Power Mode — ${displayName}: ${modelId}`
            );
            console.log(`[SEMANTICGUARD STATUS] ✅ Status bar set to Power Mode with ${displayName}: ${modelId}`);
        } else if (apiKey) {
            setStatus(
                'powerMode',
                `$(zap) SemanticGuard: Power Mode`,
                `SemanticGuard Power Mode — ${displayName}`
            );
            console.log(`[SEMANTICGUARD STATUS] ✅ Status bar set to Power Mode with ${displayName} (no model specified)`);
        } else {
            setStatus(
                'powerMode',
                `$(zap) SemanticGuard: Power Mode [No API Key]`,
                `SemanticGuard Power Mode — API key not configured`
            );
            console.log(`[SEMANTICGUARD STATUS] ⚠️ Status bar set to Power Mode but no API key found`);
        }
    } else {
        // Priority 4: Server online, Local Mode - clear any yellow color
        statusBarItem.color = undefined;
        setStatus('online');
        console.log(`[SEMANTICGUARD STATUS] ✅ Status bar set to online (local mode)`);
    }
}

// ─── Commands ─────────────────────────────────────────────────────────────────

async function showStatus() {
    const cfg = vscode.workspace.getConfiguration("semanticguard");
    const url = cfg.get("serverUrl");
    const enabled = cfg.get("enabled");
    vscode.window.showInformationMessage(
        `🛡️ SemanticGuard Gatekeeper\n\nServer: ${url}\nAirbag: ${enabled ? "ARMED ✅" : "DISABLED ⚫"}\nServer: ${serverOnline ? "online" : "offline"}`
    );
}

async function toggleEnabled() {
    const cfg = vscode.workspace.getConfiguration("semanticguard");
    const current = cfg.get("enabled");
    await cfg.update("enabled", !current, vscode.ConfigurationTarget.Global);
    vscode.window.showInformationMessage(`🛡️ SemanticGuard Airbag: ${!current ? "ARMED ✅" : "DISABLED ⚫"}`);
    setStatus(!current ? (serverOnline ? "online" : "offline") : "offline");
}

function openPillarFile(name) {
    const folders = vscode.workspace.workspaceFolders;
    if (!folders?.length) return;
    const filePath = path.join(folders[0].uri.fsPath, ".semanticguard", name);
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
        console.warn('[SEMANTICGUARD AI AUTONOMY] No workspace folder open - cannot execute file operations');
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
        console.log(`[SEMANTICGUARD AI AUTONOMY] Found [${sectionName}] section - using explicit actions`);

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
        console.log('[SEMANTICGUARD AI AUTONOMY] No [AI_ASSISTANT_ACTIONS] found - using fallback heuristics');

        let thoughtMatch = llmResponse.match(/\[THOUGHT\]([\s\S]*?)(?:\[|$)/);
        if (!thoughtMatch) {
            console.log('[SEMANTICGUARD AI AUTONOMY] No [THOUGHT] section found - continuing without thought heuristics');
            // Continue without returning so this autonomy code cannot block the save/fetch flow.
            thoughtMatch = ['', ''];
        }

        const thought = (thoughtMatch[1] || '').trim().toLowerCase();
        const timestamp = new Date().toISOString().split('T')[0];

        // HEURISTIC 1: Detect rule violations (high drift score + REJECT)
        if (verdict === 'REJECT' && score >= 0.40) {
            const violationKeywords = ['violates', 'breaks', 'forbidden', 'not allowed', 'against rule'];
            if (violationKeywords.some(kw => thought.includes(kw))) {
                console.log('[SEMANTICGUARD AI AUTONOMY] Detected rule violation - recording in problems');

                const content = `## Problem: Rule Violation Detected (${timestamp})
**Status**: UNRESOLVED
**Drift Score**: ${score.toFixed(2)}
**Description**: Code violates architectural rules
**AI Analysis**: ${thoughtMatch[1].trim().substring(0, 200)}...
`;
                if (await appendToFile(projectRoot, '.semanticguard/problems_and_resolutions.md', content)) {
                    executedCount++;
                }
            }
        }

        // HEURISTIC 2: Detect errors/failures
        const errorKeywords = ['error', 'failed', 'doesn\'t work', 'broken', 'issue', 'problem'];
        if (errorKeywords.some(kw => thought.includes(kw))) {
            console.log('[SEMANTICGUARD AI AUTONOMY] Detected error pattern - recording in problems');

            const content = `## Problem: Error Detected (${timestamp})
**Status**: UNRESOLVED
**Description**: AI detected potential error in code
**AI Analysis**: ${thoughtMatch[1].trim().substring(0, 200)}...
`;
            if (await appendToFile(projectRoot, '.semanticguard/problems_and_resolutions.md', content)) {
                executedCount++;
            }
        }

        // HEURISTIC 3: Detect pattern compliance (low drift score + ACCEPT)
        if (verdict === 'ACCEPT' && score <= 0.15) {
            const patternKeywords = ['follows pattern', 'correct approach', 'good practice', 'recommended', 'aligns with'];
            if (patternKeywords.some(kw => thought.includes(kw))) {
                console.log('[SEMANTICGUARD AI AUTONOMY] Detected pattern compliance - noting success');

                const content = `## Success: Pattern Followed (${timestamp})
**Drift Score**: ${score.toFixed(2)}
**Description**: Code follows architectural patterns correctly
**AI Analysis**: ${thoughtMatch[1].trim().substring(0, 200)}...
`;
                if (await appendToFile(projectRoot, '.semanticguard/history_phases.md', content)) {
                    executedCount++;
                }
            }
        }
    }

    // Show notification if any actions were executed
    if (executedCount > 0) {
        vscode.window.showInformationMessage(
            `🤖 SemanticGuard AI Autonomy: Executed ${executedCount} pillar update(s)`,
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
            console.warn(`[SEMANTICGUARD AI AUTONOMY] File not found: ${fullPath} - skipping`);
            return false;
        }

        const existingContent = fs.readFileSync(fullPath, 'utf-8');
        const needsNewline = existingContent.length > 0 && !existingContent.endsWith('\n');
        const contentToAppend = (needsNewline ? '\n' : '') + content + '\n';

        fs.appendFileSync(fullPath, contentToAppend, 'utf-8');
        console.log(`[SEMANTICGUARD AI AUTONOMY] ✅ Successfully appended to ${filePath}`);
        return true;

    } catch (error) {
        console.error(`[SEMANTICGUARD AI AUTONOMY] ❌ Failed to append to ${filePath}:`, error);
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

class SemanticGuardSidebarProvider {
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
            console.log('[SEMANTICGUARD WEBVIEW] Received message:', message);
            
            // Handle BYOK configuration request
            if (message.command === 'configure_byok') {
                console.log('[SEMANTICGUARD WEBVIEW] Executing semanticguard.configureBYOK command');
                try {
                    await vscode.commands.executeCommand('semanticguard.configureBYOK');
                    console.log('[SEMANTICGUARD WEBVIEW] Command executed successfully');
                } catch (error) {
                    console.error('[SEMANTICGUARD WEBVIEW] Command execution failed:', error);
                    vscode.window.showErrorMessage(`Failed to open BYOK config: ${error.message}`);
                }
                return;
            }
            
            // Handle Power Mode toggle request
            if (message.command === 'toggle_power_mode') {
                console.log('[SEMANTICGUARD WEBVIEW] Executing semanticguard.togglePowerMode command');
                try {
                    await vscode.commands.executeCommand('semanticguard.togglePowerMode');
                    console.log('[SEMANTICGUARD WEBVIEW] Power mode toggled successfully');
                } catch (error) {
                    console.error('[SEMANTICGUARD WEBVIEW] Power mode toggle failed:', error);
                    vscode.window.showErrorMessage(`Failed to toggle power mode: ${error.message}`);
                }
                return;
            }

            if (message.command === 'resign_vault') {
                const cfg = vscode.workspace.getConfiguration("semanticguard");
                const serverUrl = cfg.get("serverUrl") ?? "http://127.0.0.1:8000";
                try {
                    vscode.window.showInformationMessage("🛡️ Re-signing SemanticGuard Vault...");
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
                    vscode.window.showErrorMessage(`❌ Failed to connect to SemanticGuard server to re-sign: ${err.message}`);
                }
            }

            if (message.command === 'revert_save') {
                const { filename } = message;
                const folders = vscode.workspace.workspaceFolders;
                if (!folders?.length) return;
                const vaultPath = path.join(folders[0].uri.fsPath, ".semanticguard", "semanticguard_vault", filename);
                const livePath = path.join(folders[0].uri.fsPath, ".semanticguard", filename);
                if (fs.existsSync(vaultPath)) {
                    fs.copyFileSync(vaultPath, livePath);
                    const doc = await vscode.workspace.openTextDocument(livePath);
                    await vscode.window.showTextDocument(doc);
                    vscode.window.showInformationMessage(`🛡️ Reverted ${filename} to vault state.`);
                    this.sendMessage({ type: 'reset' });
                }
            }

            if (message.command === 'force_override') {
                vscode.window.showWarningMessage(`⚠️ Force Override acknowledged. SemanticGuard will allow the next save for this file.`);
                this.sendMessage({ type: 'reset' });
            }

            if (message.command === 'apply_fix') {
                const { line, text, ruleId, reason, filePath } = message;
                
                const relativePath = vscode.workspace.asRelativePath(filePath || '');
                const prompt = `SemanticGuard detected a Rule ${ruleId} violation in file '${relativePath}' on line ${line}.\nReason: ${reason}\nSuggested fix: ${text}\n\nPlease apply this fix.`;
                
                vscode.env.clipboard.writeText(prompt);
                vscode.window.showInformationMessage(`📋 Fix prompt for '${relativePath}' copied to clipboard! Paste it to your IDE Agent.`);
            }

            if (message.command === 'run_workspace_audit') {
                console.log('[SEMANTICGUARD WEBVIEW] Executing semanticguard.auditEntireFolder command');
                try {
                    await vscode.commands.executeCommand('semanticguard.auditEntireFolder');
                    console.log('[SEMANTICGUARD WEBVIEW] Workspace audit started successfully');
                } catch (error) {
                    console.error('[SEMANTICGUARD WEBVIEW] Workspace audit failed:', error);
                    vscode.window.showErrorMessage(`Failed to start workspace audit: ${error.message}`);
                }
                return;
            }

            if (message.command === 'toggle_cpu_gpu') {
                console.log('[SEMANTICGUARD WEBVIEW] Executing semanticguard.toggleProcessor command');
                try {
                    await vscode.commands.executeCommand('semanticguard.toggleProcessor');
                    console.log('[SEMANTICGUARD WEBVIEW] CPU/GPU toggle executed successfully');
                } catch (error) {
                    console.error('[SEMANTICGUARD WEBVIEW] CPU/GPU toggle failed:', error);
                    vscode.window.showErrorMessage(`Failed to toggle CPU/GPU: ${error.message}`);
                }
                return;
            }

            if (message.command === 'initialize_project') {
                console.log('[SEMANTICGUARD WEBVIEW] Executing semanticguard.initializeProject command');
                try {
                    await vscode.commands.executeCommand('semanticguard.initializeProject');
                    console.log('[SEMANTICGUARD WEBVIEW] Project initialization started successfully');
                } catch (error) {
                    console.error('[SEMANTICGUARD WEBVIEW] Project initialization failed:', error);
                    vscode.window.showErrorMessage(`Failed to initialize project: ${error.message}`);
                }
                return;
            }

            if (message.command === 'update_model') {
                const { model } = message;
                console.log('[SEMANTICGUARD WEBVIEW] Updating model to:', model);
                const extensionContext = global.semanticguardContext;
                if (!extensionContext) {
                    vscode.window.showErrorMessage('Extension context not available');
                    return;
                }
                const provider = extensionContext.globalState.get('semanticguard.provider') || 'openrouter';
                const modelKey = provider === 'openrouter' ? 'openrouter_model' : 'groq_model';
                await extensionContext.globalState.update(modelKey, model);
                vscode.window.showInformationMessage(`Model updated to: ${model}`);
                this.sendMessage({ type: 'updateModelBadge', modelId: model });
                return;
            }

            if (message.command === 'toggle_mode') {
                console.log('[SEMANTICGUARD WEBVIEW] Executing semanticguard.togglePowerMode command from settings');
                try {
                    await vscode.commands.executeCommand('semanticguard.togglePowerMode');
                    console.log('[SEMANTICGUARD WEBVIEW] Power mode toggled successfully from settings');
                } catch (error) {
                    console.error('[SEMANTICGUARD WEBVIEW] Power mode toggle failed:', error);
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
            vscode.commands.executeCommand("semanticguard.explorer.focus", { preserveFocus: true });
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
        const extensionContext = global.semanticguardContext;
        const mode = extensionContext?.globalState.get('semanticguard.mode') || 'local';
        const provider = extensionContext?.globalState.get('semanticguard.provider') || 'openrouter';
        
        // Get model name
        const modelKey = provider === 'openrouter' ? 'openrouter_model' : 'groq_model';
        const modelId = extensionContext?.globalState.get(modelKey);
        
        // Check if API key exists
        const keyName = provider === 'openrouter' ? 'openrouter_api_key' : 'groq_api_key';
        const apiKey = await extensionContext?.secrets.get(keyName);
        
        // Build model badge HTML (only for Power Mode) - WITHOUT provider prefix
        let modelBadgeHtml = '';
        if (mode === 'cloud') {
            if (apiKey && modelId) {
                // Show only the model ID, no provider prefix
                modelBadgeHtml = '<span id="model-badge" style="font-size: 10px; padding: 2px 6px; border-radius: 4px; background-color: #333; color: #ccc; vertical-align: middle; margin-left: 8px;">' + modelId + '</span>';
            } else if (!apiKey) {
                modelBadgeHtml = '<span id="model-badge" style="font-size: 10px; padding: 2px 6px; border-radius: 4px; color: #ff5555; border: 1px solid #ff5555; vertical-align: middle; margin-left: 8px;">No API Key Detected</span>';
            }
        }
        
        return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline';">
    <title>SemanticGuard Architect</title>
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
        
        /* V2 SECURITY FINDINGS STYLING */
        .finding-card {
            background-color: var(--vscode-editor-inactiveSelectionBackground);
            border-left: 4px solid #f48771;
            border-radius: 6px;
            padding: 16px;
            margin: 12px 0;
            font-size: 0.9em;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .finding-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
            font-weight: bold;
        }
        .severity-badge {
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.8em;
            font-weight: bold;
            color: white;
        }
        .finding-desc {
            margin-top: 6px;
            line-height: 1.5;
            color: var(--vscode-editor-foreground);
        }
        
        /* SAFE STATE STYLING */
        .safe-state {
            background: rgba(78, 201, 176, 0.1);
            border: 2px solid rgba(78, 201, 176, 0.3);
            border-radius: 8px;
            padding: 20px;
            margin: 15px 0;
            text-align: center;
        }
        .safe-checkmark {
            font-size: 2em;
            color: #4ec9b0;
            margin-bottom: 10px;
        }
        
        /* 🛠️ LATENCY INDICATOR STYLING */
        .latency-indicator {
            font-size: 0.8em;
            color: #dcdcaa;
            background: rgba(220, 220, 170, 0.1);
            padding: 2px 6px;
            border-radius: 3px;
            margin-left: 8px;
            font-weight: normal;
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
        <p>The architectural pillars have been modified outside of SemanticGuard's authorization. Please review the rules in your .semanticguard folder.</p>
        <button id="resign-btn" class="btn btn-danger">⚠️ I have reviewed the rules. Re-Sign Vault.</button>
    </div>

    <div id="content">
        <div class="header-container">
            <h2>🏛️ SemanticGuard Vault Access${modelBadgeHtml}</h2>
            <button id="settings-gear" class="settings-gear" title="Open Settings" onclick="window.openSettings()">⚙️</button>
        </div>
        <p>Awaiting architectural changes...</p>
    </div>
    
    <div id="settings-panel" style="display: none; padding: 0; margin-top: 15px;">
        <div style="background: #1e1e1e; border-radius: 6px; overflow: hidden;">
            <div style="padding: 15px; border-bottom: 1px solid #333;">
                <h3 style="margin: 0; color: var(--vscode-editor-foreground);">⚙️ SemanticGuard Settings</h3>
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
                    <button id="initialize-project-btn" onclick="window.initializeProject()" style="width: 100%; padding: 10px; background: #252525; color: white; border: 1px solid #333; border-radius: 4px; cursor: pointer; font-size: 0.9em; font-weight: 500; transition: background 0.2s;" onmouseover="this.style.background='#2d2d2d'" onmouseout="this.style.background='#252525'">Initialize SemanticGuard</button>
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


        function renderFindings(findings, filePath) {
            try {
                if (!findings || !Array.isArray(findings)) return '';
                
                if (findings.length === 0) {
                    // SAFE STATE: Green success UI
                    return '<div style="background: rgba(78, 201, 176, 0.1); border: 2px solid rgba(78, 201, 176, 0.3); border-radius: 8px; padding: 20px; margin: 15px 0; text-align: center;">' +
                           '<div style="font-size: 2em; color: #4ec9b0; margin-bottom: 10px;">✓</div>' +
                           '<div style="font-size: 1.1em; font-weight: bold; color: #4ec9b0; margin-bottom: 8px;">SAFE</div>' +
                           '<div style="color: var(--vscode-editor-foreground); font-size: 0.9em;">No architectural drift or vulnerabilities detected.</div>' +
                           '</div>';
                }
                
                // VULNERABLE STATE: Multi-card layout
                let html = '<div class="findings-container" style="margin: 15px 0;">';
                html += '<h4 style="margin-bottom: 15px; color: var(--vscode-errorForeground);">🚨 Security Vulnerabilities Detected</h4>';
                
                findings.forEach((finding, index) => {
                    if (!finding) return;
                    
                    // Color-code severity
                    let severityColor = '#f48771'; // Default orange
                    let severityBg = 'rgba(244, 135, 113, 0.1)';
                    
                    switch ((finding.severity || '').toUpperCase()) {
                        case 'CRITICAL':
                            severityColor = '#ff4d4d';
                            severityBg = 'rgba(255, 77, 77, 0.1)';
                            break;
                        case 'HIGH':
                            severityColor = '#ff8c42';
                            severityBg = 'rgba(255, 140, 66, 0.1)';
                            break;
                        case 'MEDIUM':
                            severityColor = '#ffd700';
                            severityBg = 'rgba(255, 215, 0, 0.1)';
                            break;
                        case 'LOW':
                            severityColor = '#90ee90';
                            severityBg = 'rgba(144, 238, 144, 0.1)';
                            break;
                    }
                    
                    html += '<div class="finding-card" style="background: ' + severityBg + '; border-left: 4px solid ' + severityColor + '; border-radius: 6px; padding: 16px; margin-bottom: 12px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">';
                    html += '<div class="finding-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">';
                    html += '<div style="display: flex; align-items: center; gap: 8px;">';
                    html += '<span style="background: ' + severityColor + '; color: white; padding: 4px 8px; border-radius: 4px; font-size: 0.8em; font-weight: bold;">' + escapeHtml(finding.severity || 'MEDIUM') + '</span>';
                    html += '<span style="color: var(--vscode-editor-foreground); font-weight: bold;">' + escapeHtml(finding.vulnerability_type || 'Security Issue') + '</span>';
                    html += '</div>';
                    html += '<span style="color: #ce9178; font-family: var(--vscode-editor-font-family); font-size: 0.9em;">Line ' + (finding.line_number || '?') + '</span>';
                    html += '</div>';
                    
                    // 🛠️ RESTORE RULE ID DISPLAY - Show BYOK rule mapping
                    if (finding.rule_id && finding.rule_id !== 'NONE') {
                        html += '<div class="rule-id-display" style="background: rgba(100, 149, 237, 0.1); border: 1px solid rgba(100, 149, 237, 0.3); padding: 6px 10px; border-radius: 4px; margin-bottom: 10px; font-size: 0.85em;">';
                        html += '<span style="color: #6495ed; font-weight: bold;">📋 Rule:</span> ';
                        html += '<span style="color: var(--vscode-editor-foreground);">' + escapeHtml(finding.rule_id) + '</span>';
                        html += '</div>';
                    }
                    
                    html += '<div class="finding-description" style="color: var(--vscode-editor-foreground); line-height: 1.5; margin-bottom: 12px; font-size: 0.95em;">';
                    html += escapeHtml(finding.description || 'Security vulnerability detected.');
                    html += '</div>';
                    html += '<div style="background: rgba(0,0,0,0.2); padding: 8px 12px; border-radius: 4px; font-family: var(--vscode-editor-font-family); font-size: 0.85em; color: #dcdcaa;">';
                    html += '<strong>Vulnerability ID:</strong> SECURITY-' + String(index + 1).padStart(3, '0');
                    html += '</div>';
                    html += '</div>';
                });
                
                html += '</div>';
                return html;
            } catch (err) {
                console.error('[WEBVIEW ERROR] renderFindings failed:', err);
                return '<p style="color: var(--vscode-errorForeground);">⚠️ Error rendering security findings. See developer console.</p>';
            }
        }

        // Legacy violations renderer - DEPRECATED in V2
        // Only kept for backward compatibility, should not be used
        function renderViolations(violations, filePath) {
            // V2 PURGE: Legacy violations are deprecated
            // All security issues should use renderFindings() instead
            return '';
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
                contentDiv.innerHTML = '<div class="header-container"><h2>🏛️ SemanticGuard Vault Access</h2><div style="display: flex; gap: 8px; align-items: center;"><button id="mode-toggle" class="settings-gear" title="Toggle Local/Power Mode" style="font-size: 14px; padding: 4px 8px; color: white; background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.3);" onclick="window.toggleMode()"><span id="mode-text">Local</span></button><button class="settings-gear" title="Configure Power Mode (BYOK)" onclick="window.configureBYOK()">⚙️</button></div></div><p>Awaiting architectural changes...</p>';
                return;
            }
            
            if (message.type === 'resign_success') {
                document.body.classList.remove('compromised');
                compromiseBanner.classList.remove('active');
                contentDiv.innerHTML = '<div class="header-container"><h2>🏛️ SemanticGuard Vault Access</h2><div style="display: flex; gap: 8px; align-items: center;"><button id="mode-toggle" class="settings-gear" title="Toggle Local/Power Mode" style="font-size: 14px; padding: 4px 8px; color: white; background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.3);" onclick="window.toggleMode()"><span id="mode-text">Local</span></button><button class="settings-gear" title="Configure Power Mode (BYOK)" onclick="window.configureBYOK()">⚙️</button></div></div><p style="color: var(--vscode-testing-iconPassed); font-weight: bold;">✅ Successfully Re-Signed Vault!</p>';
                setTimeout(() => {
                    contentDiv.innerHTML = '<div class="header-container"><h2>🏛️ SemanticGuard Vault Access</h2><div style="display: flex; gap: 8px; align-items: center;"><button id="mode-toggle" class="settings-gear" title="Toggle Local/Power Mode" style="font-size: 14px; padding: 4px 8px; color: white; background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.3);" onclick="window.toggleMode()"><span id="mode-text">Local</span></button><button class="settings-gear" title="Configure Power Mode (BYOK)" onclick="window.configureBYOK()">⚙️</button></div></div><p>Awaiting architectural changes...</p>';
                }, 3000);
                return;
            }

            // SCANNING: show loading spinner while AI is thinking
            if (message.type === 'scanning') {
                contentDiv.innerHTML = '<div class="header-container"><h2>🏛️ SemanticGuard Vault Access</h2><div style="display: flex; gap: 8px; align-items: center;"><button id="mode-toggle" class="settings-gear" title="Toggle Local/Power Mode" style="font-size: 14px; padding: 4px 8px; color: white; background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.3);" onclick="window.toggleMode()"><span id="mode-text">Local</span></button><button class="settings-gear" title="Configure Power Mode (BYOK)" onclick="window.configureBYOK()">⚙️</button></div></div><div class="scanning"><div class="spinner"></div><span>🛡️ SemanticGuard is evaluating architectural drift...</span></div>';
                return;
            }

            // ERROR: show server failure while evaluating
            if (message.type === 'error') {
                contentDiv.innerHTML = '<div class="header-container"><h2>🏛️ SemanticGuard Vault Access</h2><div style="display: flex; gap: 8px; align-items: center;"><button id="mode-toggle" class="settings-gear" title="Toggle Local/Power Mode" style="font-size: 14px; padding: 4px 8px; color: white; background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.3);" onclick="window.toggleMode()"><span id="mode-text">Local</span></button><button class="settings-gear" title="Configure Power Mode (BYOK)" onclick="window.configureBYOK()">⚙️</button></div></div><div class="action-card" style="border-left: 4px solid var(--vscode-errorForeground);"><p class="action-error">⚠️ SemanticGuard Error</p><p style="color: var(--vscode-editor-foreground); font-size: 0.9em;">' + message.message + '</p><p style="color: var(--vscode-terminal-ansiYellow); font-style: italic; font-size: 0.85em; margin-top: 8px;">Audit failed — check server logs for details.</p></div>';
                return;
            }
            
            if (message.type === 'log') {
                if (message.action === 'VAULT_COMPROMISED') {
                    document.body.classList.add('compromised');
                    compromiseBanner.classList.add('active');
                }

                const entry = document.createElement('div');
                entry.className = 'log-entry';
                let html = '<h3>' + message.title;
                
                // 🛠️ RESTORE LATENCY INDICATOR - Clean, modern style
                if (message.cloud_latency) {
                    html += ' <span class="latency-indicator">⚡ ' + message.cloud_latency + 's</span>';
                } else if (message.local_latency) {
                    html += ' <span class="latency-indicator">⚡ ' + message.local_latency + 's</span>';
                }
                
                html += '</h3>';
                
                // FIX 2: DRIFT METER WITH COLOR CODING (Distance-Based)
                // 0.0 = Perfect (Green), 0.3-0.6 = Warning (Yellow), 0.6+ = Critical (Red)
                // ONLY show risk score if there are findings (vulnerabilities detected)
                const findings = message.findings || [];
                if (message.score && findings.length > 0) {
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
                    html += '<span class="drift-label">Risk Score:</span> ';
                    html += '<span class="drift-score ' + scoreClass + '">' + message.score + '</span> ';
                    html += '<div style="margin-top: 5px; font-size: 0.85em; opacity: 0.8;">';
                    html += 'V2 Taint Analysis with Risk Surface Detection';
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

                // V2: Pure findings-based UI - no legacy performance tracking

                if (message.action === 'ACCEPT') {
                    html += '<p class="action-accept">✅ Verdict: ACCEPT</p>';
                    
                    // V2: Use findings array if available, fallback to violations
                    const findings = message.findings || [];
                    const violations = message.violations || [];
                    
                    if (findings.length > 0) {
                        html += renderFindings(findings, message.fullPath);
                    }

                } else if (message.action === 'REJECT') {
                    html += '<p class="action-reject">🛑 Verdict: REJECT</p>';
                    
                    // V2: Use findings array if available, fallback to violations
                    const findings = message.findings || [];
                    const violations = message.violations || [];
                    
                    if (findings.length > 0) {
                        html += renderFindings(findings, message.fullPath);
                    } else {
                        html += '<p style="color: var(--vscode-terminal-ansiYellow); font-style: italic; margin-top: 8px;">⚠️ Violation data missing (Check server logs)</p>';
                    }
                    
                    html += '<div style="margin-top:10px;">';
                    html += '<button class="btn btn-revert" id="revertBtn">↩️ Revert Save</button>';
                    html += '<button class="btn btn-warn" id="overrideBtn">⚠️ Force Override</button>';
                    html += '</div>';

                } else if (message.action === 'ERROR') {
                    html += '<p class="action-error">⚠️ Verdict: ERROR (AI hallucinated — no valid output)</p>';
                    
                    // V2: Use findings array if available, fallback to violations
                    const findings = message.findings || [];
                    const violations = message.violations || [];
                    
                    if (findings.length > 0) {
                        html += renderFindings(findings, message.fullPath);
                    } else {
                        html += '<p style="color: var(--vscode-terminal-ansiYellow); font-style: italic; margin-top: 8px;">⚠️ Evaluation failed (AI output malformed)</p>';
                    }

                } else if (message.action === 'VAULT_COMPROMISED') {
                    html += '<p class="action-compromised">🚨 VAULT COMPROMISED</p>';

                } else if (message.action === 'WARN') {
                    // FIX 4: Handle partial audits (missing [ACTION] tag)
                    html += '<p class="action-warn">⚠️ Verdict: INCOMPLETE AUDIT</p>';
                    html += '<p style="color: var(--vscode-terminal-ansiYellow); font-size: 0.9em; margin-top: 4px;">Parser detected truncated output - [ACTION] tag missing</p>';
                    
                    // V2: Use findings array if available, fallback to violations
                    const findings = message.findings || [];
                    const violations = message.violations || [];
                    
                    if (findings.length > 0) {
                        html += renderFindings(findings, message.fullPath);
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
                    
                    // V2: Use findings array if available, fallback to violations
                    const findings = message.findings || [];
                    const violations = message.violations || [];
                    
                    if (findings.length > 0) {
                        html += renderFindings(findings, message.fullPath);
                    }
                }

                entry.innerHTML = html;
                contentDiv.innerHTML = '<div class="header-container"><h2>🏛️ SemanticGuard Vault Access</h2><div style="display: flex; gap: 8px; align-items: center;"><button id="mode-toggle" class="settings-gear" title="Toggle Local/Power Mode" style="font-size: 14px; padding: 4px 8px; color: white; background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.3);" onclick="window.toggleMode()"><span id="mode-text">Local</span></button><button class="settings-gear" title="Configure Power Mode (BYOK)" onclick="window.configureBYOK()">⚙️</button></div></div>';
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
const semanticguardSidebarProvider = new SemanticGuardSidebarProvider();

/**
 * Hands off an AI-suggested fix to the Antigravity IDE Agent.
 * @param {number} line - The 1-indexed line number
 * @param {string} text - The replacement text (or whole code)
 */
// application logic end

// ─── Exports ─────────────────────────────────────────────────────────────────

function deactivate() { }

module.exports = { activate, deactivate };


