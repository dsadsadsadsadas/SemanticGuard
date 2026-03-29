#!/usr/bin/env python3
import os
import re
import sys
import argparse
from typing import List, Tuple, Dict
from pathlib import Path

# --- Replication of CloudLayer1PreScreener from server.py ---

class CloudLayer1PreScreener:
    HARD_SKIP_PATTERNS = {
        "test_file": r"\.test\.(ts|js)$",
        "spec_file": r"\.spec\.(ts|js)$",
        "test_dir": r"[/\\]test[s]?[/\\]",
        "mock_file": r"\.mock\.(ts|js)$",
    }
    
    SAFE_FILENAME_KEYWORDS = {
        "css": r"(?i)(style|css|theme|color|icon|view|ui|component|button|input|label|modal|dialog|sidebar|toolbar|menu|widget)",
        "test": r"(?i)(test|spec|mock|fixture|stub)",
        "doc": r"(?i)(readme|doc|example|sample|demo)",
    }
    
    SAFE_CONTENT_KEYWORDS = {
        "css_content": r"(?i)(\.css|@media|@keyframes|background-color|border-radius|font-size|padding|margin)",
        "theme_content": r"(?i)(theme|color|palette|dark|light|accent|primary|secondary)",
        "ui_content": r"(?i)(react|vue|angular|component|jsx|tsx|\bdom\b)",
    }
    
    EXPLOITABILITY_KEYWORDS = {
        "user_controlled_spawn": r"spawn\s*\(\s*(?:userInput|req\.|request\.|params\.|query\.|body\.)",
        "shell_true_subprocess": r"subprocess\s*\.\s*(?:call|run|Popen)\s*\([^)]*shell\s*=\s*True",
        "eval_with_input": r"eval\s*\(\s*(?:userInput|req\.|request\.|params\.|query\.|body\.|expr|formula|input|data)",
        "exec_with_input": r"exec\s*\(\s*(?:userInput|req\.|request\.|params\.|query\.|body\.|expr|formula|input|data)",
        "os_system_with_input": r"os\.system\s*\(\s*(?:userInput|req\.|request\.|params\.|query\.|body\.)",
        "env_injection": r"(?:LD_PRELOAD|BASH_ENV|ZDOTDIR|PYTHONPATH|NODE_OPTIONS)\s*:\s*(?:userInput|req\.|request\.|params\.|query\.|body\.)",
        "zip_slip": r"(?i)(zipfile|ZipFile|tarfile|extractall|extract\()",
        "deserialization": r"(?i)(yaml\.load\(|pickle\.loads\()",
        "prototype_pollution_sink": r"(?i)(__proto__|prototype|Object\.assign\()",
        "open_redirect_sink": r"(?i)(window\.location|res\.redirect\()",
        "insecure_config": r"debug\s*=\s*True",
        "file_upload_risk": r"(?i)(mimetype|file_upload)",
        "ssh_injection": r"exec_command",
    }
    
    SYSTEM_KEYWORDS = {
        "os_system": r"\bos\.system\s*\(",
        "subprocess_call": r"\bsubprocess\.",
        "spawn": r"\bspawn\s*\(",
        "popen": r"\bpopen\s*\(",
        "exec_call": r"\bexec\s*\(",
        "eval_call": r"\beval\s*\(",
        "compile_call": r"\bcompile\s*\(",
        "file_open": r"\bopen\s*\(",
        "file_read": r"\.read\s*\(",
        "file_write": r"\.write\s*\(",
        "fs_module": r"\bfs\.",
        "path_join": r"\bpath\.join",
        "require_fs": r"require\s*\(\s*['\"]fs['\"]",
        "require_child": r"require\s*\(\s*['\"]child_process['\"]",
        "http": r"(?i)(http|https|request|response)",
        "fetch": r"\bfetch\s*\(",
        "axios": r"\baxios\.",
        "database": r"(?i)(database|sql|query|connection|pool|sqlite3|cursor\.execute|SQLAlchemy|execute\()",
        "execute_query": r"(?i)(execute|query)\s*\(",
        "auth": r"(?i)(authenticate|authorize|permission|role|access|login|session)",
        "crypto": r"(?i)(crypto|encrypt|decrypt|hash|sign|verify|\brandom\.|Math\.random)",
        "data_parsing": r"(?i)(\bxml\.|ElementTree|yaml\.load)",
        "json_parse": r"JSON\.parse",
        "pickle_load": r"pickle\.load",
        "unvalidated_request_json": r"request\.json(?!.*(validate|sanitize|schema|jsonschema|pydantic|marshmallow))",
        "unvalidated_req_body": r"req\.body(?!.*(validate|sanitize|schema|joi|yup|zod))",
        "ui_template": r"(?i)(render_template|html\.escape|\bjinja|innerHTML|template|format|<div|<h[1-6]|<html|html\s*=|f\"\"\"[\s\S]*?<|class=\")",
        "hardcoded_key": r"(?i)(api_key|apikey|secret|password|token)\s*=\s*['\"][^'\"]{8,}['\"]",
        "aws_key": r"(?i)(aws_access_key|aws_secret)",
        "bearer_token": r"(?i)bearer\s+[a-zA-Z0-9_\-\.]+",
        "concurrency": r"(?i)\b(threading|thread|mutex|lock)\b",
        "xml_advanced": r"(?i)(lxml|etree|XMLParser)",
        "cors_network": r"(?i)(\bcors\b|Access-Control-Allow)",
        "deep_link": r"(?i)(window\.location|\bhref\b)",
        "file_upload": r"(?i)(multer|formidable|req\.files?)",
        "graphql": r"(?i)(ApolloServer|\bgraphql\b|introspection)",
        "prototype_pollution": r"(?i)(__proto__|\.prototype\b|Object\.assign|\bmerge\b)",
        "redos_risk": r"(?i)(RegExp|\.match\(|\.test\()",
        "financial_logic": r"(?i)(transfer|balance|payment|transaction|checkout|invoice|amount)",
    }
    
    UI_PENALTIES = {
        "html_element": r"(?i)(HTMLElement|innerHTML|textContent|className)",
        "color": r"(?i)(color|Color|COLOR)",
        "theme": r"(?i)(theme|Theme|THEME)",
        "style": r"(?i)(style|Style|STYLE)",
        "view": r"(?i)(view|View|VIEW)",
    }

    SECRET_KEYWORDS = {
        "secret": r"(?i)secret",
        "password": r"(?i)password",
        "api_key": r"(?i)api_key",
        "token": r"(?i)token",
        "credentials": r"(?i)credentials",
        "stripe": r"(?i)stripe",
        "aws": r"(?i)aws"
    }

    @staticmethod
    def _is_hard_skip_file(filename: str, code: str) -> Tuple[bool, str]:
        filename_lower = filename.lower()
        for name, pattern in CloudLayer1PreScreener.HARD_SKIP_PATTERNS.items():
            if re.search(pattern, filename_lower): return True, f"Hard skip: {name}"
        for name, pattern in CloudLayer1PreScreener.SAFE_FILENAME_KEYWORDS.items():
            if re.search(pattern, filename_lower): return True, f"Hard skip: {name} in filename"
        for name, pattern in CloudLayer1PreScreener.SAFE_CONTENT_KEYWORDS.items():
            if re.search(pattern, code[:2000]): return True, f"Hard skip: {name} in content"
        return False, ""

    @staticmethod
    def calculate_risk_score(code: str) -> int:
        score = 0
        for _, p in CloudLayer1PreScreener.EXPLOITABILITY_KEYWORDS.items(): score += len(re.findall(p, code)) * 5
        for _, p in CloudLayer1PreScreener.SECRET_KEYWORDS.items(): score += len(re.findall(p, code)) * 5
        for _, p in CloudLayer1PreScreener.SYSTEM_KEYWORDS.items(): score += len(re.findall(p, code)) * 2
        for _, p in CloudLayer1PreScreener.UI_PENALTIES.items(): score -= len(re.findall(p, code)) * 3
        return max(0, score)

    @staticmethod
    def should_audit(code: str, file_extension: str, filename: str = "") -> Tuple[bool, str, int]:
        if len(code) < 100: return False, "Small file", 0
        if file_extension.lower() in ['.md', '.txt', '.json', '.yaml', '.yml', '.lock', '.env', '.toml', '.ini', '.css', '.scss']: 
            return False, "Non-exe", 0
        if filename:
            skip, reason = CloudLayer1PreScreener._is_hard_skip_file(filename, code)
            if skip: return False, reason, 0
        score = CloudLayer1PreScreener.calculate_risk_score(code)
        if score >= 2: return True, f"Risk {score}", score
        return False, "No risk", 0

# --- Prompt Construction Replication ---

def get_base_prompt():
    return """You are an AGGRESSIVE AppSec auditor focused on EXPLOITABILITY, not patterns.
Your job is to find REAL, EXPLOITABLE security issues. Avoid false positives."""

def get_hardened_system_prompt(dynamic_rules: str = "", prompt_type: str = "v2_hardened") -> str:
    # Replicate STRESS_TEST_GENIUS_SYSTEM length for estimation
    if prompt_type == "stress_test_genius":
        # Stress Test prompt is ~2500 words/tokens
        placeholder = "STRESS TEST GENIUS SYSTEM PROMPT " * 500 
        return placeholder + dynamic_rules
    
    # Standard V2 prompt estimation
    rules_block = f"\nPROJECT-SPECIFIC SECURITY RULES:\n\n{dynamic_rules}\n" if dynamic_rules else ""
    return f"{rules_block}\n{get_base_prompt()}\nStandard V2 Rules Context " * 5

# --- Main Script Logic ---

def main():
    parser = argparse.ArgumentParser(description="Estimate token usage for a folder audit.")
    parser.add_argument("folder", nargs="?", help="Folder to scan (optional, will prompt if missing)")
    parser.add_argument("--rules", help="Path to .semanticguard/system_rules.md", default=None)
    parser.add_argument("--prompt", choices=["v2_hardened", "stress_test_genius"], default="v2_hardened", help="Audit engine to use")
    args = parser.parse_args()

    # If folder not provided as argument, ask the user
    folder_input = args.folder
    if not folder_input:
        print("\n🛡️ SemanticGuard Token Auditor")
        folder_input = input("Enter the path of the folder you want to audit (default: .): ").strip()
        if not folder_input:
            folder_input = "."

    target_path = Path(folder_input).absolute()
    if not target_path.exists():
        print(f"Error: {target_path} does not exist.")
        sys.exit(1)

    # 1. Load Rules
    dynamic_rules = ""
    # Search for rules in the target directory, or the parent of the target file
    rules_search_dir = target_path if target_path.is_dir() else target_path.parent
    rules_path = Path(args.rules) if args.rules else rules_search_dir / ".semanticguard" / "system_rules.md"
    if rules_path.exists():
        dynamic_rules = rules_path.read_text(encoding='utf-8', errors='ignore')
        print(f"[*] Loaded rules from {rules_path}")

    system_prompt = get_hardened_system_prompt(dynamic_rules, args.prompt)
    print(f"[*] Using prompt engine: {args.prompt}")
    system_prompt_tokens = len(re.findall(r"\w+|[^\w\s]", system_prompt))

    # --- Line Range Prompt ---
    line_start, line_end = None, None
    range_input = input("Enter line range (e.g., 1-100) or press Enter for full file: ").strip()
    if range_input:
        try:
            if "-" in range_input:
                s, e = range_input.split("-")
                line_start, line_end = int(s), int(e)
            else:
                line_start = int(range_input)
            print(f"[*] Applying line range: {line_start} to {line_end if line_end else 'END'}")
        except ValueError:
            print("[!] Invalid range format. Using full file.")

    # 2. Scan Files
    total_tokens: int = 0
    auditable_files: List[dict] = []
    skipped_count: int = 0

    if target_path.is_file():
        print(f"[*] Analyzing single file: {target_path.name}")
        try:
            full_code = target_path.read_text(encoding='utf-8', errors='ignore')
            
            # Apply line range if specified
            if line_start is not None:
                lines = full_code.splitlines()
                start_idx = max(0, int(line_start) - 1)
                end_idx = int(line_end) if line_end is not None else len(lines)
                code = "\n".join(lines[start_idx:end_idx])
            else:
                code = full_code

            # For specific file: NO SKIPPING (as requested)
            risk_score = CloudLayer1PreScreener.calculate_risk_score(code)
            
            code_tokens = len(re.findall(r"\w+|[^\w\s]", code))
            output_reserve = 500
            estimated_tokens = system_prompt_tokens + code_tokens + output_reserve
            
            auditable_files.append({
                "path": target_path.name,
                "score": risk_score,
                "tokens": estimated_tokens
            })
            total_tokens += estimated_tokens
        except Exception as e:
            print(f"[!] Error reading {target_path}: {e}")
            sys.exit(1)
    else:
        print(f"[*] Scanning directory: {target_path}")
        for root, dirs, files in os.walk(target_path):
            # Exclude common noise dirs
            dirs[:] = [d for d in dirs if d not in ['.git', 'node_modules', '.venv', 'venv', '__pycache__', '.semanticguard']]
            
            for file in files:
                file_path = Path(root) / file
                ext = file_path.suffix
                
                try:
                    full_code = file_path.read_text(encoding='utf-8', errors='ignore')
                    
                    # Apply line range if specified
                    if line_start is not None:
                        lines = full_code.splitlines()
                        s_idx = max(0, int(line_start) - 1)
                        e_idx = int(line_end) if line_end is not None else len(lines)
                        code = "\n".join(lines[s_idx:e_idx])
                    else:
                        code = full_code

                    if not code.strip(): continue # Skip if empty after slice

                    should_audit, reason, score = CloudLayer1PreScreener.should_audit(code, ext, file)
                    
                    if should_audit:
                        # Formula from server.py (Step 5)
                        code_tokens = len(re.findall(r"\w+|[^\w\s]", code))
                        output_reserve = 500
                        estimated_tokens = system_prompt_tokens + code_tokens + output_reserve
                        
                        auditable_files.append({
                            "path": file_path.relative_to(target_path),
                            "score": score,
                            "tokens": estimated_tokens
                        })
                        total_tokens += estimated_tokens
                    else:
                        skipped_count += 1
                except Exception as e:
                    print(f"[!] Error reading {file_path}: {e}")

    # 3. Output Results
    print("\n" + "="*80)
    print(f"{'FILE':<50} | {'RISK':<5} | {'TOKENS':<10}")
    print("-" * 80)
    
    for f in sorted(auditable_files, key=lambda x: x['score'], reverse=True):
        path_str = str(f['path'])
        if len(path_str) > 50: path_str = "..." + path_str[-47:]
        print(f"{path_str:<50} | {f['score']:<5} | {f['tokens']:<10,}")

    print("="*80)
    print(f"Summary:")
    print(f"  Auditable Files: {len(auditable_files)}")
    print(f"  Skipped Files:   {skipped_count}")
    print(f"  Total Tokens:    {total_tokens:,}")
    print("="*80)

if __name__ == "__main__":
    main()
