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

## Rule 7: Test the Critical Path
- Write tests for business logic
- Write tests for edge cases
- Don't test trivial getters/setters

## Mandatory Security Baseline
- NO hardcoded secrets, API keys, or passwords
- NO `eval()` or `exec()` with user input
- NO `os.system()` or `subprocess` with `shell=True`
- ALL file paths must use `os.path.realpath()` + `startswith()` validation
- ALL SQL queries must use parameterized statements


## Hi