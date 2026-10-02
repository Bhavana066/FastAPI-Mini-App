# StudyAI – Smart PDF Summary and Quiz Generator

StudyAI is a beginner-friendly web app. You upload a PDF, the app reads the text (and uses OCR if the PDF is scanned), then an AI creates a summary and a quiz.

This project uses **one Python file only**: `app.py`.

---

## 1. What is StudyAI?

StudyAI helps students:

1. Register and login
2. Upload PDF notes
3. Extract text from PDFs
4. Use OCR for scanned PDFs
5. Generate an AI summary
6. Generate an AI quiz
7. Take the quiz and see the score

---

## 2. Features

- User registration and JWT login
- Google OpenID Connect sign-up/login with verified-email account matching
- Private PDFs (User A cannot see User B files)
- PDF upload into the `uploads/` folder
- PyMuPDF text extraction
- Tesseract OCR fallback
- Groq AI summary (overview, points, concepts, terms, conclusion)
- Groq AI multiple-choice quiz
- Dashboard, summary page, and quiz page
- Swagger docs at `/docs`

---

## 3. Technologies

| Area | Tools |
|------|--------|
| Backend | Python, FastAPI, Uvicorn |
| Database | SQLite + SQLAlchemy |
| Auth | JWT, Google OpenID Connect (Authlib), signed OAuth state, passlib hashing |
| PDF | PyMuPDF |
| OCR | Tesseract + Pillow + pytesseract |
| AI | Groq API |
| Frontend | HTML, CSS, Bootstrap 5, JavaScript |
| Config | python-dotenv |

---

## 4. Project structure

```text
StudyAI/
├── app.py
├── requirements.txt
├── .env
├── .env.example
├── .gitignore
├── README.md
├── uploads/
├── templates/
│   ├── index.html
│   ├── login.html
│   ├── register.html
│   ├── dashboard.html
│   ├── upload.html
│   ├── summary.html
│   └── quiz.html
├── static/
│   ├── style.css
│   └── script.js
└── notebook/
    └── pdf_pipeline.ipynb
```

There is **no** `main.py`, `models.py`, or `routes/` folder. Everything backend is inside `app.py`.

---

## 5. Installation (Windows)

### Step A – Open the folder

```bash
cd StudyAI
```

### Step B – Create a virtual environment

```bash
python -m venv venv
```

### Step C – Activate it

PowerShell:

```bash
.\venv\Scripts\Activate.ps1
```

If PowerShell blocks scripts, run:

```bash
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Command Prompt:

```bash
venv\Scripts\activate
```

### Step D – Install packages

```bash
pip install -r requirements.txt
```

---

## 6. Installing Tesseract (OCR)

OCR is needed for **scanned** PDFs (pictures of text).

1. Download the Windows installer from: [UB Mannheim Tesseract](https://github.com/UB-Mannheim/tesseract/wiki)
2. Install it. A common folder is: `C:\Program Files\Tesseract-OCR`
3. Open a new PowerShell window and run:

```bash
tesseract --version
```

You should see a version number.

### If Windows cannot find Tesseract

Do one of these:

**Option 1 – Add it to PATH**

Add `C:\Program Files\Tesseract-OCR` to your Windows PATH, then open a new terminal.

**Option 2 – Set the full path in `.env`**

```text
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```

Normal (text) PDFs still work without Tesseract. Scanned PDFs need Tesseract.

---

## 7. Creating `.env`

Copy the example file:

```bash
copy .env.example .env
```

Then edit `.env`:

```text
SECRET_KEY=replace_with_a_long_random_secret
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/auth/google/callback
SESSION_COOKIE_SECURE=false
AI_API_KEY=your_groq_api_key
AI_MODEL=openai/gpt-oss-20b
TESSERACT_CMD=
```

Generate a strong `SECRET_KEY` in PowerShell with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Get a Groq key from: https://console.groq.com/

Never put the real key inside `app.py`. Never upload `.env` to GitHub.

### Google OAuth credentials

1. Open the [Google Cloud Console](https://console.cloud.google.com/) and create a project or select an existing one.
2. Open **APIs & Services → OAuth consent screen** (or **Google Auth Platform** in the updated console). Configure the app name, support email, and audience. For a personal test app, choose **External** and add your Google account under **Test users** while the app is in testing.
3. Configure the OAuth consent screen with the basic OpenID scopes `openid`, `email`, and `profile`. The app does not request Gmail access.
4. Open **APIs & Services → Credentials → Create Credentials → OAuth client ID**.
5. Select **Web application** as the application type.
6. Add this exact URI under **Authorized redirect URIs**: `http://127.0.0.1:8000/auth/google/callback`. No authorized JavaScript origin is needed because the OAuth exchange happens on the backend.
7. Create the client, then copy its **Client ID** and **Client Secret** into the matching fields in your local `.env` file. Do not put the secret in HTML or JavaScript, and do not commit `.env`.
8. Keep the app running at `127.0.0.1:8000`. If you use another host or port, update both `GOOGLE_REDIRECT_URI` in `.env` and the authorized redirect URI in Google Cloud so they match exactly.

`SESSION_COOKIE_SECURE=false` is for local HTTP development. Set it to `true` when serving the app over HTTPS in production. Restart the app after changing `.env`.

---

## 8. Running the application

From the `StudyAI` folder (with venv active):

```bash
uvicorn app:app --reload
```

Open:

- Website: http://127.0.0.1:8000
- Swagger: http://127.0.0.1:8000/docs

### Test Google sign-up and login

1. Start the app and open http://127.0.0.1:8000/register.
2. Select **Continue with Google**, then choose a Google account included in the consent-screen test users if the app is still in testing.
3. The first successful sign-in creates a StudyAI account using the verified Google email. Later sign-ins, or sign-ins matching an existing account email, reuse that account.
4. Confirm the browser returns to the StudyAI dashboard. The existing **Log out** button clears the StudyAI login token; logging out of StudyAI does not sign you out of Google itself.
5. Test password login at `/login` as before. It accepts the existing username or the account email.

Common setup errors:

- `redirect_uri_mismatch`: Make the URI in Google Cloud and `GOOGLE_REDIRECT_URI` identical, including `127.0.0.1`, port, and path. Restart the app after editing `.env`.
- `Google sign-in is not configured`: Add both Google client values to `.env` and restart the app.
- `Access blocked` or `Error 403: access_denied`: Add your Google account to the OAuth consent screen's test-user list, or publish/configure the consent screen as appropriate.
- `Google sign-in was cancelled`: Retry and approve the account selection/consent prompt; no account is created when authorization is cancelled.
- Cookie/state or invalid-state errors: Keep the same browser session through the redirect, use the exact callback host consistently, and ensure cookies are enabled.
- If using port `5000`, run `uvicorn app:app --reload --port 5000` and change the callback URL in both `.env` and Google Cloud to `http://127.0.0.1:5000/auth/google/callback`.

Do **not** use `uvicorn app.main:app --reload`. There is no `main.py`.

---

## 9. How to test APIs in Swagger

1. Open http://127.0.0.1:8000/docs
2. **POST /users** – create a user (`username`, `email`, `password`)
3. **POST /auth/login** – click Try it out, enter username and password, execute
4. Copy `access_token`
5. Click **Authorize** at the top, paste the token, Authorize
6. **POST /materials/upload** – choose a PDF
7. **POST /materials/{id}/summary** – use the material id from the upload response
8. **POST /materials/{id}/quiz** – generate questions

You do **not** create `test_app.py` because this assignment allows only one Python file. Swagger is the test tool.

---

## 10. How OCR works

```text
PDF
 ↓
Try reading text (PyMuPDF)
 ↓
Enough text?  YES → use it
 ↓ NO
Render each page as an image
 ↓
Tesseract OCR
 ↓
Text
```

---

## 11. How AI summary works

```text
PDF
 ↓
Extract text
 ↓
If the text is huge, cut it (MAX_AI_CHARS)
 ↓
Send text to Groq
 ↓
Save JSON: overview, main points, concepts, terms, conclusion
```

---

## 12. How AI quiz works

```text
PDF
 ↓
Extract text
 ↓
Send text to Groq
 ↓
AI returns 5–10 questions
 ↓
Save in SQLite
 ↓
Website shows the quiz and score
```

---

## 13. How JWT login works

```text
User Login
     ↓
Check Password
     ↓
Create JWT Token
     ↓
User receives Token
     ↓
User sends Token with protected requests
     ↓
Server verifies Token
     ↓
Request allowed
```

---

## 14. Google Colab notebook

Open `notebook/pdf_pipeline.ipynb` in Google Colab.

It shows:

Upload PDF → extract text → OCR if needed → summary → quiz → display results

Use **Colab Secrets** for `AI_API_KEY`. Do not paste keys into the notebook.

---

## 15. GitHub upload

`.gitignore` already ignores `.env`, `venv/`, `*.db`, and uploaded PDFs.

```bash
cd StudyAI
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin YOUR_GITHUB_REPOSITORY_URL
git push -u origin main
```

Replace `YOUR_GITHUB_REPOSITORY_URL` with your real GitHub URL.

Do not upload:

- API keys
- `.env`
- virtual environment
- `studyai.db`
- temporary files

---

## 16. Beginner map of `app.py`

| Section | What it does | Why we need it |
|---------|----------------|----------------|
| 1 Imports | Loads libraries | So we can use FastAPI, SQLAlchemy, Groq, etc. |
| 2 Configuration | Reads `.env` | Secrets stay out of the code |
| 3 FastAPI app | Creates `app` | Uvicorn starts this object |
| 4 Database | Connects to SQLite | Save users and PDFs |
| 5 Models | User, Material, Quiz tables | Database shape |
| 6 Schemas | JSON validation | Catch bad input |
| 7 Passwords | Hashing | Never store plain passwords |
| 8 JWT | Create/read tokens | Stay logged in safely |
| 9 Auth | Current user + ownership | Protect routes |
| 10 PDF text | `extract_text_from_pdf` | Read normal PDFs |
| 11 OCR | Tesseract | Read scanned PDFs |
| 12 AI summary | `generate_summary` | Study notes |
| 13 AI quiz | `generate_quiz` | Practice questions |
| 14 HTML routes | Website pages | Browser UI |
| 15–19 APIs | users, login, upload, summary, quiz | Required assignment APIs |
| 20 Errors | Friendly JSON errors | Easier debugging |

---

