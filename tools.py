from pathlib import Path
import json
import subprocess

from crewai.tools import tool

# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------

IGNORED_NAMES = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "dist",
    "build",
    ".idea",
    ".vscode",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}

MAX_FILE_SIZE = 100_000
MAX_FILE_LIST = 300
MAX_SEARCH_RESULTS = 50
MAX_OUTPUT_CHARS = 20_000
MAX_GIT_DIFF_CHARS = 30_000


# ---------------------------------------------------------
# INTERNAL HELPERS
# ---------------------------------------------------------


def _project_root(project_path: str) -> Path:
    """
    Validate and return the project root.
    """

    root = Path(project_path).expanduser().resolve()

    if not root.exists():
        raise ValueError(f"Project path does not exist: {project_path}")

    if not root.is_dir():
        raise ValueError(f"Project path is not a directory: {project_path}")

    return root


def _safe_path(
    project_path: str,
    relative_path: str,
) -> Path:
    """
    Resolve a file path and make sure it stays
    inside the project directory.
    """

    root = _project_root(project_path)

    target = (root / relative_path).resolve()

    try:
        target.relative_to(root)

    except ValueError:
        raise ValueError(
            "Access denied: requested path is outside " "the project directory."
        )

    return target


def _is_ignored(path: Path) -> bool:
    """
    Return True if any part of the path belongs
    to an ignored directory.
    """

    return any(part in IGNORED_NAMES for part in path.parts)


def _looks_binary(path: Path) -> bool:
    """
    Basic binary-file detection.
    """

    try:
        sample = path.read_bytes()[:1024]

        return b"\x00" in sample

    except OSError:
        return True


# ---------------------------------------------------------
# TOOL 1: LIST PROJECT FILES
# ---------------------------------------------------------


@tool("List Project Files")
def list_project_files(
    project_path: str,
) -> str:
    """
    List useful files inside a software project.

    Args:
        project_path:
            Absolute or relative path to the
            project directory.
    """

    try:
        root = _project_root(project_path)

        files = []

        for path in root.rglob("*"):

            if not path.is_file():
                continue

            relative = path.relative_to(root)

            if _is_ignored(relative):
                continue

            files.append(str(relative))

            if len(files) >= MAX_FILE_LIST:
                break

        if not files:
            return "No useful project files were found."

        result = "\n".join(sorted(files))

        if len(files) >= MAX_FILE_LIST:
            result += (
                f"\n\nFile listing stopped after "
                f"{MAX_FILE_LIST} files to avoid "
                "excessive output."
            )

        return result

    except Exception as error:
        return f"Unable to list project files: {error}"


# ---------------------------------------------------------
# TOOL 2: READ PROJECT FILE
# ---------------------------------------------------------


@tool("Read Project File")
def read_project_file(
    project_path: str,
    file_path: str,
) -> str:
    """
    Read a text source file from inside the project.

    Args:
        project_path:
            Path to the project directory.

        file_path:
            File path relative to the project root.
    """

    try:
        path = _safe_path(
            project_path,
            file_path,
        )

        if not path.exists():
            return f"File does not exist: {file_path}"

        if not path.is_file():
            return f"Path is not a file: {file_path}"

        file_size = path.stat().st_size

        if file_size > MAX_FILE_SIZE:
            return (
                "File is too large to read safely " f"({file_size} bytes): {file_path}"
            )

        if _looks_binary(path):
            return f"Binary file skipped: {file_path}"

        content = path.read_text(
            encoding="utf-8",
            errors="replace",
        )

        numbered_lines = []

        for line_number, line in enumerate(
            content.splitlines(),
            start=1,
        ):
            numbered_lines.append(f"{line_number:4}: {line}")

        result = "\n".join(numbered_lines)

        return result[:MAX_OUTPUT_CHARS]

    except Exception as error:
        return f"Unable to read file: {error}"


# ---------------------------------------------------------
# TOOL 3: SEARCH PROJECT CODE
# ---------------------------------------------------------


@tool("Search Project Code")
def search_project_code(
    project_path: str,
    query: str,
) -> str:
    """
    Search for text across source files
    in a project.

    Args:
        project_path:
            Path to the project directory.

        query:
            Text to search for.
    """

    try:
        if not query.strip():
            return "Search query cannot be empty."

        root = _project_root(project_path)

        matches = []

        for path in root.rglob("*"):

            if not path.is_file():
                continue

            relative = path.relative_to(root)

            if _is_ignored(relative):
                continue

            try:
                if path.stat().st_size > MAX_FILE_SIZE:
                    continue

                if _looks_binary(path):
                    continue

                lines = path.read_text(
                    encoding="utf-8",
                    errors="replace",
                ).splitlines()

            except OSError:
                continue

            for line_number, line in enumerate(
                lines,
                start=1,
            ):

                if query.lower() in line.lower():

                    matches.append(f"{relative}:" f"{line_number}: " f"{line.strip()}")

                    if len(matches) >= MAX_SEARCH_RESULTS:
                        break

            if len(matches) >= MAX_SEARCH_RESULTS:
                break

        if not matches:
            return f'No matches found for "{query}".'

        result = "\n".join(matches)

        if len(matches) >= MAX_SEARCH_RESULTS:
            result += "\n\nSearch stopped after " f"{MAX_SEARCH_RESULTS} matches."

        return result[:MAX_OUTPUT_CHARS]

    except Exception as error:
        return f"Unable to search project: {error}"


# ---------------------------------------------------------
# TOOL 4: DETECT TEST SETUP
# ---------------------------------------------------------


@tool("Detect Project Test Setup")
def detect_test_setup(
    project_path: str,
) -> str:
    """
    Inspect a project and determine how its
    tests are probably executed.

    This tool DOES NOT execute project code.

    Args:
        project_path:
            Path to the project directory.
    """

    try:
        root = _project_root(project_path)

        detected = []

        # -------------------------------------------------
        # PYTHON PROJECT DETECTION
        # -------------------------------------------------

        if (root / "pyproject.toml").exists():
            detected.append("Python project: pyproject.toml found")

        if (root / "pytest.ini").exists():
            detected.append("pytest configuration: pytest.ini found")

        if (root / "tests").is_dir():
            detected.append("Python tests directory: tests/ found")

        if (root / "uv.lock").exists():
            detected.append("uv project detected")

        # -------------------------------------------------
        # PYTEST FILE DETECTION
        # -------------------------------------------------

        pytest_files = []

        for path in root.rglob("test_*.py"):

            if not path.is_file():
                continue

            relative = path.relative_to(root)

            if _is_ignored(relative):
                continue

            pytest_files.append(relative)

        for path in root.rglob("*_test.py"):

            if not path.is_file():
                continue

            relative = path.relative_to(root)

            if _is_ignored(relative):
                continue

            if relative not in pytest_files:
                pytest_files.append(relative)

        pytest_files = sorted(pytest_files)

        if pytest_files:

            visible_files = pytest_files[:20]

            detected.append(
                "Pytest-compatible test files found: "
                + ", ".join(str(path) for path in visible_files)
            )

            if len(pytest_files) > 20:
                detected.append("Additional pytest files: " f"{len(pytest_files) - 20}")

            detected.append("Recommended test type for " "Run Project Tests: python")

        # -------------------------------------------------
        # NODE.JS PROJECT DETECTION
        # -------------------------------------------------

        package_json = root / "package.json"

        if package_json.exists():

            detected.append("Node.js project: package.json found")

            try:
                package_data = json.loads(package_json.read_text(encoding="utf-8"))

                test_script = package_data.get("scripts", {}).get("test")

                if test_script:

                    detected.append(f"npm test script: " f"{test_script}")

                    detected.append(
                        "Recommended test type for " "Run Project Tests: node"
                    )

            except (
                json.JSONDecodeError,
                OSError,
            ):
                detected.append("package.json exists but " "could not be parsed.")

        # -------------------------------------------------
        # NOTHING DETECTED
        # -------------------------------------------------

        if not detected:
            return "No recognized test setup " "was detected."

        return "\n".join(detected)

    except Exception as error:
        return f"Unable to detect test setup: {error}"


# ---------------------------------------------------------
# TOOL 5: RUN PROJECT TESTS
# ---------------------------------------------------------


@tool("Run Project Tests")
def run_project_tests(
    project_path: str,
    test_type: str,
) -> str:
    """
    Run a recognized local test command.

    Supported test_type values:
        python
        node

    Only use this tool on a trusted project.

    Args:
        project_path:
            Path to the project directory.

        test_type:
            Either 'python' or 'node'.
    """

    try:
        root = _project_root(project_path)

        normalized_type = test_type.strip().lower()

        # -------------------------------------------------
        # PYTHON TESTS
        # -------------------------------------------------

        if normalized_type == "python":

            if (root / "uv.lock").exists():

                command = [
                    "uv",
                    "run",
                    "pytest",
                    "-q",
                ]

            else:

                command = [
                    "python",
                    "-m",
                    "pytest",
                    "-q",
                ]

        # -------------------------------------------------
        # NODE TESTS
        # -------------------------------------------------

        elif normalized_type == "node":

            package_json = root / "package.json"

            if not package_json.exists():
                return "Cannot run Node tests: " "package.json not found."

            command = [
                "npm",
                "test",
                "--",
                "--runInBand",
            ]

        else:
            return "Unsupported test type. " "Use 'python' or 'node'."

        # -------------------------------------------------
        # EXECUTE
        # -------------------------------------------------

        completed = subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=90,
            shell=False,
        )

        output = (
            f"Command: {' '.join(command)}\n"
            f"Exit code: "
            f"{completed.returncode}\n\n"
            f"STDOUT:\n"
            f"{completed.stdout}\n\n"
            f"STDERR:\n"
            f"{completed.stderr}"
        )

        return output[:MAX_OUTPUT_CHARS]

    except subprocess.TimeoutExpired:
        return "Test execution stopped because " "it exceeded 90 seconds."

    except FileNotFoundError as error:
        return "Required test command " f"was not found: {error}"

    except Exception as error:
        return f"Unable to run project tests: {error}"


# ---------------------------------------------------------
# GIT HELPERS
# ---------------------------------------------------------


def _git_project_root(
    project_path: str,
) -> Path:
    """
    Validate that the supplied project is a
    Git repository.
    """

    root = _project_root(project_path)

    completed = subprocess.run(
        [
            "git",
            "rev-parse",
            "--is-inside-work-tree",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=15,
        shell=False,
    )

    if completed.returncode != 0 or completed.stdout.strip() != "true":
        raise ValueError("The supplied project is not " "a Git repository.")

    return root


def _run_git(
    project_path: str,
    arguments: list[str],
    timeout: int = 30,
) -> str:
    """
    Run a predefined read-only Git command.
    """

    root = _git_project_root(project_path)

    completed = subprocess.run(
        [
            "git",
            *arguments,
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=False,
    )

    if completed.returncode != 0:

        message = (
            completed.stderr.strip() or completed.stdout.strip() or "Unknown Git error."
        )

        raise RuntimeError(message)

    return completed.stdout.strip()


# ---------------------------------------------------------
# TOOL 6: GET GIT STATUS
# ---------------------------------------------------------


@tool("Get Git Status")
def get_git_status(
    project_path: str,
) -> str:
    """
    Show the current Git working-tree status.

    Useful for detecting modified, staged,
    deleted, renamed, and untracked files.

    This tool is read-only.

    Args:
        project_path:
            Path to the Git repository.
    """

    try:
        output = _run_git(
            project_path,
            [
                "status",
                "--short",
            ],
        )

        if not output:
            return "Git working tree is clean."

        return output[:MAX_OUTPUT_CHARS]

    except Exception as error:
        return f"Unable to read Git status: {error}"


# ---------------------------------------------------------
# TOOL 7: GET LATEST COMMIT
# ---------------------------------------------------------


@tool("Get Latest Git Commit")
def get_latest_git_commit(
    project_path: str,
) -> str:
    """
    Return information about the latest commit.

    This tool is read-only.

    Args:
        project_path:
            Path to the Git repository.
    """

    try:
        output = _run_git(
            project_path,
            [
                "log",
                "-1",
                "--pretty=format:"
                "Commit: %H%n"
                "Author: %an%n"
                "Date: %ad%n"
                "Subject: %s",
                "--date=iso-strict",
            ],
        )

        if not output:
            return "No Git commits were found."

        return output[:MAX_OUTPUT_CHARS]

    except Exception as error:
        return "Unable to read latest " f"Git commit: {error}"


# ---------------------------------------------------------
# TOOL 8: GET GIT CHANGED FILES
# ---------------------------------------------------------


@tool("Get Git Changed Files")
def get_git_changed_files(
    project_path: str,
    review_mode: str,
) -> str:
    """
    Return files changed according to a Git
    review mode.

    Supported review_mode values:

        uncommitted
        latest_commit

    Args:
        project_path:
            Path to the Git repository.

        review_mode:
            Either 'uncommitted'
            or 'latest_commit'.
    """

    try:
        mode = review_mode.strip().lower()

        # -------------------------------------------------
        # UNCOMMITTED
        # -------------------------------------------------

        if mode == "uncommitted":

            tracked_output = _run_git(
                project_path,
                [
                    "diff",
                    "--name-only",
                    "HEAD",
                ],
            )

            untracked_output = _run_git(
                project_path,
                [
                    "ls-files",
                    "--others",
                    "--exclude-standard",
                ],
            )

            changed_files = set()

            if tracked_output:
                changed_files.update(tracked_output.splitlines())

            if untracked_output:
                changed_files.update(untracked_output.splitlines())

            if not changed_files:
                return "No uncommitted changed " "files found."

            return "\n".join(sorted(changed_files))[:MAX_OUTPUT_CHARS]

        # -------------------------------------------------
        # LATEST COMMIT
        # -------------------------------------------------

        if mode == "latest_commit":

            output = _run_git(
                project_path,
                [
                    "diff-tree",
                    "--no-commit-id",
                    "--name-only",
                    "-r",
                    "HEAD",
                ],
            )

            if not output:
                return "No changed files were found " "in the latest commit."

            return output[:MAX_OUTPUT_CHARS]

        return (
            "Unsupported Git review mode. " "Use 'uncommitted' or " "'latest_commit'."
        )

    except Exception as error:
        return "Unable to determine changed " f"files: {error}"


# ---------------------------------------------------------
# TOOL 9: GET GIT DIFF
# ---------------------------------------------------------


@tool("Get Git Diff")
def get_git_diff(
    project_path: str,
    review_mode: str,
) -> str:
    """
    Return source-code differences for a
    Git review mode.

    Supported review_mode values:

        uncommitted
        latest_commit

    This tool is read-only.

    Args:
        project_path:
            Path to the Git repository.

        review_mode:
            Either 'uncommitted'
            or 'latest_commit'.
    """

    try:
        mode = review_mode.strip().lower()

        # -------------------------------------------------
        # UNCOMMITTED
        # -------------------------------------------------

        if mode == "uncommitted":

            output = _run_git(
                project_path,
                [
                    "diff",
                    "--no-ext-diff",
                    "--unified=3",
                    "HEAD",
                ],
            )

            if not output:
                return (
                    "No tracked uncommitted Git diff found. "
                    "Untracked files may still exist and "
                    "should be inspected using "
                    "Get Git Changed Files and "
                    "Read Project File."
                )

            if len(output) > MAX_GIT_DIFF_CHARS:
                return (
                    output[:MAX_GIT_DIFF_CHARS]
                    + "\n\n"
                    + "Git diff truncated because it "
                    + "exceeded "
                    + f"{MAX_GIT_DIFF_CHARS} characters."
                )

            return output

        # -------------------------------------------------
        # LATEST COMMIT
        # -------------------------------------------------

        if mode == "latest_commit":

            root = _git_project_root(project_path)

            parent_check = subprocess.run(
                [
                    "git",
                    "cat-file",
                    "-e",
                    "HEAD^",
                ],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=15,
                shell=False,
            )

            if parent_check.returncode != 0:
                return (
                    "The parent of the latest commit "
                    "is not available locally. "
                    "Clone the repository with Git "
                    "depth 2 or greater to review "
                    "the latest commit diff."
                )

            output = _run_git(
                project_path,
                [
                    "diff",
                    "--no-ext-diff",
                    "--unified=3",
                    "HEAD^",
                    "HEAD",
                ],
            )

            if not output:
                return "No source-code diff was found " "for the latest commit."

            if len(output) > MAX_GIT_DIFF_CHARS:
                return (
                    output[:MAX_GIT_DIFF_CHARS]
                    + "\n\n"
                    + "Git diff truncated because it "
                    + "exceeded "
                    + f"{MAX_GIT_DIFF_CHARS} characters."
                )

            return output

        return (
            "Unsupported Git review mode. " "Use 'uncommitted' or " "'latest_commit'."
        )

    except Exception as error:
        return f"Unable to read Git diff: {error}"


# ---------------------------------------------------------
# TOOL GROUPS
# ---------------------------------------------------------

CODE_TOOLS = [
    list_project_files,
    read_project_file,
    search_project_code,
]


TEST_TOOLS = [
    detect_test_setup,
    run_project_tests,
]


GIT_TOOLS = [
    get_git_status,
    get_latest_git_commit,
    get_git_changed_files,
    get_git_diff,
]
