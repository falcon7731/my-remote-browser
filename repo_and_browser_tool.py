#!/usr/bin/env python3
"""
Remote‑driven automation orchestrator with cursor helpers, shallow updates,
and a continuous polling loop that executes numerically‑named .py files
from the 'client' branch on the 'server' branch.

After manual stop, both branches are completely emptied (no files, no history).
"""

import os, sys, time, traceback, threading, argparse, shutil, re
from git import Repo, GitCommandError

# ---------- Playwright import ----------
try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

# ==================== CONSOLE LOGGING ====================
def log(msg: str):
    """Print to stdout immediately."""
    print(msg, flush=True)

def global_exception_handler(exc_type, exc_value, exc_tb):
    tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    log(f"FATAL UNHANDLED EXCEPTION:\n{tb_str}")

sys.excepthook = global_exception_handler

# ==================== TASK SCHEDULER ====================
class TaskScheduler:
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
    log(f"[Page] Waiting {seconds} seconds...")
    page.wait_for_timeout(seconds * 1000)
    log("[Page] Fixed wait done.")


# ==================== GIT OPERATIONS ====================
class GitRepo:
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
        """Force local branch to exactly match remote (shallow, no history)."""
        try:
            # Fetch only the latest commit of the remote branch
            self.repo.git.fetch("--depth", "1", "origin", branch)
            # Force local branch to point to the fetched commit
            self.repo.git.reset("--hard", f"origin/{branch}")
            log(f"[Git] Force reset to origin/{branch} (shallow).")
        except GitCommandError as e:
            log(f"[Git] Shallow reset failed for '{branch}': {e}")

    def check_branch_update(self, branch="main"):
        self.origin.fetch()
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

    def _empty_orphan_branch(self, branch_name):
        """Create (or reset) an orphan branch, delete all content, commit empty, force push."""
        log(f"[Git] Orphaning branch '{branch_name}'...")
        self.repo.git.checkout('--orphan', branch_name)
        for item in os.listdir('.'):
            if item != '.git':
                full_path = os.path.join('.', item)
                if os.path.isfile(full_path) or os.path.islink(full_path):
                    os.remove(full_path)
                elif os.path.isdir(full_path):
                    shutil.rmtree(full_path)
        self.repo.git.commit('--allow-empty', '-m', 'Empty branch')
        self.repo.git.push('--force', '--set-upstream', 'origin', branch_name)
        log(f"[Git] Branch '{branch_name}' is now empty (orphaned).")


# ==================== TASK ORCHESTRATION LOOP ====================
def natural_sort_key(filename):
    """Extract the leading integer from a filename like '12.py' for natural sorting."""
    m = re.match(r'(\d+)', filename)
    return int(m.group(1)) if m else float('inf')


def orchestrate_loop(git_repo, browser, page, scheduler):
    """
    Infinite loop:
     1. Checkout client branch, shallow update.
     2. Find next unexecuted .py file (numerically sorted).
     3. If none, wait 3s and repeat.
     4. Read script, switch to server, shallow update.
     5. Execute script with injected helpers + sequence_number.
     6. Mark as executed, loop back to step 1.
    """
    log("=== Starting infinity task loop ===")
    executed = set()  # filenames (without .py extension) already processed

    # ---------- Build cursor helper functions (if browser is active) ----------
    cursor_helpers = {}
    if page is not None:
        def _move_mouse(x, y):
            page.mouse.move(x, y)

        def _get_cursor_position():
            pos = page.evaluate("""() => {
                return { x: window.__cursorX || 0, y: window.__cursorY || 0 };
            }""")
            return pos['x'], pos['y']

        def _show_cursor():
            page.evaluate("""() => {
                if (document.getElementById('__custom_cursor')) return;
                let cursor = document.createElement('div');
                cursor.id = '__custom_cursor';
                cursor.style.position = 'fixed';
                cursor.style.width = '20px';
                cursor.style.height = '20px';
                cursor.style.borderRadius = '50%';
                cursor.style.backgroundColor = 'red';
                cursor.style.pointerEvents = 'none';
                cursor.style.zIndex = '999999';
                cursor.style.transform = 'translate(-50%, -50%)';
                document.body.appendChild(cursor);
                window.__cursorX = 0;
                window.__cursorY = 0;
                window.addEventListener('mousemove', e => {
                    window.__cursorX = e.clientX;
                    window.__cursorY = e.clientY;
                    cursor.style.left = e.clientX + 'px';
                    cursor.style.top = e.clientY + 'px';
                });
            }""")

        def _hide_cursor():
            page.evaluate("""() => {
                let cursor = document.getElementById('__custom_cursor');
                if (cursor) cursor.remove();
            }""")

        cursor_helpers = {
            'move_mouse': _move_mouse,
            'get_cursor_position': _get_cursor_position,
            'show_cursor': _show_cursor,
            'hide_cursor': _hide_cursor,
        }

    while True:
        try:
            # ----- 1. Switch to client + shallow update -----
            git_repo.repo.git.checkout('client')
            git_repo.shallow_pull('client')

            # ----- 2. Discover unexecuted scripts -----
            all_files = [f for f in os.listdir('.') if f.endswith('.py') and f != '__init__.py']
            unexecuted = [f for f in all_files if os.path.splitext(f)[0] not in executed]

            if not unexecuted:
                log("No new unexecuted scripts. Waiting 3 seconds...")
                time.sleep(3)
                continue

            # Natural sort by leading integer
            unexecuted.sort(key=natural_sort_key)
            script_name = unexecuted[0]
            script_stem = os.path.splitext(script_name)[0]
            log(f"Next script: {script_name} (sequence {script_stem})")

            # Read code while on client
            with open(script_name, 'r', encoding='utf-8') as f:
                code = f.read()

            # ----- 3. Switch to server + shallow update -----
            git_repo.repo.git.checkout('server')
            git_repo.shallow_pull('server')

            # ----- 4. Execute script -----
            task_globals = {
                'browser': browser,
                'page': page,
                'git_repo': git_repo,
                'scheduler': scheduler,
                'log': log,
                'wait_for_page_loaded': wait_for_page_loaded,
                'wait_for_element': wait_for_element,
                'wait_timeout': wait_timeout,
                'time': time,
                'os': os,
                'sys': sys,
                'sequence_number': script_stem,
            }
            # Add cursor helpers if available
            task_globals.update(cursor_helpers)

            log(f"--- Executing {script_name} ---")
            try:
                exec(compile(code, script_name, 'exec'), task_globals)
                log(f"{script_name} completed successfully.")
            except Exception as e:
                log(f"{script_name} failed: {e}")
                traceback.print_exc()

            # ----- 5. Mark as executed -----
            executed.add(script_stem)
            log(f"Marked {script_name} as executed. Total completed: {len(executed)}")

        except Exception as loop_err:
            log(f"Loop iteration error (will retry): {loop_err}")
            traceback.print_exc()
            time.sleep(5)   # Avoid tight crash loop


# ==================== MAIN ====================
def main():
    log("===== Script started =====")
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", action="store_true", help="Launch stealth browser")
    parser.add_argument("--headless", action="store_true", help="Headless mode")
    args = parser.parse_args()

    # Ensure Git identity is set (fallback in case workflow didn't)
    os.system('git config user.name "github-actions[bot]"')
    os.system('git config user.email "github-actions[bot]@users.noreply.github.com"')

    git_repo = None
    browser = None
    page = None
    scheduler = TaskScheduler()

    try:
        # 1. Initialize Git repo
        git_repo = GitRepo(".")
        log("Pulling latest main branch...")
        git_repo.pull()

        # 2. Bootstrap: force both branches to be empty orphans (no history, no files)
        log("Initialising empty client & server branches...")
        git_repo._empty_orphan_branch('client')
        git_repo._empty_orphan_branch('server')

        # 3. Browser (if requested)
        if args.browser:
            if not HAS_PLAYWRIGHT:
                log("Playwright not installed. Exiting.")
                sys.exit(1)
            browser = StealthBrowser(headless=args.headless)
            browser.start()
            page = browser.new_page()
        else:
            log("Running without browser.")

        # 4. Enter infinite orchestration loop (blocks until manual stop)
        orchestrate_loop(git_repo, browser, page, scheduler)

    except KeyboardInterrupt:
        log("Manual stop requested.")
    except Exception as e:
        log(f"Fatal error in main: {e}")
        traceback.print_exc()
    finally:
        # ALWAYS empty both client and server branches
        if git_repo:
            for branch in ['client', 'server']:
                try:
                    git_repo._empty_orphan_branch(branch)
                except Exception as e:
                    log(f"Failed to empty branch '{branch}': {e}")

        if browser:
            try:
                browser.stop()
            except Exception:
                pass

        log("===== Script finished =====")


if __name__ == "__main__":
    main()