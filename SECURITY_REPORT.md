# Security Report

## Project

- Application: `Integrated_Ethics_and_MBA`
- Review type: source code review
- Review date: 2026-06-11
- Reviewer: Codex

## Scope

This review focused on:

- shared authentication and account linking
- legacy Ethics authentication and session handling
- password reset behavior
- CSRF protections
- file access and upload/download routes
- basic browser security headers
- request abuse protections such as rate limiting

This was a code-level review only. It did not include:

- live penetration testing
- dependency vulnerability scanning
- Render infrastructure configuration review
- SMTP transport verification
- secret history scanning outside the visible workspace

## Executive Summary

The system has a solid base in some areas, especially around shared CSRF handling in the integrated app, short-lived SSO tokens, and object-level access checks for many Ethics documents. The biggest risks are concentrated in the legacy Ethics app and the password reset/account-linking design.

The highest-priority issues are:

1. plaintext temporary passwords sent by email
2. inconsistent and partially bypassed CSRF protection in the legacy Ethics app
3. no visible rate limiting on login and reset flows
4. password propagation between MBA and Ethics accounts during cross-system provisioning
5. path-based file serving that needs stricter path containment checks

## Risk Ratings

- High: likely to enable account compromise or major unauthorized actions
- Medium: meaningful weakness that increases attack surface or weakens trust boundaries
- Low: lower-likelihood weakness or defense-in-depth gap

## Findings

### 1. Plaintext Password Reset by Email

- Severity: High
- Location:
  - [app/auth.py](./app/auth.py)
- Evidence:
  - `_password_reset_email_body(...)` includes the temporary password in the email body.
  - `forgot_password()` generates a temporary password, writes it directly to user accounts, and emails it.
- Why it matters:
  - plaintext passwords can be exposed through compromised inboxes, mail forwarding, mail provider logs, screenshots, or copied support messages
  - the reset flow changes the real account password before the user proves control through a one-time action
  - a single email address can reset multiple linked accounts at once
- Recommended fix:
  - replace this with one-time password reset tokens
  - email only a time-limited reset link
  - require the user to choose a new password in-app
  - reset accounts individually rather than bundling multiple systems into one blind reset

### 2. Legacy Ethics CSRF Protection Can Fail Open

- Severity: High
- Location:
  - [app/ethics_production_app/app.py](./app/ethics_production_app/app.py)
- Evidence:
  - the app tries to import `CSRFProtect`, but if that fails it installs a fallback no-op class
  - template helper fallback can return an empty token instead of failing startup
- Why it matters:
  - if the dependency chain breaks or is missing in a real environment, the app may still start with little or no CSRF protection
  - this is especially risky because the legacy app contains many admin and workflow-changing form submissions
- Recommended fix:
  - fail startup if CSRF middleware cannot be loaded
  - remove the no-op fallback in production code
  - keep test-only bypasses isolated to test configuration, not runtime app logic

### 3. Multiple Legacy Write Endpoints Are Explicitly CSRF-Exempt

- Severity: High
- Location:
  - [app/ethics_production_app/app.py](./app/ethics_production_app/app.py)
  - [app/ethics_production_app/ROUTES/routes_form_workflows.py](./app/ethics_production_app/ROUTES/routes_form_workflows.py)
- Evidence:
  - several autosave routes use `@csrf.exempt`
  - `/admin/upload_student_docs` is both admin-only and `@csrf.exempt`
- Why it matters:
  - admin actions and student edits can potentially be triggered cross-site if an authenticated browser visits a malicious page
  - removing CSRF on convenience endpoints is a common source of silent privilege abuse
- Recommended fix:
  - remove `@csrf.exempt` from all browser-facing write routes
  - use token headers for JavaScript autosave requests
  - if a route must remain exempt, require a separate signed API token and isolate it from cookie auth

### 4. No Visible Rate Limiting on Login or Reset Flows

- Severity: High
- Location:
  - [app/auth.py](./app/auth.py)
  - [app/ethics_production_app/app.py](./app/ethics_production_app/app.py)
- Evidence:
  - no request throttling or lockout mechanism was found for login or password reset routes
  - no Flask-Limiter or equivalent was found in the repository
- Why it matters:
  - allows credential stuffing
  - allows password spraying against known usernames
  - increases reset abuse risk
- Recommended fix:
  - add per-IP and per-account rate limits to:
    - shared login
    - legacy login
    - forgot password
    - Microsoft auth retry paths where relevant
  - add audit alerts for repeated failures

### 5. Passwords Are Propagated Across Systems During Cross-System Provisioning

- Severity: Medium
- Location:
  - [app/auth.py](./app/auth.py)
- Evidence:
  - cross-system helper functions accept `password=...`
  - successful login in one system can create or update credentials in the other system
- Why it matters:
  - reduces separation between MBA and Ethics accounts
  - a compromise or reset event in one system can spread to the other
  - makes reasoning about account ownership and credential lifecycle harder
- Recommended fix:
  - stop copying raw passwords between systems
  - prefer:
    - explicit account linking
    - SSO-only bridge for shared access
    - independent password stores where local passwords must exist

### 6. Path-Based File Serving Needs Stronger Path Containment

- Severity: Medium
- Location:
  - [app/ethics_production_app/app.py](./app/ethics_production_app/app.py)
- Evidence:
  - file-serving helpers accept stored string paths and join them under `static`
  - the code checks existence, but does not clearly enforce normalized containment inside approved directories
- Why it matters:
  - if an attacker can store a crafted relative path in a file field, this could expose unintended local files
  - path traversal risk often appears through trusted database content rather than direct request input
- Recommended fix:
  - resolve paths with `Path.resolve()`
  - ensure the resolved file remains inside an approved upload root
  - reject any path that escapes that root
  - prefer opaque document IDs mapped to stored files instead of direct path strings

### 7. Content Security Policy Is Report-Only and Permissive

- Severity: Medium
- Location:
  - [app/ethics_production_app/app.py](./app/ethics_production_app/app.py)
- Evidence:
  - CSP is sent as `Content-Security-Policy-Report-Only`
  - policy allows both `'unsafe-inline'` and `'unsafe-eval'` for scripts
- Why it matters:
  - report-only mode does not block active attacks
  - permissive script settings weaken the browser’s ability to contain XSS
- Recommended fix:
  - move to enforced `Content-Security-Policy`
  - remove `unsafe-eval`
  - reduce inline script dependence with nonces or external scripts

### 8. Legacy Session Model Relies Heavily on Raw Session Keys

- Severity: Medium
- Location:
  - [app/ethics_production_app/app.py](./app/ethics_production_app/app.py)
- Evidence:
  - the legacy app uses manual session keys such as `id`, `role`, `supervisor_role`, `admin_role`
  - authorization logic is split across many routes and helpers
- Why it matters:
  - hand-managed session state is easier to drift or misuse over time
  - it increases the chance of inconsistent authorization between routes
- Recommended fix:
  - continue migrating legacy auth to the shared auth layer
  - centralize identity and role resolution
  - reduce route-level dependence on ad hoc session flags

### 9. Debug Mode Can Be Enabled by Environment

- Severity: Low
- Location:
  - [run.py](./run.py)
- Evidence:
  - the app uses `FLASK_DEBUG` to decide whether to run with debug enabled
- Why it matters:
  - expected in development, but dangerous if ever exposed in production
- Recommended fix:
  - ensure deployment never sets debug mode
  - consider explicit production guardrails in the startup path

## Positive Controls Observed

- The integrated app has a central CSRF validator in [app/security.py](./app/security.py).
- Shared auth uses short-lived signed SSO tokens.
- Session cookie settings include `HttpOnly` and `SameSite`.
- The legacy file routes do perform object-level authorization checks before serving many documents.
- Admin-only legacy routes often use server-side role checks rather than trusting request parameters alone.

## Recommended Remediation Order

### Immediate

1. Replace plaintext password reset with token-based reset.
2. Remove legacy CSRF fallbacks and fail closed if CSRF middleware is unavailable.
3. Remove `@csrf.exempt` from browser-authenticated write routes.
4. Add rate limiting to login and reset flows.

### Next

1. Stop syncing raw passwords across systems.
2. Harden file path handling with strict resolved-path checks.
3. Enforce CSP after reducing unsafe script requirements.

### Longer-Term

1. Finish consolidating legacy Ethics auth/session behavior into the shared auth system.
2. Review all legacy routes for consistent object-level authorization.
3. Add automated security tests for:
   - CSRF enforcement
   - route access control
   - password reset behavior
   - file access boundaries

## Suggested Security Backlog

- add password reset tokens and reset forms
- add Flask-Limiter or equivalent
- add centralized audit logging for failed auth
- add path-safe file storage abstraction
- add enforced CSP with nonce support
- add role and object-access test coverage
- remove no-op CSRF compatibility code from production runtime

## Conclusion

The codebase is workable, but the legacy Ethics subsystem still carries several security design shortcuts that should be addressed before treating the platform as hardened. The most important improvement is to move away from emailed temporary passwords and to make CSRF and request-abuse protections consistent across both systems.
