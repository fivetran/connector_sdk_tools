# AI Connector Generator

A web application for generating Fivetran connectors using AI. The application consists of a FastAPI backend and a React/Vite frontend.

## Prerequisites

- **Python 3.12.x** (for backend)
- **uv** (fast Python package manager) - [Install uv](https://docs.astral.sh/uv/getting-started/installation/)
- **Node.js** v22.22.x (for frontend)
- **npm** v10.9.x

## Environment Variables

Set these environment variables in your shell config (e.g., `~/.bashrc` or `~/.zshrc`):

```bash
# ===================
# REQUIRED
# ===================

# Anthropic API key for Claude AI (falls back to ANTHROPIC_API_KEY if not set)
export CSDKAI_ANTHROPIC_API_KEY="your_anthropic_api_key_here"

# Google OAuth Client ID for authentication (used by both backend and frontend)
export CSDKAI_GOOGLE_CLIENT_ID="your_google_oauth_client_id_here"

# Master secret for encrypting user configuration files
# Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"
export CSDKAI_MASTER_SECRET="your_generated_secret_here"

# ===================
# OPTIONAL
# ===================

# Comma-separated list of allowed email domains (default: fivetran.com)
export CSDKAI_ALLOWED_DOMAINS="fivetran.com"

# Comma-separated list of allowed CORS origins (default: localhost)
export CSDKAI_ALLOWED_ORIGINS="http://localhost:5173"
```

## Running the Application

### Backend (FastAPI/Python)

```bash
# Navigate to backend directory
cd backend

# Create a virtual environment and install dependencies
uv venv
source .venv/bin/activate  # On macOS/Linux
uv pip install -r requirements.txt

# Run the backend server
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

The backend will be available at `http://127.0.0.1:8001`

### Frontend (Vite/React)

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Run the development server
npm run dev
```

The frontend will be available at `http://localhost:5173`

## Running Services

Use the scripts in `scripts/` to manage services:

```bash
# Start services
./scripts/start-be.sh    # Start backend
./scripts/start-fe.sh    # Start frontend

# Check status
./scripts/status-be.sh   # Check if backend is running
./scripts/status-fe.sh   # Check if frontend is running

# View logs
./scripts/tail-be.sh     # Follow backend logs
./scripts/tail-fe.sh     # Follow frontend logs

# Stop services
./scripts/stop-be.sh     # Stop backend
./scripts/stop-fe.sh     # Stop frontend
```

This will run:
- **Backend** on port 8001
- **Frontend** on port 5173

## API Documentation

Once the backend is running, you can access:
- Swagger UI: `http://127.0.0.1:8001/docs`
- ReDoc: `http://127.0.0.1:8001/redoc`

---

## Security Considerations (Alpha)

### Remote Code Execution by Design

This application allows authenticated users to execute arbitrary Python code on the server via connector testing. This is intentional for the product's functionality but carries inherent risks:

**What users can do:**
- Execute any Python code within their connector
- Install packages from `requirements.txt`
- Make network requests from the server
- Access filesystem within their workspace

**Current mitigations:**
- Domain-based login restriction (only `@fivetran.com` users by default)
- Session-based authentication with 48-hour expiry
- Per-user isolated workspace directories
- Path traversal protection on API endpoints

**Acceptable Use for Alpha:**
1. **Do NOT store production credentials** in connector configurations
2. **Do NOT access other users' data** via filesystem exploration
3. **Do NOT install packages** that could compromise the server
4. **Do NOT make requests** to internal Fivetran services

**Production Roadmap:**
- Containerized connector execution (Docker/gVisor)
- Resource limits (CPU, memory, network, disk)
- Network isolation and egress filtering
- Read-only filesystem with private /tmp

By using this alpha application, you acknowledge these limitations and agree to use the service responsibly.