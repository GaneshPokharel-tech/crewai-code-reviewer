from crewai import Agent, Crew, LLM, Process, Task

# ---------------------------------------------------------
# LLM
# ---------------------------------------------------------

llm = LLM(
    model="gemini/gemini-3.5-flash-lite",
)


# ---------------------------------------------------------
# CREW BUILDER
# ---------------------------------------------------------


def build_code_review_crew(code_tools=None, test_tools=None):
    """
    Build and return the complete Code Review Crew.

    code_tools:
        Tools used for reading/searching source code.

    test_tools:
        Tools used for detecting and running tests.
    """

    code_tools = code_tools or []
    test_tools = test_tools or []

    # -----------------------------------------------------
    # AGENT 1: CODE ANALYST
    # -----------------------------------------------------

    code_analyst = Agent(
        role="Code Analyst",
        goal=(
            "Understand the software project's structure, purpose, "
            "technology stack, important files, modules, and execution flow."
        ),
        backstory=(
            "You are an experienced software engineer who specializes in "
            "quickly understanding unfamiliar codebases. Your responsibility "
            "is to build a clear technical picture of the project before "
            "other reviewers perform deeper analysis."
        ),
        llm=llm,
        tools=code_tools,
        verbose=True,
        allow_delegation=False,
        # Keep free-tier LLM usage controlled.
        max_iter=4,
        # Do not automatically repeat failed LLM calls.
        max_retry_limit=0,
    )

    # -----------------------------------------------------
    # AGENT 2: BUG HUNTER
    # -----------------------------------------------------

    bug_hunter = Agent(
        role="Bug Hunter",
        goal=(
            "Find real bugs, incorrect logic, runtime risks, edge cases, "
            "and weak error handling in the project."
        ),
        backstory=(
            "You are a senior software engineer experienced in debugging "
            "production applications. You focus on concrete problems that "
            "can cause crashes, incorrect results, broken workflows, or "
            "unexpected application behavior."
        ),
        llm=llm,
        tools=code_tools,
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
            "Identify security weaknesses in authentication, authorization, "
            "input validation, secrets handling, file access, API usage, "
            "and other security-sensitive areas."
        ),
        backstory=(
            "You are an application security engineer who reviews software "
            "for practical vulnerabilities. You avoid inventing security "
            "problems and report only issues supported by the available code."
        ),
        llm=llm,
        tools=code_tools,
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
            "Evaluate the project's tests, identify missing coverage, "
            "important untested scenarios, and test failures."
        ),
        backstory=(
            "You are a software test engineer experienced in unit, "
            "integration, and API testing. You focus on high-value tests "
            "that protect important application behavior rather than "
            "creating unnecessary tests."
        ),
        llm=llm,
        # Code-reading tools are always available.
        # Test execution tools are optional and are only supplied
        # when the user enables --run-tests.
        tools=code_tools + test_tools,
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
            "Combine all review findings into a clear, accurate, "
            "prioritized code review report."
        ),
        backstory=(
            "You are a senior software engineer responsible for final "
            "technical reviews before code reaches production. You remove "
            "duplicate findings, reject unsupported claims, prioritize "
            "problems by severity, and provide practical recommendations."
        ),
        llm=llm,
        verbose=True,
        allow_delegation=False,
        max_iter=4,
        max_retry_limit=0,
    )

    # -----------------------------------------------------
    # TASK 1: ANALYZE PROJECT
    # -----------------------------------------------------

    analyze_project_task = Task(
        description=(
            "Analyze the software project located at:\n"
            "{project_path}\n\n"
            "Start by listing the project files. Then read only the files "
            "needed to understand the project.\n\n"
            "Determine:\n"
            "- the purpose of the project\n"
            "- programming language and technology stack\n"
            "- important files and modules\n"
            "- application entry points\n"
            "- major components\n"
            "- how components interact\n"
            "- overall execution flow\n\n"
            "Do not perform a detailed bug or security review yet.\n"
            "Avoid repeatedly reading the same files unless necessary."
        ),
        expected_output=(
            "A concise technical overview containing:\n"
            "1. Project purpose\n"
            "2. Technology stack\n"
            "3. Important files/modules\n"
            "4. Main components\n"
            "5. Execution flow\n"
            "6. Areas that deserve deeper review"
        ),
        agent=code_analyst,
    )

    # -----------------------------------------------------
    # TASK 2: FIND BUGS
    # -----------------------------------------------------

    bug_review_task = Task(
        description=(
            "Perform a focused bug review of the project located at:\n"
            "{project_path}\n\n"
            "Use the previous project analysis as context.\n\n"
            "Inspect relevant source files and look for:\n"
            "- incorrect business logic\n"
            "- runtime errors\n"
            "- unsafe assumptions\n"
            "- missing edge-case handling\n"
            "- incorrect conditions\n"
            "- broken control flow\n"
            "- exception-handling problems\n"
            "- resource-handling problems\n\n"
            "Do not report speculative issues without evidence.\n"
            "Do not repeatedly inspect files that are unrelated to the review."
        ),
        expected_output=(
            "A list of confirmed or strongly supported bugs.\n\n"
            "For every issue include:\n"
            "- Severity\n"
            "- File\n"
            "- Relevant line/location when available\n"
            "- Problem\n"
            "- Why it matters\n"
            "- Recommended fix\n\n"
            "If no meaningful bug is found, clearly state that."
        ),
        agent=bug_hunter,
    )

    # -----------------------------------------------------
    # TASK 3: SECURITY REVIEW
    # -----------------------------------------------------

    security_review_task = Task(
        description=(
            "Perform a security review of the project located at:\n"
            "{project_path}\n\n"
            "Use the previous project analysis as context.\n\n"
            "Inspect security-relevant files and check areas including:\n"
            "- authentication\n"
            "- authorization\n"
            "- input validation\n"
            "- injection risks\n"
            "- secret handling\n"
            "- unsafe file access\n"
            "- insecure API usage\n"
            "- sensitive data exposure\n"
            "- dependency-related risks when visible\n\n"
            "Only report vulnerabilities supported by actual code evidence."
        ),
        expected_output=(
            "A security review containing supported findings only.\n\n"
            "For every finding include:\n"
            "- Severity\n"
            "- File\n"
            "- Vulnerability\n"
            "- Evidence\n"
            "- Potential impact\n"
            "- Recommended mitigation\n\n"
            "Clearly state if no meaningful security issue is identified."
        ),
        agent=security_reviewer,
    )

    # -----------------------------------------------------
    # TASK 4: TEST REVIEW
    # -----------------------------------------------------

    test_review_task = Task(
        description=(
            "Review the testing quality of the project located at:\n"
            "{project_path}\n\n"
            "Use the previous project analysis as context.\n\n"
            "Inspect existing test files.\n"
            "If a test-execution tool is available, first detect the test "
            "setup and then run the supported test suite when appropriate.\n\n"
            "Determine:\n"
            "- what is currently tested\n"
            "- whether existing tests pass or fail when execution is enabled\n"
            "- important missing test cases\n"
            "- missing edge-case coverage\n"
            "- weak or misleading tests\n"
            "- high-risk functionality without tests\n\n"
            "Prioritize useful tests rather than suggesting tests for "
            "every function."
        ),
        expected_output=(
            "A testing assessment containing:\n"
            "1. Existing test coverage overview\n"
            "2. Test execution result when available\n"
            "3. Missing high-priority tests\n"
            "4. Important edge cases\n"
            "5. Recommended testing improvements"
        ),
        agent=test_engineer,
    )

    # -----------------------------------------------------
    # TASK 5: FINAL REVIEW
    # -----------------------------------------------------

    final_review_task = Task(
        description=(
            "Review all previous analysis produced by the Code Analyst, "
            "Bug Hunter, Security Reviewer, and Test Engineer.\n\n"
            "Create the final professional code review report.\n\n"
            "Requirements:\n"
            "- remove duplicate findings\n"
            "- reject unsupported claims\n"
            "- prioritize issues based on actual impact\n"
            "- keep recommendations practical and specific\n"
            "- do not invent files, line numbers, vulnerabilities, or bugs\n"
            "- clearly distinguish confirmed issues from recommendations"
        ),
        expected_output=(
            "# Code Review Report\n\n"
            "## Project Overview\n"
            "Brief explanation of the reviewed project.\n\n"
            "## Review Summary\n"
            "Number of Critical, High, Medium, and Low findings.\n\n"
            "## Findings\n"
            "For every meaningful finding include:\n"
            "- Severity\n"
            "- Category\n"
            "- File/location\n"
            "- Problem\n"
            "- Impact\n"
            "- Recommendation\n\n"
            "## Testing Gaps\n"
            "Important missing or weak tests.\n\n"
            "## Positive Observations\n"
            "Good engineering practices actually observed in the code.\n\n"
            "## Recommended Fix Order\n"
            "Prioritized action plan from highest to lowest importance.\n\n"
            "The report must be specific to the reviewed project and "
            "must not contain generic filler."
        ),
        agent=senior_reviewer,
        markdown=True,
        output_file="code_review_report.md",
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
        # Run tasks one after another.
        process=Process.sequential,
        verbose=True,
        # Keep unnecessary extra LLM calls disabled.
        memory=False,
        planning=False,
        # Gemini free tier currently showed a 5 RPM limit
        # in our run, so we stay below that.
        max_rpm=4,
    )

    return crew
