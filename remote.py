#!/usr/bin/env python3
"""
All-in-one script:
  - Git operations (zero API)
  - Stealth Playwright browser (persistent context)
  - Period task scheduler (delayed + repeated)
  - User-defined run() function

To use: modify the run() function at the bottom and execute:
  python repo_and_browser_tool.py [--browser] [--headless]
"""

import os, sys, time, threading, argparse
from git import Repo, GitCommandError

# ---------- Playwright import ----------
try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


# ==================== TASK SCHEDULER ====================
class TaskScheduler:
    """
    Minimal scheduler to run functions after a delay, with optional repetition.
    Jobs are tracked in `self.jobs` (list of threading.Timer).
    Use:
        sched = TaskScheduler()
        sched.after(10, my_func, repeat=3, interval=5)   # 10s delay, then 3 times every 5s
        sched.list_jobs()      # show active timers
        sched.cancel_all()     # stop all
    """
    def __init__(self):
        self.jobs = []          # list of threading.Timer objects

    def _run_repeated(self, func, remaining, interval, *args, **kwargs):
        """Internal: execute func and re-schedule if repeats left."""
        if remaining <= 0:
            return
        func(*args, **kwargs)
        remaining -= 1
        if remaining > 0:
            t = threading.Timer(interval, self._run_repeated,
                                args=[func, remaining, interval] + list(args),
                                kwargs=kwargs)
            t.daemon = True
            t.start()
            self.jobs.append(t)

    def after(self, delay, func, repeat=1, interval=0.0, *args, **kwargs):
        """
        Schedule func to run after 'delay' seconds.
        If repeat > 1, it will run every 'interval' seconds for 'repeat' times.
        Interval applies between consecutive runs.
        Returns the first Timer object.
        """
        if repeat <= 0:
            return None
        # First run after delay, then schedule repetitions
        def starter():
            self._run_repeated(func, repeat, interval, *args, **kwargs)
        t = threading.Timer(delay, starter)
        t.daemon = True
        t.start()
        self.jobs.append(t)
        return t

    def list_jobs(self):
        """Print info about all currently active timers."""
        active = [j for j in self.jobs if j.is_alive()]
        print(f"[Scheduler] Active jobs: {len(active)}")
        for i, j in enumerate(active):
            print(f"  {i}: interval={j.interval:.1f}s, function={j.function}")

    def cancel_all(self):
        """Cancel all pending timers."""
        for j in self.jobs:
            j.cancel()
        self.jobs.clear()
        print("[Scheduler] All jobs cancelled.")


# ==================== STEALTH BROWSER ====================
class StealthBrowser:
    """Manages a persistent Chromium with anti-detection flags."""
    def __init__(self, user_data_dir="./browser_profile", headless=False):
        if not HAS_PLAYWRIGHT:
            raise RuntimeError("Playwright not installed. See setup instructions.")
        self.user_data_dir = user_data_dir
        self.headless = headless
        self._pw = None
        self._context = None

    def start(self):
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
        print("[Browser] Started persistent context.")

    def stop(self):
        if self._context:
            self._context.close()
        if self._pw:
            self._pw.stop()
        print("[Browser] Stopped.")

    def new_page(self):
        if not self._context:
            raise RuntimeError("Browser not started.")
        return self._context.new_page()

    # ---------- Browser actions ----------
    def goto(self, page, url, wait_until="domcontentloaded"):
        page.goto(url, wait_until=wait_until)
        print(f"[Browser] Navigated to {url}")

    def current_url(self, page):
        return page.url

    def click(self, page, selector, timeout=30000):
        page.click(selector, timeout=timeout)
        print(f"[Browser] Clicked {selector}")

    def scroll(self, page, direction, amount=300):
        if direction == "down":
            page.evaluate(f"window.scrollBy(0, {amount})")
        elif direction == "up":
            page.evaluate(f"window.scrollBy(0, -{amount})")
        elif direction == "right":
            page.evaluate(f"window.scrollBy({amount}, 0)")
        elif direction == "left":
            page.evaluate(f"window.scrollBy(-{amount}, 0)")
        print(f"[Browser] Scrolled {direction} by {amount}px")

    def type_text(self, page, selector, text, delay=50):
        page.fill(selector, "")
        page.type(selector, text, delay=delay)
        print(f"[Browser] Typed '{text}' into {selector}")

    def screenshot(self, page, path="screenshot.png", full_page=True):
        page.screenshot(path=path, full_page=full_page)
        print(f"[Browser] Screenshot saved: {path}")


# ------------------ Page loading helpers ------------------
def wait_for_page_loaded(page, timeout=30000, wait_for_network_idle=True):
    """
    Wait until page is fully loaded.
    - First waits for 'load' event.
    - Optionally waits for network idle (no ongoing requests for 500ms).
    Returns True if finished within timeout.
    """
    try:
        page.wait_for_load_state("load", timeout=timeout)
        if wait_for_network_idle:
            page.wait_for_load_state("networkidle", timeout=timeout)
        print("[Page] Fully loaded (and network idle).")
        return True
    except Exception as e:
        print(f"[Page] Load timeout/error: {e}")
        return False

# (Optional) Wait for a specific element to be visible
def wait_for_element(page, selector, timeout=10000):
    try:
        page.wait_for_selector(selector, state="visible", timeout=timeout)
        print(f"[Page] Element '{selector}' visible.")
        return True
    except Exception:
        print(f"[Page] Element '{selector}' not visible within timeout.")
        return False


# ==================== GIT OPERATIONS (ZERO API) ====================
class GitRepo:
    """Wrapper for all requested Git operations (using transport, not REST)."""
    def __init__(self, repo_path="."):
        self.repo = Repo(repo_path)
        if self.repo.bare:
            raise ValueError("Bare repo not supported.")
        self.origin = self.repo.remote("origin")

    def pull(self, rebase=False):
        before = self.repo.head.commit.hexsha
        self.origin.pull(rebase=rebase)
        return before != self.repo.head.commit.hexsha

    def shallow_fetch(self, branch="main"):
        self.repo.git.fetch("--depth", "1", "origin", branch)
        print(f"[Git] Shallow fetch of {branch} done.")

    def shallow_pull(self, branch="main"):
        self.repo.git.pull("--depth", "1", "origin", branch)
        print(f"[Git] Shallow pull of {branch} done.")

    def check_branch_update(self, branch="main"):
        self.origin.fetch()  # Git protocol
        try:
            local_commit = self.repo.head.commit
            remote_commit = self.repo.refs[f"origin/{branch}"].commit
        except IndexError:
            print(f"[Git] Remote branch origin/{branch} not found.")
            return []
        diffs = remote_commit.diff(local_commit)
        changed = [d.a_path for d in diffs]
        if changed:
            print(f"[Git] Remote branch '{branch}' has changes: {changed}")
        else:
            print(f"[Git] Branch '{branch}' up to date.")
        return changed

    def check_file_update(self, file_path, branch="main"):
        return file_path in self.check_branch_update(branch)

    def switch_branch(self, branch_name, create=False):
        if create:
            self.repo.git.checkout("-b", branch_name)
        else:
            self.repo.git.checkout(branch_name)
        print(f"[Git] Switched to branch '{branch_name}'.")

    def remove_specific_file(self, file_path, commit_message=None):
        self.repo.index.remove([file_path], working_tree=True)
        if commit_message:
            self.repo.index.commit(commit_message)
            print(f"[Git] Removed '{file_path}' & committed.")
        else:
            print(f"[Git] Removed '{file_path}' (uncommitted).")

    def clean_branch(self, commit_message="Clean branch"):
        tracked = [item.a_path for item in self.repo.index.diff(None)]
        if not tracked:
            tracked = [item.a_path for item in self.repo.head.commit.diff(None)]
        if tracked:
            self.repo.index.remove(tracked, working_tree=True)
            self.repo.index.commit(commit_message)
            print("[Git] Branch cleaned.")
        else:
            print("[Git] No files to remove.")

    def add_all(self):
        self.repo.git.add(A=True)

    def commit(self, message="Automated commit"):
        if self.repo.is_dirty(untracked_files=True):
            self.repo.index.commit(message)
            print(f"[Git] Committed: {message}")
        else:
            print("[Git] Nothing to commit.")

    def push(self, force=False):
        if force:
            self.origin.push(force=True)
            print("[Git] Force pushed.")
        else:
            self.origin.push()
            print("[Git] Pushed.")

    def add_commit_force_push(self, message="Automated force push"):
        self.add_all()
        self.commit(message)  # commits even if no changes? No, commit() checks dirtiness
        self.push(force=True)
        print("[Git] add + commit + force push completed.")

    @staticmethod
    def shallow_clone(repo_url, target_dir=".", branch="main"):
        import shutil
        if os.path.exists(target_dir):
            shutil.rmtree(target_dir)
        Repo.clone_from(repo_url, target_dir, branch=branch, depth=1)
        print(f"[Git] Shallow clone into '{target_dir}'.")


# ==================== USER RUN FUNCTION ====================

'''
# Example: Schedule a task – take screenshot every 30 seconds, 5 times, starting 10s from now
    def take_screenshot_job():
        print("Scheduled screenshot...")
        browser.screenshot(page, f"scheduled_{int(time.time())}.png")

    scheduler.after(10, take_screenshot_job, repeat=5, interval=30)

    # Example: Periodic file check (Git zero-API)
    def check_remote_file():
        if git_repo.check_file_update("data.json"):
            print("Remote data.json changed, pulling...")
            git_repo.pull()
            # maybe process the new data...

    scheduler.after(20, check_remote_file, repeat=3, interval=60)

    # Keep the script alive for the scheduled tasks (they run in background threads)
    print("Run function finished, waiting for scheduled jobs...")
    # Optionally wait until all jobs are done, or just let the script exit with daemon threads.
    # Daemon threads will be stopped when the program exits. If you need them to finish, join them.
    for job in scheduler.jobs:
        if job.is_alive():
            job.join()   # wait for each to finish; blocking

    print("Main run completed.")
    
'''
def run(browser, git_repo, page, scheduler):
    """
    Actions‑friendly automation:
      1. Go to YouTube (invisible headless browser)
      2. Save a screenshot (youtube.png)
      3. Push the file to the 'season' branch
    """
    if browser is None or page is None:
        print("❌ Browser not available. Run with --browser --headless in Actions.")
        return

    # 1. Navigate to YouTube and wait until fully loaded
    browser.goto(page, "https://www.youtube.com")
    wait_for_page_loaded(page, timeout=30000)

    # 2. Take screenshot
    screenshot_file = "youtube.png"
    browser.screenshot(page, screenshot_file)
    print(f"📸 Screenshot saved: {screenshot_file}")

    # 3. Switch to / reset the 'season' branch (create if not exists,
    #    reset to the current commit to avoid conflicts)
    git_repo.repo.git.checkout('-B', 'season')

    # 4. Stage the new file, commit, and push with upstream
    git_repo.add_all()
    git_repo.commit("Add YouTube screenshot")
    git_repo.repo.git.push('--set-upstream', 'origin', 'season')

    print("✅ Screenshot pushed to 'season' branch.")

    


# ==================== MAIN ENTRY POINT ====================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", action="store_true", help="Launch stealth browser")
    parser.add_argument("--headless", action="store_true", help="Headless mode (only with --browser)")
    args = parser.parse_args()

    # 1. Initialize Git repo
    try:
        git_repo = GitRepo(".")
    except Exception as e:
        print(f"Git init error: {e}")
        sys.exit(1)

    # 2. Pull latest (zero API)
    print("Pulling latest changes...")
    pulled = git_repo.pull()
    if pulled:
        changes = git_repo.check_branch_update()
        if changes:
            print("Remote changes detected:", changes)
    else:
        print("Already up to date.")

    # 3. Browser (if requested)
    browser = None
    page = None
    if args.browser:
        if not HAS_PLAYWRIGHT:
            print("Playwright not installed. Exiting.")
            sys.exit(1)
        browser = StealthBrowser(headless=args.headless)
        browser.start()
        page = browser.new_page()
    else:
        print("Running without browser (Git-only mode).")

    # 4. Create scheduler
    scheduler = TaskScheduler()

    # 5. Call user's run function
    try:
        run(browser, git_repo, page, scheduler)
    finally:
        if browser:
            browser.stop()


if __name__ == "__main__":
    main()