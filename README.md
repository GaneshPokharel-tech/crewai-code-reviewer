# CrewAI Code Reviewer

AI-powered multi-agent code review application built with **CrewAI, Streamlit, Git, and Gemini**.

The application reviews either a public GitHub repository or a local Git repository using specialized AI agents for code analysis, bug detection, security review, test assessment, and final review consolidation.

---

## Features

### Multi-Agent Code Review

The application uses five specialized CrewAI agents:

#### 1. Code Analyst
- Understands project structure
- Detects the technology stack
- Identifies important modules and entry points
- Understands execution flow
- Analyzes relevant Git changes

#### 2. Bug Hunter
- Detects runtime errors
- Finds logic problems
- Reviews unsafe assumptions
- Identifies edge cases
- Detects regressions

#### 3. Security Reviewer
- Reviews authentication and authorization
- Checks input validation
- Detects secret exposure
- Reviews unsafe filesystem access
- Identifies API and application security weaknesses

#### 4. Test Engineer
- Detects existing test setup
- Reviews test coverage
- Identifies missing regression tests
- Identifies important edge cases
- Can execute supported tests when explicitly enabled

#### 5. Senior Code Reviewer
- Consolidates findings from all agents
- Removes duplicate findings
- Rejects unsupported claims
- Normalizes severity levels
- Generates the final code review report

---

## Review Sources

The application supports two repository sources.

### GitHub Repository

Provide a public GitHub repository URL:

```text
https://github.com/owner/repository
```

Supported modes:

- Full Repository
- Latest Commit

GitHub repositories are cloned into a temporary workspace and automatically removed after the review completes.

### Local Repository

Provide the absolute path of a local Git repository:

```text
/Users/username/projects/my-project
```

Supported modes:

- Full Repository
- Latest Commit
- Uncommitted Changes

The application reviews the local repository directly.

It does not automatically commit, push, reset, or modify repository files.

---

## Review Modes

### Full Repository

Reviews the repository as a whole.

Useful for:

- Initial repository audits
- Understanding unfamiliar codebases
- General bug review
- Security review
- Test coverage assessment

### Latest Commit

Reviews the latest Git commit and its impact.

The agents inspect:

- Latest commit metadata
- Changed files
- Git diff
- Relevant surrounding source code
- Potential regressions
- Security impact
- Missing tests

For GitHub repositories, the application clones enough Git history to compare the latest commit with its parent.

### Uncommitted Changes

Available for local repositories.

Reviews:

- Staged changes
- Unstaged changes
- Untracked files
- Git diff
- Changed source code

This mode is useful before committing changes.

---

## AI Model

The current version uses:

```text
Gemini 3.5 Flash Lite
```

All five CrewAI agents use Gemini.

The application uses conservative request throttling to reduce the chance of exceeding free-tier API limits.

---

## Custom Tools

Custom tools are defined in `tools.py`.

### Code Tools

- List repository files
- Read source files
- Search repository code

### Git Tools

- Get Git status
- Get latest Git commit
- Detect changed files
- Read Git diff

The Git inspection tools are read-only.

### Test Tools

- Detect Python test setup
- Detect Node.js test setup
- Run Python tests with pytest
- Run Node.js tests with npm

Test execution is disabled by default.

---

## Test Execution Safety

Running repository tests may execute arbitrary code from the selected repository.

For this reason:

```text
Run repository tests = OFF
```

by default.

The user must explicitly enable test execution and confirm the warning before tests can run.

Only enable test execution for repositories you trust.

---

## Architecture

```text
Repository
    |
    v
Code Analyst
    |
    v
Bug Hunter
    |
    v
Security Reviewer
    |
    v
Test Engineer
    |
    v
Senior Code Reviewer
    |
    v
Final Markdown Review
```

CrewAI runs the agents sequentially.

Each reviewer receives context from earlier stages of the review.

---

## Project Structure

```text
crewai-code-reviewer/
├── main.py
├── crew.py
├── tools.py
├── pyproject.toml
├── uv.lock
├── .python-version
├── .gitignore
├── .env
└── README.md
```

### `main.py`

Streamlit application responsible for:

- User interface
- GitHub URL validation
- Local repository validation
- Repository cloning
- Review source selection
- Review mode selection
- Optional test execution
- Crew execution
- Error handling
- Final report display
- Markdown report download

### `crew.py`

Defines:

- Gemini model configuration
- Five CrewAI agents
- Review-mode instructions
- Agent tasks
- Sequential Crew workflow

### `tools.py`

Defines:

- Repository file tools
- Source-code search tools
- Git inspection tools
- Test setup detection
- Test execution

---

## Requirements

- Python 3.12
- Git
- uv
- Gemini API key

---

## Installation

Clone the repository:

```bash
git clone https://github.com/YOUR_USERNAME/crewai-code-reviewer.git
cd crewai-code-reviewer
```

Install dependencies:

```bash
uv sync
```

---

## Environment Variables

Create a `.env` file in the project root:

```env
GEMINI_API_KEY=your_gemini_api_key_here
```

Do not commit `.env`.

The project `.gitignore` excludes environment secrets.

---

## Run the Application

Start Streamlit:

```bash
uv run streamlit run main.py
```

Streamlit will show a local URL, usually:

```text
http://localhost:8501
```

Open that URL in your browser.

---

## Example: GitHub Repository Review

Select:

```text
Review Source:
GitHub Repository
```

Enter:

```text
https://github.com/owner/repository
```

Choose either:

```text
Full Repository
```

or:

```text
Latest Commit
```

Then click:

```text
Review Repository
```

---

## Example: Local Uncommitted Review

Select:

```text
Review Source:
Local Repository
```

Enter:

```text
/Users/username/projects/my-project
```

Choose:

```text
Uncommitted Changes
```

Then click:

```text
Review Repository
```

The agents will focus on the current Git working-tree changes.

---

## Final Review Report

The Senior Code Reviewer produces a Markdown report containing:

- Review Scope
- Project Overview
- Review Summary
- Findings
- Testing
- Positive Observations
- Recommended Fix Order

Each meaningful finding may contain:

- Severity
- Category
- File or location
- Problem
- Evidence
- Impact
- Recommended fix

The final report can be downloaded directly from the Streamlit interface.

---

## Rate Limiting

The Crew currently uses:

```python
max_rpm=4
```

This is intentionally conservative for Gemini free-tier usage.

During a review, CrewAI may display:

```text
Max RPM reached, waiting for next minute to start.
```

This is expected throttling behavior and does not necessarily indicate a failure.

---

## Security Controls

The application includes several safety controls:

- GitHub repository URLs are validated
- Embedded credentials in URLs are rejected
- Repository file access is restricted to the selected project root
- Path traversal outside the repository is blocked
- Large files are limited
- Binary files are skipped
- Common generated directories are ignored
- Git inspection commands are read-only
- Subprocess commands use `shell=False`
- Test execution requires explicit user confirmation
- Temporary GitHub clones are deleted after review

---

## Current Limitations

### GitHub

Currently supports:

- Public GitHub repositories

Not yet implemented:

- Private repository authentication
- Pull-request-specific review
- Branch selection
- Commit-range comparison
- GitHub inline review comments

### Testing

Automatic execution currently focuses on:

- Python projects using pytest
- Node.js projects using an npm test script

Other ecosystems are not automatically executed yet.

### AI Review

AI-generated findings should be treated as engineering assistance.

Developers should verify important findings before making production, security, or deployment decisions.

---

## Technology Stack

- Python 3.12
- CrewAI
- Streamlit
- Gemini
- Git
- uv

---

## Development Commands

Syntax check:

```bash
uv run python -m py_compile main.py crew.py tools.py
```

Check repository status:

```bash
git status
```

Check diff formatting:

```bash
git diff --check
```

Run the application:

```bash
uv run streamlit run main.py
```

---

## Future Improvements

Potential future additions:

- Pull request review
- Branch comparison
- Commit-range review
- Private GitHub repository support
- GitHub authentication
- Inline review comments
- Structured JSON findings
- Review history
- More test frameworks
- CI/CD integration
- Automated pull-request checks

---

## Disclaimer

This project is an AI-assisted software engineering tool.

Generated findings should be verified by developers before applying production changes or making security-sensitive decisions.

---

## License

A license has not yet been selected.
