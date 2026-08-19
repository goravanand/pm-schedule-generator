# ── AI PM Schedule Generator — GitHub Deploy Script ──────────────────────────
# Run this once in PowerShell to create the repo and push all files.
# Prerequisites: GitHub Desktop installed, gh CLI installed

$GIT = "C:\Users\z0056wyn\AppData\Local\GitHubDesktop\app-3.5.12\resources\app\git\cmd\git.exe"
$env:PATH = "C:\Program Files\GitHub CLI\;" + $env:PATH
Set-Location "C:\Users\z0056wyn\pm-generator"

Write-Host "`n=== Step 1: Login to GitHub ===" -ForegroundColor Cyan
Write-Host "A browser window will open — sign in and authorise the GitHub CLI." -ForegroundColor Yellow
gh auth login --web --hostname github.com

Write-Host "`n=== Step 2: Create GitHub repository ===" -ForegroundColor Cyan
gh repo create pm-schedule-generator --public --description "AI PM Schedule Generator — AR-952 prototype" --confirm

Write-Host "`n=== Step 3: Initialise git and push code ===" -ForegroundColor Cyan
& $GIT init
& $GIT add .
& $GIT commit -m "Initial commit — AI PM Schedule Generator prototype (AR-952)"
& $GIT branch -M main

# Get GitHub username
$ghUser = gh api user --jq .login
& $GIT remote add origin "https://github.com/$ghUser/pm-schedule-generator.git"
& $GIT push -u origin main

Write-Host "`n=== Done! ===" -ForegroundColor Green
Write-Host "GitHub repo: https://github.com/$ghUser/pm-schedule-generator" -ForegroundColor Green
Write-Host "`nNext step — deploy to Streamlit Cloud:" -ForegroundColor Cyan
Write-Host "1. Go to https://share.streamlit.io" -ForegroundColor White
Write-Host "2. Sign in with GitHub" -ForegroundColor White
Write-Host "3. Click New app → select pm-schedule-generator → app.py → Deploy" -ForegroundColor White
Write-Host "4. Under Advanced settings → Secrets, paste your API key:" -ForegroundColor White
Write-Host '   ANTHROPIC_API_KEY = "your-key-here"' -ForegroundColor Yellow
