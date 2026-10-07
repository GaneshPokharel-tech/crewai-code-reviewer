from crewai import Agent, Crew, LLM, Process, Task

# ---------------------------------------------------------
# MODEL CONFIG
# ---------------------------------------------------------

GEMINI_MODEL = "gemini/gemini-3.5-flash-lite"


def create_gemini_llm() -> LLM:
    """
    Create the Gemini LLM used by all CrewAI agents.
    """

    return LLM(
        model=GEMINI_MODEL,
    )


# ---------------------------------------------------------
# REVIEW MODES
# ---------------------------------------------------------

SUPPORTED_REVIEW_MODES = {
    "full_repository",
    "latest_commit",
    "uncommitted",
}


def _get_review_scope(
    review_mode: str,
) -> str:
    """
    Return instructions describing exactly what
    should be reviewed for the selected mode.
    """

    if review_mode == "latest_commit":
        return """
REVIEW MODE: Latest Commit

Focus primarily on code introduced or changed in the latest Git commit.

Start by using Git tools to:
1. Get the latest commit information.
2. Get files changed in the latest commit.
3. Read the latest commit diff.

Use normal code-reading tools only when surrounding context is needed.

Do not turn unrelated pre-existing issues into findings unless they are
directly relevant to understanding the changed code.
"""

    if review_mode == "uncommitted":
        return """
REVIEW MODE: Uncommitted Changes

Focus primarily on staged, unstaged, and untracked changes in the current
working tree.

Start by using Git tools to:
1. Inspect Git status.
2. Get changed files.
3. Inspect the available Git diff.
4. Read untracked files directly when necessary.

Do not report unrelated problems from untouched parts of the repository.
"""

    return """
REVIEW MODE: Full Repository

Review the repository as a whole.

Inspect the overall project structure and the source files necessary to
understand the application, bugs, security risks, and testing quality.
"""


# ---------------------------------------------------------
# CREW BUILDER
# ---------------------------------------------------------


def build_code_review_crew(
    code_tools=None,
    test_tools=None,
    git_tools=None,
    review_mode="full_repository",
):
    """
    Build and return the CrewAI code review crew.

    Supported review modes:
        full_repository
        latest_commit
        uncommitted
    """

    code_tools = code_tools or []
    test_tools = test_tools or []
    git_tools = git_tools or []

    review_mode = review_mode.strip().lower()

    if review_mode not in SUPPORTED_REVIEW_MODES:
        raise ValueError(
            "Unsupported review mode. Use: "
            "full_repository, latest_commit, or uncommitted."
        )

    review_scope = _get_review_scope(review_mode)

    llm = create_gemini_llm()

    # Git tools are only necessary for
    # Git-focused review modes.
    active_git_tools = git_tools if review_mode != "full_repository" else []

    # -----------------------------------------------------
    # AGENT 1: CODE ANALYST
    # -----------------------------------------------------

    code_analyst = Agent(
        role="Code Analyst",
        goal=(
            "Understand the software project and identify "
            "the code relevant to the selected review scope."
        ),
        backstory=(
            "You are an experienced software engineer who quickly "
            "understands unfamiliar repositories. You identify the "
            "technology stack, architecture, important files, execution "
            "flow, and relevant code changes before deeper reviewers begin."
        ),
        llm=llm,
        tools=(code_tools + active_git_tools),
        verbose=True,
        allow_delegation=False,
        max_iter=4,
        max_retry_limit=0,
    )

    # -----------------------------------------------------
    # AGENT 2: BUG HUNTER
    # -----------------------------------------------------

    bug_hunter = Agent(
        role="Bug Hunter",
        goal=(
            "Find concrete bugs, incorrect logic, runtime failures, "
            "unsafe assumptions, and edge-case problems relevant "
            "to the selected review scope."
        ),
        backstory=(
            "You are a senior software engineer experienced in debugging "
            "production systems. You report problems supported by actual "
            "code evidence rather than speculative concerns."
        ),
        llm=llm,
        tools=(code_tools + active_git_tools),
        verbose=True,
        allow_delegation=False,
        max_iter=4,
        max_retry_limit=0,
    )

    # -----------------------------------------------------
    # AGENT 3: SECURITY REVIEWER
    # -----------------------------------------------------

    security_reviewer = Agent(
        role="Security Reviewer",
        goal=(
            "Identify concrete security weaknesses relevant "
            "to the selected repository review scope."
        ),
        backstory=(
            "You are an application security engineer. You review "
            "authentication, authorization, input validation, secrets, "
            "file access, APIs, and sensitive-data handling. You report "
            "only vulnerabilities supported by available code evidence."
        ),
        llm=llm,
        tools=(code_tools + active_git_tools),
        verbose=True,
        allow_delegation=False,
        max_iter=4,
        max_retry_limit=0,
    )

    # -----------------------------------------------------
    # AGENT 4: TEST ENGINEER
    # -----------------------------------------------------

    test_engineer = Agent(
        role="Test Engineer",
        goal=(
            "Evaluate testing quality and determine whether the "
            "selected code changes are adequately protected by tests."
        ),
        backstory=(
            "You are a software test engineer experienced in unit, "
            "integration, regression, and API testing. You identify "
            "high-value testing gaps and use actual test execution "
            "results when test tools are available."
        ),
        llm=llm,
        tools=(code_tools + active_git_tools + test_tools),
        verbose=True,
        allow_delegation=False,
        max_iter=4,
        max_retry_limit=0,
    )

    # -----------------------------------------------------
    # AGENT 5: SENIOR REVIEWER
    # -----------------------------------------------------

    senior_reviewer = Agent(
        role="Senior Code Reviewer",
        goal=(
            "Combine all agent findings into an accurate, concise, "
            "prioritized engineering review."
        ),
        backstory=(
            "You are a senior software engineer responsible for final "
            "code reviews. You remove duplicates, reject unsupported "
            "claims, normalize severity levels, and produce practical "
            "recommendations developers can act on."
        ),
        llm=llm,
        verbose=True,
        allow_delegation=False,
        max_iter=4,
        max_retry_limit=0,
    )

    # -----------------------------------------------------
    # TASK 1: PROJECT / CHANGE ANALYSIS
    # -----------------------------------------------------

    analyze_project_task = Task(
        description=(
            f"{review_scope}\n\n"
            "The repository is located at:\n"
            "{project_path}\n\n"
            "Determine:\n"
            "- project purpose\n"
            "- programming language and technology stack\n"
            "- important files/modules relevant to this review\n"
            "- application entry points when relevant\n"
            "- main components involved\n"
            "- execution flow\n"
            "- files or changes requiring deeper review\n\n"
            "For Git-focused review modes, inspect Git information first "
            "and then read only the code necessary to understand the changes.\n\n"
            "Avoid repeatedly reading the same files unless additional "
            "context is genuinely required.\n\n"
            "Do not perform the detailed bug or security review yet."
        ),
        expected_output=(
            "A concise technical analysis containing:\n"
            "1. Review scope\n"
            "2. Project purpose\n"
            "3. Technology stack\n"
            "4. Relevant files/modules\n"
            "5. Main execution flow\n"
            "6. Changed areas when Git review is active\n"
            "7. Areas requiring deeper review"
        ),
        agent=code_analyst,
    )

    # -----------------------------------------------------
    # TASK 2: BUG REVIEW
    # -----------------------------------------------------

    bug_review_task = Task(
        description=(
            f"{review_scope}\n\n"
            "Repository:\n"
            "{project_path}\n\n"
            "Use the Code Analyst result as context.\n\n"
            "Look for:\n"
            "- incorrect logic\n"
            "- runtime errors\n"
            "- broken conditions\n"
            "- unsafe assumptions\n"
            "- missing edge-case handling\n"
            "- exception-handling problems\n"
            "- resource-handling problems\n"
            "- regressions introduced by changed code\n\n"
            "For Git-focused reviews, findings should normally relate "
            "to changed code or consequences directly caused by the change.\n\n"
            "Inspect only the files necessary to support a finding.\n\n"
            "Do not report speculative problems."
        ),
        expected_output=(
            "A list of supported bugs.\n\n"
            "For each finding include:\n"
            "- Severity\n"
            "- File\n"
            "- Relevant line/location when available\n"
            "- Problem\n"
            "- Evidence\n"
            "- Impact\n"
            "- Recommended fix\n\n"
            "Clearly state if no meaningful bug was found."
        ),
        agent=bug_hunter,
    )

    # -----------------------------------------------------
    # TASK 3: SECURITY REVIEW
    # -----------------------------------------------------

    security_review_task = Task(
        description=(
            f"{review_scope}\n\n"
            "Repository:\n"
            "{project_path}\n\n"
            "Use previous analysis as context.\n\n"
            "Review relevant code for:\n"
            "- authentication weaknesses\n"
            "- authorization problems\n"
            "- input validation failures\n"
            "- injection risks\n"
            "- secret exposure\n"
            "- unsafe filesystem access\n"
            "- insecure API behavior\n"
            "- sensitive-data exposure\n"
            "- dependency risks visible from repository files\n\n"
            "For Git-focused reviews, prioritize vulnerabilities "
            "introduced, modified, or exposed by the selected changes.\n\n"
            "Inspect only the files necessary to support findings.\n\n"
            "Report only issues supported by actual code evidence."
        ),
        expected_output=(
            "A security assessment containing supported findings.\n\n"
            "For each finding include:\n"
            "- Severity\n"
            "- File/location\n"
            "- Vulnerability\n"
            "- Evidence\n"
            "- Potential impact\n"
            "- Recommended mitigation\n\n"
            "State clearly if no meaningful vulnerability is identified."
        ),
        agent=security_reviewer,
    )

    # -----------------------------------------------------
    # TASK 4: TEST REVIEW
    # -----------------------------------------------------

    test_review_task = Task(
        description=(
            f"{review_scope}\n\n"
            "Repository:\n"
            "{project_path}\n\n"
            "Use previous analysis as context.\n\n"
            "Determine:\n"
            "- what functionality is currently tested\n"
            "- whether changed functionality has relevant tests\n"
            "- missing regression tests\n"
            "- important edge cases\n"
            "- weak or misleading tests\n"
            "- high-risk functionality without coverage\n\n"
            "If test execution tools are available:\n"
            "1. Detect the project's test setup.\n"
            "2. Run the supported test suite when appropriate.\n"
            "3. Report the actual command, exit status, and test result.\n\n"
            "Never claim that tests passed unless a test tool actually "
            "executed them successfully during this review."
        ),
        expected_output=(
            "A testing assessment containing:\n"
            "1. Existing test coverage\n"
            "2. Test execution result, if actually executed\n"
            "3. Change-specific test coverage when applicable\n"
            "4. Missing high-priority tests\n"
            "5. Important edge cases\n"
            "6. Recommended testing improvements"
        ),
        agent=test_engineer,
    )

    # -----------------------------------------------------
    # TASK 5: FINAL REVIEW
    # -----------------------------------------------------

    final_review_task = Task(
        description=(
            f"{review_scope}\n\n"
            "Combine the Code Analyst, Bug Hunter, Security Reviewer, "
            "and Test Engineer outputs into the final review.\n\n"
            "Requirements:\n"
            "- remove duplicate findings\n"
            "- reject unsupported claims\n"
            "- normalize severity consistently\n"
            "- prioritize based on actual impact\n"
            "- preserve the selected review scope\n"
            "- do not invent files or line numbers\n"
            "- do not claim tests passed unless test execution evidence exists\n"
            "- distinguish confirmed defects from optional improvements\n\n"
            "For Git-focused modes, make it clear that findings refer "
            "to the selected changes rather than presenting the output "
            "as a complete repository audit."
        ),
        expected_output=(
            "# Code Review Report\n\n"
            "## Review Scope\n"
            "State whether this was a full repository, latest commit, "
            "or uncommitted changes review.\n\n"
            "## Project Overview\n"
            "Brief technical overview.\n\n"
            "## Review Summary\n"
            "Critical, High, Medium, and Low finding counts.\n\n"
            "## Findings\n"
            "For each meaningful finding include:\n"
            "- Severity\n"
            "- Category\n"
            "- File/location\n"
            "- Problem\n"
            "- Evidence\n"
            "- Impact\n"
            "- Recommendation\n\n"
            "## Testing\n"
            "Include actual test execution results only when tests "
            "were executed, plus important testing gaps.\n\n"
            "## Positive Observations\n"
            "Good practices supported by evidence.\n\n"
            "## Recommended Fix Order\n"
            "Prioritized next actions."
        ),
        agent=senior_reviewer,
        markdown=True,
    )

    # -----------------------------------------------------
    # CREW
    # -----------------------------------------------------

    crew = Crew(
        agents=[
            code_analyst,
            bug_hunter,
            security_reviewer,
            test_engineer,
            senior_reviewer,
        ],
        tasks=[
            analyze_project_task,
            bug_review_task,
            security_review_task,
            test_review_task,
            final_review_task,
        ],
        process=Process.sequential,
        verbose=True,
        memory=False,
        planning=False,
        # Conservative rate limit for the
        # Gemini free tier.
        max_rpm=4,
    )

    return crew
