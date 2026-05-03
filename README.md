# 📚 Bibliotheca — Library Management System

A full-stack library management system built with **FastAPI**, **PostgreSQL**, **Redis**, and a vanilla HTML/CSS/JS frontend.

---

## 🏗️ Architecture

```
library-management-api/
├── backend/              FastAPI application
│   ├── app/
│   │   ├── auth/         JWT authentication (register, login, /me)
│   │   ├── books/        Book CRUD (Admin: full CRUD, Member: read)
│   │   ├── borrow/       Borrow & return system
│   │   ├── dashboard/    Monitoring dashboard + metrics API
│   │   ├── system/       Logger, Redis cache, metrics, utils
│   │   └── core/         Database, config
│   ├── tests/            52 pytest tests
│   ├── conftest.py       Async test fixtures
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/             Vanilla HTML/CSS/JS
│   ├── index.html        Login & Register
│   ├── dashboard.html    Main app (books, borrows, admin, monitoring)
│   ├── css/style.css
│   └── js/
│       ├── api.js        Centralised API client
│       ├── utils.js      Toast, modals, helpers
│       └── dashboard.js  App controller
├── docker-compose.yml    Full stack orchestration
├── nginx.conf            Frontend proxy config
└── README.md
```

---

## ⚡ Quick Start — Local Development (No Docker)

### 1. Backend Setup

```bash
cd backend

# Install dependencies
pip install -r requirements.txt

# Start the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be at: **http://localhost:8000**
Interactive docs: **http://localhost:8000/docs**

### 2. Frontend Setup

Open `frontend/index.html` in your browser, **or** serve it with a local server:

```bash
# Option A — Python
cd frontend && python -m http.server 5500

# Option B — VS Code Live Server
# Right-click index.html → "Open with Live Server"
```

Then open: **http://localhost:5500**

### 3. Run Tests

```bash
cd backend
python -m pytest tests/ -v
# Expected: 52 passed
```

---

## 🐳 Docker — Full Stack (Recommended)

### Prerequisites
- Docker Desktop installed and running
- Docker Compose v2+

### Step 1 — Build & Start Everything

```bash
# From the project root (where docker-compose.yml is)
docker compose up --build
```

This starts 4 containers:
| Container | Service | Port |
|-----------|---------|------|
| `library-db` | PostgreSQL 16 | internal only |
| `library-redis` | Redis 7 | internal only |
| `library-backend` | FastAPI | **8000** |
| `library-frontend` | Nginx + HTML | **8080** |

### Step 2 — Open the App

| URL | What |
|-----|------|
| http://localhost:8080 | Frontend app |
| http://localhost:8000/docs | API documentation |
| http://localhost:8000/dashboard | Monitoring dashboard |
| http://localhost:8000/health | Health check |

### Step 3 — Stop

```bash
docker compose down          # stop containers
docker compose down -v       # stop + delete database volumes
```

### Useful Docker commands

```bash
# View logs
docker compose logs backend      # FastAPI logs
docker compose logs db           # Postgres logs
docker compose logs redis        # Redis logs
docker compose logs -f           # follow all logs

# Rebuild after code changes
docker compose up --build backend

# Run tests inside Docker
docker compose exec backend python -m pytest tests/ -v

# Open a shell inside the backend container
docker compose exec backend bash

# Check Redis cache
docker compose exec redis redis-cli keys "*"
```

---

## 🔐 Authentication & Roles

| Role | Permissions |
|------|-------------|
| **Admin** | Full CRUD on books, view all borrow records, delete borrows, monitoring dashboard |
| **Member** | Browse books, borrow/return books, view own history |

### Default test accounts (create via register):

```
Admin:  username=admin  email=admin@library.com  password=Admin123!  role=admin
Member: username=user1  email=user1@library.com  password=Pass123!   role=member
```

---

## 📡 API Endpoints

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/auth/register` | Register new user |
| POST | `/api/v1/auth/login` | Login, get JWT token |
| GET | `/api/v1/auth/me` | Get current user |

### Books
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/v1/books` | ✅ Any | List all books |
| GET | `/api/v1/books/{id}` | ✅ Any | Get book by ID |
| POST | `/api/v1/books` | 🔐 Admin | Create book |
| PUT | `/api/v1/books/{id}` | 🔐 Admin | Update book |
| DELETE | `/api/v1/books/{id}` | 🔐 Admin | Delete book |

### Borrows
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/v1/borrow` | ✅ Any | Borrow a book |
| GET | `/api/v1/borrow` | ✅ Any | My borrows (Admin: all) |
| GET | `/api/v1/borrow/{id}` | ✅ Owner/Admin | Get borrow by ID |
| PUT | `/api/v1/borrow/{id}/return` | ✅ Owner/Admin | Return book |
| GET | `/api/v1/borrow/user/{uid}` | 🔐 Admin | All borrows for user |
| DELETE | `/api/v1/borrow/{id}` | 🔐 Admin | Delete borrow record |

### Dashboard
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/dashboard` | HTML monitoring UI |
| GET | `/dashboard/metrics` | JSON metrics |
| GET | `/dashboard/logs?lines=50` | Recent log lines |

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI 0.115, Python 3.12 |
| Database | PostgreSQL 16 (prod) / SQLite (dev) |
| ORM | SQLAlchemy 2.0 (async) |
| Cache | Redis 7 |
| Auth | JWT (python-jose + passlib/bcrypt) |
| Validation | Pydantic v2 |
| Testing | pytest + pytest-asyncio + httpx |
| Frontend | Vanilla HTML/CSS/JS (ES Modules) |
| Proxy | Nginx Alpine |
| Container | Docker + Docker Compose |

---

## 👥 Team

| Member | Module | Branch |
|--------|--------|--------|
| M1 | Project setup, config, database | feature/m1-setup |
| M2 | JWT Authentication | feature/m2-auth |
| M3 | Books CRUD | feature/m3-books |
| M4 | Borrow system | feature/m4-borrow |
| M5 | Redis caching, logging, monitoring | feature/m5-system |

---

## 📝 Notes

- The backend falls back to **SQLite** when no PostgreSQL is configured (local dev)
- Redis is **optional** — the API works without it (caching silently disabled)
- All 52 tests pass without needing Redis or PostgreSQL (uses in-memory SQLite)
