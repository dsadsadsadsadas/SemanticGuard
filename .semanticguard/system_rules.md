# Solo-Indie System Rules (The Speedster)

## Core Philosophy
Keep it simple, keep it readable. You're flying solo, so future-you needs to understand what present-you wrote.

## Rule 1: Function Size Limit
- NO functions longer than 50 lines
- If a function does more than one thing, split it
- Each function should have a single, clear purpose

## Rule 2: Nesting Depth Limit
- Maximum 3 levels of nesting (if/for/while)
- Deeply nested code is a code smell - refactor it
- Use early returns to reduce nesting

## Rule 3: Naming Clarity
- Variable names must be descriptive (no single letters except loop counters)
- Function names must be verbs (getUserData, calculateTotal, validateInput)
- Class names must be nouns (User, DataProcessor, ValidationEngine)

## Rule 4: Comment the Why, Not the What
- Don't comment obvious code
- DO comment complex business logic
- DO comment workarounds and edge cases

## Rule 5: DRY (Don't Repeat Yourself)
- If you copy-paste code more than twice, make it a function
- Shared logic belongs in utility modules
- Configuration belongs in config files, not scattered in code

## Rule 6: Error Handling
- Always handle errors explicitly
- No silent failures
- Log errors with context (what failed, why, when)
z## Rule 7: Test the Critical Path
- Write tests for business logic
- Write tests for edge cases
- Don't test trivial getters/setters

## Mandatory Security Baseline
- NO hardcoded secrets, API keys, or passwords
- NO `eval()` or `exec()` with user input
- NO `os.system()` or `subprocess` with `shell=True`
- ALL file paths must use `os.path.realpath()` + `startswith()` validation
- ALL SQL queries must use parameterized statements


## VitalCare Security Protocol (V1.0)

 # RULE_8: PHI_PROTECTION
Under NO circumstances should Patient Health Information (PHI) be logged. 
This includes:
- Patient Name
- Diagnosis / Condition
- Social Security Numbers

 # RULE_9: ERROR_HANDLING
When an error occurs, the system must return a generic 'Internal Server Error' to the client. 
Never expose the raw error object or the patient's data in the response logs.

 # RULE_10: LOGGING_GATE
Use the custom 'secureLogger' utility for ALL terminal output.

## Rule 11: Multi-Hop Taint Analysis (The "Source-to-Sink" Mandate)

**Context:** Modern vulnerabilities rarely happen on a single line. Developers abstract data through classes, helper functions, and state variables.

**The Directive:** When analyzing code, you MUST perform strict backward taint analysis. If you detect a dangerous execution sink (e.g., `subprocess.run`, `os.system`, `eval`, `exec`, raw SQL queries), you cannot assume the inputs are safe just because the immediate surrounding code looks benign.

**Execution Steps:**

**Step 0 — Static Dangerous Content Check (Pre-Taint):** Before tracing any data flow, scan for hardcoded dangerous values that are dangerous regardless of their source:
- Any hardcoded string containing `<script>`, `javascript:`, `onerror=`, `onload=`, or HTML event handlers
- Any hardcoded string passed directly to `innerHTML`, `document.write()`, or `eval()`
- Any hardcoded string that IS the payload (not a sanitized output, but a raw attack string)

These are CRITICAL findings even if no runtime user input is involved. A hardcoded XSS payload is still an XSS payload.

1. **Identify the Sink:** Locate any function that executes commands, queries, or renders raw HTML.
2. **Trace Backward:** Trace the variables passed into that sink backward through all function calls, class instantiations, and return values.
3. **Identify the Source:** Did this data originate from an untrusted source (e.g., `request.json`, `req.query`, `sys.argv`, file uploads)?
4. **Check for Sanitization:** Was the data explicitly sanitized, cast to a safe type, or parameterized between the Source and the Sink?
5. **The Verdict:** If the data flows from an Untrusted Source to a Dangerous Sink without explicit sanitization, you MUST flag it as a Critical Vulnerability, even if the flow crosses multiple files, classes, or functions.

## Trepan Mandatory Defaults
Rule 1 : Strict Contextual Synchronization. Every architectural change must logically align with the established Project Context (README). If a developer introduces a new feature, rule, or concept, they must simultaneously update all affected pillars to prevent architectural drift. Isolated updates that create a contradiction between pillars or the project's core context are strictly forbidden.
Rule 2 : After Understanding With User What the Project is about, create a Detailed And Planned Readme File, that is also Accepted by User.
Rule 3 : YOUR ARE NOT ALLOWED TO TOUCH trepan_vault NOR .trepan.lock


## SemanticGuard Mandatory Defaults
Rule 4 : YOUR ARE NOT ALLOWED TO TOUCH semanticguard_vault NOR .semanticguard.lock

## Forbidden Libraries (Context Drift Detection)

**RULE_12: FORBIDDEN_LIBRARY_REQUESTS**

DO NOT use the `requests` library in this project.
- Use `httpx` instead for all HTTP operations
- Reason: Project standardizes on httpx for async support and better performance

If you detect usage of `import requests` or `requests.get/post/put/delete`, flag as:
- Severity: MEDIUM
- Vulnerability Type: Context Drift - Forbidden Library
- Description: "Code uses 'requests' library which is forbidden in this project. Use 'httpx' instead for async support."
