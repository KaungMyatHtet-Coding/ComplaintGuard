# Project Task Board

This lightweight board is optimized for one active developer. `PROJECT_PLAN.md` remains the schedule and source of truth.

## Backlog

- Confirm which official team members, if any, will review or present later.
- Choose the repository remote/hosting organization when collaboration begins.

## In Progress

- None.

## Review

- None.

## Done

### Day 1

- Read `PROJECT_PLAN.md` and freeze the title, problem, users, departments, must-haves, and exclusions.
- Create the Git repository structure, root README, scope, task board, safe ignore rules, and placeholder environment template.
- Record one active developer as owner with self-review checkpoints.

### Day 2

- Confirm `D:\ComplaintGuard` and branch `chore/day-2-architecture` before changes.
- Audit the installed local software without installing dependencies first.
- Scaffold the npm-based Next.js frontend with TypeScript, App Router, Tailwind CSS, ESLint, and `src`.
- Keep the generated page as a simple environment-ready placeholder with no ComplaintGuard features.
- Create and verify the root Python 3.12 `.venv`.
- Record lightweight future Python development dependencies without installing them.
- Document the zero-cost architecture, offline training flow, live prediction flow, data boundaries, and free-tier limitations.
- Document local setup and Windows PowerShell troubleshooting.
- Verify the frontend with ESLint, a production build, and an HTTP 200 development-server response.
- Confirm `.venv`, `node_modules`, `.next`, local environment files, and raw CFPB data are ignored.
- Review all Day 2 files and scan trackable content for likely secrets; none were found.
- Record the unresolved moderate transitive PostCSS advisory without applying npm's breaking forced downgrade.
- Confirm the Firebase project is on Spark with no billing account attached.
- Confirm free Vercel and Hugging Face account logins work.

### Day 3

- Reconfirm branch `data/dataset-profile` and a clean starting worktree.
- Validate the 1,420,663,360-byte CFPB archive with ZIP CRC testing and SHA-256.
- Confirm `data/raw/` is ignored and extract the single CSV member without changing the archive.
- Profile all 17,034,951 rows in 171 chunks without emitting narratives or complaint-level records.
- Record snapshot metadata, schema, logical types, missing values, safe aggregate distributions, intended columns, and privacy limitations.
- Document the source data dictionary and reproducible local data procedure.
- Record the initial mapping approach without creating the mapping or starting cleaning/model work.
- Perform the owner self-review and retain all Day 3 changes uncommitted for review.

## Day 2 completion rule

Move verification to Done only after `npm run lint` and `npm run build` pass and the repository audit confirms that secrets and generated/local files will not be committed. Account availability is confirmed, but credentials and service integration remain deferred to their scheduled project days.

## Day 3 completion rule

Move Day 3 work to Done only after archive validation, extracted-size verification, a complete chunked profile, documentation review, ignore checks, and a scan confirming that tracked outputs contain no narratives or complaint-level records. Cleaning, sampling, translation, feature engineering, mapping implementation, and model work remain deferred.
