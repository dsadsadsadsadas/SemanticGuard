#!/usr/bin/env python3
"""
🦅 TREPAN - The Observer, Watchdog & Clipboard Brain
A dynamic context injection system with:
- Phase 1: File-based context detection
- Phase 2: Loop detection via AI response monitoring
- Phase 3: Smart clipboard-based context injection with Groq AI

Author: Project TREPAN
"""

import os
import sys
import time
import difflib
import threading
from pathlib import Path
from collections import deque
from typing import Optional

# Third-party imports
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from watchdog.events import FileSystemEventHandler
from dotenv import load_dotenv
from ast_engine import scan_for_secrets

# Load environment variables
load_dotenv()

# Conditional imports for Window Title (Windows only)
try:
    import ctypes
    WINDOW_AWARENESS_AVAILABLE = True
except ImportError:
    WINDOW_AWARENESS_AVAILABLE = False
    print("⚠️  ctypes not available - Window Awareness disabled")

# Conditional imports for clipboard
try:
    import pyperclip
    CLIPBOARD_AVAILABLE = True
except ImportError:
    CLIPBOARD_AVAILABLE = False
    print("⚠️  pyperclip not installed - clipboard monitoring disabled")

# Conditional imports for Groq
try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False
    print("⚠️  groq not installed - AI context analysis disabled")


# ============================================================================
# CONFIGURATION
# ============================================================================

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

# Path constants
RULES_FILE = "GEMINI.md"  # Antigravity reads this automatically
AI_TRACE_FILE = "ai_trace.txt"

# Loop detection settings
SIMILARITY_THRESHOLD = 0.85
MEMORY_SIZE = 5

# Clipboard settings
CLIPBOARD_CHECK_INTERVAL = 0.5  # seconds
MAX_CLIPBOARD_LENGTH = 25000  # Increased for long prompts (handled by AI relevance check)

# ============================================================================
# CONTEXT RULES DICTIONARY
# ============================================================================

CONTEXT_RULES = {
    "Security": """## Current Mode: 🔒 SECURITY MODE

You are now in SECURITY-FOCUSED development mode.

### Priority Rules:
1. **Input Validation First** - Always validate and sanitize ALL user inputs
2. **No Hardcoded Secrets** - Never hardcode passwords, API keys, or tokens
3. **Parameterized Queries** - Use parameterized queries to prevent SQL injection
4. **Principle of Least Privilege** - Request minimum permissions necessary
5. **Error Handling** - Never expose stack traces or internal errors to users

### Security Checklist:
- [ ] Input validation implemented
- [ ] Authentication/authorization verified
- [ ] Sensitive data encrypted
- [ ] HTTPS enforced for data transmission
- [ ] Dependencies checked for vulnerabilities
""",

    "GUI": """## Current Mode: 🎨 GUI MODE

You are now in GUI/FRONTEND development mode.

### Priority Rules:
1. **Accessibility First** - Ensure WCAG 2.1 compliance (aria labels, keyboard nav)
2. **Responsive Design** - Mobile-first approach, test all breakpoints
3. **Performance** - Optimize images, lazy load, minimize reflows
4. **User Feedback** - Loading states, error messages, success confirmations
5. **Consistency** - Follow existing design system/component patterns

### UI/UX Checklist:
- [ ] Keyboard navigation works
- [ ] Color contrast meets WCAG AA
- [ ] Touch targets are 44x44px minimum
- [ ] Forms have proper labels and validation
- [ ] Animations respect prefers-reduced-motion
""",

    "Database": """## Current Mode: 🗄️ DATABASE MODE

You are now in DATABASE development mode.

### Priority Rules:
1. **Migrations** - Always create reversible migrations
2. **Indexing** - Add indexes for frequently queried columns
3. **Transactions** - Use transactions for multi-step operations
4. **Backup Awareness** - Consider data recovery implications
5. **Query Optimization** - Avoid N+1 queries, use EXPLAIN

### Database Checklist:
- [ ] Migration is reversible
- [ ] Indexes added for search columns
- [ ] Foreign keys properly constrained
- [ ] Data types are appropriate
- [ ] Query performance tested with realistic data
""",

    "Default": """## Current Mode: 💻 DEFAULT MODE

You are a helpful AI coding assistant. Focus on writing clean, maintainable code.

### General Guidelines:
1. Write clear, self-documenting code
2. Follow the project's existing patterns and conventions
3. Add appropriate error handling
4. Consider edge cases
5. Keep functions small and focused
""",

    "Emergency_Loop": """## 🚨🚨🚨 EMERGENCY: LOOP DETECTED 🚨🚨🚨

# STOP. YOU ARE LOOPING.

**CRITICAL RESET REQUIRED**

You have been detected repeating the same response pattern multiple times.
This indicates you are stuck in a reasoning loop.

## MANDATORY ACTIONS:
1. **STOP** your current approach immediately
2. **DISCARD** your previous strategy entirely  
3. **RE-READ** the original user request from scratch
4. **TRY** a completely different approach
5. **ASK** the user for clarification if genuinely stuck

## DO NOT:
- Continue with the same solution
- Make minor variations of the same code
- Repeat explanations you've already given
- Ignore this warning

**This message was auto-injected by TREPAN Loop Detection System.**
"""
}

# File patterns for context detection
SECURITY_PATTERNS = {
    'extensions': ['.pem', '.key', '.crt', '.env'],
    'keywords': ['auth', 'security', 'password', 'credential', 'secret', 'token', 
                 'encrypt', 'decrypt', 'hash', 'login', 'permission', 'oauth']
}

GUI_PATTERNS = {
    'extensions': ['.css', '.scss', '.sass', '.less', '.html', '.htm', '.jsx', 
                   '.tsx', '.vue', '.svelte'],
    'keywords': ['component', 'style', 'ui', 'frontend', 'view', 'layout', 
                 'template', 'button', 'form', 'modal']
}

DATABASE_PATTERNS = {
    'extensions': ['.sql', '.prisma', '.graphql'],
    'keywords': ['model', 'migration', 'schema', 'database', 'db', 'query', 
                 'repository', 'orm', 'entity', 'table']
}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_active_window_title() -> str:
    """Get the title of the currently active window."""
    if not WINDOW_AWARENESS_AVAILABLE:
        return ""
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        buff = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
        return buff.value
    except Exception:
        return ""

def is_ide_window() -> bool:
    """Check if the active window is a known IDE/Editor."""
    title = get_active_window_title()
    ide_keywords = ['Antigravity', 'Cursor', 'Code', 'Manager', 'Windsurf', 'PyCharm', 'Sublime']
    for keyword in ide_keywords:
        if keyword in title:
            return True
    return False

def get_project_map(watch_dir: str) -> str:
    """
    Generate a map of top-level files and folders in the project.
    Used to provide Groq AI with project context.
    """
    items = []
    ignore_patterns = {'.git', '__pycache__', 'venv', 'node_modules', '.env', '.venv'}
    
    try:
        for entry in os.listdir(watch_dir):
            if entry in ignore_patterns or entry.startswith('.'):
                continue
            
            full_path = os.path.join(watch_dir, entry)
            if os.path.isdir(full_path):
                try:
                    file_count = sum(1 for _ in Path(full_path).rglob('*') if _.is_file())
                    items.append(f"📁 {entry}/ ({file_count} files)")
                except:
                    items.append(f"📁 {entry}/")
            else:
                size = os.path.getsize(full_path)
                if size < 1024:
                    size_str = f"{size}B"
                else:
                    size_str = f"{size // 1024}KB"
                items.append(f"📄 {entry} ({size_str})")
    except Exception as e:
        items.append(f"Error reading directory: {e}")
    
    return "\n".join(items) if items else "Empty project"


# ============================================================================
# PROJECT CACHE - Full Context Awareness
# ============================================================================

class ProjectCache:
    """
    Reads and caches all project files on startup for full context awareness.
    Provides the AI with complete knowledge of the codebase.
    """
    
    # File extensions to read and cache
    CODE_EXTENSIONS = {
        '.py', '.js', '.ts', '.jsx', '.tsx', '.vue', '.svelte',
        '.html', '.css', '.scss', '.sass', '.less',
        '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg',
        '.md', '.txt', '.rst',
        '.sql', '.prisma', '.graphql',
        '.sh', '.bash', '.ps1', '.bat',
        '.dockerfile', '.docker-compose.yml',
        '.env.example', '.gitignore', '.cursorrules'
    }
    
    # Directories to ignore
    IGNORE_DIRS = {
        '.git', '__pycache__', 'venv', '.venv', 'node_modules',
        'dist', 'build', '.next', '.nuxt', 'coverage',
        '.pytest_cache', '.mypy_cache', 'eggs', '*.egg-info'
    }
    
    # Files to ignore (TREPAN's own files should NEVER be cached)
    IGNORE_FILES = {
        '.env', '.DS_Store', 'Thumbs.db', '*.pyc', '*.pyo',
        'package-lock.json', 'yarn.lock', 'poetry.lock',
        'trepan.py', 'ai_trace.txt', 'GEMINI.md', 'requirements.txt'  # TREPAN's own files
    }
    
    # Max file size to cache (100KB)
    MAX_FILE_SIZE = 100 * 1024
    
    # Max total cache size (500KB)
    MAX_CACHE_SIZE = 500 * 1024
    
    def __init__(self, watch_dir: str):
        self.watch_dir = watch_dir
        self.cache: dict[str, str] = {}
        self.total_size = 0
        self.file_count = 0
        self.load_time = 0.0
    
    def _should_ignore_dir(self, dirname: str) -> bool:
        """Check if directory should be ignored."""
        return dirname in self.IGNORE_DIRS or dirname.startswith('.')
    
    def _should_cache_file(self, filepath: str) -> bool:
        """Check if file should be cached."""
        filename = os.path.basename(filepath)
        ext = os.path.splitext(filepath)[1].lower()
        
        # Ignore hidden files
        if filename.startswith('.') and filename not in {'.gitignore', '.env.example'}:
            return False
        
        # Ignore specific files
        if filename in self.IGNORE_FILES:
            return False
        
        # Check extension or specific filenames
        if ext in self.CODE_EXTENSIONS:
            return True
        
        # Also cache extensionless important files
        if filename.lower() in {'dockerfile', 'makefile', 'readme', 'license'}:
            return True
        
        return False
    
    def _read_file_safe(self, filepath: str) -> Optional[str]:
        """Safely read a file, handling encoding issues."""
        try:
            size = os.path.getsize(filepath)
            if size > self.MAX_FILE_SIZE:
                return f"[FILE TOO LARGE: {size // 1024}KB - content truncated]"
            
            # Try UTF-8 first, then fallback
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return f.read()
            except UnicodeDecodeError:
                try:
                    with open(filepath, 'r', encoding='latin-1') as f:
                        return f.read()
                except:
                    return "[BINARY FILE - cannot read]"
        except Exception as e:
            return f"[ERROR: {e}]"
    
    def build_cache(self) -> None:
        """Scan and cache all project files."""
        start_time = time.time()
        self.cache = {}
        self.total_size = 0
        self.file_count = 0
        
        print(f"📚 [{time.strftime('%H:%M:%S')}] Building project cache...")
        
        for root, dirs, files in os.walk(self.watch_dir):
            # Filter out ignored directories
            dirs[:] = [d for d in dirs if not self._should_ignore_dir(d)]
            
            for filename in files:
                # Skip Windows reserved device names
                if filename.lower() in {'nul', 'con', 'prn', 'aux', 'com1', 'com2', 'lpt1', 'lpt2'}:
                    continue
                
                filepath = os.path.join(root, filename)
                
                # Try to get relative path, skip if it fails (Windows special files)
                try:
                    rel_path = os.path.relpath(filepath, self.watch_dir)
                except ValueError:
                    continue
                
                if not self._should_cache_file(filepath):
                    continue
                
                # Check if we've exceeded max cache size
                if self.total_size >= self.MAX_CACHE_SIZE:
                    print(f"⚠️  Cache limit reached ({self.MAX_CACHE_SIZE // 1024}KB)")
                    break
                
                content = self._read_file_safe(filepath)
                if content:
                    self.cache[rel_path] = content
                    self.total_size += len(content)
                    self.file_count += 1
            else:
                continue
            break
        
        self.load_time = time.time() - start_time
        print(f"✅ [{time.strftime('%H:%M:%S')}] Cached {self.file_count} files ({self.total_size // 1024}KB) in {self.load_time:.2f}s")
    
    def get_context_string(self, max_length: int = 50000) -> str:
        """
        Generate a context string for the AI with project file contents.
        
        Args:
            max_length: Maximum character length for the context
            
        Returns:
            Formatted string with file contents
        """
        if not self.cache:
            return "No files cached."
        
        lines = [f"## Project Files ({self.file_count} files, {self.total_size // 1024}KB)\n"]
        current_length = len(lines[0])
        
        # Prioritize important files first
        priority_files = ['README.md', 'PLANS.md', 'PENDING_TASKS.md', 'requirements.txt', 
                         'package.json', 'pyproject.toml', '.cursorrules']
        
        sorted_files = []
        for pf in priority_files:
            if pf in self.cache:
                sorted_files.append(pf)
        
        # Add remaining files
        for filepath in sorted(self.cache.keys()):
            if filepath not in sorted_files:
                sorted_files.append(filepath)
        
        for filepath in sorted_files:
            content = self.cache[filepath]
            
            # Truncate large files for context
            if len(content) > 2000:
                content = content[:2000] + "\n... [truncated]"
            
            file_block = f"\n### 📄 {filepath}\n```\n{content}\n```\n"
            
            if current_length + len(file_block) > max_length:
                lines.append(f"\n... [{len(sorted_files) - len(lines) + 1} more files not shown due to length limit]")
                break
            
            lines.append(file_block)
            current_length += len(file_block)
        
        return "".join(lines)
    
    def get_file_summary(self) -> str:
        """Get a brief summary of cached files."""
        if not self.cache:
            return "No files cached."
        
        # Group by extension
        by_ext: dict[str, int] = {}
        for filepath in self.cache:
            ext = os.path.splitext(filepath)[1] or 'other'
            by_ext[ext] = by_ext.get(ext, 0) + 1
        
        summary = [f"📚 Cached: {self.file_count} files ({self.total_size // 1024}KB)"]
        for ext, count in sorted(by_ext.items(), key=lambda x: -x[1])[:5]:
            summary.append(f"  {ext}: {count}")
        
        return "\n".join(summary)


def calculate_similarity(text1: str, text2: str) -> float:
    """Calculate similarity ratio between two text strings."""
    if not text1 or not text2:
        return 0.0
    text1 = text1.strip().lower()
    text2 = text2.strip().lower()
    return difflib.SequenceMatcher(None, text1, text2).ratio()


def inject_context(filepath: str, watch_dir: str) -> str:
    """Determine which context rule to apply based on file extension and name."""
    filename = os.path.basename(filepath).lower()
    extension = os.path.splitext(filepath)[1].lower()
    filepath_lower = filepath.lower()
    
    # Check Security patterns
    if extension in SECURITY_PATTERNS['extensions']:
        return "Security"
    for keyword in SECURITY_PATTERNS['keywords']:
        if keyword in filename or keyword in filepath_lower:
            return "Security"
    
    # Check GUI patterns
    if extension in GUI_PATTERNS['extensions']:
        return "GUI"
    for keyword in GUI_PATTERNS['keywords']:
        if keyword in filename or keyword in filepath_lower:
            return "GUI"
    
    # Check Database patterns
    if extension in DATABASE_PATTERNS['extensions']:
        return "Database"
    for keyword in DATABASE_PATTERNS['keywords']:
        if keyword in filename or keyword in filepath_lower:
            return "Database"
    
    return "Default"


def update_rules_file(context: str, watch_dir: str, trigger_file: str):
    """Update the .cursorrules file with the appropriate context rules."""
    rules_path = os.path.join(watch_dir, RULES_FILE)
    
    header = f"""# 🦅 TREPAN Dynamic Context Rules
# Auto-generated based on: {os.path.basename(trigger_file)}
# Last updated: {time.strftime('%Y-%m-%d %H:%M:%S')}

"""
    content = header + CONTEXT_RULES[context]
    
    with open(rules_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✅ [{time.strftime('%H:%M:%S')}] Injected {context.upper()} context → {RULES_FILE}")


# ============================================================================
# FILE WATCHING HANDLERS
# ============================================================================

class TREPANEventHandler(FileSystemEventHandler):
    """Event handler for file-based context detection."""
    
    def __init__(self, watch_dir: str):
        super().__init__()
        self.watch_dir = watch_dir
        self.last_context = None
        self._ignore_files = {'.cursorrules', '.git', '__pycache__', 'venv', 'ai_trace.txt'}
    
    def _should_ignore(self, path: str) -> bool:
        basename = os.path.basename(path)
        if basename.startswith('.') or basename in self._ignore_files:
            return True
        for ignore in self._ignore_files:
            if ignore in path:
                return True
        return False
    
    def on_modified(self, event):
        if event.is_directory:
            return
        if self._should_ignore(event.src_path):
            return
        
        context = inject_context(event.src_path, self.watch_dir)
        
        if context != self.last_context:
            update_rules_file(context, self.watch_dir, event.src_path)
            self.last_context = context
            
        # 🟡 AST Security Scan for Python files
        if event.src_path.endswith('.py'):
            try:
                with open(event.src_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                issues = scan_for_secrets(content)
                if issues:
                    print(f"\n🔴🔴🔴 CRITICAL SECURITY ALERT in {os.path.basename(event.src_path)} 🔴🔴🔴")
                    for issue in issues:
                        print(f"   Line {issue['line']}: [{issue['type']}] {issue['message']}")
                    print("─────────────────────────────────────────────────────────────────\n")
            except Exception as e:
                pass


class LoopSniffer(FileSystemEventHandler):
    """Handler for loop detection via ai_trace.txt monitoring."""
    
    def __init__(self, watch_dir: str):
        super().__init__()
        self.watch_dir = watch_dir
        self.memory: deque = deque(maxlen=MEMORY_SIZE)
        self.last_content = ""
        self.loop_detected = False
        self.trace_file = os.path.join(watch_dir, AI_TRACE_FILE)
    
    def on_modified(self, event):
        if event.is_directory:
            return
        if os.path.basename(event.src_path) != AI_TRACE_FILE:
            return
        
        try:
            with open(event.src_path, 'r', encoding='utf-8') as f:
                current_content = f.read()
        except Exception as e:
            print(f"⚠️  Error reading trace file: {e}")
            return
        
        if current_content == self.last_content:
            return
        
        new_text = current_content[len(self.last_content):].strip()
        self.last_content = current_content
        
        if not new_text or new_text.startswith('#'):
            return
        
        self._on_ai_response(new_text)
    
    def _on_ai_response(self, text: str):
        print(f"🔍 [{time.strftime('%H:%M:%S')}] Analyzing response ({len(text)} chars)...")
        
        max_similarity = 0.0
        for past_response in self.memory:
            similarity = calculate_similarity(text, past_response)
            max_similarity = max(max_similarity, similarity)
            
            if similarity >= SIMILARITY_THRESHOLD:
                self._trigger_emergency_break(text, past_response, similarity)
                return
        
        self.memory.append(text)
        self.loop_detected = False
        print(f"✅ [{time.strftime('%H:%M:%S')}] Response OK (max similarity: {max_similarity:.1%}) - Memory: {len(self.memory)}/{MEMORY_SIZE}")
    
    def _trigger_emergency_break(self, new_text: str, matched_text: str, similarity: float):
        if self.loop_detected:
            print(f"🚨 [{time.strftime('%H:%M:%S')}] Still in EMERGENCY mode (similarity: {similarity:.1%})")
            return
        
        self.loop_detected = True
        print(f"\n🚨🚨🚨 LOOP DETECTED! 🚨🚨🚨")
        print(f"   Similarity: {similarity:.1%} (threshold: {SIMILARITY_THRESHOLD:.0%})")
        print(f"   New text preview: {new_text[:50]}...")
        print(f"   Matched preview:  {matched_text[:50]}...\n")
        
        rules_path = os.path.join(self.watch_dir, RULES_FILE)
        header = f"""# 🦅 TREPAN Dynamic Context Rules
# 🚨 EMERGENCY INJECTION - Loop Detected!
# Last updated: {time.strftime('%Y-%m-%d %H:%M:%S')}
# Similarity: {similarity:.1%}

"""
        content = header + CONTEXT_RULES["Emergency_Loop"]
        
        with open(rules_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"🚨 [{time.strftime('%H:%M:%S')}] Injected EMERGENCY_LOOP context → {RULES_FILE}")


# ============================================================================
# CLIPBOARD BRAIN (Phase 3)
# ============================================================================

class ClipboardBrain:
    """
    Smart clipboard monitoring with AI-powered context analysis.
    Uses Groq to distinguish user prompts from code/AI responses.
    Now with full project context from ProjectCache.
    """
    
    def __init__(self, watch_dir: str, project_cache: Optional[ProjectCache] = None):
        self.watch_dir = watch_dir
        self.last_clipboard = ""
        self.running = False
        self.client = None
        self.project_cache = project_cache
        
        # Result cache (Prompt -> Generated Rules)
        self.result_cache: dict[str, str] = {}
        self.MAX_CACHE_SIZE = 20
        
        # Loop Detection Memory
        self.memory: deque = deque(maxlen=MEMORY_SIZE)
        
        # Initialize Groq client
        if GROQ_AVAILABLE and GROQ_API_KEY:
            try:
                self.client = Groq(api_key=GROQ_API_KEY)
                print(f"🧠 Groq AI connected (model: {GROQ_MODEL})")
            except Exception as e:
                print(f"⚠️  Failed to initialize Groq: {e}")
        else:
            print("⚠️  Groq disabled - missing API key or library")
    
    def _get_system_prompt(self) -> str:
        """Generate the system prompt with full project context."""
        project_map = get_project_map(self.watch_dir)
        
        # Get full project context from cache if available
        if self.project_cache and self.project_cache.cache:
            project_context = self.project_cache.get_context_string(max_length=12000)
        else:
            project_context = "No project files cached."
        
        return f"""You are an AI Orchestrator for development tools. Analyze the user's clipboard text.

## Your Task:
Determine if the clipboard content is a DEVELOPER PROMPT that needs context, or something to IGNORE.

## IGNORE if the text is:
- An AI-generated response or explanation
- A code snippet without any question/request
- Error logs, stack traces, or console output
- Random data, JSON blobs, or configuration dumps
- Markdown documentation without a question
- Code that looks like it was copied to move elsewhere
- **Clearly referring to a DIFFERENT project** (e.g. prompt asks about "TREPAN Architecture" but the current project is a Game with `players.py`)
- *Note: If a file exists in BOTH (like helpful scripts), check if the prompt aligns with the CURRENT project's goals (e.g. Game Logic vs Tool Logic).*

## RESPOND with optimized .cursorrules if:
- It's a question or request from a developer
- It's a task description or feature request
- It's a problem statement seeking a solution
- It's a prompt that would benefit from focused AI assistance
- **It IS relevant to the current project structure below**

## Current Project Structure:
{project_map}

## Full Project Context (Cached Files):
{project_context}

## Output Format:
- If IGNORE: Output EXACTLY the word "IGNORE" (nothing else)
- If PROMPT: Output a focused, helpful .cursorrules content that will help an AI solve the specific request. Include:
  1. A brief summary of the task
  2. Key constraints or requirements based on existing code patterns
  3. Suggested approach using existing project patterns/libraries
  4. Relevant code snippets or file references from the project"""

    def _analyze_with_groq(self, text: str) -> Optional[str]:
        """Send text to Groq for analysis."""
        if not self.client:
            return None
        
        try:
            response = self.client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": f"Analyze this clipboard content:\n\n{text}"}
                ],
                temperature=0.3,
                max_tokens=1000
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"⚠️  Groq API error: {e}")
            return None

    def _is_ai_response(self, text: str) -> bool:
        """Heuristic check: Is this text likely an AI response?"""
        # Check for Common AI Phrasings
        ai_phrases = [
            "Here is the code", "Here's the code", "Certainly!", "I understand",
            "I apologize", "As an AI", "Based on the code", "Sure, here is",
            "I've updated the", "The issue is caused by"
        ]

        # Check start of text
        start_text = text[:100].lower()
        for phrase in ai_phrases:
            if phrase.lower() in start_text:
                return True

        # Check for large Markdown Block ratio (AI responses are mostly Code Blocks)
        if "```" in text:
            # Simple heuristic: If it has code blocks and fits the phrases, it's AI
            pass

        return False

    def _check_for_loops(self, text: str):
        """Check if this AI response is a duplicate (Loop Detection)."""
        print(f"🤖 [AI RESPONSE] Cached for loop detection")

        max_similarity = 0.0
        for past_response in self.memory:
            similarity = calculate_similarity(text, past_response)
            max_similarity = max(max_similarity, similarity)

            if similarity >= SIMILARITY_THRESHOLD:
                self._trigger_emergency_break(text, past_response, similarity)
                return

        self.memory.append(text)
        # print(f"✅ Loop Check OK (max similarity: {max_similarity:.1%})")

    def _trigger_emergency_break(self, new_text: str, matched_text: str, similarity: float):
        print(f"\n🚨🚨🚨 LOOP DETECTED! (Similarity: {similarity:.1%}) 🚨🚨🚨")
        rules_path = os.path.join(self.watch_dir, RULES_FILE)
        header = f"""# 🦅 TREPAN Dynamic Context Rules
# 🚨 EMERGENCY INJECTION - Loop Detected!
# Last updated: {time.strftime('%Y-%m-%d %H:%M:%S')}
# Similarity: {similarity:.1%}

"""
        with open(rules_path, 'w', encoding='utf-8') as f:
            f.write(header + CONTEXT_RULES["Emergency_Loop"])
        print(f"🚨 [EMERGENCY] Injected STOP context → {RULES_FILE}")

    def _process_clipboard(self, text: str):
        """Process new clipboard content."""

        # Step 0: Window Awareness Check
        if WINDOW_AWARENESS_AVAILABLE:
            if not is_ide_window():
                print(f"🚫 [IGNORED] Active window is not IDE ({get_active_window_title()})")
                return

        # Step 1: Local filter - check length
        if len(text) > MAX_CLIPBOARD_LENGTH:
            print(f"🚫 [IGNORED] Too long ({len(text)} chars)")
            return

        # Step 2: Auto-Detect AI Response (Phase 2 Loop Detection)
        if self._is_ai_response(text):
            self._check_for_loops(text)
            return

        # Step 3: Check Cache (Exact match + Similarity check)
        if text in self.result_cache:
            result = self.result_cache[text]
            print(f"📝 [PROMPT] Reuse cached result (Exact match)")
            self._apply_rules(result)
            return

        for cached_prompt, cached_result in self.result_cache.items():
            if calculate_similarity(text, cached_prompt) > 0.95:
                print(f"📝 [PROMPT] Reuse cached result (95%+ match)")
                self._apply_rules(cached_result)
                self._add_to_cache(text, cached_result)
                return

        # Step 4: AI Gatekeeper (Groq)
        print(f"🧠 Analyzing prompt ({len(text)} chars)...")
        result = self._analyze_with_groq(text)

        if result is None:
            print(f"⚠️  Skipped (Groq unavailable)")
            return

        # Step 5: Cache and Apply
        self._add_to_cache(text, result)
        self._apply_rules(result)

    def _add_to_cache(self, text: str, result: str):
        """Add to cache with LRU eviction."""
        if len(self.result_cache) >= self.MAX_CACHE_SIZE:
            first_key = next(iter(self.result_cache))
            del self.result_cache[first_key]
        self.result_cache[text] = result

    def _apply_rules(self, result: str):
        """Write the result to the rules file."""
        if result.strip().upper() == "IGNORE":
            print(f"🚫 [IGNORED] Content irrelevant or not a prompt")
            return

        # It's a valid prompt - update rules file
        rules_path = os.path.join(self.watch_dir, RULES_FILE)
        header = f"""# 🦅 TREPAN Dynamic Context Rules
# 🧠 AI-GENERATED from clipboard prompt
# Last updated: {time.strftime('%Y-%m-%d %H:%M:%S')}

"""
        with open(rules_path, 'w', encoding='utf-8') as f:
            f.write(header + result)

        print(f"📝 [PROMPT] BRAIN UPDATED: Context injected!")

    def monitor(self):
        """Main clipboard monitoring loop."""
        self.running = True
        print(f"📋 Clipboard monitoring started (checking every {CLIPBOARD_CHECK_INTERVAL}s)")

        while self.running:
            try:
                current = pyperclip.paste()
                if current and current != self.last_clipboard:
                    self.last_clipboard = current
                    self._process_clipboard(current)
            except Exception:
                pass
            time.sleep(CLIPBOARD_CHECK_INTERVAL)

    def stop(self):
        """Stop the clipboard monitoring."""
        self.running = False


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    """Main entry point for TREPAN."""
    watch_dir = os.getcwd()
    
    # Initialize .cursorrules if it doesn't exist
    rules_path = os.path.join(watch_dir, RULES_FILE)
    if not os.path.exists(rules_path):
        header = f"""# 🦅 Kodkod Dynamic Context Rules
# Auto-initialized on startup
# Last updated: {time.strftime('%Y-%m-%d %H:%M:%S')}

"""
        with open(rules_path, 'w', encoding='utf-8') as f:
            f.write(header + CONTEXT_RULES["Default"])
        print(f"📝 Created {RULES_FILE} with Default context")
    
    # Initialize ai_trace.txt if it doesn't exist
    trace_path = os.path.join(watch_dir, AI_TRACE_FILE)
    if not os.path.exists(trace_path):
        with open(trace_path, 'w', encoding='utf-8') as f:
            f.write("# AI Trace File - Paste AI responses here for loop detection\n")
        print(f"📝 Created {AI_TRACE_FILE}")
    
    print("""
╔═══════════════════════════════════════════════════════════════════╗
║  🦅 KODKOD - The Observer, Watchdog & Clipboard Brain              ║
║  Dynamic Context Injection + Loop Detection + Smart Clipboard      ║
╚═══════════════════════════════════════════════════════════════════╝
    """)
    print(f"👁️  Watching: {watch_dir}")
    print(f"📝 Rules file: {RULES_FILE}")
    print(f"🔍 Trace file: {AI_TRACE_FILE}")
    print(f"🧠 Groq Model: {GROQ_MODEL}")
    print("─" * 68)
    print("Features: File Context | Loop Detection | Clipboard Brain")
    print(f"Thresholds: Loop={SIMILARITY_THRESHOLD:.0%} | Clipboard Max={MAX_CLIPBOARD_LENGTH} chars")
    print("─" * 68)
    print("Press Ctrl+C to stop...\n")
    
    # Build project cache for full context awareness
    project_cache = ProjectCache(watch_dir)
    project_cache.build_cache()
    
    # Set up file watchers
    context_handler = TREPANEventHandler(watch_dir)
    # loop_sniffer = LoopSniffer(watch_dir)  <-- REMOVED (Replaced by ClipboardBrain Loop Detection)
    
    observer = Observer()
    observer.schedule(context_handler, watch_dir, recursive=True)
    # observer.schedule(loop_sniffer, watch_dir, recursive=False)
    
    # Set up clipboard brain (in separate thread) with project cache
    clipboard_brain = None
    clipboard_thread = None
    
    if CLIPBOARD_AVAILABLE and GROQ_AVAILABLE and GROQ_API_KEY:
        clipboard_brain = ClipboardBrain(watch_dir, project_cache)
        clipboard_thread = threading.Thread(target=clipboard_brain.monitor, daemon=True)
        clipboard_thread.start()
    else:
        print("⚠️  Clipboard Brain disabled (missing dependencies or API key)")
    
    try:
        observer.start()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n🛑 Kodkod stopped. Cleaning up...")
        if clipboard_brain:
            clipboard_brain.stop()
        observer.stop()
        
        # Delete .cursorrules to avoid confusion when Kodkod is not running
        rules_path = os.path.join(watch_dir, RULES_FILE)
        try:
            if os.path.exists(rules_path):
                os.remove(rules_path)
                print(f"🧹 Deleted {RULES_FILE} (clean exit)")
        except Exception as e:
            print(f"⚠️  Could not delete {RULES_FILE}: {e}")
        
        print("👋 Goodbye!")
    
    observer.join()


if __name__ == "__main__":
    main()
