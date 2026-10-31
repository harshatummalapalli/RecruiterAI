"""Bridge — the seam between the new `recruiter/` engine and the OCI backend.

Phase 0: persistence (RoleModel session + confirmation stores over SearchStore).
Phase 1: translate (engine objects -> frontend contract) + IntakeService (the
7-agent brain behind the routes). `build_intake_service` wires the live pipeline.
"""


def build_intake_service(org: str = "default"):
    """The live IntakeService: the real CrustData/Claude pipeline behind the
    frontend's intake/search contract. Lazy imports so the engine only loads when
    the new-engine path is actually enabled."""
    from backend.bridge.intake_service import IntakeService
    from recruiter.live import build_live_pipeline
    return IntakeService(build_live_pipeline(org=org))
