# Security Review: CSDK-CMDD (AI Connector Builder)

**Date:** 2026-02-04
**Context:** Alpha release with restricted user base (domain-based login whitelist)
**Threat Model:** Defend against (a) cross-tenant access bugs, (b) benign user with compromised browser/session token

---

## Executive Summary

This review identifies security vulnerabilities that should be addressed even in an alpha with trusted users. The issues fall into three categories:

| Priority | Issue | Risk | Status |
|----------|-------|------|--------|
| ~~P3~~ | ~~Session tokens in localStorage (XSS target)~~ | ~~Low~~ | **FIXED** - HttpOnly cookies |
| P3 | In-memory session storage | Low | Deferred (needs Redis) |
| P4 | Session file stores tokens on disk | Info | Deferred (needs Redis) |
| ~~P4~~ | ~~Error messages may leak information~~ | ~~Info~~ | **FIXED** - Generic messages |

---

## P3: Low - Nice to Have

### 1. ~~Session Tokens in localStorage (XSS Target)~~ -- FIXED

**Status:** Fixed on 2026-02-06

**What was done:**
- Backend now sets `HttpOnly, Secure, SameSite=Lax` cookies on login/refresh
- Frontend no longer stores `session_token` in localStorage (only `username`)
- All API calls use `credentials: 'include'` instead of `Authorization: Bearer` headers
- CSRF mitigated by `SameSite=Lax` + JSON `Content-Type` on all mutating endpoints

---

### 2. In-Memory Session Storage

**Location:** `main.py:90`

```python
# In-memory session storage (in production, use Redis or database)
active_sessions = {}
```

**Issue:**
- Sessions lost on server restart (mitigated by `sessions.json` persistence)
- Not horizontally scalable (can't run multiple backend instances)
- Memory grows with active sessions (no cleanup of expired sessions except on access)

**Current Mitigation:** Sessions are persisted to `sessions.json` on disk (`main.py:232-281`)

**Risk Level for Alpha:** Acceptable for single-instance deployment.

**Production Fix:**
```python
# Use Redis for session storage
import redis
session_store = redis.Redis(host='localhost', port=6379, db=0)

def create_session(username: str) -> str:
    session_token = secrets.token_urlsafe(32)
    session_data = json.dumps({
        "username": username,
        "created_at": datetime.now().isoformat(),
        "expires_at": (datetime.now() + timedelta(hours=48)).isoformat()
    })
    session_store.setex(f"session:{session_token}", 48*3600, session_data)
    return session_token
```

---

## P4: Informational - Low Priority

### 3. Session File Stores Tokens on Disk

**Location:** `main.py:232` - `SESSIONS_FILE = Path(__file__).parent / "sessions.json"`

**Issue:** Session tokens are persisted to disk in plaintext JSON. If an attacker gains read access to the filesystem, they can steal all active session tokens.

**Current State:**
```json
{
  "abc123...": {
    "username": "john_doe",
    "session_token": "abc123...",
    "created_at": "2026-02-04T10:00:00",
    "expires_at": "2026-02-06T10:00:00"
  }
}
```

**Risk Level for Alpha:** Low - if attacker has filesystem access, they likely have access to more valuable targets (env vars, source code).

**Production Fix:** Use Redis or encrypted session storage, or accept that filesystem access = game over.

---

### 4. Credentials Stored in Memory

**Location:** `main.py:98-100`

```python
# Session credentials storage (maps "session_token:project_name" to sensitive config values)
session_credentials = {}
credentials_lock = threading.Lock()
```

**Issue:** User-provided API credentials (for their connectors) are stored in server memory. A memory dump or debug endpoint could expose these.

**Current Mitigations:**
- Credentials are cleared from disk after use (`_run.py:194-206`)
- Credentials are keyed by session token (can't access other users' creds without their session)

**Risk Level for Alpha:** Acceptable - memory-only storage is reasonable for credentials.

**Note:** Consider using a secrets manager (AWS Secrets Manager, HashiCorp Vault) for production.

---

### 5. No CSRF Protection

**Issue:** Now that we use cookies, CSRF must be considered.

**Current Mitigations:**
- `SameSite=Lax` on session cookie blocks cross-origin POST requests
- All mutating endpoints use `Content-Type: application/json`, which cross-origin forms cannot forge
- CORS restricts allowed origins

**Risk Level:** Low - mitigated by SameSite + JSON content type. Consider adding CSRF tokens for production.

---

### 6. ~~Error Messages May Leak Information~~ -- FIXED

**Status:** Fixed on 2026-02-06

**What was done:**
- All `str(e)` and `traceback.format_exc()` removed from client-facing API responses
- Generic error messages returned to users (e.g., "Failed to load connectors. Please try again.")
- Detailed errors logged server-side via `logger.error()` with `exc_info=True`
- Subprocess scripts sanitized to print generic messages to stdout (details go to stderr)
- Files modified: `main.py`, `_generate.py`, `_run.py`, `_validate.py`, `_fix_revise.py`, `_interact.py`

---

## Implementation Plan

### Phase 2: Before Beta / Wider Release

**P3 - Low:**

- [ ] Consider basic process isolation (separate user accounts per connector run)

### Phase 3: Before Production

- [x] Implement HttpOnly cookies for session tokens
- [ ] Move to Redis for session storage (horizontal scaling)
- [ ] Implement connector execution sandboxing (Docker/gVisor)
- [ ] Add structured logging with sensitive field redaction
- [x] Generic error messages for end users
- [ ] Security audit of AI-generated connector code execution
- [ ] Add CSRF tokens (if needed beyond SameSite protection)

---

## Testing Checklist

### Cross-User Access Test
```bash
# User A creates a project
# User B (different session cookie) tries to access it - should fail with 403
curl -X GET http://localhost:8001/user-connectors/user_a \
  --cookie "session_token=$USER_B_TOKEN"
```

---

## Appendix: Security Headers (Future Enhancement)

For production, consider adding these HTTP security headers:

```python
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware

# Force HTTPS
app.add_middleware(HTTPSRedirectMiddleware)

# Restrict hosts
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["your-domain.com"])

# Add security headers via middleware
@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    return response
```

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-02-04 | Security Review | Initial comprehensive review |
| 2026-02-06 | Security Fix | Fixed: CORS methods/headers (P4), debug logging (P3), rate limiting (P3), RCE documentation (P2) |
| 2026-02-06 | Security Fix | Fixed: HttpOnly cookies for session tokens (P3), generic error messages (P4) |
