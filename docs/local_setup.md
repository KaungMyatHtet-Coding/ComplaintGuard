# Local Development Setup

These instructions describe the verified Day 2 environment on Windows PowerShell. They contain placeholders only and do not require Firebase, Vercel, or Hugging Face credentials.

## Required software and observed versions

Observed on 21 July 2026 in `D:\ComplaintGuard`:

| Tool | Required now | Observed version/state |
|---|---:|---|
| Git | Yes | 2.43.0.windows.1 |
| Node.js | Yes | 22.17.0 |
| npm / npx | Yes | 10.9.2 |
| Python | Yes | 3.12.0, 64-bit CPython |
| pip in `.venv` | Bundled | 23.2.1 |
| Java | Later for Firebase emulator | 24.0.2 |
| Uvicorn / pytest globally | Not used on Day 2 | Uvicorn 0.51.0; pytest 8.3.4 |
| Firebase CLI | Later | Not found |
| Jupyter, Ruff, Black, Docker, uv | Not required today | Not found |

Check the essential tools without installing anything:

```powershell
git --version
node --version
npm.cmd --version
npx.cmd --version
python --version
```

## Clone/location check

Run commands from the repository root and confirm the expected branch:

```powershell
Set-Location D:\ComplaintGuard
git rev-parse --show-toplevel
git branch --show-current
```

For this Day 2 work, the expected branch is `chore/day-2-architecture`.

## Frontend

The `frontend` application was generated with npm using TypeScript, App Router, Tailwind CSS, ESLint, and a `src` directory. Install only the dependencies locked in `frontend/package-lock.json`:

```powershell
Set-Location D:\ComplaintGuard\frontend
npm.cmd install
npm.cmd run dev
```

Open `http://localhost:3000`. Run checks before committing:

```powershell
npm.cmd run lint
npm.cmd run build
```

Do not add Firebase, charting, translation, component-library, or state-management packages during Day 2.

### Day 2 dependency audit note

`npm audit --omit=dev --audit-level=moderate` reported two moderate findings in the version of PostCSS nested inside Next.js 16.2.10. npm's proposed forced remediation would install the incompatible Next.js 9.3.3, so no forced or breaking change was applied. Recheck the advisory when a compatible stable Next.js update is available; do not use `npm audit fix --force` without reviewing the resulting framework version.

## Python 3.12 virtual environment

ComplaintGuard uses exactly one local virtual environment at the repository root. Create it from the root:

```powershell
Set-Location D:\ComplaintGuard
python -m venv .venv
```

Activate it in Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python --version
python -m pip --version
```

Exit it with:

```powershell
deactivate
```

If script execution is blocked, do not weaken the permanent machine policy. Either use a process-only policy for the current terminal:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

or run the environment's executables without activation:

```powershell
& .\.venv\Scripts\python.exe --version
& .\.venv\Scripts\python.exe -m pip --version
```

`requirements-dev.txt` lists only lightweight future test/lint tools. No Python packages were installed into `.venv` on Day 2 because there is no Python implementation or test suite yet. When Python work starts on its scheduled day, review the file and then install deliberately:

```powershell
& .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Do not install PyTorch, Transformers, NLLB, PySpark, Docker, or other heavy dependencies during Day 2.

## Configuration and secrets

`.env.example` contains placeholder names only. Do not create or commit real configuration until integration is scheduled. When that time comes, copy placeholders locally and keep the result ignored:

```powershell
Copy-Item .env.example .env.local
```

Never commit `.env.local`, access tokens, Firebase service-account JSON, private keys, real customer information, or raw CFPB data. Firebase must remain on the Spark plan with billing disabled.

## Common Windows PowerShell issues

- **`npm.ps1` is blocked:** use `npm.cmd` and `npx.cmd`, which call the same installed npm tools without changing execution policy.
- **Virtual-environment activation is blocked:** use the process-only policy or direct `.venv\Scripts\python.exe` commands shown above.
- **`py` says no Python is installed:** this machine's `py` launcher is not configured; use `python`, which resolves to CPython 3.12.
- **Long first install/build:** npm dependency installation can take time. Do not cancel while files are actively changing.
- **Generated folders appear in searches:** `frontend/node_modules`, `frontend/.next`, and root `.venv` are local outputs and are ignored by Git.

## Account setup not completed

Day 2 does not claim that the Firebase project, Vercel account/project, or Hugging Face Space exists. Their setup remains manual and unchecked until the project owner confirms it. Any Firebase project must use Spark with billing disabled.
