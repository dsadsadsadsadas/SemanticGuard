#!/usr/bin/env python3
"""
🛡️ TREPAN 4.0 (Enterprise Edition)
A DevSecOps Context Enforcer with TRANSPARENT user consent:

PATH A: Paste with Policy (Shows diff, asks consent - NO silent modification)
PATH B: Red Team Trigger (Only on Trouble Keywords)

Key Principle: VISIBLE TRUST over invisible tricks

Author: Project TREPAN
"""

# =============================================================================
# CRITICAL: FIX #2 - Windows Encoding (MUST BE FIRST)
# =============================================================================
import sys
import io

# Fix Windows console encoding for Unicode/emoji output
if sys.platform == 'win32':
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass  # Ignore if already wrapped

# =============================================================================
# CRITICAL: FIX #1 - Logger MUST be initialized BEFORE any other imports
# =============================================================================
import logging

logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("TREPAN")

# =============================================================================
# CRITICAL: FIX #3 - Global constants MUST be defined at top level
# =============================================================================
CONTEXT_FILE = "GEMINI.md"  # The Architect's instruction file
MAX_CLIPBOARD_HISTORY = 5
SAFE_EXTENSIONS = {'.py', '.js', '.ts', '.jsx', '.tsx', '.mjs', '.html', '.css', '.java', '.cpp'}
SCANNABLE_EXTENSIONS = {'.py', '.js', '.ts', '.jsx', '.tsx', '.mjs'}  # Files we can taint-analyze

# =============================================================================
# STANDARD IMPORTS (After logger and constants are ready)
# =============================================================================
import time
import os
import threading
import ast
import json
from datetime import datetime
from dotenv import load_dotenv
import pyperclip
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Load environment variables
load_dotenv()

# =============================================================================
# CODE DETECTION HEURISTIC (The Brain)
# =============================================================================
import re

def is_code_heuristic(text):
    """
    Checks if text looks like code using Regex patterns.
    Used to trigger Audit even without explicit 'BUG' keywords.
    """
    if not text or len(text) < 10:
        return False
    
    # Patterns that identify code (Python/JS/General)
    code_patterns = [
        r"^import\s+\w+",          # Imports
        r"def\s+\w+\(.*\):",       # Functions
        r"class\s+\w+:",           # Classes
        r"[{};=]{2,}",             # Syntax symbols
        r"^\s+return\s+",          # Return statements
        r"var\s+|const\s+|let\s+", # JS/TS
        r"print\(|console\.log\("  # Prints
    ]
    
    for pattern in code_patterns:
        if re.search(pattern, text, re.MULTILINE):
            return True
            
    return False

# =============================================================================
# OPTIONAL IMPORTS (With graceful fallback - logger is now available)
# =============================================================================

# --- TREPAN 4.0: Policy UI (Diff View) ---
try:
    from policy_ui import show_policy_dialog, PolicyDecision
    POLICY_UI_AVAILABLE = True
    logger.info("✅ Policy UI loaded")
except ImportError:
    POLICY_UI_AVAILABLE = False
    logger.warning("⚠️ policy_ui.py not found - falling back to console mode")

# --- TREPAN 4.0: System Tray (FIX #4 - Graceful handling) ---
try:
    from system_tray import create_tray, TrepanStatus
    TRAY_AVAILABLE = True
    logger.info("✅ System tray module loaded")
except ImportError as e:
    TRAY_AVAILABLE = False
    logger.warning(f"⚠️ System tray unavailable: {e}")
except Exception as e:
    TRAY_AVAILABLE = False
    logger.warning(f"⚠️ System tray failed to load: {e}")

# --- PHASE 5: Polyglot Taint Engine ---
try:
    from taint_engine import PolyglotTaintEngine, Language
    POLYGLOT_AVAILABLE = True
    _taint_engine = PolyglotTaintEngine()
    logger.info("✅ Polyglot Taint Engine loaded")
except ImportError:
    POLYGLOT_AVAILABLE = False
    _taint_engine = None
    logger.warning("⚠️ taint_engine.py not found - JavaScript/TypeScript scanning disabled")
except Exception as e:
    POLYGLOT_AVAILABLE = False
    _taint_engine = None
    logger.warning(f"⚠️ Taint Engine failed: {e}")

# --- PHASE 7: LLM Gateway (Model-Agnostic AI) ---
try:
    from llm_gateway import LLMGateway
    _llm_gateway = LLMGateway()  # Auto-loads from llm_config.yaml
    LLM_AVAILABLE = _llm_gateway.is_available()
    if LLM_AVAILABLE:
        info = _llm_gateway.get_provider_info()
        logger.info(f"🔌 LLM Gateway: {info['provider']} ({info['model']})")
    else:
        logger.warning("⚠️ LLM Gateway loaded but provider not available")
except ImportError:
    LLM_AVAILABLE = False
    _llm_gateway = None
    logger.warning("⚠️ llm_gateway.py not found - Red Team disabled")
except Exception as e:
    LLM_AVAILABLE = False
    _llm_gateway = None
    logger.warning(f"⚠️ LLM Gateway initialization failed: {e}")


# --- PHASE 9: PACKAGE SENTINEL & AUDIT ---
try:
    from trepan_audit import audit_log
    AUDIT_AVAILABLE = True
except ImportError:
    AUDIT_AVAILABLE = False
    audit_log = None
    print("⚠️ trepan_audit.py not found - Security logging disabled (Law #3 violation)")

try:
    from package_sentinel import check_package_security
    SENTINEL_AVAILABLE = True
except ImportError:
    SENTINEL_AVAILABLE = False
    print("⚠️ package_sentinel.py not found - Supply chain checking disabled")

# --- TR-01: Hardware Sentinel (Compute Router) ---
try:
    from hardware_sentinel import sentinel as hardware
    HARDWARE_AVAILABLE = True
    logger.info(f"🖥️ Hardware Sentinel: {hardware.config.device.upper()} mode")
except ImportError:
    HARDWARE_AVAILABLE = False
    hardware = None
    logger.warning("⚠️ hardware_sentinel.py not found - Compute routing disabled")
except Exception as e:
    HARDWARE_AVAILABLE = False
    hardware = None
    logger.warning(f"⚠️ Hardware Sentinel failed: {e}")

# --- TR-02: Drift Engine (Semantic Analysis) ---
try:
    from drift_engine import drift_monitor
    DRIFT_AVAILABLE = drift_monitor.is_ready
    if DRIFT_AVAILABLE:
        logger.info(f"🧠 Drift Engine: ONLINE (device={drift_monitor.device})")
    else:
        logger.warning("⚠️ Drift Engine loaded but model not ready")
except ImportError:
    DRIFT_AVAILABLE = False
    drift_monitor = None
    logger.warning("⚠️ drift_engine.py not found - Semantic drift detection disabled")
except Exception as e:
    DRIFT_AVAILABLE = False
    drift_monitor = None
    logger.warning(f"⚠️ Drift Engine failed: {e}")

# --- TR-03: Clipboard Sentinel (Semantic Firewall) ---
try:
    from clipboard_sentinel import sentinel as clipboard_guard
    CLIPBOARD_SENTINEL_AVAILABLE = True
    logger.info("🛡️ Clipboard Sentinel: READY")
except ImportError:
    CLIPBOARD_SENTINEL_AVAILABLE = False
    clipboard_guard = None
    logger.warning("⚠️ clipboard_sentinel.py not found - Semantic firewall disabled")
except Exception as e:
    CLIPBOARD_SENTINEL_AVAILABLE = False
    clipboard_guard = None
    logger.warning(f"⚠️ Clipboard Sentinel failed: {e}")


# =============================================================================
# 1. PROJECT CACHE (The Memory)
# =============================================================================

class ProjectCache:
    def __init__(self):
        self.files = []
        self.scan_project()

    def scan_project(self):
        """Maps all relevant files in the directory."""
        self.files = []
        for root, _, filenames in os.walk("."):
            if "node_modules" in root or ".git" in root or "__pycache__" in root or "venv" in root:
                continue
            for f in filenames:
                if any(f.endswith(ext) for ext in SAFE_EXTENSIONS):
                    self.files.append(os.path.join(root, f))
        logger.info(f"📚 Cached {len(self.files)} project files")
    
    def find_relevant_file(self, query):
        """Heuristic to find a file based on content or filename matching."""
        query_lower = query.lower()
        
        # 1. CONTENT MATCH: Check if the query IS the content of a file
        for f in self.files:
            try:
                with open(f, 'r', encoding='utf-8', errors='ignore') as file:
                    content = file.read()
                    # If the query is a substantial portion of the file content
                    if len(query) > 50 and query.strip() in content:
                        return f
                    # Or if the first 100 chars match
                    if content[:100].strip() == query[:100].strip():
                        return f
            except Exception:
                continue
        
        # 2. Exact filename match (e.g. "login.py")
        for f in self.files:
            if os.path.basename(f).lower() == query_lower:
                return f
        
        # 3. Fuzzy filename match with STRICT threshold (0.6)
        import difflib
        best_match = None
        best_ratio = 0.0
        
        for f in self.files:
            fname = os.path.basename(f).lower()
            ratio = difflib.SequenceMatcher(None, query_lower, fname).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = f
        
        if best_ratio >= 0.6:
            return best_match
            
        return None


# =============================================================================
# 2. AST ENGINE (Passive Defense - Local Security Scanning)
# =============================================================================

class SecurityVisitor(ast.NodeVisitor):
    def __init__(self):
        self.issues = []

    def visit_Assign(self, node):
        """Detects hardcoded secrets in variables."""
        for target in node.targets:
            if isinstance(target, ast.Name):
                var_name = target.id.lower()
                if any(s in var_name for s in ['password', 'secret', 'key', 'token', 'auth', 'credential']):
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                        if len(node.value.value.strip()) > 0:
                            self.issues.append(f"Hardcoded Secret in '{target.id}' (line {node.lineno})")
        self.generic_visit(node)

    def visit_Call(self, node):
        """Detects unsafe logging of sensitive variables."""
        func_name = ""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr
        
        unsafe_funcs = {'print', 'info', 'debug', 'warning', 'error', 'log'}
        if func_name in unsafe_funcs:
            for arg in node.args:
                if isinstance(arg, ast.Name):
                    if any(s in arg.id.lower() for s in ['password', 'secret', 'key', 'token']):
                        self.issues.append(f"Unsafe logging of '{arg.id}' in {func_name}() (line {node.lineno})")
        self.generic_visit(node)


def scan_file_security(filepath):
    """Runs AST analysis on a file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        tree = ast.parse(content)
        visitor = SecurityVisitor()
        visitor.visit(tree)
        return visitor.issues
    except Exception:
        return []  # Ignore parse errors


# =============================================================================
# 3. RED TEAM MODULE (Active Attack - On Demand Only)
# =============================================================================

def execute_red_team_attack(target_content, filename):
    """Sends code to LLM Gateway for a hostile audit (model-agnostic)."""
    if not LLM_AVAILABLE or not _llm_gateway:
        logger.error("Red Team unavailable - LLM Gateway not initialized")
        return {"status": "ERROR", "issue": "LLM Gateway not available"}
    
    print(f"\n🚀 Launching Red Team attack on {filename}...")
    info = _llm_gateway.get_provider_info()
    print(f"   Provider: {info['provider']}")
    print(f"   Model: {info['model']}")
    
    try:
        result = _llm_gateway.audit_code(target_content, filename)
        if isinstance(result, list):
            return result[0] if result else {"status": "SAFE", "issue": "No issues found"}
        return result
    except KeyboardInterrupt:
        print("\n⚠️ SCAN ABORTED BY USER")
        return {"status": "ERROR", "issue": "Scan aborted by user"}
    except Exception as e:
        logger.error(f"Red Team Error: {e}")
        return {"status": "ERROR", "issue": str(e)}


def update_gemini_rules(audit_result, filename):
    """Writes the security constraint to GEMINI.md."""
    if audit_result.get("status") == "DANGER":
        rule = f"""
# 🛑 SECURITY INTERVENTION ({datetime.now().strftime('%H:%M:%S')})
# The Red Team detected a vulnerability in '{filename}': {audit_result['issue']}
# CONSTRAINT: You MUST implement the following fix: {audit_result.get('fix_instruction', 'Review and fix')}
"""
        try:
            with open(CONTEXT_FILE, "a", encoding="utf-8") as f:
                f.write(rule)
            print(f"✅ GEMINI.md updated with security constraint for {filename}.")
        except Exception as e:
            logger.error(f"Failed to update rules: {e}")


# =============================================================================
# 4. CLIPBOARD MONITOR (The Brain - TRANSPARENT CONSENT)
# =============================================================================

# Global reference for system tray integration
_tray = None

def build_context_proposal(text: str, project_cache) -> str:
    """
    Build the proposed context injection content.
    Returns the proposed text that would be written to GEMINI.md.
    """
    timestamp = datetime.now().strftime('%H:%M:%S')
    snippet = text[:300].replace('\n', ' ').strip()
    if len(text) > 300:
        snippet += "..."
    
    # Find relevant file if possible
    relevant_file = project_cache.find_relevant_file(text)
    file_context = ""
    if relevant_file:
        file_context = f"\n# Related file: {relevant_file}"
    
    proposal = f"""
# 🧠 USER CONTEXT ({timestamp}){file_context}
# User copied: {snippet}
"""
    return proposal


# [TR-05: LEGACY MONITOR DISABLED TO PREVENT RACE CONDITION]
def monitor_clipboard(project_cache):
    """
    🛡️ TREPAN 4.0 - Transparent Consent Clipboard Monitor
    DISABLED in favor of TR-03/05 Clipboard Sentinel (Smart Semantic Firewall)
    """
    return # Legacy loop disabled by TR-05 patch
    # Original code commented out below:
    # global _tray
    # last_text = pyperclip.paste()
    # while True:
    #     try:
    #         text = pyperclip.paste()
    #         if text != last_text and text.strip():
    #             last_text = text
    '''
    # --- PRIORITY CHECK: RED TEAM TRIGGER (Path B) ---
                # Keywords that imply a BUG or a SECURITY CONCERN
                trouble_keywords = [
                    "why is", "not working", "error", "exception", "failed", 
                    "vulnerability", "exploit", "hack", "secure?", "safe?", 
                    "broken", "crash", "bug", "issue",
                    "!audit", "!attack"  # Explicit commands
                ]
                
                is_trouble = any(k in text.lower() for k in trouble_keywords)
                is_code = is_code_heuristic(text)
                
                if is_trouble or is_code:
                    trigger_reason = "Code Pattern Detected" if is_code and not is_trouble else "Trouble Keywords"
                    print(f"\n🚨 Trigger: {trigger_reason} | Size: {len(text)} chars")
                    # Update tray status to alert
                    if _tray and TRAY_AVAILABLE:
                        _tray.set_status(TrepanStatus.ALERT)
                    
                    # Identify Target File from Cache
                    target_file = "CLIPBOARD_SNIPPET"
                    found = project_cache.find_relevant_file(text)
                    if found:
                        target_file = found
                        # Quick local scan first
                        issues = scan_file_security(target_file)
                        if issues:
                            print(f"\n🔍 Pre-scan found {len(issues)} issue(s) in {target_file}")

                    # --- THE INTERRUPTION (Only when truly needed) ---
                    print("\n" + "=" * 60)
                    print(f"🕵️  INTERCEPTED: Troubleshooting/Security Context detected.")
                    print(f"🎯 Target: {target_file}")
                    print(f"❓ Trigger: '{text[:50]}...'")
                    
                    user_input = input(">>> 🧨 Launch Red Team Audit? [y/N]: ").strip().lower()
                    
                    if user_input == 'y':
                        if _tray and TRAY_AVAILABLE:
                            _tray.set_status(TrepanStatus.PROCESSING)
                        
                        content_to_audit = text
                        if target_file != "CLIPBOARD_SNIPPET":
                            try:
                                with open(target_file, 'r', encoding='utf-8') as f:
                                    content_to_audit = f.read()
                            except Exception as e:
                                print(f"⚠️ Could not read file: {e}")
                        
                        result = execute_red_team_attack(content_to_audit, target_file)
                        
                        # LOG THE ATTACK
                        if AUDIT_AVAILABLE:
                            audit_log.log_event("RED_TEAM_ATTACK", target_file, result)

                        if result.get('status') == 'DANGER':
                            print(f"\n🔴 DANGER DETECTED: {result['issue']}")
                            
                            # TRANSPARENT: Ask before updating GEMINI.md with security rule
                            if POLICY_UI_AVAILABLE:
                                # Read ACTUAL current GEMINI.md content
                                current_gemini = ""
                                try:
                                    if os.path.exists(CONTEXT_FILE):
                                        with open(CONTEXT_FILE, "r", encoding="utf-8") as f:
                                            current_gemini = f.read()
                                except Exception:
                                    pass
                                
                                security_proposal = f"""
# 🛑 SECURITY INTERVENTION ({datetime.now().strftime('%H:%M:%S')})
# Red Team detected vulnerability in '{target_file}': {result['issue']}
# CONSTRAINT: {result.get('fix_instruction', 'Review and fix this issue')}
"""
                                decision = show_policy_dialog(
                                    original=f"[Current {CONTEXT_FILE}]\n\n{current_gemini[-500:] if len(current_gemini) > 500 else current_gemini}",
                                    proposed=f"[Proposed Security Rule]\n{security_proposal}",
                                    context_type="Security Constraint",
                                    source="Red Team Audit",
                                    auto_timeout=None
                                )
                                
                                if decision == PolicyDecision.ACCEPT:
                                    update_gemini_rules(result, target_file)
                                    
                                    # Copy FIXED CODE to clipboard for easy application
                                    fixed_code = result.get('fixed_code', '')
                                    if fixed_code:
                                        pyperclip.copy(fixed_code)
                                        last_text = fixed_code  # PREVENT LOOP: Update last_text
                                        print("📋 FIXED CODE copied to clipboard!")
                                    else:
                                        # Fallback to fix instruction if no code provided
                                        fix_text = result.get('fix_instruction', '')
                                        if fix_text:
                                            pyperclip.copy(fix_text)
                                            last_text = fix_text  # PREVENT LOOP
                                            print("📋 Fix instruction copied to clipboard")
                                    
                                    if _tray and TRAY_AVAILABLE:
                                        _tray.show_notification(
                                            "Security Constraint Added",
                                            f"Rule added for {target_file}"
                                        )
                                else:
                                    print("⏸ Security rule injection rejected")
                            else:
                                update_gemini_rules(result, target_file)
                        else:
                            print(f"\n🟢 Status: SAFE. No logical flaws detected.")
                        
                        if _tray and TRAY_AVAILABLE:
                            _tray.set_status(TrepanStatus.ACTIVE)
                    else:
                        print(">>> Continuing monitoring.")
                        if _tray and TRAY_AVAILABLE:
                            _tray.set_status(TrepanStatus.ACTIVE)
                    print("=" * 60 + "\n")

                else:
                    # --- PATH A: PASTE WITH POLICY (TRANSPARENT) ---
                    # Only execute if NOT a security trigger
                    
                    # Determine if this looks like user-generated content worth tracking
                    # Skip very short content, pure code blocks, and AI responses
                    is_worth_tracking = (
                        len(text) > 20 and 
                        len(text) < 5000 and
                        not text.strip().startswith("```") and
                        not any(marker in text.lower()[:100] for marker in 
                                ["here's", "here is", "i'll", "i will", "let me", "certainly"])
                    )
                    
                    if is_worth_tracking:
                        proposal = build_context_proposal(text, project_cache)
                        
                        # Read current context file content
                        current_context = ""
                        try:
                            if os.path.exists(CONTEXT_FILE):
                                with open(CONTEXT_FILE, "r", encoding="utf-8") as f:
                                    current_context = f.read()
                        except Exception:
                            pass
                        
                        proposed_context = current_context + proposal
                        
                        # TRANSPARENT: Show user what we want to inject
                        if POLICY_UI_AVAILABLE:
                            # GUI mode - show diff dialog
                            decision = show_policy_dialog(
                                original=f"[Current {CONTEXT_FILE}]\n\n{current_context[-500:] if len(current_context) > 500 else current_context}",
                                proposed=f"[Proposed Addition]\n{proposal}",
                                context_type="Clipboard Context Update",
                                source="Clipboard Monitor",
                                auto_timeout=None  # No auto-accept - full user control
                            )
                            
                            if decision == PolicyDecision.ACCEPT:
                                try:
                                    with open(CONTEXT_FILE, "a", encoding="utf-8") as f:
                                        f.write(proposal)
                                    logger.info(f"✅ Context updated with user consent")
                                    if _tray and TRAY_AVAILABLE:
                                        _tray.set_status(TrepanStatus.ACTIVE)
                                except Exception as e:
                                    logger.error(f"Failed to write context: {e}")
                            else:
                                logger.info(f"⏸ Context injection rejected by user")
                        else:
                            # Console fallback mode
                            print("\n" + "─" * 50)
                            print("📋 CONTEXT UPDATE PROPOSAL:")
                            print(proposal[:200])
                            user_input = input(">>> Accept context update? [y/N]: ").strip().lower()
                            if user_input == 'y':
                                with open(CONTEXT_FILE, "a", encoding="utf-8") as f:
                                    f.write(proposal)
                                print("✅ Context updated")
                            else:
                                print("⏸ Skipped")
                            print("─" * 50 + "\n")
                        
            time.sleep(1)
        except Exception as e:
            logger.error(f"Clipboard Error: {e}")
            time.sleep(1)
    '''


# =============================================================================
# 5. FILE WATCHER (The Observer - Polyglot Taint Analysis)
# =============================================================================

class TREPANEventHandler(FileSystemEventHandler):
    """Watches files and runs security analysis on modifications."""
    
    def on_modified(self, event):
        if event.is_directory:
            return
        
        # Skip internal files
        skip_patterns = ["trepan.py", "__pycache__", "node_modules", ".git", "venv"]
        if any(pattern in event.src_path for pattern in skip_patterns):
            return
        
        # Get file extension
        filename = os.path.basename(event.src_path)
        _, ext = os.path.splitext(event.src_path)
        
        # Skip non-scannable files (unless they are package manifests)
        is_package_manifest = filename in ['requirements.txt', 'package.json']
        if ext not in SCANNABLE_EXTENSIONS and not is_package_manifest:
            return
        
        # AUDIT LOGGING (Law #3)
        if AUDIT_AVAILABLE:
            audit_log.log_event("FILE_MODIFIED", event.src_path, {"action": "scan_started"})
        
        all_issues = []

        # --- PACKAGE SENTINEL: Supply Chain Security ---
        if is_package_manifest and SENTINEL_AVAILABLE:
            sentinel_issues = check_package_security(event.src_path)
            all_issues.extend(sentinel_issues)

        # --- PYTHON FILES: Use legacy AST + new taint engine ---
        if ext == '.py':
            # Legacy AST scan (hardcoded secrets, unsafe logging)
            ast_issues = scan_file_security(event.src_path)
            for issue in ast_issues:
                all_issues.append({"type": "AST", "severity": "high", "message": issue})
            
            # New: Polyglot engine Python scan (if available)
            if POLYGLOT_AVAILABLE and _taint_engine:
                try:
                    result = _taint_engine.scan_file(event.src_path)
                    for vuln in result.vulnerabilities:
                        all_issues.append(vuln)
                except Exception:
                    pass  # Silently continue if taint scan fails
        
        # --- JAVASCRIPT/TYPESCRIPT FILES: Use Polyglot Taint Engine ---
        elif ext in {'.js', '.ts', '.jsx', '.tsx', '.mjs'}:
            if POLYGLOT_AVAILABLE and _taint_engine:
                try:
                    result = _taint_engine.scan_file(event.src_path)
                    
                    # Convert taint results to issues
                    for sink in result.sinks:
                        # Report sinks as potential vulnerabilities
                        all_issues.append({
                            "type": sink.get("type", "SINK"),
                            "severity": sink.get("severity", "medium"),
                            "message": f"{sink.get('name', 'Unknown')} at line {sink.get('line', '?')}",
                            "line": sink.get("line")
                        })
                except Exception as e:
                    logger.debug(f"Taint scan error: {e}")
        
        # --- REPORT ISSUES ---
        if all_issues:
            print("\n" + "!" * 60)
            print(f"🔴 SECURITY ALERT in {filename}:")
            for issue in all_issues:
                severity = issue.get('severity', 'medium').upper()
                issue_type = issue.get('type', 'UNKNOWN')
                message = issue.get('message', str(issue))
                emoji = {'CRITICAL': '🔴', 'HIGH': '🟠', 'MEDIUM': '🟡', 'LOW': '🟢'}.get(severity, '⚪')
                print(f"   {emoji} [{issue_type}] {message}")
            print("!" * 60 + "\n")


# =============================================================================
# SELF-DIAGNOSTIC (Immunization Against Feature Drift)
# =============================================================================

def self_diagnostic():
    """Checks if Trepan functions have been stripped by AI refactoring."""
    print("\n🔍 SYSTEM HEALTH CHECK:")
    critical_modules = [
        ("Policy UI (Diff View)", POLICY_UI_AVAILABLE),
        ("Polyglot Engine (JS/Py)", POLYGLOT_AVAILABLE),
        ("LLM Gateway (The Brain)", LLM_AVAILABLE),
        ("System Tray (Background)", TRAY_AVAILABLE),
        ("Audit Logger (Law #3)", AUDIT_AVAILABLE),
        ("Package Sentinel (Supply Chain)", SENTINEL_AVAILABLE),
        ("Hardware Sentinel (Compute Router)", HARDWARE_AVAILABLE),
        ("Drift Engine (Semantic Analysis)", DRIFT_AVAILABLE)
    ]
    
    # Show compute router status
    if HARDWARE_AVAILABLE and hardware:
        print(f"\n🖥️ COMPUTE ROUTER:")
        print(f"   - Device: {hardware.config.device.upper()}")
        print(f"   - Vector Ops: {hardware.route_task('VECTOR_SEARCH').upper()}")
        print(f"   - AST Ops: {hardware.route_task('AST_PARSING').upper()}")
        if hardware.config.vram_mb > 0:
            print(f"   - VRAM: {hardware.config.vram_mb:.0f}MB")
    
    # Show drift engine status
    if DRIFT_AVAILABLE and drift_monitor:
        # Quick self-test
        test_drift = drift_monitor.calculate_drift_score(
            "print('hello world')",
            "import os; os.system('rm -rf /')"
        )
        print(f"\n🧠 DRIFT ENGINE:")
        print(f"   - Model: all-MiniLM-L6-v2")
        print(f"   - Device: {drift_monitor.device.upper()}")
        print(f"   - Self-Test Sensitivity: {test_drift:.4f}")
    
    health = 100
    for name, is_online in critical_modules:
        status = "✅ ONLINE" if is_online else "❌ OFFLINE (Feature Missing)"
        print(f"   - {name}: {status}")
        if not is_online:
            health -= 15 # Adjusted penalty
    
    if health < 100:
        print(f"\n⚠️  WARNING: Trepan is operating at {health}% capacity.")
        print("    If features are missing unexpectedly, CHECK TREPAN_CONSTITUTION.md.")
    else:
        print("\n✅ SYSTEM INTEGRITY: 100% (All Enterprise Features Active)")
    print("=" * 60 + "\n")


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def main():
    global _tray
    
    # Run self-diagnostic first
    self_diagnostic()
    
    # Initialize GEMINI.md if it doesn't exist
    if not os.path.exists(CONTEXT_FILE):
        with open(CONTEXT_FILE, "w", encoding="utf-8") as f:
            f.write(f"# 🛡️ TREPAN Context File\n# Initialized: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        print(f"📝 Created {CONTEXT_FILE}")
    
    # Initialize Project Cache
    cache = ProjectCache()
    
    # Initialize System Tray (if available) - FIX #4: Graceful handling
    if TRAY_AVAILABLE:
        try:
            def on_quit():
                print("\n\n🛑 TREPAN stopped via system tray. Goodbye!")
                os._exit(0)
            
            def on_secure_paste():
                # Trigger manual secure paste flow
                text = pyperclip.paste()
                if text.strip():
                    proposal = build_context_proposal(text, cache)
                    if POLICY_UI_AVAILABLE:
                        decision = show_policy_dialog(
                            original=text[:500],
                            proposed=f"{text[:500]}\n\n--- Trepan Context ---\n{proposal}",
                            context_type="Manual Secure Paste",
                            source="Hotkey Trigger"
                        )
                        if decision == PolicyDecision.ACCEPT:
                            with open(CONTEXT_FILE, "a", encoding="utf-8") as f:
                                f.write(proposal)
                            logger.info("✅ Secure paste completed")
            
            _tray = create_tray(
                on_secure_paste=on_secure_paste,
                on_quit=on_quit
            )
            if _tray:
                print("🔔 System tray initialized")
        except Exception as e:
            logger.warning(f"⚠️ System tray initialization failed: {e}")
            _tray = None
    
    # Start Clipboard Monitor Thread (Legacy)
    clipboard_thread = threading.Thread(target=monitor_clipboard, args=(cache,), daemon=True)
    clipboard_thread.start()
    
    # Start Clipboard Sentinel (TR-03 Semantic Firewall)
    if CLIPBOARD_SENTINEL_AVAILABLE and clipboard_guard:
        print("[*] Starting Clipboard Sentinel (Semantic Firewall)...")
        sentinel_thread = threading.Thread(target=clipboard_guard.scan_loop, daemon=True)
        sentinel_thread.start()
    
    # Start File Watcher
    observer = Observer()
    event_handler = TREPANEventHandler()
    observer.schedule(event_handler, path=".", recursive=True)
    observer.start()
    
    print("""
╔═══════════════════════════════════════════════════════════════════╗
║  🛡️ TREPAN 4.0 (Enterprise Edition)                               ║
║  TRANSPARENT Context Enforcement + AST Defense + Red Team         ║
╚═══════════════════════════════════════════════════════════════════╝
    """)
    print(f"👁️  Watching: {os.getcwd()}")
    print(f"📝 Context File: {CONTEXT_FILE}")
    print(f"📚 Cached Files: {len(cache.files)}")
    print("─" * 68)
    print("🔐 PATH A: PASTE WITH POLICY - Shows diff, asks consent")
    print("🧨 PATH B: Red Team Audit on trouble keywords")
    if LLM_AVAILABLE:
        info = _llm_gateway.get_provider_info()
        print(f"🔌 LLM: {info['provider']} ({info['model']})")
    else:
        print("⚠️ LLM: Not available (Red Team disabled)")
    if TRAY_AVAILABLE and _tray:
        print("🔔 System Tray: Active (right-click for options)")
    print("─" * 68)
    # Prepare Queue for UI Requests (TR-05)
    import queue
    ui_request_queue = queue.Queue()
    
    # Link Queue to Sentinel
    if CLIPBOARD_SENTINEL_AVAILABLE and clipboard_guard:
        clipboard_guard.set_queue(ui_request_queue)
        print("[*] Linked UI Queue to Clipboard Sentinel")

    print("[*] Trepan Main Loop Active (Waiting for Signals...)")
    print("Press Ctrl+C to stop...\n")
    
    try:
        # TR-05: Main Thread Loop (Polls the queue)
        while True:
            try:
                # Check if Sentinel requested a UI Popup
                request = ui_request_queue.get(timeout=0.1)
                
                if request['type'] == 'SHOW_UI':
                    # RUN UI ON MAIN THREAD
                    from policy_gatekeeper import launch_gatekeeper
                    from context_manager import context_db
                    
                    print(f"⚡ Handling UI Request on Main Thread (Drift: {request['score']:.2f})")
                    
                    action, intent_law, intent_why = launch_gatekeeper(
                        request['score'], 
                        request['old'], 
                        request['new']
                    )
                    
                    if action == "BLOCK":
                        if HAS_PYPERCLIP:
                            pyperclip.copy("")
                        print("🚫 BLOCKED by User")
                        if context_db:
                            context_db.log_block(request['score'], request['new'])
                            
                    elif action == "COMMIT":
                        if context_db:
                            context_db.log_diamond(request['score'], request['new'], intent_law, intent_why)
                            print("💎 COMMITTED to Context")
                            
                    elif action == "IGNORE":
                        print("💨 IGNORED by User")

            except queue.Empty:
                pass # No requests, keep looping
            
    except KeyboardInterrupt:
        print("\n\n🛑 TREPAN stopped. Goodbye!")
        if _tray:
            try:
                _tray.stop()
            except Exception:
                pass
        if clipboard_guard:
            clipboard_guard.stop()
        observer.stop()
    
    observer.join()



if __name__ == "__main__":
    main()
