# C0 integration change request — Research Lab v1

Status: OPEN. Owner: C0. This domain branch does not edit C0-owned paths.

Required before integration can pass:

1. Mount `ResearchAPI.dispatch` under the shared authenticated server route and construct `CoreRefs` only from the authenticated MIS session or machine identity.
2. Inject `ResearchOperationsAdapter` backed by real C0 implementations of `GovernedResearchOperationsPort`; do not use descriptors or fallback success.
3. Register `ResearchLabExtension.tsx` in the real AppShell through `TemplateSDKPort`, and exercise its list/create/detail/action/error/recovery routes in browser E2E.
4. Register `templates.research_lab.cli:main` beneath the shipped `agentops template research-lab` CLI with the same operations adapter.
5. Implement `ResearchCorePort`, `CoreMigrationTransactionPort`, `CoreRuntimeDomainPort`, export/citation evidence ports and transactional outbox calls over MIS Core with exact workspace/project/Run readback.
6. Run cross-template isolation, install/upgrade/rollback/uninstall and real runtime regression at the exact integration head.
7. The domain `register_with_sdk` now registers repositories, workflows, teams,
   skills, tools, policies, evaluators, UI, reports, API routes, CLI commands,
   fixtures, testing hooks and exporters. C0 must reject partial registration and
   read back all declarations before activation.
8. C0 receipt implementations must produce canonical, MIS-Core-authoritative,
   cryptographically signed, purpose-separated receipts with Audit IDs, trusted
   key IDs, rotation/revocation support and every binding required by the C1
   adapters. Signing material must remain outside caller/domain payloads. A
   truthy or merely 64-hex receipt hash is insufficient.
9. Runtime start/resume readback must attest the complete receipt document; a
   completed resume must also attest atomic domain output and outbox commit.
   Migration LifecycleReceipt readback requires its own document attestation.
10. Register and read back all 41 concrete API method/path declarations; mount
    the React extension with real popstate/deep-link navigation browser tests.
11. Governed packaging must stamp `provenance.source_commit` from the exact
   reviewed commit and recompute manifest integrity before signing. The all-zero
   source commit in this staged candidate is an intentional non-promotable
   placeholder.

Until this change request is merged and verified, API/CLI/UI/runtime/migration declarations in C1 are integration-ready domain adapters, not a claim of mounted product availability.
