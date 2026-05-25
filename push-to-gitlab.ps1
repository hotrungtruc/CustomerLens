# Script để push các cập nhật lên GitLab
# Usage: .\push-to-gitlab.ps1

$gitlabUrl = "https://gitlab.com/hotrungtruc1706/face-recognition-system"
$branch = "main"
$commitMessage = "Update database and add new students/staff"

Write-Host "🚀 Pushing to GitLab..." -ForegroundColor Cyan

# 1. Kiểm tra Git repository
if (-not (Test-Path ".git")) {
    Write-Host "⚠️  Initializing Git repository..." -ForegroundColor Yellow
    git init
    git branch -M $branch
}

# 2. Thêm remote GitLab nếu chưa có
$remoteExists = git remote | Select-String origin
if (-not $remoteExists) {
    Write-Host "➕ Adding GitLab remote..." -ForegroundColor Yellow
    git remote add origin $gitlabUrl
}
else {
    Write-Host "✅ Remote 'origin' already exists" -ForegroundColor Green
}

# 3. Cấu hình Git (nếu chưa có)
Write-Host "🔧 Configuring Git..." -ForegroundColor Yellow
git config --local user.email "hotrungtruc1706@gmail.com"
git config --local user.name "Ho Trung Truc"

# 4. Add tất cả các thay đổi
Write-Host "📝 Staging changes..." -ForegroundColor Yellow
git add .

# 5. Kiểm tra status
$status = git status --porcelain
if ($status) {
    Write-Host "📊 Files to commit:" -ForegroundColor Cyan
    git status --short
    
    # 6. Commit
    Write-Host "💾 Committing changes..." -ForegroundColor Yellow
    git commit -m $commitMessage
    
    # 7. Push to GitLab
    Write-Host "📤 Pushing to GitLab ($branch)..." -ForegroundColor Yellow
    git push -u origin $branch
    
    Write-Host "✅ Pushed successfully!" -ForegroundColor Green
    Write-Host "View at: $gitlabUrl/-/tree/$branch" -ForegroundColor Cyan
}
else {
    Write-Host "⏭️  No changes to commit" -ForegroundColor Yellow
}

Write-Host ""
