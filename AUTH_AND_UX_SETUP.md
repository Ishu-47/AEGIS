# AEGIS dashboard authentication and UX update

## What changed

- Added email/password dashboard accounts with per-user application ownership.
- Passwords are stored as salted PBKDF2-SHA256 hashes.
- Sessions are server-managed: the browser gets an opaque `HttpOnly` session cookie, while PostgreSQL stores only the SHA-256 hash of the session token.
- Sessions expire after seven days and are revoked in the database on logout.
- State-changing dashboard requests require a CSRF token.
- Dashboard-only APIs now use the session cookie. External ingestion and legacy integration routes remain protected by `X-API-Key`.
- Added an Applications page with application IDs, platform, creation date, key rotation, and delete confirmation.
- API keys are shown only when created or rotated and are never saved in `localStorage`.
- The frontend now fetches the application list from the backend and persists only the selected application ID.
- With multiple applications, the selector offers “All applications” for aggregate dashboard/incident views. Ingestion still requires one specific application.
- Added a `platform` column to applications; existing applications receive `Other`.
- Added application ownership so each dashboard account sees and manages only its own applications. Existing applications are assigned to the first existing dashboard account when the ownership migration runs.

## Apply the update

1. Back up your project folder and database.
2. Copy the updated `backend/app`, `backend/migrations/versions/9a1c3f5d7e20_add_dashboard_user.py`, `backend/migrations/versions/bc71d4a9e205_add_application_ownership.py`, and updated `frontend/src` files into the corresponding folders in your project.
3. Keep your existing `backend/.env` and do not replace your database URL or Gemini key. Add these local-development settings if absent:

   ```env
   AEGIS_COOKIE_SECURE=false
   AEGIS_FRONTEND_ORIGINS=http://localhost:5173
   ```

4. Run the migration from `backend` with the virtual environment active:

   ```powershell
   python -m alembic upgrade head
   python -m alembic current
   python -m alembic check
   ```

   The expected current revision is `bc71d4a9e205 (head)`. Existing applications are retained, their platform defaults to `Other`, and existing records are assigned to the first existing dashboard account when available.

5. Restart the backend:

   ```powershell
   uvicorn app.main:app --reload --port 8000
   ```

6. Start the frontend as usual from `frontend`:

   ```powershell
   npm run dev
   ```

7. Open `http://localhost:5173/register` to create an account. Each account sees only the applications it owns. Use `/login` after logging out.

## Security and behavior notes

- For HTTPS deployment, set `AEGIS_COOKIE_SECURE=true` and set `AEGIS_FRONTEND_ORIGINS` to the exact deployed frontend origin(s), comma-separated if needed.
- The session table means logout revokes that session server-side. The session cookie is `HttpOnly`, `SameSite=Lax`, and expires after seven days.
- Accounts are separate, but this MVP does not yet implement teams/shared applications, password reset, login rate limiting, email verification, or account recovery. Registration is open to anyone who can reach the app; restrict it before public production deployment.
- The browser cache from the previous version (`aegis.applications`) is removed because it contained plaintext API keys. The backend only stores API-key hashes, so previously generated keys cannot be displayed again. If you no longer have a key needed by an external integration, rotate it in Applications and update that integration.
- Existing external ingestion remains available at `POST /api/ingest/logs` and `POST /api/applications/{application_id}/logs` with `X-API-Key`. The dashboard's manual paste/upload page uses the separate cookie-authenticated dashboard endpoint.
- Alembic is now the schema-change mechanism. Startup no longer calls `Base.metadata.create_all()`, so apply migrations before starting the updated backend.
