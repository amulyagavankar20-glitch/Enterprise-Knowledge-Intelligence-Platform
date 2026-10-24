# Enterprise Knowledge Intelligence frontend

The runnable browser app is `index.html`, `app.css`, and `app.js`; it follows the Stitch palette and layout and uses the existing FastAPI endpoints directly. The original Stitch exports and screenshots are organized under `designs/` as design references.

## Run locally

From the repository root in PowerShell:

```powershell
conda activate enterprise-rag
$env:PYTHONPATH = (Resolve-Path .\backend).Path
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/`. FastAPI serves the frontend and API from the same origin, so no browser CORS configuration is needed. The backend still needs its normal database, JWT, and generation settings configured locally. This frontend does not read or contain `.env` values.

## Connected features

- Register at `/api/v1/auth/register` and sign in at `/api/v1/auth/token`.
- Ask questions at `/api/v1/query/`; display answer citations and the matching retrieved source excerpts.
- List, upload, inspect, paginate extracted content, switch document versions, download originals, and delete documents through `/api/v1/documents`.
- The bearer token is kept in tab-scoped `sessionStorage`; signing out or receiving an expired-session response clears it.
- Uploads are sent one file per request because that is the current API contract. Accepted extensions and the 20 MB limit match the backend.
- The app fetches the authenticated profile to display the server-assigned role; administrators get a paginated audit view.
- Answers are grouped with their question and evidence, source labels jump to the associated excerpt, and users can submit a helpful/not-helpful rating with an optional comment.
- Responsive layouts, keyboard skip navigation, focus-managed deletion confirmation, reduced-motion styling, and status/error messages are included.

The browser does not persist conversation history. Feedback submits the selected question, answer and optional comment to the authenticated API for quality review; the UI discloses this before submission. The admin/member access boundary remains enforced by the backend.

## Browser verification

The repository has backend TestClient coverage for served assets, security headers, registration/profile, feedback authorization, and audit access. There is no configured browser automation suite, so keyboard/screen-reader behavior and real-device responsive layouts still need manual browser verification before production use.
