# Golden Templates Implementation

## Overview
The Golden Templates system provides three pre-configured architectural styles for initializing Trepan projects. Each template includes mode-specific rules, LLM-generated code examples, and cryptographic vault initialization.

---

## The Three Modes

### 1. Solo-Indie (The Speedster) ⚡
**For**: Solo developers who need readable, maintainable code without over-engineering

**Focus Areas**:
- Function size limits (max 50 lines)
- Nesting depth limits (max 3 levels)
- Clear, descriptive naming
- DRY principle (Don't Repeat Yourself)
- Comment the 'why', not the 'what'

**Use Cases**:
- Personal projects
- Rapid prototyping
- Small-scale applications
- Learning projects

### 2. Clean-Layers (The Architect) 🏗️
**For**: Serious, long-term projects that need strict separation of concerns

**Focus Areas**:
- Strict layer separation (Presentation, Business Logic, Data Access)
- Dependency direction (outer depends on inner)
- Interface contracts at layer boundaries
- Single Responsibility Principle
- Dependency Injection

**Use Cases**:
- Enterprise applications
- Team projects
- Long-term maintenance
- Scalable architectures

### 3. Secure-Stateless (The Fortress) 🛡️
**For**: Maximum security projects with zero-trust architecture

**Focus Areas**:
- Zero Trust Architecture
- Input sanitization (mandatory)
- Stateless sessions with JWT
- Encryption everywhere (TLS 1.3+, AES-256)
- Audit logging
- Privacy by design

**Use Cases**:
- Financial applications
- Healthcare systems
- Government projects
- High-security environments

---

## Architecture

### Server-Side Components

#### 1. Template Definitions (`GOLDEN_TEMPLATES`)
Located in `trepan_server/server.py`, lines ~32-250

Each template contains:
```python
{
    "name": "Display name",
    "description": "Brief description",
    "system_rules": "Complete markdown rules document",
    "llm_prompt": "Prompt for generating Perfect Execution example"
}
```

#### 2. Initialization Function (`initialize_project_with_template`)
Located in `trepan_server/server.py`, lines ~700-850

**Steps**:
1. Create `.trepan/` directory structure
2. Write `system_rules.md` based on chosen mode
3. Generate `golden_state.md` using LLM
4. Initialize other pillar files
5. Create vault snapshots
6. Generate cryptographic lock
7. Initialize `Walkthrough.md`
8. Generate `README.md`

#### 3. API Endpoints

**POST /initialize_project**
```json
Request:
{
  "mode": "solo-indie | clean-layers | secure-stateless",
  "project_path": "/absolute/path/to/project"
}

Response:
{
  "status": "success",
  "message": "Project initialized with Solo-Indie (The Speedster) mode"
}
```

**GET /templates**
```json
Response:
{
  "templates": [
    {
      "id": "solo-indie",
      "name": "Solo-Indie (The Speedster)",
      "description": "..."
    },
    ...
  ]
}
```

### Client-Side Components

#### 1. VS Code Command (`trepan.initializeProject`)
Located in `extension/extension.js`, lines ~160-260

**User Flow**:
1. User runs "Trepan: Initialize Project" from command palette
2. Extension checks if workspace is open
3. Shows warning if `.trepan/` already exists
4. Displays QuickPick menu with three template options
5. Sends request to server
6. Shows progress notification
7. Opens generated `system_rules.md` and `golden_state.md`
8. Shows success message

#### 2. Template Selection UI
```javascript
const templates = [
    {
        label: "$(zap) Solo-Indie (The Speedster)",
        description: "Simple, readable code for solo developers",
        detail: "Focus: Function size limits, nesting depth, clear naming, DRY principle",
        id: "solo-indie"
    },
    // ... other templates
];
```

---

## LLM Integration

### Perfect Execution Generation

Each template includes a specialized prompt for generating a "Perfect Execution" code example:

**Solo-Indie Prompt**:
- Generate a simple, readable function
- Maximum 50 lines, 3 levels of nesting
- Clear naming, proper error handling
- Include 'why' comments

**Clean-Layers Prompt**:
- Show three-layer architecture
- Demonstrate separation of concerns
- Show dependency injection
- Include interface contracts

**Secure-Stateless Prompt**:
- Show secure API endpoint
- Demonstrate JWT authentication
- Show input sanitization
- Include rate limiting and audit logging

### LLM Call Flow
```
User selects template
    ↓
Server writes system_rules.md
    ↓
Server calls Llama 3.1 with template-specific prompt
    ↓
LLM generates Perfect Execution example
    ↓
Server writes golden_state.md with:
    - Mode description
    - LLM-generated example
    - Architectural principles
    ↓
Server initializes vault and lock
```

---

## File Structure After Initialization

```
project_root/
├── .trepan/
│   ├── system_rules.md          (Mode-specific rules)
│   ├── golden_state.md          (LLM-generated example + principles)
│   ├── done_tasks.md            (Empty, ready for use)
│   ├── pending_tasks.md         (Empty, ready for use)
│   ├── history_phases.md        (Initialization timestamp)
│   ├── problems_and_resolutions.md (Empty, ready for use)
│   ├── Walkthrough.md           (Reference Architecture template)
│   ├── README.md                (Auto-generated documentation)
│   ├── .trepan.lock             (Cryptographic signature)
│   └── trepan_vault/            (Frozen snapshots)
│       ├── system_rules.md
│       ├── golden_state.md
│       ├── done_tasks.md
│       ├── pending_tasks.md
│       ├── history_phases.md
│       └── problems_and_resolutions.md
```

---

## Example: Solo-Indie Mode

### Generated system_rules.md
```markdown
# Solo-Indie System Rules (The Speedster)

## Core Philosophy
Keep it simple, keep it readable. You're flying solo, so future-you needs to understand what present-you wrote.

## Rule 1: Function Size Limit
- NO functions longer than 50 lines
- If a function does more than one thing, split it
...
```

### Generated golden_state.md
```markdown
# Golden State - Solo-Indie (The Speedster)

## Mode Description
For solo developers who need readable, maintainable code without over-engineering

## Perfect Execution Example

[LLM-generated code example showing best practices]

## Architectural Principles

This project follows the **solo-indie** architectural style...

### Key Principles:
- Keep functions under 50 lines
- Maximum 3 levels of nesting
...
```

---

## Security & Vault Integration

### Cryptographic Signing
After initialization, all pillar files are:
1. Copied to `.trepan/trepan_vault/` (frozen snapshots)
2. Hashed together using SHA-256
3. Signature stored in `.trepan.lock`

### Tamper Detection
Any manual edits to:
- `.trepan/trepan_vault/*` files
- `.trepan/.trepan.lock` file

Will trigger vault compromise detection on next save.

### Meta-Gate Protection
Changes to `.trepan/*.md` files go through special validation:
1. Diff calculated against vault snapshot
2. LLM evaluates if changes weaken architectural rules
3. If ACCEPT: Vault updated and re-signed
4. If REJECT: Changes blocked, vault unchanged

---

## Usage Examples

### Command Palette
```
1. Press Ctrl+Shift+P (Windows) or Cmd+Shift+P (Mac)
2. Type "Trepan: Initialize Project"
3. Select your mode:
   - Solo-Indie (The Speedster)
   - Clean-Layers (The Architect)
   - Secure-Stateless (The Fortress)
4. Wait for LLM to generate Perfect Execution example
5. Review generated system_rules.md and golden_state.md
```

### API Direct Call
```bash
curl -X POST http://127.0.0.1:8000/initialize_project \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "secure-stateless",
    "project_path": "/path/to/project"
  }'
```

### Get Available Templates
```bash
curl http://127.0.0.1:8000/templates
```

---

## Error Handling

### Server Offline
```
Extension shows: "Trepan initialization failed: Failed to fetch"
User action: Start Trepan server
```

### Invalid Mode
```
Server returns 400: "Invalid mode: xyz. Must be one of: solo-indie, clean-layers, secure-stateless"
```

### LLM Generation Failure
```
Server returns 500: "Model inference failed: [error details]"
User action: Check Ollama is running with llama3.1 model
```

### Already Initialized
```
Extension shows warning: "Trepan is already initialized in this project. Reinitialize?"
Options: "Yes, Reinitialize" | "Cancel"
```

---

## Testing

### Test Template Generation
```bash
# Start server
cd trepan_server
python -m uvicorn server:app --reload

# Test initialization
curl -X POST http://127.0.0.1:8000/initialize_project \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "solo-indie",
    "project_path": "/tmp/test_project"
  }'

# Verify files created
ls -la /tmp/test_project/.trepan/
cat /tmp/test_project/.trepan/system_rules.md
cat /tmp/test_project/.trepan/golden_state.md
```

### Test Extension Command
1. Open VS Code
2. Open a folder
3. Press Ctrl+Shift+P
4. Run "Trepan: Initialize Project"
5. Select a mode
6. Verify files are created and opened

---

## Performance Considerations

### LLM Generation Time
- Solo-Indie: ~5-10 seconds (simple example)
- Clean-Layers: ~10-15 seconds (multi-layer example)
- Secure-Stateless: ~15-20 seconds (complex security example)

### Timeout Settings
- Extension timeout: 60 seconds
- Server timeout: No limit (waits for LLM)
- User sees progress notification during generation

### Optimization Tips
- Use Q4_K_M quantization for faster inference
- Ensure GPU is utilized (check with `nvidia-smi`)
- Pre-warm Ollama by running a test query

---

## Future Enhancements

### Custom Templates
Allow users to define their own templates:
```json
{
  "custom-template": {
    "name": "My Custom Style",
    "system_rules": "...",
    "llm_prompt": "..."
  }
}
```

### Template Marketplace
- Share templates with community
- Import templates from GitHub
- Rate and review templates

### Multi-Language Support
- Generate examples in user's preferred language
- Language-specific rules (Python, JavaScript, Go, Rust)

### Interactive Wizard
- Step-by-step template customization
- Preview rules before applying
- Modify LLM-generated examples

---

## Summary

The Golden Templates system provides:

✅ **Three Pre-Configured Modes**: Solo-Indie, Clean-Layers, Secure-Stateless  
✅ **LLM-Generated Examples**: Perfect Execution code for each mode  
✅ **Automatic Vault Initialization**: Cryptographic signing from day one  
✅ **VS Code Integration**: One-command project setup  
✅ **Extensible Architecture**: Easy to add new templates  

**Result**: Users can initialize a Trepan project with production-ready architectural rules and code examples in under 30 seconds.

**The Golden Templates are now live. 🛡️**
