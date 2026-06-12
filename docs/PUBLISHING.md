# Publishing To GitHub

Use this checklist before making the repository public.

## 1. Verify No Private Data Is Present

Run:

```bash
git status --short
```

Do not commit:

- `.env`
- `data/`
- SQLite databases
- PostgreSQL dumps
- local tarballs
- screenshots with real customer data

Search for venue-specific values:

```bash
rg "your-real-domain|your-server-ip|your-venue-name|password|secret|token"
```

Review any matches before committing.

## 2. Choose The Public Repository Name

Recommended:

```text
arenaflow
```

Suggested description:

```text
Browser-based attraction game scheduling and capacity control for family entertainment centers.
```

## 3. First Commit

From the project folder:

```bash
git branch -M main
git add .dockerignore .env.example .gitignore Dockerfile LICENSE README.md SECURITY.md docker-compose.yml docs requirements.txt server.py static
git commit -m "Initial public ArenaFlow release"
```

## 4. Create The GitHub Repo

Option A: GitHub website

1. Go to GitHub.
2. Create a new public repository named `arenaflow`.
3. Do not initialize it with a README, license, or gitignore because this repo already has those files.
4. Copy the remote URL GitHub gives you.

Then:

```bash
git remote add origin https://github.com/YOUR-USER/arenaflow.git
git push -u origin main
```

Option B: GitHub CLI

If `gh` is installed and authenticated:

```bash
gh repo create YOUR-USER/arenaflow --public --source=. --remote=origin --push
```

## 5. Add GitHub Topics

Suggested topics:

```text
family-entertainment-center
laser-tag
scheduler
ticket-printer
thermal-printer
docker
postgresql
```

## 6. Create A Release

After the first push, create a GitHub release such as:

```text
v0.1.0
```

Suggested release title:

```text
ArenaFlow v0.1.0
```

Mention that this is an early public release and operators should test in dry-run printer mode before live use.
