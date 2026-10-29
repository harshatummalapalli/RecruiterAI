# Golden-set net

The regression net that makes "new role, new issue" stop. Every architecture
change runs against these real roles before it ships.

- `golden.py` — `GoldenRole` (notes + boundary + `expect`) and `all_roles()`.
- `fixtures/` — one file per real role. Each encodes the failures a real run
  exposed, so they can never silently return.
- `assertions.py` — pure checks over a `RoleModel` (and, later, over search
  results). `check_role_model(model, expect)` returns the failures (empty = pass).

## How it grows

1. **Now (RoleModel level):** a fixture's `expect` is the contract the Intake
   agent must satisfy — correct cities, seniority floor, role-defining
   capability, disclosed limitations.
2. **As agents land:** add result-level assertions (location spread of the
   retrieved pool, no good-senior exclusions, top-5 evidence quality) and an
   end-to-end runner `notes+boundary -> Intake -> Briefing -> ... -> findings`.
3. **Offline first:** retrieved pools are recorded as fixtures so the net runs
   with no CrustData credits on every change; one measured live run per
   milestone, with explicit permission.

Run: `pytest recruiter/tests -q`
