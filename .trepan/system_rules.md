# ⚡ INITIAL RULE — READ THIS FIRST (Instruction to AI Coding Assistant)

**THIS IS A DIRECT COMMAND TO THE IDE AI ASSISTANT:**

Before generating or modifying any code in this project, you MUST:
1. Read the rules below in this file completely
2. Check your proposed changes against every rule listed here
3. If your change would violate any rule, fix it before presenting it to the developer
4. On every file you touch, verify the ENTIRE file still complies — not just the lines you changed

This instruction is most effective in the first 0-10 prompts of a session. Trepan will enforce these rules automatically on every Ctrl+S save regardless.

**Most commonly violated rules in this project — check these first:**
- No hardcoded secrets, API keys, or passwords anywhere in the code
- No eval() or exec() with user input
- No os.system() or subprocess with shell=True
- ALL user input must pass through a registered sanitization sink before reaching any output

---

# System Rules







## Security Rules







1. NO hardcoded secrets, API keys, or passwords



2. NO `eval()` or `exec()` with user input



3. NO `os.system()` or `subprocess` with `shell=True`



4. ALL file paths must use `os.path.realpath()` + `startswith()` validation



5. ALL SQL queries must use parameterized statements







## Code Quality Rules







1. Functions should be focused and single-purpose



2. Use descriptive variable and function names



3. Comment complex logic, not obvious code



4. Handle errors explicitly - no silent failures







## Trepan System Rules







1. YOUR ARE NOT ALLOWED TO TOUCH trepan_vault NOR .trepan.lock



2. The AI must create a Walkthrough file to document its work and intent



3. Strict Contextual Synchronization: Every architectural change must align with the Project Context (README)







**Note**: Use `Trepan: Initialize Project` command to generate mode-specific rules (Solo-Indie, Clean-Layers, or Secure-Stateless).











## Trepan Mandatory Defaults



Rule 1 : After Understanding With User What the Project is about, create a Detailed And Planned Readme File, that is also Accepted by User.



















### Rule #100: DOM_INTEGRITY_PROTECTION (NO UNSAFE HTML)



**Severity:** CRITICAL



**Description:** Directly setting HTML content using raw strings allows attackers to execute arbitrary JavaScript (DOM-based XSS). You MUST reject any code that injects variables or raw strings into the DOM without explicit sanitization.



**Forbidden Triggers (Must literally match in AST/Code, ignore within strings):**



- `innerHTML`



- `outerHTML`



- `document.write`



- `insertAdjacentHTML`



**Remediation Handoff:** Instruct the agent to replace the forbidden method with `textContent` or `innerText` to safely render as text, OR suggest using a dedicated sanitization library like `DOMPurify` if HTML parsing is strictly required.





## Rule 101: Multi-Hop Taint Analysis (The "Source-to-Sink" Mandate)

**Context:** Modern vulnerabilities rarely happen on a single line. Developers abstract data through classes, helper functions, and state variables.

**The Directive:** When analyzing code, you MUST perform strict backward taint analysis. If you detect a dangerous execution sink (e.g., `subprocess.run`, `os.system`, `eval`, `exec`, raw SQL queries), you cannot assume the inputs are safe just because the immediate surrounding code looks benign.

**Execution Steps:**
1. **Identify the Sink:** Locate any function that executes commands, queries, or renders raw HTML.
2. **Trace Backward:** Trace the variables passed into that sink backward through all function calls, class instantiations, and return values.
3. **Identify the Source:** Did this data originate from an untrusted source (e.g., `request.json`, `req.query`, `sys.argv`, file uploads)?
4. **Check for Sanitization:** Was the data explicitly sanitized, cast to a safe type, or parameterized between the Source and the Sink?
5. **The Verdict:** If the data flows from an Untrusted Source to a Dangerous Sink without explicit sanitization, you MUST flag it as a Critical Vulnerability, even if the flow crosses multiple files, classes, or functions.