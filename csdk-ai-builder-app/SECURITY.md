# Security TODOs

Outstanding security items that need to be addressed.

## Critical - Architectural Decision Required

### RCE via connector execution

User-uploaded connectors are executed server-side with `fivetran debug`, and user-specified `requirements.txt` is installed via `pip install`. Python package install hooks and connector code can run arbitrary commands.

**Current mitigations:**
- Users must authenticate via Google OAuth with domain whitelist
- Each user has isolated workspace directory
- Processes run as the server user (not root)

**Recommended actions:**
- [ ] Run connector execution in containers/sandboxes (Docker, Firecracker, gVisor)
- [ ] Use `--no-deps` and allowlist for pip installs
- [ ] Implement resource limits (CPU, memory, network)
- [ ] Consider serverless execution model

## Medium

### No CSP in nginx

Content-Security-Policy is commented out in nginx config. Increases blast radius of any future XSS vulnerabilities.

**Action:**
- [ ] Enable strict CSP in production (`connector-generator.nginx:31`)

## Low / Informational

### Path sanitization is brittle

`sanitize_path()` uses `replace('..', '')` which can create confusing collisions. Currently supplemented with `validate_project_name()` regex validation.

**Location:** `backend/app/main.py:426`

**Action:**
- [ ] Consider using `pathlib.Path.resolve()` with proper containment checks

### Absolute server paths in errors

Some error responses include server filesystem paths (minor info leak).

**Location:** `backend/app/main.py:1651`

**Action:**
- [ ] Audit error responses for path leakage

## Deployment Checklist

- [ ] Set `PRODUCTION=true` environment variable
- [ ] Configure nginx to set X-Forwarded-For header
- [ ] Enable CSP headers in nginx
- [ ] Review domain whitelist (ALLOWED_DOMAINS)
- [ ] Set up log monitoring for error IDs
- [ ] Regular security updates for dependencies
