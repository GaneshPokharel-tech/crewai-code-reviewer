import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import streamlit as st

from crew import build_code_review_crew
from tools import CODE_TOOLS, GIT_TOOLS, TEST_TOOLS

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

if "review_mode_label" not in st.session_state:
    st.session_state.review_mode_label = None

if "review_source_label" not in st.session_state:
    st.session_state.review_source_label = None


# ---------------------------------------------------------
# GITHUB URL HELPERS
# ---------------------------------------------------------


def normalize_github_url(
    repo_url: str,
) -> str:
    """
    Remove query parameters and fragments
    from a GitHub repository URL.
    """

    parsed = urlparse(repo_url.strip())

    clean_url = f"{parsed.scheme}://" f"{parsed.netloc}" f"{parsed.path}"

    return clean_url.rstrip("/")


def validate_github_url(
    repo_url: str,
) -> tuple[bool, str]:
    """
    Validate a public GitHub repository URL.
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


def get_repo_name(
    repo_url: str,
) -> str:
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
# LOCAL REPOSITORY VALIDATION
# ---------------------------------------------------------


def validate_local_repository(
    local_path: str,
) -> tuple[bool, str, Path | None]:
    """
    Validate a local Git repository path.

    The path refers to the machine where
    Streamlit is running.
    """

    if not local_path.strip():
        return (
            False,
            "Local repository path is required.",
            None,
        )

    try:
        project_path = Path(local_path).expanduser().resolve()

    except Exception:
        return (
            False,
            "Invalid local repository path.",
            None,
        )

    if not project_path.exists():
        return (
            False,
            "Local repository path does not exist.",
            None,
        )

    if not project_path.is_dir():
        return (
            False,
            "Local repository path must be a directory.",
            None,
        )

    try:
        completed = subprocess.run(
            [
                "git",
                "rev-parse",
                "--is-inside-work-tree",
            ],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=15,
            shell=False,
        )

    except FileNotFoundError:
        return (
            False,
            "Git could not be found on this machine.",
            None,
        )

    except subprocess.TimeoutExpired:
        return (
            False,
            "Git repository validation timed out.",
            None,
        )

    if completed.returncode != 0 or completed.stdout.strip() != "true":
        return (
            False,
            "The selected folder is not a Git repository.",
            None,
        )

    return (
        True,
        "",
        project_path,
    )


# ---------------------------------------------------------
# REVIEW MODE
# ---------------------------------------------------------


def get_internal_review_mode(
    selected_mode: str,
) -> str:
    """
    Convert UI review mode into the value
    expected by crew.py.
    """

    mapping = {
        "Full Repository": "full_repository",
        "Latest Commit": "latest_commit",
        "Uncommitted Changes": "uncommitted",
    }

    return mapping[selected_mode]


# ---------------------------------------------------------
# GITHUB CLONE
# ---------------------------------------------------------


def clone_repository(
    repo_url: str,
    destination: Path,
    review_mode: str,
) -> None:
    """
    Clone a public GitHub repository.

    Full Repository:
        depth 1

    Latest Commit:
        depth 2 so HEAD^ is available
        for the latest commit diff.
    """

    clone_depth = "2" if review_mode == "latest_commit" else "1"

    command = [
        "git",
        "clone",
        "--depth",
        clone_depth,
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
    Convert common errors into readable
    Streamlit UI messages.
    """

    message = str(error)

    lower_message = message.lower()

    # -----------------------------------------------------
    # GEMINI FREE-TIER QUOTA
    # -----------------------------------------------------

    if (
        "429" in message
        or "resource_exhausted" in lower_message
        or "quota" in lower_message
    ):
        return (
            "Gemini free-tier rate limit was reached. "
            "Wait for the quota window to reset and try again."
        )

    # -----------------------------------------------------
    # GEMINI TEMPORARY AVAILABILITY
    # -----------------------------------------------------

    if (
        "503" in message
        or "unavailable" in lower_message
        or "high demand" in lower_message
    ):
        return (
            "Gemini is temporarily unavailable or experiencing "
            "high demand. Try the review again later."
        )

    # -----------------------------------------------------
    # GITHUB REPOSITORY NOT FOUND
    # -----------------------------------------------------

    if "repository not found" in lower_message:
        return (
            "GitHub repository could not be found. "
            "Check that the repository exists and is public."
        )

    # -----------------------------------------------------
    # PRIVATE / AUTHENTICATED REPOSITORY
    # -----------------------------------------------------

    if (
        "authentication failed" in lower_message
        or "could not read username" in lower_message
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
    review_mode: str,
) -> str:
    """
    Build and execute the CrewAI review.
    """

    # Test execution tools are only exposed
    # when the user explicitly enables them.
    test_tools = TEST_TOOLS if run_tests else []

    # Git tools are needed only for
    # Latest Commit or Uncommitted Changes.
    git_tools = GIT_TOOLS if review_mode != "full_repository" else []

    crew = build_code_review_crew(
        code_tools=CODE_TOOLS,
        test_tools=test_tools,
        git_tools=git_tools,
        review_mode=review_mode,
    )

    result = crew.kickoff(
        inputs={
            "project_path": str(project_path),
        }
    )

    if hasattr(
        result,
        "raw",
    ):
        return result.raw

    return str(result)


# ---------------------------------------------------------
# HEADER
# ---------------------------------------------------------

st.title("CrewAI Code Reviewer")

st.markdown("""
Review a **public GitHub repository** or a **local Git repository**
using specialized CrewAI agents powered by Gemini.
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
- Analyze relevant Git changes

### Bug Hunter
- Find runtime errors
- Detect logic problems
- Identify edge cases
- Review error handling
- Detect regressions
""")

        st.markdown("""
### Security Reviewer
- Authentication issues
- Authorization problems
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
- Find missing regression tests
- Identify important edge cases
- Run tests when explicitly enabled

### Senior Reviewer
- Combine agent findings
- Remove duplicates
- Reject unsupported claims
- Normalize severity
- Generate final report
""")

        st.markdown("""
### Git Capabilities
- Inspect Git status
- Inspect latest commit
- Detect changed files
- Analyze Git diff
- Review uncommitted changes
""")


# ---------------------------------------------------------
# REVIEW SOURCE
# ---------------------------------------------------------

st.divider()

st.subheader("Review Source")

selected_source = st.radio(
    "Choose where the repository comes from",
    options=[
        "GitHub Repository",
        "Local Repository",
    ],
    horizontal=True,
)


# ---------------------------------------------------------
# REPOSITORY INPUT
# ---------------------------------------------------------

st.subheader("Repository")

repo_url = ""
local_repo_path = ""


if selected_source == "GitHub Repository":

    repo_url = st.text_input(
        "GitHub Repository URL",
        placeholder=("https://github.com/owner/repository"),
        help=(
            "Currently supports public GitHub repositories. "
            "Query parameters and URL fragments are removed "
            "automatically."
        ),
    )


else:

    local_repo_path = st.text_input(
        "Local Repository Path",
        placeholder=("/Users/ganesh/projects/my-project"),
        help=("The path must exist on the machine " "where Streamlit is running."),
    )

    st.caption(
        "The local repository is reviewed directly. "
        "The application does not copy, modify, commit, "
        "or push repository files."
    )


# ---------------------------------------------------------
# REVIEW MODE
# ---------------------------------------------------------

st.subheader("Review Mode")


if selected_source == "GitHub Repository":

    review_mode_options = [
        "Full Repository",
        "Latest Commit",
    ]

else:

    review_mode_options = [
        "Full Repository",
        "Latest Commit",
        "Uncommitted Changes",
    ]


selected_review_mode = st.radio(
    "Choose what you want the agents to review",
    options=review_mode_options,
    horizontal=True,
)


review_mode = get_internal_review_mode(selected_review_mode)


# ---------------------------------------------------------
# REVIEW MODE DESCRIPTION
# ---------------------------------------------------------

if selected_review_mode == "Full Repository":

    st.caption("Reviews the repository as a whole.")


elif selected_review_mode == "Latest Commit":

    st.caption(
        "Reviews files changed in the latest commit "
        "and compares the commit against its parent."
    )


elif selected_review_mode == "Uncommitted Changes":

    st.caption(
        "Reviews staged, unstaged, and untracked local "
        "changes that have not yet been committed."
    )


# ---------------------------------------------------------
# MODEL INFO
# ---------------------------------------------------------

st.subheader("AI Model")

st.info("All review agents use Gemini 3.5 Flash Lite.")


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
        "Running tests executes code from the selected "
        "repository on the machine running Streamlit. "
        "Only enable this for repositories you trust."
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

    # Clear the previous result.
    st.session_state.report = None
    st.session_state.repo_name = None
    st.session_state.review_mode_label = None
    st.session_state.review_source_label = None

    # -----------------------------------------------------
    # TEST EXECUTION CONFIRMATION
    # -----------------------------------------------------

    if run_tests and not confirmed_test_execution:

        st.error(
            "Please confirm that you understand " "repository code may be executed."
        )

        st.stop()

    # -----------------------------------------------------
    # WORKSPACE VARIABLES
    # -----------------------------------------------------

    workspace = None
    project_path = None
    repo_name = None

    try:

        # =================================================
        # GITHUB REPOSITORY
        # =================================================

        if selected_source == "GitHub Repository":

            clean_repo_url = normalize_github_url(repo_url)

            valid, validation_error = validate_github_url(clean_repo_url)

            if not valid:

                st.error(validation_error)

                st.stop()

            repo_name = get_repo_name(clean_repo_url)

            workspace = Path(tempfile.mkdtemp(prefix="crewai_code_review_"))

            project_path = workspace / repo_name

            with st.status(
                "Preparing repository...",
                expanded=True,
            ) as status:

                st.write(f"Cloning `{repo_name}`...")

                st.write("Source: **GitHub Repository**")

                st.write(f"Review mode: " f"**{selected_review_mode}**")

                st.write("AI model: " "**Gemini 3.5 Flash Lite**")

                clone_repository(
                    repo_url=clean_repo_url,
                    destination=project_path,
                    review_mode=review_mode,
                )

                st.write("Repository cloned successfully.")

                if review_mode == "latest_commit":

                    st.write("Git history depth: " "**2 commits**")

                st.write(
                    "Test execution: "
                    + ("**Enabled**" if run_tests else "**Disabled**")
                )

                status.update(
                    label="Repository ready",
                    state="complete",
                )

        # =================================================
        # LOCAL REPOSITORY
        # =================================================

        else:

            (
                valid,
                validation_error,
                validated_path,
            ) = validate_local_repository(local_repo_path)

            if not valid:

                st.error(validation_error)

                st.stop()

            project_path = validated_path

            repo_name = project_path.name

            with st.status(
                "Preparing repository...",
                expanded=True,
            ) as status:

                st.write(f"Using local repository " f"`{repo_name}`...")

                st.write("Source: **Local Repository**")

                st.write(f"Review mode: " f"**{selected_review_mode}**")

                st.write("AI model: " "**Gemini 3.5 Flash Lite**")

                st.write("Local repository validated successfully.")

                if review_mode == "uncommitted":

                    st.write("Git working-tree changes " "will be inspected.")

                st.write(
                    "Test execution: "
                    + ("**Enabled**" if run_tests else "**Disabled**")
                )

                status.update(
                    label="Repository ready",
                    state="complete",
                )

        # -------------------------------------------------
        # RUN CREWAI REVIEW
        # -------------------------------------------------

        st.info(
            f"CrewAI agents are running a " f"{selected_review_mode.lower()} review."
        )

        with st.spinner("Running multi-agent code review..."):

            report = run_code_review(
                project_path=project_path,
                run_tests=run_tests,
                review_mode=review_mode,
            )

        # -------------------------------------------------
        # STORE RESULT
        # -------------------------------------------------

        st.session_state.report = report

        st.session_state.repo_name = repo_name

        st.session_state.review_mode_label = selected_review_mode

        st.session_state.review_source_label = selected_source

        st.success("Repository review completed successfully.")

    # -----------------------------------------------------
    # ERROR HANDLING
    # -----------------------------------------------------

    except subprocess.TimeoutExpired:

        st.error("Git operation timed out.")

    except FileNotFoundError:

        st.error("A required command could not be found " "on this machine.")

    except Exception as error:

        st.error(format_review_error(error))

    # -----------------------------------------------------
    # CLEANUP
    # -----------------------------------------------------

    finally:

        # Only GitHub repositories use a temporary
        # clone workspace.
        #
        # Never remove the user's local repository.
        if workspace is not None:

            shutil.rmtree(
                workspace,
                ignore_errors=True,
            )


# ---------------------------------------------------------
# FINAL REPORT
# ---------------------------------------------------------

if st.session_state.report:

    st.divider()

    st.subheader("Code Review Report")

    metadata_col1, metadata_col2 = st.columns(2)

    with metadata_col1:

        st.caption("Source: " f"{st.session_state.review_source_label}")

    with metadata_col2:

        st.caption("Review mode: " f"{st.session_state.review_mode_label}")

    st.markdown(st.session_state.report)

    # -----------------------------------------------------
    # DOWNLOAD REPORT
    # -----------------------------------------------------

    mode_suffix = st.session_state.review_mode_label.lower().replace(
        " ",
        "_",
    )

    report_filename = f"{st.session_state.repo_name}_" f"{mode_suffix}_review.md"

    st.download_button(
        label="Download Review Report",
        data=st.session_state.report,
        file_name=report_filename,
        mime="text/markdown",
        width="stretch",
    )
