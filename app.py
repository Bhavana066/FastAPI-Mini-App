# ==========================================
# StudyAI – Smart PDF Summary and Quiz Generator
# ALL backend code lives in this ONE file (app.py).
# Start the app with:  uvicorn app:app --reload
# ==========================================

# ==========================================
# 1. IMPORTS
# ==========================================
# What does this do?
#   Python needs extra tools (libraries) to build a website, talk to a database,
#   read PDFs, and call an AI API. An "import" loads those tools into this file.
# Why do we need it?
#   Without imports, we would have to write everything from scratch.
# How does it work?
#   Each "import" line brings in a ready-made package from requirements.txt.
import json
import logging
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import fitz  # PyMuPDF – reads PDF files
import pytesseract  # talks to Tesseract OCR
from authlib.integrations.starlette_client import OAuth, OAuthError
from email_validator import EmailNotValidError, validate_email
from PIL import Image  # Pillow – works with images
from dotenv import load_dotenv  # reads the .env file
from fastapi import (
    Depends,
    FastAPI,
    File,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from groq import Groq  # AI API client
from jose import JWTError, jwt  # create and check JWT tokens
from passlib.context import CryptContext  # hash passwords
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, create_engine, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker
from starlette.middleware.sessions import SessionMiddleware

# ==========================================
# 2. CONFIGURATION
# ==========================================
# What does this do?
#   Loads secret settings from the .env file (API key, JWT secret, etc.).
# Why do we need it?
#   Secrets must NOT be written inside the code. If we put them in .env,
#   we can share the code on GitHub without sharing the keys.
# How does it work?
#   load_dotenv() reads .env. os.getenv("NAME") gets each value.

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "openai/gpt-oss-20b")
TESSERACT_CMD = os.getenv("TESSERACT_CMD", "")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
GOOGLE_REDIRECT_URI = os.getenv(
    "GOOGLE_REDIRECT_URI",
    "http://127.0.0.1:8000/auth/google/callback",
).strip()
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"

if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY is missing. Copy .env.example to .env and set SECRET_KEY."
    )

# If Windows cannot find Tesseract, set TESSERACT_CMD in .env to the full path,
# for example: C:\Program Files\Tesseract-OCR\tesseract.exe
if TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
elif os.name == "nt":
    default_win = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.exists(default_win):
        pytesseract.pytesseract.tesseract_cmd = default_win

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# If a PDF has fewer than this many characters, we try OCR (scanned PDF).
MIN_TEXT_LENGTH = 80
# We do not send unlimited text to the AI (that would be slow and expensive).
MAX_AI_CHARS = 12000
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

# ==========================================
# 3. FASTAPI APP
# ==========================================
# What does this do?
#   Creates the web application object named "app".
# Why do we need it?
#   Uvicorn looks for this object:  uvicorn app:app --reload
#   (file name "app.py" + variable name "app")
# How does it work?
#   FastAPI receives HTTP requests (GET, POST) and calls the matching function.

app = FastAPI(
    title="StudyAI",
    description="Upload PDFs, extract text (with OCR if needed), generate AI summaries and quizzes.",
    version="1.0.0",
)
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    same_site="lax",
    https_only=SESSION_COOKIE_SECURE,
)

oauth = OAuth()
if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
    oauth.register(
        name="google",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# ==========================================
# 4. DATABASE CONNECTION
# ==========================================
# What does this do?
#   Connects the app to a SQLite file named studyai.db.
# Why do we need it?
#   We must save users, PDFs, summaries, and quizzes so they are not lost
#   when we restart the server.
# How does it work?
#   SQLAlchemy talks to SQLite. get_db() opens a session for each request
#   and closes it afterwards.

DATABASE_URL = "sqlite:///" + os.path.join(BASE_DIR, "studyai.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Give one database session to a route, then close it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ==========================================
# 5. DATABASE MODELS
# ==========================================
# What does this do?
#   Describes the tables: User, Material, Quiz.
# Why do we need it?
#   The database needs a clear shape: columns and relationships.
# How does it work?
#   Each Python class becomes one SQLite table.


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(120), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    google_sub = Column(String(255), unique=True, index=True, nullable=True)
    full_name = Column(String(120), nullable=True)
    picture_url = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    materials = relationship("Material", back_populates="owner")


class Material(Base):
    __tablename__ = "materials"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    extracted_text = Column(Text, default="")
    summary = Column(Text, default="")  # stored as JSON text
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    owner = relationship("User", back_populates="materials")
    quizzes = relationship("Quiz", back_populates="material")


class Quiz(Base):
    __tablename__ = "quizzes"

    id = Column(Integer, primary_key=True, index=True)
    material_id = Column(Integer, ForeignKey("materials.id"), nullable=False)
    questions = Column(Text, nullable=False)  # stored as JSON text
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    material = relationship("Material", back_populates="quizzes")


Base.metadata.create_all(bind=engine)

# Add Google profile columns to existing SQLite databases without replacing user data.
with engine.begin() as connection:
    user_columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(users)")}
    if "google_sub" not in user_columns:
        connection.exec_driver_sql("ALTER TABLE users ADD COLUMN google_sub VARCHAR(255)")
    if "full_name" not in user_columns:
        connection.exec_driver_sql("ALTER TABLE users ADD COLUMN full_name VARCHAR(120)")
    if "picture_url" not in user_columns:
        connection.exec_driver_sql("ALTER TABLE users ADD COLUMN picture_url VARCHAR(500)")
    connection.exec_driver_sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_google_sub ON users (google_sub)"
    )

# ==========================================
# 6. PYDANTIC SCHEMAS
# ==========================================
# What does this do?
#   Defines the shape of JSON we accept or return (validation).
# Why do we need it?
#   If a user forgets email or password, FastAPI can return a clear error.
# How does it work?
#   Incoming data is checked against these classes before our code runs.


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=6, max_length=72)


class UserOut(BaseModel):
    id: int
    username: str
    email: EmailStr
    created_at: datetime

    class Config:
        from_attributes = True


class TokenOut(BaseModel):
    access_token: str
    token_type: str

# ==========================================
# 7. PASSWORD FUNCTIONS
# ==========================================
# What does this do?
#   Turns a password into a hash (a scrambled string) and later checks it.
# Why do we need it?
#   We must NEVER store the real password. If the database leaks, attackers
#   should not see the original password.
# How does it work?
#   hash_password("secret") -> long hashed string
#   verify_password("secret", hashed) -> True or False

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

# ==========================================
# 8. JWT FUNCTIONS
# ==========================================
# What does this do?
#   Creates and reads a JWT token (a signed ticket that proves who you are).
# Why do we need it?
#   After login, the browser stores a token instead of sending the password
#   on every request.
# How does it work? (simple flow)
#   User Login
#        ↓
#   Check Password
#        ↓
#   Create JWT Token
#        ↓
#   User receives Token
#        ↓
#   User sends Token with protected requests
#        ↓
#   Server verifies Token
#        ↓
#   Request allowed


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

# ==========================================
# 9. AUTHENTICATION
# ==========================================
# What does this do?
#   Reads the Bearer token from the request and finds the logged-in user.
# Why do we need it?
#   Upload / summary / quiz must only work for a real logged-in user.
# How does it work?
#   Header: Authorization: Bearer <token>
#   We decode the token, load the user from the database, or return 401.

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials. Please log in again.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        username = payload.get("sub")
        if not username:
            raise credentials_error
    except JWTError:
        raise credentials_error

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_error
    return user


def get_owned_material(material_id: int, current_user: User, db: Session) -> Material:
    """User A must not see User B's PDFs."""
    material = db.query(Material).filter(Material.id == material_id).first()
    if material is None:
        raise HTTPException(status_code=404, detail="Material not found.")
    if material.owner_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to access this PDF.",
        )
    return material

# ==========================================
# 10. PDF TEXT EXTRACTION
# ==========================================
# What does this do?
#   Opens a PDF and copies the text from every page.
# Why do we need it?
#   The AI cannot "see" a PDF file. It needs plain text.
# How does it work?
#   Open PDF → loop pages → extract text → join into one string.


def extract_text_from_pdf(file_path: str) -> str:
    """Read selectable text from a PDF using PyMuPDF."""
    text_parts = []
    document = fitz.open(file_path)
    try:
        for page in document:
            text_parts.append(page.get_text() or "")
    finally:
        document.close()
    return "\n".join(text_parts).strip()

# ==========================================
# 11. OCR FUNCTIONS
# ==========================================
# What does this do?
#   If the PDF is a scan (picture of text), Tesseract reads the image.
# Why do we need it?
#   Many study notes are scanned. Normal PDF extraction finds almost no text.
# How does it work?
#   PDF
#    ↓
#   Try reading text
#    ↓
#   Text found?  YES → use text
#    ↓ NO
#   Convert page to image
#    ↓
#   Tesseract
#    ↓
#   Text
#
# Windows install (short):
#   1. Download Tesseract from: https://github.com/UB-Mannheim/tesseract/wiki
#   2. Install it (remember the folder, usually C:\Program Files\Tesseract-OCR)
#   3. Open PowerShell and run:  tesseract --version
#   4. If Windows cannot find it, add that folder to PATH, or set TESSERACT_CMD
#      in .env to: C:\Program Files\Tesseract-OCR\tesseract.exe


def ocr_pdf(file_path: str) -> str:
    """Render each PDF page as an image and run Tesseract OCR."""
    text_parts = []
    document = fitz.open(file_path)
    try:
        for page in document:
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            image = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
            page_text = pytesseract.image_to_string(image)
            text_parts.append(page_text or "")
    finally:
        document.close()
    return "\n".join(text_parts).strip()


def get_pdf_text(file_path: str) -> str:
    """Try normal extraction first. If there is too little text, use OCR."""
    text = extract_text_from_pdf(file_path)
    if len(text) >= MIN_TEXT_LENGTH:
        return text
    try:
        ocr_text = ocr_pdf(file_path)
        if ocr_text:
            return ocr_text
    except Exception:
        # OCR may fail if Tesseract is not installed. Keep whatever text we have.
        pass
    return text

# ==========================================
# 12. AI SUMMARY
# ==========================================
# What does this do?
#   Sends PDF text to Groq (an LLM API) and asks for a study summary.
# Why do we need it?
#   Students want a short, clear version of a long PDF.
# How does it work?
#   PDF → Extract Text → Truncate if too long → Send to AI → AI Summary


def truncate_for_ai(text: str) -> str:
    if len(text) <= MAX_AI_CHARS:
        return text
    return text[:MAX_AI_CHARS] + "\n\n[Text was truncated so the AI request stays small.]"


def _require_ai_key() -> None:
    if not AI_API_KEY or AI_API_KEY == "your_api_key_here":
        raise HTTPException(
            status_code=500,
            detail="AI_API_KEY is not set. Add your Groq key to the .env file.",
        )


def _parse_json_from_ai(raw: str):
    """AI sometimes wraps JSON in ```json ... ```. This cleans it."""
    cleaned = raw.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\}|\[.*\])", cleaned, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        raise


def generate_summary(text: str) -> dict:
    """
    Ask the AI for a structured summary.
    Returns a dictionary with overview, main_points, important_concepts,
    important_terms, and conclusion.
    """
    _require_ai_key()
    client = Groq(api_key=AI_API_KEY)
    prompt = f"""
You are a helpful study assistant. Read the notes and return ONLY valid JSON
with this exact shape (no extra keys, no markdown):
{{
  "overview": "short paragraph",
  "main_points": ["point 1", "point 2", "point 3"],
  "important_concepts": ["concept 1", "concept 2"],
  "important_terms": ["term 1", "term 2"],
  "conclusion": "short paragraph"
}}

Study text:
{truncate_for_ai(text)}
"""
    response = client.chat.completions.create(
        model=AI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    raw = response.choices[0].message.content or ""
    data = _parse_json_from_ai(raw)
    if not isinstance(data, dict):
        raise ValueError("AI summary was not a JSON object.")
    return {
        "overview": str(data.get("overview", "")),
        "main_points": list(data.get("main_points") or []),
        "important_concepts": list(data.get("important_concepts") or []),
        "important_terms": list(data.get("important_terms") or []),
        "conclusion": str(data.get("conclusion", "")),
    }

# ==========================================
# 13. AI QUIZ
# ==========================================
# What does this do?
#   Asks the AI to create 5–10 multiple-choice questions from the PDF text.
# Why do we need it?
#   Quizzes help students check if they understood the material.
# How does it work?
#   PDF → Extract Text → Send to AI → AI creates questions → Store → Show quiz


def generate_quiz(text: str) -> list:
    """
    Returns a list of questions. Each item has:
    question, options, correct_answer, explanation
    """
    _require_ai_key()
    client = Groq(api_key=AI_API_KEY)
    prompt = f"""
Create 8 multiple-choice questions using only the study text below.
Every question must test a specific fact or concept stated in that text.
Each question must have exactly four distinct answer options:
- one correct answer supported by the text
- three plausible but incorrect distractors that are relevant to the question
    and drawn from similar concepts or details in the text
Every option must use a term or detail explicitly mentioned in the study text
or a faithful paraphrase of one. Build distractors from other details in the
text, and keep all four options in the same category and answer the same kind
of question. Never introduce unrelated terms or generic choices.
Make the correct answer unambiguous, and make the explanation cite the
relevant fact from the text in one short sentence. Keep questions and options
concise.
Return ONLY a valid JSON object in this exact shape:
{{
    "questions": [
        {{
            "question": "string",
            "options": ["A", "B", "C", "D"],
            "correct_answer": "must exactly match one of the four options",
            "explanation": "short reason"
        }}
    ]
    }}

Study text:
{truncate_for_ai(text)}
"""
    response = client.chat.completions.create(
        model=AI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        max_tokens=4096,
        temperature=0.4,
    )
    raw = response.choices[0].message.content or ""
    data = _parse_json_from_ai(raw)
    if not isinstance(data, dict) or not isinstance(data.get("questions"), list):
        raise ValueError("AI quiz did not contain a questions array.")
    data = data["questions"]

    cleaned = []
    for item in data:
        if not isinstance(item, dict):
            continue
        options = item.get("options") or []
        if not isinstance(options, list) or len(options) != 4:
            continue
        options = [str(opt).strip() for opt in options]
        if any(not option for option in options):
            continue
        if len({option.casefold() for option in options}) != 4:
            continue
        correct = str(item.get("correct_answer", "")).strip()
        if correct not in options:
            continue
        question = str(item.get("question", "")).strip()
        explanation = str(item.get("explanation", "")).strip()
        if not question or not explanation:
            continue
        cleaned.append(
            {
                "question": question,
                "options": options,
                "correct_answer": correct,
                "explanation": explanation,
            }
        )
        if len(cleaned) >= 10:
            break

    if len(cleaned) < 5:
        raise ValueError("The AI did not return enough valid quiz questions.")
    return cleaned

# ==========================================
# 14. HTML PAGE ROUTES
# ==========================================
# What does this do?
#   Shows website pages (home, login, dashboard, ...).
# Why do we need it?
#   Humans use a browser, not only Swagger JSON.
# How does it work?
#   GET request → FastAPI → Jinja2 fills the HTML template → browser shows it.


@app.get("/", response_class=HTMLResponse)
def home_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/upload", response_class=HTMLResponse)
def upload_page(request: Request):
    return templates.TemplateResponse("upload.html", {"request": request})


@app.get("/materials/{material_id}/summary", response_class=HTMLResponse)
def summary_page(request: Request, material_id: int):
    return templates.TemplateResponse(
        "summary.html",
        {"request": request, "material_id": material_id},
    )


@app.get("/materials/{material_id}/quiz", response_class=HTMLResponse)
def quiz_page(request: Request, material_id: int):
    return templates.TemplateResponse(
        "quiz.html",
        {"request": request, "material_id": material_id},
    )


@app.get("/materials/{material_id}", response_class=HTMLResponse)
def material_page(request: Request, material_id: int):
    return templates.TemplateResponse(
        "summary.html",
        {"request": request, "material_id": material_id},
    )

# ==========================================
# 15. USER API
# ==========================================
# What does this do?
#   Creates a new account (register).
# Why do we need it?
#   Each student needs their own private PDFs.
# How does it work?
#   Check duplicate username/email → hash password → save user → return user (no password).


@app.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=400, detail="Username is already taken.")
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email is already registered.")

    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.get("/api/me", response_model=UserOut)
def read_me(current_user: User = Depends(get_current_user)):
    return current_user


def google_login_error(error_code: str) -> RedirectResponse:
    """Return users to login with a safe, displayable OAuth error code."""
    return RedirectResponse(f"/login?google_error={error_code}", status_code=303)


def make_google_username(name: str, email: str, db: Session) -> str:
    """Create a readable unique username for a newly registered Google user."""
    candidate_source = name or email.partition("@")[0]
    base = re.sub(r"[^a-zA-Z0-9_.-]", "", candidate_source).strip("._-")[:42]
    if len(base) < 3:
        base = "google_user"
    candidate = base
    while db.query(User.id).filter(User.username == candidate).first():
        candidate = f"{base[:42]}_{secrets.token_hex(3)}"
    return candidate


@app.get("/auth/google")
async def google_login(request: Request):
    """Start Google's OpenID Connect authorization-code flow."""
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return google_login_error("not_configured")
    return await oauth.google.authorize_redirect(request, GOOGLE_REDIRECT_URI)


@app.get("/auth/google/callback")
async def google_callback(request: Request, db: Session = Depends(get_db)):
    """Verify Google's response, find or create the local account, and issue its JWT."""
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return google_login_error("not_configured")

    provider_error = request.query_params.get("error")
    if provider_error:
        if provider_error == "access_denied":
            return google_login_error("cancelled")
        logging.warning("Google authorization returned an error: %s", provider_error)
        return google_login_error("failed")

    try:
        token = await oauth.google.authorize_access_token(request)
        google_user = token.get("userinfo")
        if not google_user:
            return google_login_error("failed")

        google_sub = str(google_user.get("sub") or "").strip()
        raw_email = str(google_user.get("email") or "").strip()
        if not google_sub or not raw_email or not google_user.get("email_verified"):
            return google_login_error("unverified_email")
        try:
            email = validate_email(raw_email, check_deliverability=False).normalized.lower()
        except EmailNotValidError:
            return google_login_error("unverified_email")

        full_name = str(google_user.get("name") or "").strip()[:120] or None
        raw_picture = str(google_user.get("picture") or "").strip()
        picture_url = raw_picture[:500] if raw_picture.startswith("https://") else None

        user = db.query(User).filter(User.google_sub == google_sub).first()
        if user is None:
            user = db.query(User).filter(func.lower(User.email) == email).first()

        if user is None:
            user = User(
                username=make_google_username(full_name or "", email, db),
                email=email,
                hashed_password=hash_password(secrets.token_hex(32)),
                google_sub=google_sub,
                full_name=full_name,
                picture_url=picture_url,
            )
            db.add(user)
        else:
            user.google_sub = google_sub
            user.full_name = full_name or user.full_name
            user.picture_url = picture_url or user.picture_url

        db.commit()
        db.refresh(user)
    except OAuthError as error:
        logging.info("Google sign-in was not completed: %s", error.error)
        return google_login_error("cancelled" if error.error == "access_denied" else "failed")
    except IntegrityError:
        db.rollback()
        # A concurrent first login may have inserted the same verified identity.
        user = db.query(User).filter(
            (User.google_sub == google_sub) | (func.lower(User.email) == email)
        ).first()
        if user is None:
            logging.exception("Google account could not be saved after a database conflict")
            return google_login_error("failed")
    except SQLAlchemyError:
        db.rollback()
        logging.exception("Database error during Google sign-in")
        return google_login_error("failed")
    except Exception:
        logging.exception("Google sign-in could not be completed")
        return google_login_error("failed")

    access_token = create_access_token({"sub": user.username})
    return RedirectResponse(f"/login#access_token={access_token}", status_code=303)

# ==========================================
# 16. LOGIN API
# ==========================================
# What does this do?
#   Checks username + password and returns a JWT token.
# Why do we need it?
#   This is how the website knows who is logged in.
# How does it work?
#   Username + Password → Find User → Check Password → Create JWT → Return Token


@app.post("/auth/login", response_model=TokenOut)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    login_identifier = form_data.username.strip()
    user = db.query(User).filter(User.username == login_identifier).first()
    if user is None:
        user = db.query(User).filter(func.lower(User.email) == login_identifier.lower()).first()
    if user is None or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token({"sub": user.username})
    return {"access_token": token, "token_type": "bearer"}

# ==========================================
# 17. PDF UPLOAD API
# ==========================================
# What does this do?
#   Saves a PDF, extracts text (or OCR), and stores a Material row.
# Why do we need it?
#   This is the start of the study pipeline.
# How does it work?
#   Check login → accept PDF only → safe filename → save file → extract text → save DB.


@app.get("/api/materials")
def list_materials(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    materials = (
        db.query(Material)
        .filter(Material.owner_id == current_user.id)
        .order_by(Material.created_at.desc())
        .all()
    )
    items = []
    for material in materials:
        quiz_count = db.query(Quiz).filter(Quiz.material_id == material.id).count()
        items.append(
            {
                "id": material.id,
                "title": material.title,
                "filename": material.filename,
                "created_at": material.created_at.isoformat() if material.created_at else None,
                "has_summary": bool(material.summary),
                "has_quiz": quiz_count > 0,
            }
        )
    summaries = sum(1 for item in items if item["has_summary"])
    quizzes = sum(1 for item in items if item["has_quiz"])
    return {
        "username": current_user.username,
        "total_pdfs": len(items),
        "total_summaries": summaries,
        "total_quizzes": quizzes,
        "materials": items,
    }


@app.get("/api/materials/{material_id}")
def read_material(
    material_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    material = get_owned_material(material_id, current_user, db)
    summary_data = None
    if material.summary:
        try:
            summary_data = json.loads(material.summary)
        except json.JSONDecodeError:
            summary_data = None
    latest_quiz = (
        db.query(Quiz)
        .filter(Quiz.material_id == material.id)
        .order_by(Quiz.created_at.desc())
        .first()
    )
    questions = []
    if latest_quiz:
        try:
            questions = json.loads(latest_quiz.questions)
        except json.JSONDecodeError:
            questions = []
    return {
        "id": material.id,
        "title": material.title,
        "filename": material.filename,
        "created_at": material.created_at.isoformat() if material.created_at else None,
        "extracted_text": material.extracted_text or "",
        "summary": summary_data,
        "quiz": questions,
    }


@app.delete("/materials/{material_id}")
def delete_material(
    material_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    material = get_owned_material(material_id, current_user, db)
    file_path = os.path.abspath(material.file_path)
    upload_dir = os.path.abspath(UPLOAD_DIR)
    if os.path.commonpath([os.path.normcase(upload_dir), os.path.normcase(file_path)]) != os.path.normcase(upload_dir):
        raise HTTPException(status_code=400, detail="Invalid PDF storage path.")

    db.query(Quiz).filter(Quiz.material_id == material.id).delete(
        synchronize_session=False
    )
    db.delete(material)
    db.commit()

    try:
        os.remove(file_path)
    except FileNotFoundError:
        pass

    return {"message": "PDF deleted."}


@app.post("/materials/upload")
def upload_material(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    original_name = file.filename or "document.pdf"
    if not original_name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")

    content = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail="File size is too large. The maximum PDF size is 10 MB.",
        )
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    safe_name = f"{uuid.uuid4().hex}.pdf"
    save_path = os.path.join(UPLOAD_DIR, safe_name)
    with open(save_path, "wb") as out:
        out.write(content)

    try:
        normal_text = extract_text_from_pdf(save_path)
        extracted = normal_text
        used_ocr = False
        if len(normal_text) < MIN_TEXT_LENGTH:
            extracted = get_pdf_text(save_path)
            used_ocr = len(extracted) >= MIN_TEXT_LENGTH and len(normal_text) < MIN_TEXT_LENGTH
    except Exception as exc:
        os.remove(save_path)
        raise HTTPException(
            status_code=400,
            detail="Invalid PDF file. Check that the file is a readable PDF and try again.",
        ) from exc

    if not extracted.strip():
        os.remove(save_path)
        raise HTTPException(
            status_code=400,
            detail="We couldn't read text from this PDF. For scanned PDFs, make sure Tesseract OCR is installed and the pages are clear.",
        )

    title = os.path.splitext(os.path.basename(original_name))[0]
    material = Material(
        title=title,
        filename=original_name,
        file_path=save_path,
        extracted_text=extracted,
        summary="",
        owner_id=current_user.id,
    )
    db.add(material)
    db.commit()
    db.refresh(material)
    return {
        "id": material.id,
        "title": material.title,
        "filename": material.filename,
        "text_length": len(extracted),
        "used_ocr_likely": used_ocr,
        "message": "PDF uploaded and text extracted.",
    }

# ==========================================
# 18. SUMMARY API
# ==========================================
# What does this do?
#   Builds an AI summary for one of YOUR PDFs.
# Why do we need it?
#   This is the main study feature.
# How does it work?
#   Check login → check ownership → send text to AI → save JSON summary.


@app.post("/materials/{material_id}/summary")
def create_summary(
    material_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    material = get_owned_material(material_id, current_user, db)
    if not (material.extracted_text or "").strip():
        raise HTTPException(
            status_code=400,
            detail="No text was found in this PDF. Install Tesseract OCR for scanned PDFs.",
        )
    try:
        summary = generate_summary(material.extracted_text)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Unable to generate the summary. Please check your connection and try again.",
        ) from exc

    material.summary = json.dumps(summary)
    db.commit()
    return {"id": material.id, "title": material.title, "summary": summary}

# ==========================================
# 19. QUIZ API
# ==========================================
# What does this do?
#   Builds an AI quiz for one of YOUR PDFs and stores it.
# Why do we need it?
#   Students can test themselves after reading the summary.
# How does it work?
#   Check login → check ownership → AI questions → save Quiz row.


@app.post("/materials/{material_id}/quiz")
def create_quiz(
    material_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    material = get_owned_material(material_id, current_user, db)
    if not (material.extracted_text or "").strip():
        raise HTTPException(
            status_code=400,
            detail="No text was found in this PDF. Install Tesseract OCR for scanned PDFs.",
        )
    try:
        questions = generate_quiz(material.extracted_text)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Unable to generate a quiz. Please try again.",
        ) from exc

    quiz = Quiz(material_id=material.id, questions=json.dumps(questions))
    db.add(quiz)
    db.commit()
    db.refresh(quiz)
    return {"id": quiz.id, "material_id": material.id, "questions": questions}

# ==========================================
# 20. ERROR HANDLING
# ==========================================
# What does this do?
#   Turns unexpected errors into a simple JSON message.
# Why do we need it?
#   Beginners should see a clear message, not a huge crash page.
# How does it work?
#   If a route raises an error we did not expect, this handler catches it.


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return JSONResponse(
        status_code=500,
        content={"detail": "Something went wrong on the server. Please try again."},
    )


# ==========================================
# START APPLICATION
# ==========================================
# What does this do?
#   Optional helper if you run:  python app.py
# The assignment way is still:  uvicorn app:app --reload
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
