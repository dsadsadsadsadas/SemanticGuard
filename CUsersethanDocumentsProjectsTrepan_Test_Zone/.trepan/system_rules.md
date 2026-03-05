# Secure-Stateless System Rules (The Fortress)

## Core Philosophy
Trust no one. Assume every input is malicious. Privacy is non-negotiable. Stateless architecture prevents session hijacking.

## Rule 1: Input Sanitization (MANDATORY)
- ALL user input must be validated and sanitized
- Use allowlists, not denylists (specify what's allowed, not what's forbidden)
- Validate data type, length, format, and range
- Reject invalid input immediately with clear error messages
- NO raw user input in SQL, shell commands, or file paths

## Rule 2: Zero Trust Architecture
- Authenticate every request
- Authorize every action
- Validate every input
- Log every security event
- Assume breach - design for containment

## Rule 3: Stateless Sessions
- NO server-side session storage
- Use JWT tokens with short expiration (15 minutes max)
- Include refresh tokens for extended sessions
- Tokens must be signed and verified
- Store tokens in httpOnly cookies (not localStorage)

## Rule 4: Secrets Management
- NO hardcoded secrets ANYWHERE
- Use environment variables for secrets
- Use secret management services (Vault, AWS Secrets Manager)
- Rotate secrets regularly
- Secrets must never appear in logs or error messages

## Rule 5: Encryption Everywhere
- ALL data in transit must use TLS 1.3+
- ALL sensitive data at rest must be encrypted
- Use bcrypt/argon2 for password hashing (NEVER plain SHA/MD5)
- Use AES-256 for data encryption
- Key management must be separate from application code

## Rule 6: Principle of Least Privilege
- Services run with minimum required permissions
- Database users have minimum required grants
- API keys have minimum required scopes
- File system access is restricted to specific directories

## Rule 7: Audit Logging
- Log all authentication attempts (success and failure)
- Log all authorization failures
- Log all data access (who, what, when)
- Logs must be tamper-proof (write-only, signed)
- NO sensitive data in logs (passwords, tokens, PII)

## Rule 8: Rate Limiting & DDoS Protection
- Rate limit all public endpoints
- Implement exponential backoff for failed auth
- Use CAPTCHA for sensitive operations
- Monitor for suspicious patterns

## Rule 9: Secure Defaults
- Fail closed, not open (deny by default)
- Disable unnecessary features
- Remove debug endpoints in production
- Use security headers (CSP, HSTS, X-Frame-Options)

## Rule 10: Privacy by Design
- Collect minimum necessary data
- Anonymize data where possible
- Implement data retention policies
- Support data deletion requests (GDPR compliance)
- NO third-party tracking without explicit consent

## Mandatory Code Security
- NO `eval()` or `exec()` EVER
- NO `os.system()` or `subprocess` with `shell=True`
- NO dynamic SQL queries (use parameterized queries ONLY)
- ALL file paths must use `os.path.realpath()` + `startswith()` validation
- NO pickle/marshal for untrusted data
- Use safe YAML/JSON parsers (no `yaml.load()`, use `yaml.safe_load()`)

## Dependency Security
- Pin all dependency versions
- Scan dependencies for vulnerabilities (npm audit, safety)
- Update dependencies regularly
- Review dependency licenses
- Minimize dependency count
