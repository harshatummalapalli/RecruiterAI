"""Fixed scenario set for the knowledge-library spike (EXP-002).

Each scenario carries what a good intake SHOULD do, written BEFORE any run:

  expected_ask     regex over an ASK issue's text. An ASK that matches nothing here is a false-positive ASK.
                   None means "no question is warranted": every ASK is a false positive.
  expected_finding regex over everything surfaced to the recruiter (TELLs, warnings, ASK questions, the search
                   consequence). Matching means the intake noticed the thing worth noticing.

The JDs are realistic in shape and invented in content. The boundary (location, company, work mode) is fixed and
supplied separately, exactly as in production, so location questions are never expected.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Scenario:
    id: str
    label: str
    posted_title: str
    jd: str
    expected_ask: Optional[str]
    expected_finding: Optional[str]
    note: str


SCENARIOS = [
    Scenario(
        id="S1",
        label="clear role",
        posted_title="Senior Backend Engineer",
        jd="""Senior Backend Engineer
Required: 5+ years building and operating backend services in production. Strong Python. Experience designing REST APIs. PostgreSQL or another relational database.
Preferred: Kafka or another event streaming system, Docker.
You will own services end to end, from design to on-call. Mid-sized product team, hybrid.""",
        expected_ask=None,
        expected_finding=None,
        note="Zero questions is the correct outcome.",
    ),
    Scenario(
        id="S2",
        label="title says software engineer, work is platform/infra",
        posted_title="Software Engineer",
        jd="""Software Engineer
You will run our Kubernetes clusters on AWS, maintain Terraform modules, own the CI/CD pipelines and be part of the on-call rotation for production infrastructure. Some Go tooling for internal developer workflows.
Required: 4+ years with Kubernetes and Terraform in production, strong Linux, AWS.
Nice to have: Go, Prometheus and Grafana.""",
        expected_ask=None,
        expected_finding=r"platform|infrastructure|devops|sre|site reliability",
        note="The title and the work disagree; the work is unambiguous, so noticing it is a TELL, not a question.",
    ),
    Scenario(
        id="S3",
        label="conflicting experience ranges",
        posted_title="Backend Engineer",
        jd="""Backend Engineer
We are looking for an engineer with 3+ years of experience to join our payments team.
Requirements:
- 8-10 years of professional software engineering experience
- Strong Python and SQL
- Experience with distributed systems
Nice to have: Kafka.""",
        expected_ask=r"experience|years|range",
        expected_finding=r"3|8|range|conflict",
        note="Two ranges in one JD; exactly one question is warranted, and it changes the experience filter.",
    ),
    Scenario(
        id="S4",
        label="over-constrained required list",
        posted_title="Senior Software Engineer",
        jd="""Senior Software Engineer
Required skills: Python, Java, Go, Rust, C++, Kubernetes, Kafka, Spark, TensorFlow, React, Angular, iOS and Android development, Terraform, GraphQL, Snowflake.
7+ years of experience. You will work across our platform.""",
        expected_ask=r"required|must|nice|prefer|tier|stack|core|priorit|which",
        expected_finding=r"over-?constrain|narrow|all of|every|rare|unrealistic|must-have|nice-to-have|too many|multiple unrelated|few candidates",
        note="A long required list spanning unrelated stacks. Either a question about which are truly required or a plain statement that this will narrow the search is warranted.",
    ),
    Scenario(
        id="S5",
        label="impossible technology tenure",
        posted_title="DevOps Engineer",
        jd="""DevOps Engineer
Required: 12+ years of hands-on Kubernetes experience and 8+ years working with large language models in production. Strong Terraform and AWS.
You will build the deployment platform for our ML services.""",
        expected_ask=r"years|tenure|kubernetes|llm|language model|experience|required",
        expected_finding=r"kubernetes|language model|llm|years|unrealistic|tenure|recent|exist|since 20|not possible|new",
        note="Tenure that exceeds how long the technologies have existed. A TELL or a question are both acceptable; silence is not.",
    ),
    Scenario(
        id="S6",
        label="staff title, junior experience",
        posted_title="Staff Software Engineer",
        jd="""Staff Software Engineer
Join our growth team. 1-2 years of experience with Python and JavaScript. You will build features for our web app with guidance from the team.
Nice to have: React.""",
        expected_ask=r"staff|seniority|level|title|years|experience|junior|senior",
        expected_finding=r"staff|senior|junior|years|level|mismatch|conflict",
        note="Staff title over junior requirements. The regex backstop does not detect this by design; the model should.",
    ),
    Scenario(
        id="S7",
        label="AI engineer, explicitly backend-dominant",
        posted_title="AI Engineer",
        jd="""AI Engineer
About 70% of your time is backend engineering (Python, FastAPI, Kafka, PostgreSQL) and about 30% applying ML and LLMs to fraud detection.
Required: 5+ years of backend engineering, Python. Some experience shipping ML or LLM features.
Preferred: Snowflake, dbt.""",
        expected_ask=None,
        expected_finding=r"backend",
        note="The JD already says how the role divides. Asking 'AI or backend?' is a false positive; saying it reads backend-heavy is the goal.",
    ),
    Scenario(
        id="S8",
        label="vague notes only",
        posted_title="",
        jd="""need someone good with data for our fintech team. senior-ish. they will help us understand our customers better and build some dashboards and maybe some models. python or R.""",
        expected_ask=r"data (scientist|engineer|analyst)|analyst|identity|role|scientist|engineer|senior|experience|years|modeling|dashboard",
        expected_finding=r"data (scientist|engineer|analyst)|analyst|ambigu|unclear",
        note="Rough notes. Questions about which kind of data role and how senior are warranted; anything else is not.",
    ),
    Scenario(
        id="S9",
        label="data scientist title, ETL work",
        posted_title="Data Scientist",
        jd="""Data Scientist
You will build and maintain ETL pipelines in Airflow and dbt, own our Snowflake warehouse models, and make sure data lands on time for the analytics team.
Required: 4+ years of SQL and Python, Airflow, dbt, data modeling.
Preferred: exposure to statistics.""",
        expected_ask=None,
        expected_finding=r"data engineer|pipeline|etl|analytics engineer|not (a )?(traditional )?data scien",
        note="The title says scientist, the work is engineering. Noticing it is a TELL; the work is clear enough that a question is not needed.",
    ),
]
