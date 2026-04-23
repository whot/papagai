---
description: Search repository for security issues
tools: Bash(grep:*),Bash(find:*),Bash(git log:*),Bash(git add:*),Bash(git commit:*)
---

You are tasked with performing a security audit of the repository in the
current directory. Systematically search the codebase for common security
issues and report your findings.

Search for the following categories of security issues:

## Memory Safety
- Buffer overflows: unchecked array indexing, missing bounds checks,
  unsafe use of memcpy/strcpy/sprintf/strcat and similar functions
- Use-after-free patterns: pointers used after the backing memory may
  have been freed
- Double-free patterns
- Uninitialized memory reads
- Integer overflows that feed into memory allocations or buffer sizes

## Input Validation
- Missing or insufficient validation of user/external input
- Format string vulnerabilities (user-controlled format strings)
- Command injection: unsanitized input passed to system(), popen(),
  exec(), or shell commands
- Path traversal: unsanitized file paths that could escape intended
  directories (e.g. "../" sequences)
- SQL injection, XSS, or other injection flaws if applicable

## Authentication and Authorization
- Hardcoded credentials, API keys, tokens, or passwords
- Weak or missing authentication checks
- Privilege escalation opportunities
- Insecure session management

## Cryptography
- Use of weak or deprecated algorithms (MD5, SHA1 for security
  purposes, DES, RC4, etc.)
- Hardcoded cryptographic keys or IVs
- Insecure random number generation (rand(), srand(), Math.random()
  for security-sensitive contexts)
- Missing or improper certificate validation

## File and Resource Handling
- Race conditions (TOCTOU: time-of-check to time-of-use)
- Insecure temporary file creation
- Missing error checking on security-critical operations
- Insecure file permissions

## Information Disclosure
- Sensitive data written to logs
- Verbose error messages exposing internals
- Debug code or development backdoors left in production code

## Language-Specific Issues
- For C/C++: unsafe functions, missing null checks, signed/unsigned
  comparison issues
- For Python: use of eval(), pickle on untrusted data, subprocess
  with shell=True
- For JavaScript/TypeScript: prototype pollution, eval(), unsafe
  deserialization
- For Rust: excessive use of unsafe blocks, unchecked unwrap() on
  user input

## Output Format

For each finding, report:
1. **Severity**: Critical / High / Medium / Low / Informational
2. **File and line number**: exact location
3. **Category**: which category from above
4. **Description**: what the issue is and why it is a security concern
5. **Recommendation**: how to fix it

Sort findings by severity (Critical first). At the end, provide a
summary with counts by severity level.

Focus on real, exploitable issues rather than theoretical concerns.
Prioritize findings that could lead to actual security impact. Do not
report style issues or non-security bugs unless they have a clear
security implication.

## Fixing and Committing

For each issue found, fix the issue in the source code and create a
separate git commit for that fix. Each commit message must follow this
format:

    security: fix <short description of the issue>

    <Category>: <Severity>

    <Longer description of what the issue was and how it was fixed.>

Do not batch multiple issues into a single commit. Each security fix
must be an atomic, self-contained commit so that individual fixes can
be reviewed, reverted, or backported independently.
