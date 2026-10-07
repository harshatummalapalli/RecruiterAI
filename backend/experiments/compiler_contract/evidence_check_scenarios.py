"""SYNTHETIC scenarios for the Evidence Check validation (real Judge model; three scenarios; 6 runs each; no tuning between runs).

Written ONCE, by hand, before any run of this phase, and not edited afterwards. Profiles are invented text (every profile is labelled SYNTHETIC PROFILE; fictional
employers); no real person or candidate data. Profiles reused from the earlier real-Judge phase keep their exact text.

  SCENARIO A  Role 1 negative:     a SOC candidate (PRESENT), a cyber-incident / data-breach reviewer with no security-operations evidence (NOT_PRESENT), a data
                                   analyst at a security-software company (NOT_PRESENT: the exclusion is not broadened to "works for a security company"), and a profile
                                   with no description of work at all (INSUFFICIENT_EVIDENCE: not silently NOT_PRESENT)
  SCENARIO B  Role 2 proficiency:  hands-on Python and hands-on Java stated separately, in one sentence, and each alone beside a merely-familiar other language
  SCENARIO C  Role 3 proficiency:  advanced Excel and working-knowledge Power BI, each alone and together, evaluated independently
"""

from __future__ import annotations

from typing import Dict, List

from backend.experiments.compiler_contract.real_judge_scenarios import (R1_COMMON, R1_DOMAIN, R1_SOC, R3_CORE, R3_EXCEL_ADV, R3_EXCEL_BASIC, Expect, Profile, PROFILES_R2)

by_key = {p.key: p for p in PROFILES_R2}

# ---------------------------------------------------------------------------------------------------------------- A
PROFILES_A: List[Profile] = [
    Profile("E", "SOC / security-operations work", "Lead Data Analyst", "Security operations | data analysis", 2018, R1_COMMON + R1_SOC),
    Profile("A", "cyber incident review and data breach analysis; no security-operations evidence", "Lead Data Analyst", "Lead Data Analyst | review operations", 2018, R1_COMMON + R1_DOMAIN),
    Profile("G", "data analyst at a security-software company: security is the employer's field, not the candidate's work", "Senior Data Analyst",
            "Data Analyst | cybersecurity software company", 2018, (
                "SYNTHETIC PROFILE. Senior Data Analyst at Bastion Software (fictional), a cybersecurity software company, 2018 to present. Writes SQL queries and Python "
                "scripts for sales and finance dashboards. Completed the company's annual security-awareness training and reviews security-related support tickets for "
                "trends.",)),
    Profile("H", "no description of work at all (title and headline only)", "Lead Data Analyst", "Data Analyst", 2018, ()),
]
SOC = "Generic cybersecurity or security-operations backgrounds are not equivalent"
FIRM = "A strong SQL/Python analyst working at a security firm"

EXPECT_A: List[Expect] = [
    Expect("A-E-present", "E", "PATH A", "excl_state", SOC, other="PRESENT", why="explicit SOC / security-operations work"),
    Expect("A-A-not-present", "A", "PATH A", "excl_state", SOC, other="NOT_PRESENT", why="cyber incident / breach review is the domain, not security operations"),
    Expect("A-G-not-broadened", "G", "PATH A", "excl_state", SOC, other="NOT_PRESENT", why="works for a security company / mentions security / has security-adjacent duties is NOT the exclusion"),
    Expect("A-H-insufficient", "H", "PATH A", "excl_state", SOC, other="INSUFFICIENT_EVIDENCE", why="a profile with no description of work cannot clear the exclusion; it must not read as NOT_PRESENT"),
]
# informational (not part of the acceptance): the separate, broader exclusion that G literally is
INFO_A: List[Expect] = [Expect("A-G-firm-info", "G", "PATH A", "excl_state", FIRM, other="PRESENT", why="informational: this exclusion names the security-firm analyst")]

# ---------------------------------------------------------------------------------------------------------------- B
PROFILES_B: List[Profile] = [
    Profile("B0", "hands-on Python and Java in ONE sentence (the case the earlier review pass downgraded)", by_key["P1"].title, by_key["P1"].headline, 2017, by_key["P1"].passages),
    Profile("B1", "hands-on Python and hands-on Java, stated separately", "Backend Engineer", "Backend Engineer | Python, Java", 2017, (
        "SYNTHETIC PROFILE. Backend Engineer at Alder Systems (fictional), 2017 to present. Writes production Python services every day and maintains the team's Python "
        "data pipelines.",
        "SYNTHETIC PROFILE. Also builds and operates production Java services for the payments platform, owning their deployment and on-call.")),
    Profile("B2", "hands-on Python; Java only from a university course", "Backend Engineer", "Backend Engineer | Python", 2017, (
        "SYNTHETIC PROFILE. Backend Engineer at Alder Systems (fictional), 2017 to present. Writes production Python services every day and maintains the team's Python "
        "data pipelines.",
        "SYNTHETIC PROFILE. Studied Java in a university course and is familiar with the syntax. Has never used Java in a job.")),
    Profile("B3", "hands-on Java; Python only from a university course", "Backend Engineer", "Backend Engineer | Java", 2017, (
        "SYNTHETIC PROFILE. Backend Engineer at Alder Systems (fictional), 2017 to present. Builds and operates production Java services for the payments platform, "
        "owning their deployment and on-call.",
        "SYNTHETIC PROFILE. Studied Python in a university course and is familiar with the syntax. Has never used Python in a job.")),
]
HJ, HP = "hands-on Java", "hands-on Python"
EXPECT_B: List[Expect] = [
    Expect("B0-java", "B0", None, "req_met", HJ, why="Java is named in the quote and used in production"),
    Expect("B0-python", "B0", None, "req_met", HP),
    Expect("B1-java", "B1", None, "req_met", HJ, why="Java evidence is the Java passage"),
    Expect("B1-python", "B1", None, "req_met", HP, why="Python evidence is the Python passage"),
    Expect("B2-python", "B2", None, "req_met", HP),
    Expect("B2-java", "B2", None, "req_not_met", HJ, why="familiar != hands-on; Python evidence cannot be reused for Java"),
    Expect("B3-java", "B3", None, "req_met", HJ),
    Expect("B3-python", "B3", None, "req_not_met", HP, why="familiar != hands-on; Java evidence cannot be reused for Python"),
]

# ---------------------------------------------------------------------------------------------------------------- C
PROFILES_C: List[Profile] = [
    Profile("C1", "advanced Excel + working-knowledge Power BI", "FP&A Manager", "FP&A Manager", 2017, R3_CORE + R3_EXCEL_ADV),
    Profile("C2", "basic Excel + working-knowledge Power BI", "FP&A Manager", "FP&A Manager", 2017, R3_CORE + R3_EXCEL_BASIC),
    Profile("C3", "basic Excel + ADVANCED Power BI (a deeper tool still meets the weaker depth)", "FP&A Manager", "FP&A Manager", 2017, R3_CORE + (
        "SYNTHETIC PROFILE. Uses Microsoft Excel for basic spreadsheets: sums, simple formulas and charts.",
        "SYNTHETIC PROFILE. Builds advanced Power BI solutions: DAX measures, star-schema semantic models, incremental refresh and row-level security for monthly "
        "management reporting.")),
    Profile("C4", "advanced Excel, no Power BI at all", "FP&A Manager", "FP&A Manager", 2017, R3_CORE + (
        "SYNTHETIC PROFILE. Advanced Microsoft Excel user: builds dynamic driver-based financial models with VBA macros, Power Pivot data models, array formulas and data tables "
        "for scenario and sensitivity work.",)),
]
XL, PBI = "advanced proficiency in Microsoft Excel", "Working knowledge of Power BI or a similar business intelligence/reporting platform"
EXPECT_C: List[Expect] = [
    Expect("C1-excel", "C1", None, "req_met", XL, why="advanced evidence meets advanced"),
    Expect("C1-pbi", "C1", None, "req_met", PBI),
    Expect("C2-excel", "C2", None, "req_not_met", XL, why="basic Excel is not advanced"),
    Expect("C2-pbi", "C2", None, "req_met", PBI, why="working knowledge is the weaker depth"),
    Expect("C3-excel", "C3", None, "req_not_met", XL, why="Power BI depth cannot be assigned to Excel"),
    Expect("C3-pbi", "C3", None, "req_met", PBI),
    Expect("C4-excel", "C4", None, "req_met", XL),
    Expect("C4-pbi", "C4", None, "req_not_met", PBI, why="Excel depth cannot be assigned to Power BI"),
]

SCENARIOS = {"A": (PROFILES_A, EXPECT_A + INFO_A, ("R1", "PATH A")), "B": (PROFILES_B, EXPECT_B, ("R2", "ctx")), "C": (PROFILES_C, EXPECT_C, ("R3", "ctx"))}
