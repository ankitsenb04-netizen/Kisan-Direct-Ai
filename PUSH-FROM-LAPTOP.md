# Push this code to GitHub from your Ubuntu laptop

Repo: https://github.com/ankitsenb04-netizen/Kisan-Direct-Ai
Branch to create: `integration` (against `main`). Do NOT merge yet.

## 0. Make sure GitHub login works (once)

```bash
gh auth status
```

If it says "You are not logged into any GitHub hosts", run:

```bash
gh auth login
```

Choose GitHub.com, HTTPS, Yes to authenticate Git with your GitHub credentials, and Login with a web browser. `ayandevofficial` already has collaborator push permission on this repo.

## 1. Get a fresh clone (skip this if you already have one)

```bash
cd ~
git clone https://github.com/ankitsenb04-netizen/Kisan-Direct-Ai.git
cd Kisan-Direct-Ai
```

If you already have a clone, use it instead:

```bash
cd ~/Kisan-Direct-Ai
git fetch origin
git checkout main
git pull origin main
```

## 2. Create the integration branch

```bash
git checkout -b integration
```

## 3. Copy the ZIP contents over the clone

Unzip the file you downloaded (it contains one folder, `kisan-direct-ai-integration/`), then copy everything, including hidden files, into the clone:

```bash
unzip ~/Downloads/kisan-direct-ai-integration.zip -d /tmp/kisan-zip
cp -r /tmp/kisan-zip/kisan-direct-ai-integration/. .
```

Do NOT copy the `PUSH-FROM-LAPTOP.md` file itself into the commit if you do not want it in the repo; delete it first with `rm PUSH-FROM-LAPTOP.md` (it is only instructions for you).

## 4. Check, commit, push

```bash
git status
git add -A
git commit -m "Integrate homepage/auth/MVP, add orders + JWT/bcrypt auth, farmer dashboard, seed data, tests"
git push -u origin integration
```

## 5. Open the PR (do not merge)

Open this link in your browser and create the pull request against `main`:

https://github.com/ankitsenb04-netizen/Kisan-Direct-Ai/pull/new/integration

Title: `Integrate homepage, auth, marketplace MVP, orders, JWT auth, and farmer dashboard`

Body: see the PR description draft in the integration report, or use this short version:

> Integrates the standalone homepage and auth pages with the marketplace MVP into one app: JWT + bcrypt auth, real ordering backed by the orders table, a farmer dashboard wired to live endpoints, seed demo data, Docker files, pytest (8 passed) and Playwright browser tests (26 passed, 0 failed). Price/demand models still use synthetic demo data; pre-harvest listing, real buyer matching, logistics, negotiation, and FPO are not implemented. Localhost only, do not deploy as-is.

## What this ZIP is

- Final tested version, branch `integration`, commit `8a7377c` (on top of `587e0ee` integration + `4ec07bc` browser-test fixes).
- Verified: pytest `tests/test_integration.py` 8 passed, Playwright `browser-tests/test_browser.py` 26 passed, 0 failed.
- Excluded from the ZIP: virtual environments, `*.db` database files, `.env` secrets, `__pycache__`, and the downloaded Chrome binary.
- Set a real `KISAN_SECRET_KEY` (copy `.env.example` to `.env`) before any non-localhost use.
