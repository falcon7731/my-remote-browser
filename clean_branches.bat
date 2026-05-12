@echo off
setlocal enabledelayedexpansion

echo ==============================================
echo  This will EMPTY the 'client' and 'server'
echo  branches completely (no files, no history).
echo  The branches will still exist, but be empty.
echo ==============================================
set /p confirm="Type 'yes' to continue: "
if /i not "%confirm%"=="yes" (
    echo Cancelled.
    exit /b
)

echo.
echo Fetching latest remote info...
git fetch origin

:: Save current branch to return to later
for /f "tokens=*" %%a in ('git rev-parse --abbrev-ref HEAD') do set "ORIG_BRANCH=%%a"

:: Function to empty a branch
call :empty_branch client
call :empty_branch server

echo.
echo Returning to original branch: %ORIG_BRANCH%
git checkout %ORIG_BRANCH%

echo.
echo Done! 'client' and 'server' are now empty on both local and remote.
pause
exit /b

:empty_branch
set "BRANCH=%~1"
echo.
echo ----- Processing branch: %BRANCH% -----

:: Delete local branch if it exists
git branch -D %BRANCH% 2>nul

:: Remove any worktree files from a previous checkout (safety)
git reset --hard HEAD 2>nul

:: Create a brand new orphan branch (no history)
git checkout --orphan %BRANCH%
if errorlevel 1 (
    echo Failed to create orphan branch %BRANCH%. Skipping.
    exit /b
)

:: Delete ALL files and folders (except .git) from the working tree
echo Removing all files and folders...
for /d %%i in (*) do (
    if /i not "%%i"==".git" (
        rmdir /s /q "%%i" 2>nul
    )
)
for %%f in (*) do (
    del /f /q "%%f" 2>nul
)

:: Also remove hidden files/folders (like .gitignore) – but NOT .git
for /d %%i in (.*) do (
    set "dirname=%%i"
    if /i not "!dirname!"==".git" (
        rmdir /s /q "%%i" 2>nul
    )
)
for %%f in (.*) do (
    if /i not "%%f"==".git" if /i not "%%f"==".gitignore" (
        del /f /q "%%f" 2>nul
    )
)

:: Commit the empty branch (allow empty commit)
echo Committing empty branch...
git add -A
git commit --allow-empty -m "Empty branch (reset)"

:: Force push to GitHub (overwrite remote completely)
echo Pushing empty branch to origin...
git push --force origin %BRANCH%

:: Clean up local orphan branch (switch back later)
git checkout --detach
git branch -D %BRANCH%

echo Branch '%BRANCH%' has been emptied and pushed.
goto :eof