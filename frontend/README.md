# ComplaintGuard frontend

This directory contains the ComplaintGuard Next.js frontend. It uses TypeScript,
the App Router, Tailwind CSS, ESLint, a `src` directory, and npm.

Day 12 adds responsive home, login and role-specific dashboard shells,
English/Myanmar UI localization, and a configuration-gated Firebase
email/password authentication boundary. Complaint submission and other Day 13+
workflows are not included.

## Firebase configuration

Copy the safe placeholder file and replace values only in the ignored local
file:

```powershell
Copy-Item .env.example .env.local
```

Enable Firebase email/password authentication and create matching active
`users/{uid}` Firestore profiles. Valid roles are `customer`, `staff`,
`manager`, and `admin`; staff profiles also require a valid `departmentId`.
Demo credentials belong in the owner/password manager, never in Git.

When configuration is absent, the login screen shows an explicit setup state
and does not pretend authentication succeeded. Client navigation is not an
authorization boundary: `firebase/firestore.rules` and trusted backend checks
remain authoritative. Live Firebase authentication has not yet been verified.

## Verified commands

From this directory on Windows PowerShell:

```powershell
npm.cmd install
npm.cmd run dev
npm.cmd run lint
npm.cmd run typecheck
npm.cmd test
npm.cmd run build
```

Open `http://localhost:3000` after starting the development server. Use `npm.cmd` if PowerShell blocks the `npm.ps1` launcher.
