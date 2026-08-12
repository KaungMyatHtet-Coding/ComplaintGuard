# Day 32 Final Packaging Evidence

## Repository and environment state

- Verification date: 2026-08-12 (Asia/Rangoon).
- Starting branch: `test/day31-final-e2e-verification` at
  `d3419c03e99ec73cb98364615a7990c2705c99d2`.
- Updated local `main` and `origin/main`:
  `bba7e1c6a7aae2ac2e266c673f960d23535f1887`.
- Working branch: `docs/day32-final-packaging`.
- Initial worktree: clean. Ignored local dependencies, caches, model files,
  logs, and an old archive were present but not tracked.
- Supported claim: ComplaintGuard is a verified local Firebase-emulator
  complaint-management prototype. It is not production-ready or publicly
  deployed.

## Documentation audit findings recorded before correction

| ID | File or area | Evidence-supported issue | Planned minimal correction |
|---|---|---|---|
| D32-01 | `README.md` | Status still says Days 1-19 are implemented and Day 20 is in progress. | Replace with the merged Day 31 local-verification status. |
| D32-02 | `README.md` | It is not an evaluator-friendly entry point and omits an integrated role, workflow, architecture, setup, test, demo, and limitation summary. | Consolidate the entry-point information and link detailed evidence. |
| D32-03 | `README.md` | Model summary omits balanced accuracy and weighted F1. | Publish the locked metrics without changing evidence. |
| D32-04 | `docs/local_setup.md` | Fresh-machine commands use `npm install` even though lockfiles exist. | Use `npm ci` and distinguish clean setup from an already-installed workspace. |
| D32-05 | `docs/architecture.md` | The opening table and diagram describe Vercel and Hugging Face hosting as the final architecture despite the later local-only implementation boundary. | Mark public hosting as unverified planned architecture and make the verified local topology primary. |
| D32-06 | Demo documentation | `docs/demo_guide.md` is detailed operating evidence but there is no concise 5-8 minute evaluator flow. | Add `docs/final_demo_guide.md` that links to the detailed guide. |
| D32-07 | Submission packaging | No current checklist separates repository evidence from manual PowerPoint, teacher requirements, and repository-access tasks. | Add `docs/submission_checklist.md` with evidence-based checkbox states. |
| D32-08 | Project status | `docs/task_board.md` stops at Day 31. | Add Day 32 results only after the checks are executed. |
| D32-09 | Internal links and paths | No current whole-document path/link audit is recorded. | Run a repository Markdown reference check and record exact results. |
| D32-10 | Clean setup | Existing evidence verifies the active environment, not a dependency installation from a clean clone. | Verify an isolated tracked-file package and record exactly what can and cannot be reproduced locally. |
| D32-11 | PowerPoint | No verified editable PowerPoint is tracked; Day 29 COM automation was blocked. | Keep the PowerPoint checklist item open and do not create or edit one. |

## Files reviewed and updated

- Reviewed the project plan, root guidance, README, Day 30/31 evidence, task
  board, architecture, setup, demo, dataset/data dictionary, model evaluation
  and finalization, Myanmar pipeline, claim/evidence, release, security/access,
  Firestore schema, and final-report documentation.
- Updated `README.md` as the evaluator entry point.
- Updated `docs/architecture.md` to make the verified local topology primary
  and public hosting explicitly unverified.
- Updated `docs/local_setup.md` to use lockfile-based `npm ci` for a clean setup.
- Added `docs/final_demo_guide.md` and `docs/submission_checklist.md`.
- Updated `docs/task_board.md` with this evidence-supported Day 32 result.

## Setup and reproducibility verification

- Created an isolated package under `D:\ComplaintGuard\tmp`, expanded a
  `git archive` of the base commit, and verified all required manifests,
  lockfiles, environment example, Firebase configuration, seed, verification
  wrapper, and evaluation artifact were present. The archive contained 222
  tracked files and was 3,604,480 bytes. The temporary package was removed and
  the cleanup check returned true.
- The first audit used the incorrect expected path `firebase/firebase.json` and
  reported one missing file. Inspection confirmed the repository-defined file
  is the root `firebase.json`; the corrected check found zero missing files.
- Existing dependency installations and runtime prerequisites were verified on
  the current machine. A brand-new network dependency download and separate
  Python environment were not performed, so this is a clean tracked-package
  equivalence check rather than a claim of fully independent clean-clone
  installation.
- Node `v22.17.0`, npm `10.9.2`, Java `24.0.2`, and Firebase CLI `14.27.0` were
  available. The ignored model and similarity artifacts matched their hashes.
- The documented emulator seed and complete application workflow ran through
  the repository harness. Its synthetic test records were isolated and the
  harness released ports 3000, 4400, 4500, 8000, 8185, 9099, and 9150.

### Firestore startup diagnosis

The first two `firebase\npm.cmd test` attempts stopped before tests with
`Firestore Emulator did not listen on 127.0.0.1:8185`. The ports were free, and
the configuration consistently selected project `demo-complaintguard`, root
`firebase.json`, `firebase/firestore.rules`, Auth 9099, and Firestore 8185.

A direct debug launch proved Firebase CLI could find Java and start Firestore
emulator v1.19.8. It reported both emulators ready after approximately 11
seconds on the configured ports. The interrupted diagnostic left a Firebase
CLI process and its two Java children alive but not listening; their command
lines contained only this repository's emulator JAR, rules path, project, and
ports. Those confirmed diagnostic processes were stopped, and the ports were
verified free. A second bounded diagnostic created the same identifiable child
set and it was cleaned in the same scoped manner.

After cleanup, the unchanged repository harness passed. This establishes that
Java, rules, paths, ports, and the 30-second readiness limit are viable. The
original hidden `Start-Process` attempts did not preserve launcher output, so
their lower-level transient cause cannot be proven beyond environmental child-
process/launcher state. No rule, port, expectation, source, or harness change
was justified or made.

## Exact commands and results

| Command | Result |
|---|---|
| `frontend\npm.cmd test` | Pass: 19 files, 74 tests. |
| `frontend\npm.cmd run typecheck` | Pass: strict TypeScript. |
| `frontend\npm.cmd run lint` | Pass: no ESLint findings. |
| `frontend\npm.cmd run build` | First sandboxed attempt: `EPERM` opening ignored `.next/trace`; unchanged rerun with normal filesystem access passed Next.js 16.2.10 compilation, TypeScript, and six generated static pages covering `/`, `/_not-found`, `/dashboard`, and `/login`. |
| `ml-api\..\.venv\Scripts\python.exe -m pytest tests -p no:cacheprovider` | Pass: 107 passed, 7 standalone emulator skips, 1 expected xfail, 40 warnings. |
| `firebase\npm.cmd test` | First two attempts blocked before tests on Firestore readiness. After scoped orphan cleanup, pass: 4 rules, 1 Auth, 7 adapters, 3 Playwright tests. Expected permission-denied logs came from negative rules cases. |
| Focused evaluation/similarity pytest command | Pass: 9 passed, 3 dependency deprecation warnings. |
| Model/evaluation SHA-256 checks | Pass: source/generated evidence `F6B3A872...8DAE06`, model `BAFC086F...F953D5`, similarity index `9DA43206...377C2`. |
| Markdown relative-link scan | Pass: 0 broken local links. |
| Tracked secret-signature scan | Pass: Git grep exit 1, no matches. |
| Forbidden tracked-artifact scan | Pass: 0 findings across 222 tracked files. |
| `git diff --check` | Pass. |

The successful frontend and standalone backend suites were not rerun after the
resume because only documentation changed and the user explicitly requested
that already-successful expensive checks not be repeated. The focused model
tests and Firebase harness were the remaining required executable gates.

## Repository hygiene

- No raw CFPB CSV/ZIP, model binary, private key, credential-bearing `.env`,
  emulator state, cache, log, build output, temporary screenshot/archive,
  generated PowerPoint, or real customer record is tracked.
- The only non-ignored untracked files are the three new Day 32 documents.
- Local ignored items include `.venv`, Node dependencies, `.next`, Firebase
  local state/logs, generated models, root `firestore-debug.log`, and the old
  `phase2a_changes.zip`. They are excluded from the proposed commit.
- The Markdown scan found zero broken relative links. Pattern scans cannot
  prove absence of every conceivable secret, so manual review remains required.

## Included and excluded artifacts

Included in the proposed Day 32 commit: README/setup/architecture corrections,
Day 32 evidence, the concise final demo guide, submission checklist, and the
Day 32 task-board entry.

Excluded: raw CFPB data, local model and similarity binaries, `.env.local`,
generated credentials, emulator state/logs, dependency/build caches, temporary
archives, real customer data, and a PowerPoint. The privacy-reviewed Day 27 PNG
screenshots and presentation outline remain existing tracked evidence; no image
or presentation artifact changed on Day 32.

## Remaining limitations

- A full independent clean-clone dependency installation was not performed;
  the isolated tracked-package completeness check and the existing machine's
  full runtime verification are the closest safe equivalent.
- The complete historical scripts suite remains unavailable in `.venv` because
  Matplotlib is absent; Day 32 reran the nine focused model-evidence tests.
- Browser evidence uses headless Chrome and automated 390 x 844 coverage, not a
  physical device, screen reader, or multi-browser manual session.
- Myanmar automatic classification remains unreliable and manual-review only.
- Production Firebase, public deployment, retention/deletion, rate limiting,
  monitoring, recovery, admin operations, and security certification remain
  unverified or unimplemented.
- No verified editable PowerPoint is present. Team/member fields, repository
  access, teacher-specific requirements, rehearsal, and final upload require
  manual completion.

## Submission-readiness conclusion

The tracked package, documentation references, frozen evidence, application
checks, security/isolation harness, and repository hygiene passed in the
supported local-emulator scope. ComplaintGuard is a verified local Firebase-
emulator prototype ready for evaluator packaging and demonstration. It is not
production-ready or publicly deployed. Manual submission and presentation
items listed in `docs/submission_checklist.md` remain open.
