# FinPilot – AI-Powered Personal Finance Assistant

FinPilot is an educational, local-first personal finance application built with Flask. It provides individual transaction, budget, savings-goal and bill management, plus transparent machine-learning and statistical tools. It does not connect to banks or payment services.

## Features

- Secure registration/login, per-user records, CSRF protection and login rate limits
- Strong new-password policy, account password change and other-session revocation
- Session inactivity expiration, hardened cookies, security headers and a restrictive script CSP
- Transaction create/edit/delete, search/filter/sort and spreadsheet-safe CSV export
- Monthly category budgets, duplicate-budget protection and threshold alerts
- Savings goals, bill reminders with overdue/paid status and subscription tracking
- Smart Spending Guardian with private avoid preferences, a shopping cap and optional purchase decisions
- Dashboard, printable report, rule-based finance assistant and financial-health indicator
- Savings what-if calculator and a monthly expense forecast
- TF-IDF + Logistic Regression category suggestions with a manual-category path for low confidence
- Isolation Forest unusual-pattern alerts and recurring-transaction pattern detection

## Technology

- Python, Flask, Flask-Login, Flask-SQLAlchemy and Flask-WTF
- SQLite locally (the models use SQLAlchemy and can be configured for another SQLAlchemy-supported database)
- scikit-learn, NumPy and Joblib
- Jinja, Bootstrap, custom responsive CSS, Chart.js and Font Awesome
- pytest

## Architecture

```text
app.py                    Flask application factory, extensions and blueprints
config.py                 Environment-driven configuration
models/                   SQLAlchemy entities
routes/                   Authentication and feature-specific routes
services/                 Finance rules, validation, ML and recurring detection
dataset/                  Labeled sample expense-description CSV
ml/                       Runtime-generated model and evaluation metadata (ignored by Git)
templates/                Jinja pages and shared layout
static/                   Responsive styles and browser behavior
tests/                    Isolated in-memory SQLite pytest suite
instance/                 Local SQLite database (ignored by Git)
```

## Windows PowerShell setup

From the project directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000/login` and register a user. New passwords require at least 12 characters. In local development, FinPilot generates and keeps its secret in the ignored `instance/.secret_key` file. The default local database is `instance/finpilot.db`. Set `DATABASE_URL` to a SQLAlchemy connection string to use a different database.

For production, set `FINPILOT_ENV=production`, configure a random `SECRET_KEY` of at least 32 characters and a shared rate-limit backend such as `RATELIMIT_STORAGE_URI=redis://localhost:6379/0`. Serve through an HTTPS-enabled production WSGI deployment; the built-in Flask server is local-development only. Do not commit environment secrets. Production mode enables secure cookies and HSTS and refuses the in-memory rate-limit store.

## Database

SQLAlchemy models cover users, transactions, budgets, savings goals, planned purchases, avoid preferences, shopping preferences, subscriptions, dismissed recurring suggestions, bill reminders, notifications and insights. New databases are initialized on app startup. User-owned records are filtered by the authenticated user ID; changing database engines or evolving an existing schema should use a deliberate migration process before deployment.

## Machine-learning methodology

### Expense categorization

The labeled CSV contains 80 sample descriptions across eight categories. The training service normalizes labels, holds out a stratified test split (random state 42), trains a TF-IDF + Logistic Regression pipeline and persists the fitted pipeline with Joblib. Dataset content is SHA-256 checked, so changed data triggers retraining. The app records accuracy, weighted precision/recall/F1 and a confusion matrix from the held-out examples. Predictions include confidence; below 0.45, the app asks the user to select a category instead of auto-saving a guess.

The dataset is small and illustrative, so scores are not evidence of production-quality classification. The current checked-in dataset was evaluated locally as follows:

| Metric | Value |
|---|---:|
| Training rows | 60 |
| Held-out rows | 20 |
| Accuracy | 0.4500 |
| Weighted precision | 0.5708 |
| Weighted recall | 0.4500 |
| Weighted F1 | 0.4800 |

These are real results from the current dataset and installed scikit-learn version, not a promise of future performance. Retraining can produce version-dependent results. Evaluation metadata and the Joblib file are generated locally and excluded from Git; the model is trained when first needed.

### Forecasting

Expense transactions are summed by calendar month, including zero-spend gaps. Linear Regression forecasts the next month only when at least four months are available. With seven or more months, the service uses the last three months as a chronological holdout and reports MAE, RMSE and R². Forecasts are estimates and not financial advice.

### Unusual-spending detection

Isolation Forest analyzes a user's own expense amounts, categories, weekdays and day-of-month features, and requires at least ten expenses. Alerts describe unusual patterns, not fraud. The rule-based recurring payment detector compares merchant/description, amount similarity and observed date intervals; its output is a pattern suggestion, not a trained model or bank integration.

## Security and privacy

- Passwords use Werkzeug password hashing.
- New passwords must be at least 12 characters and no more than 128; existing passwords remain valid until changed. Password changes require the current password and revoke all sessions tied to the prior session version.
- Login attempts are limited to 5 per minute and 20 per hour per client address; registrations are limited to 5 per hour. Production must use a shared rate-limit store.
- CSRF protection is enabled for state-changing form submissions; logout uses POST.
- Sessions use HTTP-only, same-site cookies, a 12-hour inactivity timeout and session-ID rotation on login. Secure cookies and HSTS are enabled in production.
- Production startup requires a 32-character environment-provided `SECRET_KEY`.
- Responses include clickjacking, MIME-sniffing, referrer, permissions, cache and CSP protections; inline JavaScript was moved to local scripts.
- Failed login responses do not disclose whether a specific email exists. Password reset by email is not enabled because no verified email-delivery flow is configured; users can change their password while authenticated.
- Server-side checks reject invalid dates, unknown types/categories and non-positive amounts.
- CSV fields are escaped against spreadsheet formula execution.
- Financial queries and record mutations are scoped to the logged-in user.

## Testing

Run the isolated tests from the project directory:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The test app is configured with an in-memory SQLite URL before SQLAlchemy initialization. Tests cover authentication, CSRF, rate limits, password changes and session revocation, transaction CRUD and user isolation, CSV safety, validation, budgets, goals, bills, classifier evaluation/prediction, forecasting, anomaly detection, recurring patterns and guardian decisions.

Latest local verification: `26 passed`.

## Known limitations

- The sample classification dataset is small; add representative labeled descriptions before relying on suggestions.
- Forecasting and anomaly detection need sufficient history and can still be inaccurate.
- Recurring payment detection uses transaction patterns entered by the user; it has no access to bank accounts.
- SQLite initialization uses `create_all`; use schema migrations before shipping schema changes to production.
- The financial health score is an educational indicator, not an official credit score or financial assessment.
- This project is not financial, tax or investment advice.
