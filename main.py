import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import streamlit as st

from crew import build_code_review_crew
from tools import CODE_TOOLS, TEST_TOOLS

# ---------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------

st.set_page_config(
    page_title="CrewAI Code Reviewer",
    page_icon="🔍",
    layout="wide",
)


# ---------------------------------------------------------
# SESSION STATE
# ---------------------------------------------------------

if "report" not in st.session_state:
    st.session_state.report = None

if "repo_name" not in st.session_state:
    st.session_state.repo_name = None


# ---------------------------------------------------------
# URL HELPERS
# ---------------------------------------------------------


def normalize_github_url(repo_url: str) -> str:
    """
    Remove query parameters and fragments from a GitHub URL.

    Example:

        https://github.com/user/repo?utm_source=test

    becomes:

        https://github.com/user/repo
    """

    parsed = urlparse(repo_url.strip())

    clean_url = f"{parsed.scheme}://" f"{parsed.netloc}" f"{parsed.path}"

    return clean_url.rstrip("/")


def validate_github_url(
    repo_url: str,
) -> tuple[bool, str]:
    """
    Validate a public GitHub repository URL.

    Supported examples:

        https://github.com/owner/repository

        https://github.com/owner/repository.git

        https://github.com/owner/repository?utm_source=test
    """

    repo_url = repo_url.strip()

    if not repo_url:
        return (
            False,
            "GitHub repository URL is required.",
        )

    try:
        clean_url = normalize_github_url(repo_url)

        parsed = urlparse(clean_url)

        if parsed.scheme != "https":
            return (
                False,
                "Only HTTPS GitHub repository URLs are supported.",
            )

        if parsed.netloc.lower() != "github.com":
            return (
                False,
                "Currently only github.com repositories are supported.",
            )

        # Prevent credentials inside URL
        if parsed.username or parsed.password:
            return (
                False,
                "Repository URL must not contain credentials.",
            )

        parts = [part for part in parsed.path.split("/") if part]

        if len(parts) != 2:
            return (
                False,
                "Use the repository root URL. Example: "
                "https://github.com/owner/repository",
            )

        owner = parts[0]
        repo = parts[1]

        if repo.endswith(".git"):
            repo = repo[:-4]

        if not owner or not repo:
            return (
                False,
                "Invalid GitHub repository URL.",
            )

        return True, ""

    except Exception:
        return (
            False,
            "Invalid GitHub repository URL.",
        )


def get_repo_name(repo_url: str) -> str:
    """
    Extract repository name from GitHub URL.
    """

    clean_url = normalize_github_url(repo_url)

    path = urlparse(clean_url).path.rstrip("/")

    repo_name = path.split("/")[-1]

    if repo_name.endswith(".git"):
        repo_name = repo_name[:-4]

    return repo_name


# ---------------------------------------------------------
# GIT CLONE
# ---------------------------------------------------------


def clone_repository(
    repo_url: str,
    destination: Path,
) -> None:
    """
    Clone a public GitHub repository.

    Uses a shallow clone because the current reviewer
    analyzes the latest repository state rather than
    the entire Git history.
    """

    command = [
        "git",
        "clone",
        "--depth",
        "1",
        "--no-tags",
        repo_url,
        str(destination),
    ]

    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=120,
        shell=False,
    )

    if completed.returncode != 0:
        message = (
            completed.stderr.strip()
            or completed.stdout.strip()
            or "Unknown Git clone error."
        )

        raise RuntimeError(message)


# ---------------------------------------------------------
# ERROR HANDLING
# ---------------------------------------------------------


def format_review_error(
    error: Exception,
) -> str:
    """
    Convert common errors into readable UI messages.
    """

    message = str(error)

    if (
        "429" in message
        or "RESOURCE_EXHAUSTED" in message
        or "quota" in message.lower()
    ):
        return (
            "Gemini free-tier rate limit was reached. "
            "Try again after the quota resets."
        )

    if "503" in message or "UNAVAILABLE" in message or "high demand" in message.lower():
        return (
            "Gemini is temporarily experiencing high demand. "
            "Try the review again later."
        )

    if "repository not found" in message.lower() or "not found" in message.lower():
        return (
            "GitHub repository could not be found. "
            "Check that the repository exists and is public."
        )

    if (
        "authentication failed" in message.lower()
        or "could not read username" in message.lower()
    ):
        return (
            "Repository access failed. "
            "Currently only public GitHub repositories are supported."
        )

    return f"Review failed: {message}"


# ---------------------------------------------------------
# CREWAI REVIEW
# ---------------------------------------------------------


def run_code_review(
    project_path: Path,
    run_tests: bool,
) -> str:
    """
    Build the CrewAI crew and review the repository.
    """

    if run_tests:
        test_tools = TEST_TOOLS
    else:
        test_tools = []

    crew = build_code_review_crew(
        code_tools=CODE_TOOLS,
        test_tools=test_tools,
    )

    result = crew.kickoff(
        inputs={
            "project_path": str(project_path),
        }
    )

    if hasattr(result, "raw"):
        return result.raw

    return str(result)


# ---------------------------------------------------------
# HEADER
# ---------------------------------------------------------

st.title("CrewAI Code Reviewer")

st.markdown("""
Paste a **public GitHub repository URL** and let a team of
specialized CrewAI agents review the codebase.
""")


# ---------------------------------------------------------
# CAPABILITIES
# ---------------------------------------------------------

with st.expander(
    "What can this reviewer do?",
    expanded=False,
):

    col1, col2 = st.columns(2)

    with col1:

        st.markdown("""
### Code Analyst
- Understand project structure
- Detect technology stack
- Identify important modules
- Understand execution flow

### Bug Hunter
- Find runtime errors
- Detect logic problems
- Identify edge cases
- Review error handling

### Security Reviewer
- Authentication issues
- Input validation
- Secret handling
- Unsafe file access
- Security weaknesses
""")

    with col2:

        st.markdown("""
### Test Engineer
- Detect existing tests
- Inspect test coverage
- Find missing tests
- Run tests when enabled

### Senior Reviewer
- Combine findings
- Remove duplicates
- Prioritize issues
- Generate final report

### Current Tools
- List repository files
- Read source files
- Search code
- Detect test setup
- Run Python/Node tests
""")


# ---------------------------------------------------------
# REPOSITORY INPUT
# ---------------------------------------------------------

st.divider()

st.subheader("Repository")

repo_url = st.text_input(
    "GitHub Repository URL",
    placeholder="https://github.com/owner/repository",
    help=(
        "Currently supports public GitHub repositories. "
        "Tracking parameters in the URL are removed automatically."
    ),
)


# ---------------------------------------------------------
# REVIEW OPTIONS
# ---------------------------------------------------------

st.subheader("Review Options")

run_tests = st.checkbox(
    "Run repository tests",
    value=False,
    help=(
        "When enabled, the Test Engineer may execute " "the repository's test suite."
    ),
)


confirmed_test_execution = False

if run_tests:

    st.warning(
        "Running tests executes code from the cloned repository "
        "on your computer. Only enable this for repositories you trust."
    )

    confirmed_test_execution = st.checkbox(
        "I understand that repository code may be executed."
    )


# ---------------------------------------------------------
# REVIEW BUTTON
# ---------------------------------------------------------

st.divider()

review_clicked = st.button(
    "Review Repository",
    type="primary",
    width="stretch",
)


# ---------------------------------------------------------
# REVIEW EXECUTION
# ---------------------------------------------------------

if review_clicked:

    # Clear previous result
    st.session_state.report = None
    st.session_state.repo_name = None

    # -----------------------------------------------------
    # NORMALIZE URL
    # -----------------------------------------------------

    clean_repo_url = normalize_github_url(repo_url)

    # -----------------------------------------------------
    # VALIDATE URL
    # -----------------------------------------------------

    valid, validation_error = validate_github_url(clean_repo_url)

    if not valid:
        st.error(validation_error)
        st.stop()

    # -----------------------------------------------------
    # TEST EXECUTION CONFIRMATION
    # -----------------------------------------------------

    if run_tests and not confirmed_test_execution:
        st.error(
            "Please confirm that you understand " "repository code will be executed."
        )

        st.stop()

    # -----------------------------------------------------
    # PREPARE TEMP WORKSPACE
    # -----------------------------------------------------

    repo_name = get_repo_name(clean_repo_url)

    workspace = Path(tempfile.mkdtemp(prefix="crewai_code_review_"))

    project_path = workspace / repo_name

    try:

        # -------------------------------------------------
        # CLONE REPOSITORY
        # -------------------------------------------------

        with st.status(
            "Preparing repository...",
            expanded=True,
        ) as status:

            st.write(f"Cloning `{repo_name}`...")

            clone_repository(
                clean_repo_url,
                project_path,
            )

            st.write("Repository cloned successfully.")

            if run_tests:

                st.write("Test execution: **Enabled**")

            else:

                st.write("Test execution: **Disabled**")

            status.update(
                label="Repository ready",
                state="complete",
            )

        # -------------------------------------------------
        # RUN CREWAI
        # -------------------------------------------------

        st.info("CrewAI agents are reviewing the repository.")

        with st.spinner("Running multi-agent code review..."):

            report = run_code_review(
                project_path=project_path,
                run_tests=run_tests,
            )

        # -------------------------------------------------
        # STORE RESULT
        # -------------------------------------------------

        st.session_state.report = report
        st.session_state.repo_name = repo_name

        st.success("Repository review completed successfully.")

    # -----------------------------------------------------
    # ERROR HANDLING
    # -----------------------------------------------------

    except subprocess.TimeoutExpired:

        st.error("Repository cloning timed out.")

    except FileNotFoundError:

        st.error("Git could not be found on this machine.")

    except Exception as error:

        st.error(format_review_error(error))

    # -----------------------------------------------------
    # CLEANUP
    # -----------------------------------------------------

    finally:

        shutil.rmtree(
            workspace,
            ignore_errors=True,
        )


# ---------------------------------------------------------
# DISPLAY FINAL REPORT
# ---------------------------------------------------------

if st.session_state.report:

    st.divider()

    st.subheader("Code Review Report")

    st.markdown(st.session_state.report)

    # -----------------------------------------------------
    # DOWNLOAD REPORT
    # -----------------------------------------------------

    report_filename = f"{st.session_state.repo_name}" "_code_review.md"

    st.download_button(
        label="Download Review Report",
        data=st.session_state.report,
        file_name=report_filename,
        mime="text/markdown",
        width="stretch",
    )
