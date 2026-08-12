# Day 30 Targeted UI Audit and Verification

## Scope and baseline

- Branch: `fix/day30-ui-polish`
- Verified base: `main` at `6368e78dd4ffa96906be1149e96ccae3381a2c20`
- Initial worktree: clean, including no untracked files reported by Git
- Day 29 result: `presentation/day29-final-editable-deck` points to the same
  commit as `main`; it has no commit, diff, or tracked PowerPoint output.
- Routes: `/`, `/login`, and the role-resolved `/dashboard`; the dashboard
  renders separate customer, staff, manager, and intentionally limited admin
  shells rather than separate role URLs.

This work preserves the frozen TF-IDF plus Multinomial Naive Bayes classifier,
Day 18 evidence, local-emulator boundary, manual review, manager override, and
all Firestore/backend authorization contracts.

## Reproducible audit findings

| Route or component | Role | Problem | Expected behavior | Actual behavior before Day 30 | Severity | Minimal fix |
|---|---|---|---|---|---|---|
| `/dashboard`, customer history | Customer | Several visible labels and failures bypassed localization. | English and Myanmar modes use the selected catalog. | Refresh, ticket ID, missing summary, history/detail failure, message failure, and message authors included hard-coded English. | Medium | Reuse/add reviewed bilingual keys and remove hard-coded UI strings. |
| `/dashboard`, customer timeline | Customer | Awaiting-customer was not represented as a labeled step. | The customer can see clearly that staff is waiting for a reply. | The progress calculation knew the state, but the four-step timeline skipped its label. | Medium | Add an awaiting-customer step and make the five-step strip horizontally contained on narrow screens. |
| `/dashboard`, feedback | Customer | Star controls had no accessible name or selected state. | Screen readers announce each rating and the selected value; keyboard focus is visible. | Five buttons exposed only the star glyph. | Medium | Add localized accessible names, `aria-pressed`, and focus styling. |
| `/dashboard`, long operational text | Customer/staff | Long unbroken complaint, message, event, or resolution text could force card overflow. | User content stays inside its card at desktop and narrow widths. | Only some ticket references and message bubbles had explicit wrapping. | Medium | Apply overflow wrapping to complaint, history, and resolution content. |
| `/dashboard`, manager override | Manager | The overlay lacked dialog semantics and reason-required clarity. | Assistive technology identifies a modal; Escape/cancel restores focus; confirmation is disabled until a reason exists. | The overlay was a generic `div`, confirm appeared actionable with an empty reason, and focus behavior was unspecified. | High | Add modal labeling, initial/restored focus, Escape close, reason help, disabled confirmation, and viewport-safe scrolling. |
| All routes and controls | All roles | Keyboard focus treatment was inconsistent. | Every interactive control has a clear visible focus indicator. | Only selected inputs/textareas had local focus rules. | Medium | Add a consistent high-contrast `:focus-visible` outline. |
| `/dashboard`, manager model metrics | Manager | Balanced accuracy was present in authoritative evidence but omitted from the KPI summary. | The visible summary includes the approved headline metrics without changing values. | Accuracy, macro precision/recall/F1, and weighted F1 were shown, but balanced accuracy was absent. | Low | Render the existing `73.62%` artifact value as an additional card. |
| `/dashboard`, responsive cards/dialog | All roles | Small-screen page and modal padding consumed avoidable width. | Content remains readable at 390 px without document-level horizontal overflow. | Desktop padding was retained at the narrowest breakpoint. | Low | Reduce shell/card/dialog padding at 520 px and keep intentional tables inside scroll containers. |

## Routes and workflows inspected

- Public home and login/configuration/authentication states.
- Customer submission, routing evidence/manual review, history/detail, status
  timeline, participant messages, resolution, feedback, and Dataset Evidence.
- Department staff scoped queue, filters, detail, begin work, reply,
  awaiting-customer, resume, resolution, messages, and audit events.
- Manager operational metrics, low-confidence queue, department override,
  model/dataset pipeline, department performance, confidence evidence, and
  confusion matrix.
- English and Myanmar catalog/rendering behavior, including narrow-screen
  customer, staff, and manager dashboards.

## Verification record

| Command | Result |
|---|---|
| `cd frontend; npm.cmd test` | PASS: 19 files, 74 tests. |
| `cd frontend; npm.cmd run typecheck` | PASS: `tsc --noEmit --incremental false`. |
| `cd frontend; npm.cmd run lint` | PASS: no ESLint findings. |
| `cd frontend; npm.cmd run build` | PASS after an elevated retry allowed Next.js to write ignored `.next` trace/cache files: Next.js 16.2.10 compiled, type-checked, and generated `/`, `/_not-found`, `/dashboard`, and `/login`. The first sandboxed build attempt was blocked by `EPERM` on `.next/trace`; it was not a product failure. |
| `cd firebase; npm.cmd test` | PASS: 4 Firestore rules tests, 1 Auth identity test, 7 backend emulator-adapter tests, and 3 Playwright browser tests. The seven backend warnings were six joblib/NumPy deprecations and one Firestore positional-filter warning. Expected permission-denied log lines came from negative rules tests. |
| `git diff --check` | PASS during implementation review; repeated in final Git review. |

Browser evidence is headless Chrome/Playwright against isolated loopback Auth
and Firestore emulators with synthetic data. The existing 1280-pixel default
viewport covered the complete customer/staff/manager workflow, including
high-confidence routing, low-confidence review, messages, awaiting-customer,
resolution, feedback, override, and department isolation. A new 390 x 844
viewport check covered customer, staff, and manager dashboards in both English
and Myanmar and proved there was no document-level horizontal overflow.

The browser checks verify DOM-visible behavior and viewport containment; they
are not a manual visual-design review on physical devices and do not prove
production Firebase or deployment.

## Remaining limitations

- There are only four application routes; role experiences share the dashboard
  route, so navigation remains a compact dashboard shell rather than a
  multi-page information architecture.
- Wide manager tables and the confusion matrix intentionally use labeled,
  keyboard-focusable horizontal scroll containers on narrow screens.
- Myanmar font rendering and containment are browser-verified, but translation
  quality remains below acceptance and Myanmar/mixed complaints remain manual
  review only.
- No physical phone, screen reader, automated contrast analyzer, or manual
  cross-browser matrix was used. Keyboard semantics and focus visibility are
  covered by markup, CSS, unit tests, and headless Chrome checks.
- Admin remains an authenticated shell without operations, as documented; Day
  30 does not add admin features.
