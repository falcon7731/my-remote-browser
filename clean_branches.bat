@echo off
setlocal enabledelayedexpansion

echo ==============================================
echo  SAFE branch resetter
echo  This will make 'client' and 'server' branches
echo  completely empty (no files, no history).
echo  Your current branch will NOT be modified.
echo ==============================================
set /p confirm="Type 'yes' to continue: "
if /i not "%confirm%"=="yes" (
    echo Cancelled.
    exit /b
)

:: Save the current branch so we can return to it
for /f "tokens=*" %%a in ('git rev-parse --abbrev-ref HEAD') do set "ORIG_BRANCH=%%a"

:: Fetch remote info (needed to see if branches exist)
echo.
echo Fetching latest remote info...
git fetch origin

:: Function to empty a branch
:empty_branch
set "BRANCH=%~1"
echo.
echo ========================================
echo Processing branch: %BRANCH%
echo ========================================

:: 1. Try to checkout the branch from remote, or create orphan if missing
echo [1/5] Switching to branch %BRANCH% ...
git checkout %BRANCH% 2>nul
if errorlevel 1 (
    echo Branch does not exist locally or remote. Creating orphan...
    git checkout --orphan %BRANCH%
) else (
    echo Already on branch %BRANCH%.
    :: If we got here, we might have files. We'll delete them next.
)

:: 2. Safety check – are we REALLY on the target branch?
for /f "tokens=*" %%a in ('git rev-parse --abbrev-ref HEAD') do set "CURRENT_BRANCH=%%a"
if /i not "%CURRENT_BRANCH%"=="%BRANCH%" (
    echo ERROR: Could not switch to %BRANCH%. Aborting.
    goto :eof
)

:: 3. Delete ALL files and folders (except .git)
echo [2/5] Deleting all files and folders on %BRANCH% ...
for /d %%i in (*) do (
    if /i not "%%i"==".git" (
        rmdir /s /q "%%i" 2>nul
    )
)
for %%f in (*) do (
    del /f /q "%%f" 2>nul
)

:: Also handle hidden items (except .git)
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

:: 4. Commit the empty state (allow empty commit)
echo [3/5] Committing empty state ...
git add -A
git commit --allow-empty -m "Empty branch (reset)"

:: 5. Force push to overwrite remote history completely
echo [4/5] Force pushing to origin/%BRANCH% ...
git push --force --set-upstream origin %BRANCH%

:: 6. Detach HEAD and delete the local orphan (cleanup)
echo [5/5] Cleaning up local temporary branch ...
git checkout --detach
git branch -D %BRANCH% 2>nul

goto :eof

:: Now call the function for both branches
call :empty_branch client
call :empty_branch server

:: Return to original branch
echo.
echo Returning to original branch: %ORIG_BRANCH%
git checkout %ORIG_BRANCH%

echo.
echo Done! 'client' and 'server' are now empty on both local and remote.
echo All history has been removed.
pause