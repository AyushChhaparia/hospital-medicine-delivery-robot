# Web application setup

These instructions use platform-neutral paths and commands where possible.
Run all commands from the repository root.

## Prerequisites

- Python 3.10 or newer
- Git
- A virtual-environment-capable Python installation

## Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and set real values for `SECRET_KEY` and `ROBOT_API_TOKEN`.
Generate a strong value with:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

Initialize the local SQLite database and generate demo credentials:

```powershell
python seed.py
python app.py
```

Open `http://127.0.0.1:5000`.

If PowerShell blocks script activation, activate the environment through the
Python interpreter directly instead:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe seed.py
.venv\Scripts\python.exe app.py
```

## Linux or macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"
python seed.py
python app.py
```

Open `http://127.0.0.1:5000`.

## Demo credentials

`seed.py` does not contain fixed demo passwords. Set any of these before
running it if repeatable credentials are needed:

```text
DEMO_ADMIN_PASSWORD
DEMO_MANAGER_PASSWORD
DEMO_EMERGENCY_PASSWORD
DEMO_WARD1_PASSWORD
DEMO_WARD2_PASSWORD
```

Unset variables receive runtime-generated passwords, which `seed.py` prints
once during that run. Treat those values as credentials and do not commit
them.

## Database and environment files

The default database is `instance/hospital.db`. It is local-only and ignored
by Git. `.env` is also ignored. Start with `.env.example`, which contains
placeholders only.

## Tests

```powershell
python -m pytest -q
```

```bash
python -m pytest -q
```

The current suite has 14 collected test functions. The exact result depends on
the installed dependencies and local environment; run the command rather than
assuming a historical test count.

## Application URLs

The ward interface is served at `/ward/<ward_code>`, for example
`/ward/emergency`, `/ward/general_1`, and `/ward/general_2`. The manager and
administrator interfaces are under `/manager` and `/admin`.
