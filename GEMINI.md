# Gemini CLI Project Mandates

This file defines the foundational mandates and operational workflows for the Gemini CLI within the `auto_agents` project. These instructions take absolute precedence over general defaults.

## Project Context
`auto_agents` is a multi-application project integrating a Scrapy-based crawling system, a FastAPI backend, and multiple React frontends (Admin and Official site).

### Core Architecture
- **platform_core**: Shared infrastructure (logs, DB, storage, exceptions).
- **backend**: FastAPI service layer.
- **scrapy**: Data acquisition layer.
- **frontend**: User interface layer (Admin/Official).

## Engineering Standards

### 1. Development Lifecycle
Follow the **Research -> Strategy -> Execution** cycle for all tasks.
- **Research**: Use `grep_search` and `glob` to map the codebase. Empirical reproduction of bugs is mandatory.
- **Strategy**: Propose a grounded plan before implementation.
- **Execution**: Iterate via **Plan -> Act -> Validate**. Validation includes automated tests and project-specific checks (e.g., `ruff`, `tsc`).

### 2. Code Quality & Consistency
- **Configuration**: Adhere to `Dynaconf` patterns. Never hardcode settings.
- **Logging**: Use `platform_core.infra.log_init`. Ensure critical paths are logged.
- **Types**: Strict TypeScript for frontends; Pydantic/Type hints for Python. No `Any` or type suppression.
- **Idiomatic Updates**: Match existing styles (e.g., SQLAlchemy 2.0+ patterns, Scrapy item loaders).

### 3. Testing & Validation
- **Requirement**: Every bug fix or feature MUST include a verification test.
- **Scrapy**: Test spiders against local HTML samples when possible.
- **Backend**: Use `pytest` for API and service-level testing.

## Security & Integrity
- **Credentials**: Never commit or log secrets. Protect `.env` and `config/*.yml` files.
- **Source Control**: Only stage/commit when explicitly requested. Use `git status && git diff HEAD && git log -n 3` before proposing commits.

## Specialized Workflows

### Creating New Components
When creating new services or spiders, refer to the architectural patterns in `platform_core` and existing examples:
- **FastAPI Services**: Follow the `backend/app/api` and `backend/services` structure.
- **Scrapy Spiders**: Ensure anti-scraping measures are implemented and data is passed through `platform_core` abstractions.

### Tool Usage
- Use `codebase_investigator` for complex architectural analysis.
- Use `generalist` for batch refactoring or high-volume output tasks.
- Prefer parallel tool execution for independent tasks (e.g., reading multiple files).
