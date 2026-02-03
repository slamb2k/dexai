# Phase 9: CI/CD & Testing

**Status:** ✅ Complete
**Prerequisites:** All previous phases complete
**Objective:** Ensure code quality and prevent regressions through automated testing and continuous integration

---

## Overview

Phase 9 adds comprehensive testing infrastructure and continuous integration to DexAI. This ensures:

1. **Quality Gates** — Every PR must pass lint, type check, and tests
2. **Regression Prevention** — Automated tests catch bugs before merge
3. **Documentation** — Tests serve as executable documentation
4. **Confidence** — Safe refactoring with test coverage

---

## Success Criteria

| Criteria | Target | Verification |
|----------|--------|--------------|
| Lint passes | 0 errors | `uv run ruff check .` |
| Type check passes | 0 errors | `uv run mypy tools/` |
| Unit tests pass | 100% | `uv run pytest` |
| Coverage (critical paths) | >80% | `uv run pytest --cov` |
| CI runs on PRs | Yes | GitHub Actions status |
| Frontend lint/build | Passes | `npm run lint && npm run build` |

---

## Components

### 1. Python Project Configuration

**File:** `pyproject.toml`

Defines:
- Project metadata (name, version, description)
- Dependencies (runtime + dev)
- Tool configurations (pytest, ruff, mypy)

**Key Settings:**
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.ruff]
target-version = "py311"
line-length = 100

[tool.mypy]
python_version = "3.11"
warn_return_any = true
```

### 2. GitHub Actions CI

**File:** `.github/workflows/ci.yml`

**Jobs:**

| Job | Purpose | Triggers |
|-----|---------|----------|
| lint | Ruff check + format | push, PR |
| typecheck | mypy on tools/ | push, PR |
| test | pytest on Python 3.11/3.12 | push, PR |
| frontend | npm lint + build | push, PR |

**Matrix Strategy:** Test on Python 3.11 and 3.12

### 3. Test Infrastructure

**Directory Structure:**
```
tests/
├── __init__.py
├── conftest.py           # Shared fixtures
├── unit/
│   ├── __init__.py
│   ├── security/         # Security tool tests
│   ├── adhd/             # ADHD communication tests
│   ├── tasks/            # Task engine tests
│   └── memory/           # Memory tool tests
└── integration/          # (Future) End-to-end tests
```

**Key Fixtures:**
- `temp_db` — Temporary SQLite database for isolation
- `mock_user_id` — Standard test user
- `sample_task` — Sample task data

### 4. Test Priorities

| Priority | Module | Rationale |
|----------|--------|-----------|
| P0 | security/ | Prevents vulnerabilities |
| P0 | adhd/language_filter | Core ADHD-safe feature |
| P1 | tasks/manager | Task CRUD is heavily used |
| P1 | adhd/response_formatter | Communication layer |
| P2 | memory/commitments | Important for relationships |
| P2 | security/audit | Compliance requirement |

### 5. Frontend Testing

**Files:**
- `frontend/vitest.config.ts` — Test configuration
- `frontend/__tests__/` — Component tests

**Approach:**
- Vitest for fast unit tests
- React Testing Library for component testing
- Focus on critical UI components (DexAvatar, StatCard)

---

## Implementation Checklist

### Infrastructure
- [ ] Create `pyproject.toml` with all dependencies
- [ ] Create `.github/workflows/ci.yml`
- [ ] Create `tests/` directory structure
- [ ] Create `tests/conftest.py` with fixtures
- [ ] Update `.gitignore` for test artifacts

### Security Tests
- [ ] `test_sanitizer.py` — Input validation, injection detection
- [ ] `test_audit.py` — Event logging, query, retention
- [ ] `test_permissions.py` — RBAC role checking

### ADHD Tests
- [ ] `test_language_filter.py` — RSD phrase detection, reframing
- [ ] `test_response_formatter.py` — Brevity, one-thing mode

### Task Tests
- [ ] `test_manager.py` — Task CRUD, step management

### Memory Tests
- [ ] `test_commitments.py` — Commitment tracking, due dates

### Frontend Tests
- [ ] Configure Vitest
- [ ] `test_stat-card.tsx` — Metric display
- [ ] `test_dex-avatar.tsx` — Avatar states

### Documentation
- [ ] Update `goals/manifest.md`
- [ ] Update `tools/manifest.md`
- [ ] Update PRD with Phase 9

---

## Verification Commands

```bash
# Install dev dependencies
uv sync --dev

# Run linter
uv run ruff check .
uv run ruff format --check .

# Run type checker
uv run mypy tools/

# Run tests with coverage
uv run pytest -v --cov=tools --cov-report=term-missing

# Frontend tests
cd tools/dashboard/frontend
npm test
```

---

## Git Workflow

**Branch:** `feature/phase9-ci-testing`

**Commit Sequence:**
1. `feat(ci): add pyproject.toml with dev dependencies`
2. `feat(ci): add GitHub Actions workflow`
3. `test(security): add sanitizer and audit tests`
4. `test(adhd): add language filter tests`
5. `test(tasks): add task manager tests`
6. `test(memory): add commitment tests`
7. `test(frontend): add Vitest configuration`
8. `docs(phase9): add goal specification`

---

## Notes

### Why These Tests Matter for ADHD Users

1. **Security tests** — Protect user data and prevent exploitation
2. **Language filter tests** — Ensure RSD-safe communication (critical for emotional safety)
3. **Task manager tests** — Reliable task tracking reduces anxiety
4. **Commitment tests** — Prevents relationship damage from forgotten promises

### Future Improvements

- Integration tests for API endpoints
- E2E tests with Playwright
- Performance benchmarks
- Coverage badges in README

---

*This specification is part of the DexAI GOTCHA framework. See `CLAUDE.md` for operational guidelines.*
