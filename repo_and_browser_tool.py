#!/usr/bin/env python3
"""
All-in-one script with full debug logging.
All output goes to both console and a 'debug.log' file.
On any error, a traceback is written to 'error.log'.
"""

import os, sys, time, traceback, threading, argparse, shutil
from git import Repo, GitCommandError

# ---------- Playwright import ----------
try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

# ==================== DEBUG LOGGING ====================
LOG_FILE = "debug.log"

def log(msg: str):
    """Print to stdout and append to log file."""
    print(msg, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

# Clear log file at start
if os.path.exists(LOG_FILE):
    os.remove(LOG_FILE)

# Capture unhandled exceptions globally
def global_exception_handler(exc_type, exc_value, exc_tb):
    tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    log(f"FATAL UNHANDLED EXCEPTION:\n{tb_str}")
    with open("error.log", "w") as f:
        f.write(tb_str)

sys.excepthook = global_exception_handler

# ==================== TASK SCHEDULER ====================
class TaskScheduler:
    """Minimal scheduler (unchanged)."""
    def __init__(self):
        self.jobs = []

    def _run_repeated(self, func, remaining, interval, *args, **kwargs):
        if remaining <= 0:
            return
        try:
            func(*args, **kwargs)
        except Exception as e:
            log(f"[Scheduler] Job error: {e}")
        remaining -= 1
        if remaining > 0:
            t = threading.Timer(interval, self._run_repeated,
                                args=[func, remaining, interval] + list(args),
                                kwargs=kwargs)
            t.daemon = True
            t.start()
            self.jobs.append(t)

    def after(self, delay, func, repeat=1, interval=0.0, *args, **kwargs):
        if repeat <= 0:
            return None
        def starter():
            self._run_repeated(func, repeat, interval, *args, **kwargs)
        t = threading.Timer(delay, starter)
        t.daemon = True
        t.start()
        self.jobs.append(t)
        return t

    def list_jobs(self):
        active = [j for j in self.jobs if j.is_alive()]
        log(f"[Scheduler] Active jobs: {len(active)}")
        for i, j in enumerate(active):
            log(f"  {i}: interval={j.interval:.1f}s")

    def cancel_all(self):
        for j in self.jobs:
            j.cancel()
        self.jobs.clear()
        log("[Scheduler] All jobs cancelled.")


# ==================== STEALTH BROWSER ====================
class StealthBrowser:
    """Manages a persistent Chromium with anti-detection flags."""
    def __init__(self, user_data_dir="./browser_profile", headless=False):
        if not HAS_PLAYWRIGHT:
            raise RuntimeError("Playwright not installed.")
        self.user_data_dir = user_data_dir
        self.headless = headless
        self._pw = None
        self._context = None

    def start(self):
        log("[Browser] Starting persistent context...")
        self._pw = sync_playwright().start()
        self._context = self._pw.chromium.launch_persistent_context(
            user_data_dir=self.user_data_dir,
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
            slow_mo=100,
            viewport={"width": 1280, "height": 720},
        )
        log("[Browser] Started persistent context.")

    def stop(self):
        if self._context:
            self._context.close()
        if self._pw:
            self._pw.stop()
        log("[Browser] Stopped.")

    def new_page(self):
        if not self._context:
            raise RuntimeError("Browser not started.")
        return self._context.new_page()

    def goto(self, page, url, wait_until="domcontentloaded"):
        log(f"[Browser] Navigating to {url}...")
        page.goto(url, wait_until=wait_until, timeout=60000)
        log(f"[Browser] Arrived at {page.url}")

    def current_url(self, page):
        return page.url

    def click(self, page, selector, timeout=30000):
        log(f"[Browser] Clicking {selector}")
        page.click(selector, timeout=timeout)

    def scroll(self, page, direction, amount=300):
        direction = direction.lower()
        if direction == "down":
            page.evaluate(f"window.scrollBy(0, {amount})")
        elif direction == "up":
            page.evaluate(f"window.scrollBy(0, -{amount})")
        elif direction == "right":
            page.evaluate(f"window.scrollBy({amount}, 0)")
        elif direction == "left":
            page.evaluate(f"window.scrollBy(-{amount}, 0)")
        else:
            raise ValueError("direction must be up/down/left/right")
        log(f"[Browser] Scrolled {direction} {amount}px")

    def type_text(self, page, selector, text, delay=50):
        log(f"[Browser] Typing into {selector}")
        page.fill(selector, "")
        page.type(selector, text, delay=delay)

    def screenshot(self, page, path="screenshot.png", full_page=True):
        log(f"[Browser] Taking screenshot -> {path}")
        page.screenshot(path=path, full_page=full_page)
        if os.path.exists(path):
            log(f"[Browser] Screenshot saved, size: {os.path.getsize(path)} bytes")
        else:
            log("[Browser] ERROR: Screenshot file not created!")


# ------------------ Page loading helpers ------------------
def wait_for_page_loaded(page, timeout=60000, wait_for_network_idle=True):
    """
    Wait for page load. Timeout increased to 60s.
    If networkidle fails, log and continue.
    """
    try:
        page.wait_for_load_state("load", timeout=timeout)
        log("[Page] 'load' event fired.")
    except Exception as e:
        log(f"[Page] 'load' timeout/error: {e}")
        return False

    if wait_for_network_idle:
        try:
            page.wait_for_load_state("networkidle", timeout=timeout)
            log("[Page] Network idle reached.")
        except Exception as e:
            log(f"[Page] Network idle timeout (continuing): {e}")
    return True

def wait_for_element(page, selector, timeout=10000):
    try:
        page.wait_for_selector(selector, state="visible", timeout=timeout)
        log(f"[Page] Element '{selector}' visible.")
        return True
    except Exception:
        log(f"[Page] Element '{selector}' not visible.")
        return False

def wait_timeout(page, seconds):
    """Wait a fixed amount of time (in seconds)."""
    log(f"[Page] Waiting {seconds} seconds...")
    page.wait_for_timeout(seconds * 1000)
    log("[Page] Fixed wait done.")


# ==================== GIT OPERATIONS (debug added) ====================
class GitRepo:
    """Wrapper for Git operations (no REST API)."""
    def __init__(self, repo_path="."):
        log(f"[Git] Initialising repo at {repo_path}")
        self.repo = Repo(repo_path)
        if self.repo.bare:
            raise ValueError("Bare repo not supported.")
        self.origin = self.repo.remote("origin")

    def pull(self, rebase=False):
        log("[Git] Pulling...")
        try:
            before = self.repo.head.commit.hexsha
            self.origin.pull(rebase=rebase)
            after = self.repo.head.commit.hexsha
            changed = before != after
            log(f"[Git] Pull {'brought new commits' if changed else 'up to date'}.")
            return changed
        except GitCommandError as e:
            log(f"[Git] Pull error: {e}")
            raise

    def shallow_fetch(self, branch="main"):
        self.repo.git.fetch("--depth", "1", "origin", branch)
        log(f"[Git] Shallow fetch {branch}")

    def shallow_pull(self, branch="main"):
        self.repo.git.pull("--depth", "1", "origin", branch)
        log(f"[Git] Shallow pull {branch}")

    def check_branch_update(self, branch="main"):
        self.origin.fetch()  # Git transport
        try:
            local_commit = self.repo.head.commit
            remote_commit = self.repo.refs[f"origin/{branch}"].commit
        except IndexError:
            log(f"[Git] Remote branch origin/{branch} not found.")
            return []
        diffs = remote_commit.diff(local_commit)
        changed = [d.a_path for d in diffs]
        if changed:
            log(f"[Git] Remote '{branch}' changed: {changed}")
        else:
            log(f"[Git] Branch '{branch}' up to date.")
        return changed

    def check_file_update(self, file_path, branch="main"):
        return file_path in self.check_branch_update(branch)

    def switch_branch(self, branch_name, create=False):
        if create:
            self.repo.git.checkout("-b", branch_name)
        else:
            self.repo.git.checkout(branch_name)
        log(f"[Git] Switched to '{branch_name}'.")

    def remove_specific_file(self, file_path, commit_message=None):
        self.repo.index.remove([file_path], working_tree=True)
        if commit_message:
            self.repo.index.commit(commit_message)
            log(f"[Git] Removed '{file_path}' & committed.")
        else:
            log(f"[Git] Removed '{file_path}' (uncommitted).")

    def clean_branch(self, commit_message="Clean branch"):
        tracked = [item.a_path for item in self.repo.index.diff(None)]
        if not tracked:
            tracked = [item.a_path for item in self.repo.head.commit.diff(None)]
        if tracked:
            self.repo.index.remove(tracked, working_tree=True)
            self.repo.index.commit(commit_message)
            log("[Git] Branch cleaned.")
        else:
            log("[Git] No files to remove.")

    def add_all(self):
        self.repo.git.add(A=True)
        log("[Git] All changes staged.")

    def commit(self, message="Automated commit"):
        if self.repo.is_dirty(untracked_files=True):
            self.repo.index.commit(message)
            log(f"[Git] Committed: {message}")
        else:
            log("[Git] Nothing to commit.")

    def push(self, force=False):
        if force:
            self.origin.push(force=True)
            log("[Git] Force pushed.")
        else:
            self.origin.push()
            log("[Git] Pushed.")

    def add_commit_force_push(self, message="Automated force push"):
        self.add_all()
        self.commit(message)
        self.push(force=True)
        log("[Git] add + commit + force push done.")

    def reset_branch_to_log(self, branch_name="season"):
        """
        Resets the given branch to contain ONLY debug.log in a single commit.
        - Force‑recreates the branch locally
        - Deletes all files except debug.log and .git
        - Commits debug.log
        - Force‑pushes (replaces remote history completely)
        """
        log(f"[Git] Cleanup: resetting '{branch_name}' branch to log file only...")
        try:
            # Force‑create/switch to the branch
            self.repo.git.checkout('-B', branch_name)

            # Delete all files/folders except .git and debug.log
            for item in os.listdir('.'):
                if item not in ('.git', 'debug.log'):
                    full_path = os.path.join('.', item)
                    if os.path.isfile(full_path) or os.path.islink(full_path):
                        os.remove(full_path)
                    elif os.path.isdir(full_path):
                        shutil.rmtree(full_path)

            # Ensure debug.log exists (create an empty one if it doesn't)
            if not os.path.exists('debug.log'):
                with open('debug.log', 'w') as f:
                    f.write('')

            # Stage only debug.log
            self.repo.git.add('debug.log')

            # Commit (even if nothing changed, force a new commit)
            self.repo.index.commit("Cleanup: keep only debug.log")

            # Force push to overwrite remote history
            self.repo.git.push('--force', '--set-upstream', 'origin', branch_name)
            log(f"[Git] Cleanup complete. '{branch_name}' now contains only debug.log.")
        except Exception as e:
            log(f"[Git] Cleanup failed: {e}")
            traceback.print_exc()

    @staticmethod
    def shallow_clone(repo_url, target_dir=".", branch="main"):
        if os.path.exists(target_dir):
            shutil.rmtree(target_dir)
        Repo.clone_from(repo_url, target_dir, branch=branch, depth=1)
        log(f"[Git] Shallow clone into '{target_dir}'.")


# ==================== USER RUN FUNCTION ====================
def run(browser, git_repo, page, scheduler):
    """
    Actions‑friendly automation:
      1. Go to YouTube (headless)
      2. Save screenshot (youtube.png)
      3. Force‑push to the 'season' branch (overwrites remote)
    """
    log("=== run() started ===")
    if browser is None or page is None:
        log("❌ Browser not available. Exiting run().")
        return

    try:
        # 1. Navigate to YouTube
        log("Navigating to YouTube...")
        browser.goto(page, "https://www.youtube.com")
        loaded = wait_for_page_loaded(page, timeout=60000, wait_for_network_idle=False)
        log(f"Page loaded successfully: {loaded}")

        # Give the page extra time for lazy‑loaded icons / thumbnails to appear
        wait_timeout(page, 10)

        # 2. Screenshot
        screenshot_file = "youtube.png"
        browser.screenshot(page, screenshot_file)

        # 3. Git operations – force push to override old 'season' branch
        log("Force‑recreating 'season' branch...")
        git_repo.repo.git.checkout('-B', 'season')
        log("Staging changes...")
        git_repo.add_all()
        log("Committing...")
        git_repo.commit("Add YouTube screenshot")
        log("Force pushing to origin/season...")
        # Use --force and --set-upstream to overwrite the remote branch
        git_repo.repo.git.push('--set-upstream', '--force', 'origin', 'season')
        log("✅ Screenshot force‑pushed to 'season' branch.")
    except Exception as e:
        log(f"❌ Exception in run(): {e}")
        tb = traceback.format_exc()
        log(tb)
        with open("error.log", "w") as f:
            f.write(tb)
        raise

    log("=== run() finished ===")


# ==================== MAIN ENTRY POINT ====================
def main():
    log("===== Script started =====")
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", action="store_true", help="Launch stealth browser")
    parser.add_argument("--headless", action="store_true", help="Headless mode")
    args = parser.parse_args()

    # 1. Initialize Git repo
    try:
        git_repo = GitRepo(".")
    except Exception as e:
        log(f"Git init error: {e}")
        sys.exit(1)

    # 2. Pull latest (zero API)
    log("Pulling latest changes...")
    try:
        pulled = git_repo.pull()
        if pulled:
            changes = git_repo.check_branch_update()
            if changes:
                log(f"Remote changes: {changes}")
    except Exception as e:
        log(f"Pull failed: {e}")
        # Continue anyway – the script can still work with local state

    # 3. Browser (if requested)
    browser = None
    page = None
    if args.browser:
        if not HAS_PLAYWRIGHT:
            log("Playwright not installed. Exiting.")
            sys.exit(1)
        browser = StealthBrowser(headless=args.headless)
        try:
            browser.start()
            page = browser.new_page()
        except Exception as e:
            log(f"Browser start failed: {e}")
            log(traceback.format_exc())
            sys.exit(1)
    else:
        log("Running without browser.")

    # 4. Create scheduler
    scheduler = TaskScheduler()

    # 5. Call run() and ensure cleanup
    try:
        run(browser, git_repo, page, scheduler)
    except Exception:
        # Already logged in run()
        sys.exit(1)
    finally:
        # Cleanup the season branch – remove everything except logs
        if git_repo:
            try:
                git_repo.reset_branch_to_log('season')
            except Exception as cleanup_error:
                log(f"Branch cleanup threw an exception: {cleanup_error}")

        if browser:
            try:
                browser.stop()
            except Exception:
                pass

    log("===== Script finished successfully =====")


if __name__ == "__main__":
    main()