# Day 20 Release and Submission Checklist

Checked items must have current-worktree evidence. “Incomplete” items remain
explicitly outside the supported local academic demo.

## Academic submission

- [x] Final report reconciles every numeric claim with committed evidence.
- [x] Presentation outline contains 10–12 slides and bilingual speaker notes.
- [x] Dataset source, cleaning, EDA, mapping, algorithm and limitations are explained.
- [x] Accuracy, macro/weighted metrics, per-department evidence and confusion matrix are included.
- [x] References contain only locally verifiable authoritative sources; unresolved details are marked for verification.
- [x] Claim-to-evidence matrix and final test report are complete.

## Environment and demo readiness

- [x] Node, npm, Python `.venv`, Java and configured Chrome are available.
- [x] Frontend and Firebase dependencies already exist; nothing was installed for finalization.
- [x] Frozen model exists and matches its documented hash.
- [ ] Optional Myanmar cache availability is checked without exposing its path contents.
- [x] Four-terminal startup succeeds in documented order for both accepted Day 28 local-emulator rehearsals.
- [x] API health reports model v1 loaded through tested startup/readiness behavior.
- [x] Seeded identity/password file remains ignored and off-screen.
- [x] Customer, department staff and manager flow is exercised with synthetic text by Playwright.
- [x] Myanmar example remains manual-review only in focused backend tests.

## Privacy and security

- [x] No `.env`, seed credentials, tokens, service-account files, private keys or passwords are tracked.
- [x] No raw/cleaned CFPB narrative or raw Complaint ID is exposed.
- [x] Day 27 screenshots contain only synthetic local-emulator data and passed manual original-resolution inspection.
- [x] Redaction is described as PII reduction, not anonymization.
- [x] Operational complaint text is described as sensitive.
- [x] UI, FastAPI and Firestore authorization layers are distinguished.
- [x] Emulator evidence is not described as production certification.
- [x] Retention, rate limiting, monitoring, recovery and audit limitations are explicit.

## Artifact integrity

- [x] Day 18 source and frontend-generated JSON hashes match.
- [x] Day 18 artifact parser/CSV reconciliation tests pass.
- [x] Local frozen model hash matches when present.
- [x] Local similarity-index hash matches when present.
- [x] Day 17/18 artifacts, datasets, mappings, model and routing code are unchanged.

## Mandatory test gates

- [x] Frontend Vitest suite passes.
- [x] TypeScript passes.
- [x] ESLint passes.
- [x] Next.js production build passes.
- [x] Focused evaluation/similarity tests pass.
- [x] Backend suite passes; emulator-dependent skips are explained if run outside emulators.
- [x] Firebase rules, adapters and Playwright E2E pass, or an exact environmental blocker is recorded.
- [x] Ruff check passes.
- [x] Ruff format check passes.
- [x] Complete root scripts suite passes in `.venv`, or its exact missing-dependency blocker is recorded without substitution.
- [x] Final verification wrapper reproduces expected mandatory results with exit code 0.

## Documentation and Git safety

- [x] README and current setup no longer describe the project as Day 2/planned.
- [x] Days 15, 16, 19 and 20 statuses are accurate.
- [x] Admin shell and deployment limitations are explicit.
- [x] Strict UTF-8 scan passes.
- [x] Secret/sensitive-data and tracked-large-file audits pass.
- [x] `git diff --check` passes.
- [x] Every changed file belongs to Day 20 finalization or a defect found by its mandatory integration audit.
- [x] Ignored data/model/index/cache/dependency/build files remain untracked.

## Screenshot/presentation gate

- [x] Emulator/browser workflow passed before capture in the verified local-emulator development session.
- [x] No credential, token, environment value, terminal secret, real narrative or raw Complaint ID is visible.
- [x] Every image is manually inspected at original resolution.
- [x] Screenshot captions identify synthetic local-emulator data.
- [ ] No demo video is committed.

If these gates cannot all be proven, retain placeholder screenshot descriptions
in `presentation/slide_outline.md` rather than creating images.

## Explicitly incomplete

- [ ] Public frontend deployment
- [ ] Public ML API deployment
- [ ] Production Firebase/rules verification
- [ ] QR code and mobile public-URL test
- [ ] Approved retention/deletion workflow
- [ ] Admin operational/administration functions
- [ ] Live historical-neighbor search
- [ ] Production monitoring, rate limiting, disaster recovery or independent security audit
