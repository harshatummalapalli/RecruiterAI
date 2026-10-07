"""SYNTHETIC scenarios for validating the downstream Judge contract with the REAL Judge model.

Every profile below is invented text (no real person, employer or candidate data; company names are fictional and every profile is labelled SYNTHETIC).
They are written ONCE, by hand, before any model run, and are not edited between runs. Each profile is built to evidence (or deliberately not evidence) specific
items of a frozen compiled downstream context (Roles 1-3). An expectation names an item by its text and says what a correct reading of the contract looks like.

What is validated is whether the real model CONSUMES the new contract (positives, negatives, preferences, proficiency, work mode, path, unresolved) without
reconstructing or ignoring the new semantics. It is NOT a measure of candidate quality.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Profile:
    key: str
    label: str                       # what the profile is designed to show
    title: str
    headline: str
    start_year: int                  # current role start (drives derived experience only)
    passages: Tuple[str, ...]        # role descriptions (each becomes a passage the Judge may cite)


@dataclass(frozen=True)
class Expect:
    eid: str
    candidate: str
    context: Optional[str]           # "PATH A" / "PATH B" / None (the role's single context)
    kind: str                        # req_met | req_not_met | excl_present | excl_not_present | asked | not_asked | same_verdicts_as | pref_met | pref_not_required
    item: str = ""                   # the checklist item text (an exact text, or the start of one for exclusions)
    other: str = ""                  # same_verdicts_as: the other candidate
    why: str = ""


# ======================================================================================================================
# ROLE 1 (frozen run 3: real Path A / Path B).  Path A requires domain (cyber incident review / breach analysis) and does NOT ask Power Query;
# Path B requires Power Query (+ working knowledge) and does NOT ask the domain.
# ======================================================================================================================

R1_COMMON = (
    "SYNTHETIC PROFILE. Lead Data Analyst at Meridian Review Services (fictional), 2018 to present. Writes SQL queries every day against review databases and "
    "maintains Python scripts that automate data extraction, analysis and reporting. Produces weekly management reports, dashboards and performance metrics for "
    "operations leadership. Analyses large datasets to identify trends, anomalies and potential security risks in review populations.",
    "Leads a team of five analysts (people leadership). Sets quality-control checklists, enforces adherence to security standards and review protocols, and runs "
    "review, quality assurance and compliance audits of completed batches. Keeps accurate documentation, procedures, audit trails and quality records. Works across "
    "functions with project managers and remediation teams on review findings. Coordinates workflow, resource planning and administrative support for the Review "
    "Manager. Drives continuous improvement of operational efficiency, quality and compliance. Applies data privacy requirements and information security principles "
    "to all client data handling. Strong analytical capabilities and close attention to detail.",
)
R1_DOMAIN = ("SYNTHETIC PROFILE. Cyber incident review and data breach analysis: reviewed documents from data breach incidents for several clients to identify affected "
             "individuals, classify personal data and prepare notification lists; ran cyber incident review matters end to end as part of the review team.",)
R1_POWERQUERY = ("SYNTHETIC PROFILE. Uses Power Query regularly in Excel and Power BI to clean, merge and transform data; working knowledge of Power Query M functions "
                 "and query folding.",)
R1_SOC = ("SYNTHETIC PROFILE. Previously a Security Operations Center analyst: monitored SIEM alerts around the clock, triaged security incidents, hunted for threats, "
          "tuned firewall rules and ran vulnerability scans. Cybersecurity operations is the core of this background.",)
R1_LEGALTECH = ("SYNTHETIC PROFILE. Paralegal operations specialist: administers Relativity workspaces and Canopy projects for a legal services provider, manages "
                "legal tech tooling, user access and review batches. Has not written SQL or Python.",)

PROFILES_R1: List[Profile] = [
    Profile("A", "satisfies Path A (domain), not Path B (no Power Query)", "Lead Data Analyst", "Lead Data Analyst | review operations", 2018, R1_COMMON + R1_DOMAIN),
    Profile("B", "satisfies Path B (Power Query), not Path A (no domain)", "Lead Data Analyst", "Lead Data Analyst | reporting", 2018, R1_COMMON + R1_POWERQUERY),
    Profile("C", "satisfies both paths", "Lead Data Analyst", "Lead Data Analyst | review operations and reporting", 2018, R1_COMMON + R1_DOMAIN + R1_POWERQUERY),
    Profile("D", "satisfies neither path (common obligations only)", "Lead Data Analyst", "Lead Data Analyst", 2018, R1_COMMON),
    Profile("E", "security-operations (SOC) background: the semantic exclusion", "Lead Data Analyst", "Security operations | data analysis", 2018, R1_COMMON + R1_SOC),
    Profile("F", "preferences only (Relativity / Canopy / legal tech), no required skills", "Director of Legal Operations", "Legal operations", 2016, R1_LEGALTECH),
]

R1_DOMAIN_ITEM = "Cyber Incident Review and/or Data Breach Analysis"
R1_EXCL_SOC = "Generic cybersecurity or security-operations backgrounds are not equivalent"

EXPECT_R1: List[Expect] = [
    # path A obligations
    Expect("R1-A-domain", "A", "PATH A", "req_met", R1_DOMAIN_ITEM, why="A states the domain; Path A requires it"),
    Expect("R1-C-domain", "C", "PATH A", "req_met", R1_DOMAIN_ITEM),
    Expect("R1-B-no-domain", "B", "PATH A", "req_not_met", R1_DOMAIN_ITEM, why="B has no domain evidence: Path A is not satisfied by B"),
    Expect("R1-D-no-domain", "D", "PATH A", "req_not_met", R1_DOMAIN_ITEM),
    # path B obligations
    Expect("R1-B-pq", "B", "PATH B", "req_met", "Power Query"),
    Expect("R1-B-pq-wk", "B", "PATH B", "req_met", "working knowledge of Power Query"),
    Expect("R1-C-pq", "C", "PATH B", "req_met", "Power Query"),
    Expect("R1-A-no-pq", "A", "PATH B", "req_not_met", "Power Query", why="A has no Power Query: Path B is not satisfied by A"),
    Expect("R1-D-no-pq", "D", "PATH B", "req_not_met", "Power Query"),
    # no leakage between paths (what each path's Judge was asked)
    Expect("R1-PQ-waived-in-A", "A", "PATH A", "not_asked", "Power Query", why="Path A waives Power Query: it must not be asked"),
    Expect("R1-PQ-asked-in-B", "A", "PATH B", "asked", "Power Query", why="Path B requires Power Query"),
    Expect("R1-domain-not-asked-in-B", "A", "PATH B", "not_asked", R1_DOMAIN_ITEM, why="the domain is Path A's obligation only"),
    Expect("R1-domain-asked-in-A", "A", "PATH A", "asked", R1_DOMAIN_ITEM),
    # the semantic negative
    Expect("R1-E-soc-present", "E", "PATH A", "excl_present", R1_EXCL_SOC, why="a SOC background is the excluded profile"),
    Expect("R1-E-soc-present-B", "E", "PATH B", "excl_present", R1_EXCL_SOC),
    Expect("R1-E-domain-not-met", "E", "PATH A", "req_not_met", R1_DOMAIN_ITEM, why="cyber operations wording is not the domain"),
    Expect("R1-A-soc-absent", "A", "PATH A", "excl_not_present", R1_EXCL_SOC, why="a candidate with the real domain is not the excluded profile"),
    Expect("R1-C-soc-absent", "C", "PATH A", "excl_not_present", R1_EXCL_SOC),
    Expect("R1-B-soc-absent", "B", "PATH B", "excl_not_present", R1_EXCL_SOC),
    Expect("R1-D-soc-absent", "D", "PATH A", "excl_not_present", R1_EXCL_SOC),
    # preferences stay preferences
    Expect("R1-F-pref-met", "F", "PATH A", "pref_met", "Relativity", why="the preference IS evidenced"),
    Expect("R1-F-pref-not-enough", "F", "PATH A", "req_not_met", "hands-on SQL", why="a preference does not stand in for a requirement"),
    Expect("R1-F-pref-not-enough-B", "F", "PATH B", "req_not_met", "hands-on Python"),
    Expect("R1-A-pref-missing-still-A", "A", "PATH A", "req_met", R1_DOMAIN_ITEM, why="A lacks Relativity / Canopy: it still meets Path A's requirement"),
    # hands-on proficiency
    Expect("R1-A-handson-sql", "A", "PATH A", "req_met", "hands-on SQL"),
    Expect("R1-F-handson-sql-B", "F", "PATH B", "req_not_met", "hands-on SQL"),
]

# ======================================================================================================================
# ROLE 2 (frozen run 1: one context, no sourcing paths)
# ======================================================================================================================

PROFILES_R2: List[Profile] = [
    Profile("P1", "hands-on Python and Java in production; working-level Jira and Azure DevOps", "Software Engineer", "Software Engineer | Python, Java", 2017, (
        "SYNTHETIC PROFILE. Software Engineer at Alder Systems (fictional), 2017 to present. Writes production Python and Java services every day and ships APIs to "
        "customers; maintains the CI pipelines for them.",
        "SYNTHETIC PROFILE. Uses Jira for planning and Azure DevOps boards and pipelines as part of the team's normal delivery workflow (working knowledge).")),
    Profile("P2", "only familiar with Python and Java (coursework), never shipped", "Graduate Trainee", "Trainee | learning Python and Java", 2024, (
        "SYNTHETIC PROFILE. Graduate trainee. Took introductory university courses in Python and Java and read example code. Familiar with the syntax. Has not built or "
        "shipped any production software.",)),
    Profile("P3", "LLM / RAG / agentic work in a PAST role that ended; now a manager who no longer builds", "Engineering Manager", "Engineering Manager", 2013, (
        "SYNTHETIC PROFILE. Engineering Manager at Birch Analytics (fictional), 2023 to present. Manages planning and hiring; reviews roadmaps. Does not write code "
        "in this role.",
        "SYNTHETIC PROFILE. Senior Engineer at Cedar Labs (fictional), 2019 to 2023 (role ended in 2023). Built and deployed applications on Large Language Models, "
        "designed Retrieval-Augmented Generation pipelines, built agentic AI workflows with prompt engineering and AI orchestration.")),
    Profile("P4", "analogy title only: a Forward Deployed Engineer title, no engineering evidence", "Forward Deployed Engineer", "Forward Deployed Engineer", 2020, (
        "SYNTHETIC PROFILE. Forward Deployed Engineer at Dune Software (fictional), 2020 to present. Sits with customers on site, runs onboarding workshops and trains "
        "customer staff. Does not write production code.",)),
]
# the items whose `current` claim the source did not support (computed from the context at run time, never typed here)
R2_NO_CURRENT = ("Large Language Models", "Retrieval-Augmented Generation", "Agentic AI", "Prompt Engineering", "AI Orchestration")

EXPECT_R2: List[Expect] = [
    Expect("R2-P1-handson-python", "P1", None, "req_met", "hands-on Python", why="production Python every day is hands-on"),
    Expect("R2-P1-handson-java", "P1", None, "req_met", "hands-on Java"),
    Expect("R2-P2-handson-python", "P2", None, "req_not_met", "hands-on Python", why="familiar != hands-on: depths are distinct"),
    Expect("R2-P2-handson-java", "P2", None, "req_not_met", "hands-on Java"),
    Expect("R2-P1-wk-jira", "P1", None, "req_met", "working knowledge of Jira"),
    # unsupported proficiency is not inferred: the depth was withheld, so the Judge is never asked for it
    Expect("R2-no-invented-depth-llm", "P3", None, "not_asked", "hands-on Large Language Models", why="the source states no depth: never required"),
    Expect("R2-no-invented-depth-rag", "P3", None, "not_asked", "hands-on Retrieval-Augmented Generation"),
    Expect("R2-no-invented-depth-ai", "P3", None, "not_asked", "hands-on AI/ML Implementation"),
    Expect("R2-plain-llm-asked", "P3", None, "asked", "Large Language Models"),
    # unsupported `current` is not invented
    Expect("R2-P3-llm-past-ok", "P3", None, "req_met", "Large Language Models", why="the relationship is unspecified: past use counts, current is not invented"),
    Expect("R2-P3-rag-past-ok", "P3", None, "req_met", "Retrieval-Augmented Generation"),
    Expect("R2-P3-agentic-past-ok", "P3", None, "req_met", "Agentic AI"),
    Expect("R2-no-current-text", "P3", None, "not_asked", "Currently", why="no requirement text asks for present use"),
    # analogy title
    Expect("R2-analogy-not-asked", "P4", None, "not_asked", "Forward Deployed Engineer", why="a comparison title is not a requirement"),
    Expect("R2-analogy-no-engineering", "P4", None, "req_not_met", "hands-on Python", why="a matching analogy title does not evidence anything"),
]

# ======================================================================================================================
# ROLE 3 (frozen run 1: one context)
# ======================================================================================================================

R3_CORE = (
    "SYNTHETIC PROFILE. FP&A Manager at Linden Consumer Goods (fictional), 2017 to present, in a large multinational consumer organization. Owns financial analysis, "
    "financial planning, annual budgeting and forecasting for two business units; runs variance analysis against budget and forecast; builds financial models, "
    "scenario analysis and sensitivity analysis for revenue, cost, headcount and investment decisions. Works with SAP as the ERP. Meaningful FP&A and business-finance "
    "ownership; partners with commercial and operations leaders (commercial judgment, stakeholder management, strong business partnering and communication) and "
    "presents financial analysis and recommendations to senior stakeholders and the CFO.",
)
R3_EXCEL_ADV = ("SYNTHETIC PROFILE. Advanced Microsoft Excel user: builds dynamic driver-based financial models with VBA macros, Power Pivot data models, array formulas and "
                "data tables for scenario and sensitivity work. Power BI dashboards for monthly management reporting (working knowledge of Power BI).",)
R3_EXCEL_BASIC = ("SYNTHETIC PROFILE. Uses Microsoft Excel for basic spreadsheets: sums, simple formulas and charts. Financial models are built by other people. Has "
                  "assembled three dashboards from templates in Power BI (working knowledge of Power BI).",)
R3_REMOTE = ("SYNTHETIC PROFILE. Based in Pune and works fully remotely; not open to hybrid or on-site arrangements.",)
R3_UNILEVER = ("SYNTHETIC PROFILE. Earlier career: Senior FP&A Analyst at Unilever, 2012 to 2017.",)
R3_AUDIT_ONLY = ("SYNTHETIC PROFILE. Statutory auditor at Pine & Co (fictional audit firm), 2012 to present. Prepares tax returns, keeps books for small clients and "
                 "processes transactions. Has had no FP&A, budgeting or forecasting responsibilities.",)
R3_AUDIT_THEN_FPA = ("SYNTHETIC PROFILE. Statutory audit and tax associate at Pine & Co (fictional audit firm), 2012 to 2016.",)
R3_TAX_ADJ = ("SYNTHETIC PROFILE. Supports the tax team with tax-planning inputs to the forecast each quarter, alongside the main FP&A work.",)

PROFILES_R3: List[Profile] = [
    Profile("Q1", "advanced Excel + working-knowledge Power BI + full FP&A", "FP&A Manager", "FP&A Manager", 2017, R3_CORE + R3_EXCEL_ADV),
    Profile("Q2", "basic Excel + working-knowledge Power BI + full FP&A", "FP&A Manager", "FP&A Manager", 2017, R3_CORE + R3_EXCEL_BASIC),
    Profile("Q3", "Q1 + fully remote (work mode)", "FP&A Manager", "FP&A Manager", 2017, R3_CORE + R3_EXCEL_ADV + R3_REMOTE),
    Profile("Q4", "Q1 + a preferred-company background", "FP&A Manager", "FP&A Manager", 2012, R3_CORE + R3_EXCEL_ADV + R3_UNILEVER),
    Profile("Q5", "exclusively audit / tax / bookkeeping, no FP&A: the exclusion", "Statutory Auditor", "Statutory Auditor", 2012, R3_AUDIT_ONLY),
    Profile("Q6", "early-career audit and tax, then substantive FP&A (qualified exclusion must NOT apply)", "FP&A Manager", "FP&A Manager", 2012, R3_AUDIT_THEN_FPA + R3_CORE + R3_EXCEL_ADV),
    Profile("Q7", "FP&A with tax-planning inputs (adjacent, must NOT be excluded)", "FP&A Manager", "FP&A Manager", 2017, R3_CORE + R3_EXCEL_ADV + R3_TAX_ADJ),
]
R3_EXCL = "Experience exclusively in statutory audit"

EXPECT_R3: List[Expect] = [
    Expect("R3-Q1-adv-excel", "Q1", None, "req_met", "advanced proficiency in Microsoft Excel", why="advanced evidence meets an advanced requirement"),
    Expect("R3-Q2-adv-excel", "Q2", None, "req_not_met", "advanced proficiency in Microsoft Excel", why="basic Excel does not meet advanced"),
    Expect("R3-Q2-excel-plain", "Q2", None, "req_met", "Microsoft Excel", why="the plain skill (no depth) is met by use of Excel"),
    Expect("R3-Q2-powerbi-wk", "Q2", None, "req_met", "Working knowledge of Power BI or a similar business intelligence/reporting platform",
           why="working knowledge is the weaker requirement: light Power BI use meets it where it does not meet advanced Excel"),
    Expect("R3-Q1-powerbi-wk", "Q1", None, "req_met", "Working knowledge of Power BI or a similar business intelligence/reporting platform"),
    # work mode: unresolved, distinct from geography
    Expect("R3-workmode-not-asked", "Q3", None, "not_asked", "hybrid", why="work mode is unresolved: never asked, never judged"),
    Expect("R3-workmode-not-asked-2", "Q3", None, "not_asked", "Working arrangement", why="and never rewritten into a requirement"),
    Expect("R3-Q3-same-as-Q1", "Q3", None, "same_verdicts_as", other="Q1", why="a remote candidate is not penalised on the requirements: work mode is not geography"),
    # preferred companies stay preferences
    Expect("R3-company-not-asked", "Q4", None, "not_asked", "Unilever", why="a preferred company is not a requirement"),
    Expect("R3-Q4-same-as-Q1", "Q4", None, "same_verdicts_as", other="Q1", why="a preferred-company background does not change a requirement verdict"),
    # the qualified exclusion
    Expect("R3-Q5-excluded", "Q5", None, "excl_present", R3_EXCL, why="exclusively audit / tax / bookkeeping, no FP&A"),
    Expect("R3-Q6-not-broadened", "Q6", None, "excl_not_present", R3_EXCL, why="audit history plus substantive FP&A: the qualification does not hold"),
    Expect("R3-Q7-not-broadened", "Q7", None, "excl_not_present", R3_EXCL, why="tax-adjacent FP&A is not the excluded profile"),
    Expect("R3-Q1-not-excluded", "Q1", None, "excl_not_present", R3_EXCL),
]

# ======================================================================================================================
# CONFLICT scenario: a small synthetic intent. Legacy says "Python required + current"; the compiled meaning is "Python required, relationship UNSPECIFIED".
# ======================================================================================================================

CONFLICT_QUOTE = "Python experience is required."
CONFLICT_LEGACY_SIGNALS = ["Currently works with Python (required)"]
CONFLICT_PROFILES: List[Profile] = [
    Profile("PY_PAST", "used Python extensively in the PAST; no longer codes", "Delivery Manager", "Delivery Manager", 2010, (
        "SYNTHETIC PROFILE. Delivery Manager at Elm Works (fictional), 2020 to present. Manages delivery schedules; no longer writes code.",
        "SYNTHETIC PROFILE. Backend Developer at Fir Systems (fictional), 2012 to 2020 (ended in 2020). Used Python extensively every day to build services.")),
    Profile("PY_NOW", "uses Python today", "Backend Developer", "Backend Developer | Python", 2015, (
        "SYNTHETIC PROFILE. Backend Developer at Fir Systems (fictional), 2015 to present. Uses Python every day to build and run services.",)),
    Profile("PY_NONE", "no Python at all", "Accountant", "Accountant", 2015, (
        "SYNTHETIC PROFILE. Accountant at Gum & Co (fictional), 2015 to present. Prepares ledgers and reconciliations. Has never programmed.",)),
]
CONFLICT_COMPANY_QUOTE = "People from Quuxcorp are preferred."
CONFLICT_COMPANY_LEGACY = ["Works at Quuxcorp"]
CONFLICT_COMPANY_PROFILES: List[Profile] = [
    Profile("NO_QUUX", "no Quuxcorp background", "Backend Developer", "Backend Developer", 2015, (
        "SYNTHETIC PROFILE. Backend Developer at Fir Systems (fictional), 2015 to present. Builds services.",)),
]

# ======================================================================================================================
# ADMISSION scenarios (deterministic; fed by the real Judge's judgments where the Judge was run)
# ======================================================================================================================

# (key, title, headline, start_year): the level facts the evidence builder reads. R1 PATH A: Lead + Senior PREFERRED. PATH B: Lead REQUIRED, 6+ years.
ADMISSION_R1: List[Tuple[str, str, str, int]] = [
    ("lead", "Lead Data Analyst", "Lead Data Analyst", 2016),
    ("senior", "Senior Data Analyst", "Senior Data Analyst", 2016),
    ("director", "Director of Legal Operations", "Legal operations", 2016),
    ("junior", "Junior Data Analyst", "Junior Data Analyst", 2016),
    ("no_level", "Data Analyst", "Data Analyst", 2016),
    ("short_tenure", "Lead Data Analyst", "Lead Data Analyst", 2024),
]

# ======================================================================================================================
# CONFLICT expectations (from the review brief section 5: legacy "Python required + current" vs compiled "Python required, relationship unspecified": compiled wins)
# ======================================================================================================================

EXPECT_CONFLICT: List[Expect] = [
    Expect("CF-compiled-asks-plain-python", "PY_PAST", "compiled_vs_legacy", "asked", "Python", why="the compiled meaning is what is asked"),
    Expect("CF-legacy-sentence-never-sent", "PY_PAST", "compiled_vs_legacy", "not_asked", "Currently", why="the legacy 'current' sentence never reaches the model"),
    Expect("CF-past-python-meets-compiled", "PY_PAST", "compiled_vs_legacy", "req_met", "Python", why="past Python meets an UNSPECIFIED relationship: current is not reconstructed from the legacy intent"),
    Expect("CF-current-python-meets-compiled", "PY_NOW", "compiled_vs_legacy", "req_met", "Python"),
    Expect("CF-no-python-fails-compiled", "PY_NONE", "compiled_vs_legacy", "req_not_met", "Python"),
    Expect("CF-control-legacy-would-reject-past", "PY_PAST", "legacy_only_control", "req_not_met", CONFLICT_LEGACY_SIGNALS[0],
           why="CONTROL: with only the legacy sentence the same candidate is rejected: the compiled path is what changed the outcome"),
    Expect("CF-control-legacy-accepts-current", "PY_NOW", "legacy_only_control", "req_met", CONFLICT_LEGACY_SIGNALS[0]),
    Expect("CO-compiled-company-not-asked", "NO_QUUX", "compiled_vs_legacy", "not_asked", "Quuxcorp", why="a preferred company is not a requirement: the legacy hard line is not asked"),
    Expect("CO-control-legacy-asks-company", "NO_QUUX", "legacy_only_control", "asked", "Quuxcorp", why="CONTROL: the legacy intent would have asked it as a requirement"),
]
