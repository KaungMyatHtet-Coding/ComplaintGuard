@echo off
if "%1"=="emulators" goto emulators
if "%1"=="seed" goto seed
if "%1"=="backend" goto backend
if "%1"=="frontend" goto frontend

echo Starting ComplaintGuard Services...
echo This will open 4 separate windows.

start "Firebase Emulators" cmd /k "%~f0" emulators
start "FastAPI Backend" cmd /k "%~f0" backend
start "Next.js Frontend" cmd /k "%~f0" frontend
start "Database Seeder" cmd /k "%~f0" seed

goto :eof


:emulators
title Firebase Emulators
cd /d C:\dam\ComplaintGuard
set FIREBASE_CLI_DISABLE_UPDATE_CHECK=true
set FIREBASE_EMULATORS_PATH=C:\dam\ComplaintGuard\firebase\.firebase\emulators
set XDG_CONFIG_HOME=C:\dam\ComplaintGuard\firebase\.firebase\config
echo Starting Emulators...
node.exe firebase\node_modules\firebase-tools\lib\bin\firebase.js emulators:start --project demo-complaintguard --only auth,firestore
goto :eof


:seed
title Database Seeder
cd /d C:\dam\ComplaintGuard
set FIRESTORE_EMULATOR_HOST=127.0.0.1:8185
set FIREBASE_AUTH_EMULATOR_HOST=127.0.0.1:9099
set GCLOUD_PROJECT=demo-complaintguard
echo Waiting 15 seconds to ensure the emulators have started...
timeout /t 15
echo Seeding database...
node.exe firebase\seed-emulator.mjs
echo.
echo Seeding complete! You can close this seeder window.
goto :eof


:backend
title FastAPI Backend
cd /d C:\dam\ComplaintGuard\ml-api
set FIRESTORE_EMULATOR_HOST=127.0.0.1:8185
set FIREBASE_AUTH_EMULATOR_HOST=127.0.0.1:9099
set GOOGLE_CLOUD_PROJECT=demo-complaintguard
set FIREBASE_CONFIG={"projectId":"demo-complaintguard"}
set ALLOWED_ORIGINS=http://127.0.0.1:3000,http://localhost:3000
echo Starting Backend...
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
goto :eof


:frontend
title Next.js Frontend
cd /d C:\dam\ComplaintGuard\frontend
set NEXT_PUBLIC_FIREBASE_API_KEY=emulator-only
set NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=demo-complaintguard.firebaseapp.com
set NEXT_PUBLIC_FIREBASE_PROJECT_ID=demo-complaintguard
set NEXT_PUBLIC_FIREBASE_APP_ID=1:000:web:emulator
set NEXT_PUBLIC_APP_ENV=local-emulator
set NEXT_PUBLIC_USE_FIREBASE_EMULATORS=true
set NEXT_PUBLIC_ML_API_URL=http://127.0.0.1:8000
echo Starting Frontend...
call npm.cmd run dev -- -H 127.0.0.1 -p 3000
goto :eof
