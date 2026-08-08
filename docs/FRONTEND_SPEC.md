# RecruiterAI Frontend Specification

Version: 1.0

---

# Product Vision

RecruiterAI is not an ATS.

RecruiterAI is an AI-powered Recruiter Workbench.

The recruiter remains in control of every decision.

AI assists.

Recruiters decide.

Every screen should reinforce this philosophy.

---

# Primary Workflow

The application revolves around a single workflow.

Job Description

↓

AI parses JD

↓

Recruiter reviews Search Brief

↓

Recruiter edits Search Brief

↓

Candidate sourcing

↓

Candidate comparison

↓

Resume enrichment

↓

Recruiter scoring

↓

Export

There should never be multiple disconnected workflows.

Everything belongs to this pipeline.

---

# Design Principles

Minimal.

Professional.

Fast.

No marketing website styling.

No unnecessary gradients.

No flashy animations.

The interface should feel closer to Linear, GitHub and Cursor than Salesforce.

---

# Color Palette

Background
#0F172A

Panels
#1E293B

Secondary Panels
#334155

Primary
#3B82F6

Primary Hover
#2563EB

Success
#10B981

Warning
#F59E0B

Danger
#EF4444

Border
#475569

Primary Text
#F8FAFC

Secondary Text
#CBD5E1

Muted Text
#94A3B8

---

# Typography

Font

Inter

Headings

600-700 weight

Body

400

Numbers

tabular where possible

---

# Spacing

Use an 8px spacing system.

4

8

16

24

32

48

64

Never use arbitrary spacing.

---

# Border Radius

Inputs

8px

Cards

12px

Dialogs

16px

Buttons

8px

---

# Shadows

Very subtle.

Prefer borders over shadows.

---

# Icons

Lucide Icons only.

---

# Layout

Desktop first.

Maximum width

1600px

Two-panel application.

Left

Search Workspace

Right

Candidate Workspace

Both panels remain visible.

Do not navigate between pages.

---

# Left Panel

Contains:

Job Description

Parse JD

Editable Search Brief

Provider Selection

Search Controls

Search Progress

Search Diagnostics

Everything required before sourcing.

---

# Right Panel

Contains:

Candidate Table

Candidate Preview

Resume

Profile

Explanation

Actions

Export

Everything after sourcing.

---

# Candidate Table

Columns

Score

Name

Title

Company

Location

Experience

Skills

Provider

Status

Actions

Sticky header.

Sortable columns.

Resizable.

---

# Candidate Details

Selecting a candidate opens a detail drawer.

Tabs

Overview

Resume

LinkedIn

Enrichment

Notes

History

Raw Provider Data

---

# Resume Upload

Every candidate should support resume upload.

Store

Resume

Filename

Upload Date

Resume Status

Resume Parse Status

Future integrations will parse resumes automatically.

Design the UI now.

---

# Search Brief

Editable.

Never read-only.

The recruiter must always be able to modify:

Role

Titles

Skills

Experience

Locations

AI Flags

Ranking

Company preferences

---

# Loading

Every long operation should have progress.

Examples

Parsing JD...

Searching CrustData...

Ranking candidates...

Generating explanations...

Never freeze the interface.

---

# Empty States

Never display blank tables.

Always explain what the recruiter should do next.

---

# Validation

Inline.

Never use popup alerts.

---

# Accessibility

Keyboard navigation.

Visible focus states.

WCAG AA colors.

---

# Responsiveness

Desktop

1600

1440

1280

Tablet

1024

No mobile implementation yet.

---

# Components

Cards

Buttons

Inputs

Text Areas

Multi Select

Badge

Tabs

Drawer

Modal

Toast

Data Table

Progress

Stepper

Upload

Every component should be reusable.

---

# Future Features

Harvest enrichment

LinkedIn enrichment

Resume parsing

ATS sync

Candidate CRM

Projects

Outreach

Voice AI

Conversation history

Interview feedback

Design the architecture so these can be added without redesigning the application.

---

# What NOT to build

Do not create a landing page.

Do not create authentication.

Do not build dashboards.

Do not create marketing pages.

Do not create generic admin templates.

Focus entirely on the Recruiter Workbench.