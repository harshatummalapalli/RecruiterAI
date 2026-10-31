"""Bridge — the seam between the new `recruiter/` engine and the OCI backend.

Phase 0: persistence only (the RoleModel session + confirmation stores reuse the
existing file-JSON SearchStore). The route-contract translation (engine objects
-> frontend SearchIntent/result/SearchResponse shapes) lands here in Phase 1.
"""
