#!/usr/bin/env python3
"""
Remote‑driven automation orchestrator with cursor helpers, shallow updates,
and a continuous polling loop that executes numerically‑named .py files
from the 'client' branch on the 'server' branch.

After manual stop, both branches are cleared of all files (history kept).
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
        if remaining <= 0: return
        try: func(*args, **kwargs)
        except Exception as e: log(f"[Scheduler] Job error: {e}")
        remaining -= 1
        if remaining > 0:
            t = threading.Timer(interval, self._run_repeated,
                                args=[func, remaining, interval] + list(args), kwargs=kwargs)
            t.daemon = True; t.start(); self.jobs.append(t)
    def after(self, delay, func, repeat=1, interval=0.0, *args, **kwargs):
        if repeat <= 0: return None
        def starter(): self._run_repeated(func, repeat, interval, *args, **kwargs)
        t = threading.Timer(delay, starter)
        t.daemon = True; t.start(); self.jobs.append(t); return t
    def list_jobs(self):
        active = [j for j in self.jobs if j.is_alive()]
        log(f"[Scheduler] Active jobs: {len(active)}")
    def cancel_all(self):
        for j in self.jobs: j.cancel()
        self.jobs.clear()
        log("[Scheduler] All jobs cancelled.")

# ==================== STEALTH BROWSER ====================
class StealthBrowser:
    def __init__(self, user_data_dir="./browser_profile", headless=False):
        if not HAS_PLAYWRIGHT: raise RuntimeError("Playwright not installed.")
        self.user_data_dir = user_data_dir
        self.headless = headless
        self._pw = None; self._context = None
    def start(self):
        log("[Browser] Starting persistent context...")
        self._pw = sync_playwright().start()
        self._context = self._pw.chromium.launch_persistent_context(
            user_data_dir=self.user_data_dir, headless=self.headless,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            slow_mo=100, viewport={"width":1280,"height":720})
        log("[Browser] Started.")
    def stop(self):
        if self._context: self._context.close()
        if self._pw: self._pw.stop()
        log("[Browser] Stopped.")
    def new_page(self):
        if not self._context: raise RuntimeError("Browser not started.")
        return self._context.new_page()
    def goto(self, page, url, wait_until="domcontentloaded"):
        log(f"[Browser] Navigating to {url}...")
        page.goto(url, wait_until=wait_until, timeout=60000)
        log(f"[Browser] Arrived at {page.url}")
    def current_url(self, page): return page.url
    def click(self, page, selector, timeout=30000):
        log(f"[Browser] Clicking {selector}"); page.click(selector, timeout=timeout)
    def scroll(self, page, direction, amount=300):
        d = direction.lower()
        if d == "down": page.evaluate(f"window.scrollBy(0, {amount})")
        elif d == "up": page.evaluate(f"window.scrollBy(0, -{amount})")
        elif d == "right": page.evaluate(f"window.scrollBy({amount}, 0)")
        elif d == "left": page.evaluate(f"window.scrollBy(-{amount}, 0)")
        else: raise ValueError("direction must be up/down/left/right")
        log(f"[Browser] Scrolled {d} {amount}px")
    def type_text(self, page, selector, text, delay=50):
        log(f"[Browser] Typing into {selector}")
        page.fill(selector, "")
        page.type(selector, text, delay=delay)
    def screenshot(self, page, path="screenshot.png", full_page=True):
        log(f"[Browser] Taking screenshot -> {path}")
        page.screenshot(path=path, full_page=full_page)
        if os.path.exists(path):
            log(f"[Browser] Screenshot saved, size: {os.path.getsize(path)} bytes")
        else: log("[Browser] ERROR: Screenshot file not created!")

# ------------------ Page helpers ------------------
def wait_for_page_loaded(page, timeout=60000, wait_for_network_idle=True):
    try: page.wait_for_load_state("load", timeout=timeout); log("[Page] 'load' event fired.")
    except Exception as e: log(f"[Page] 'load' timeout/error: {e}"); return False
    if wait_for_network_idle:
        try: page.wait_for_load_state("networkidle", timeout=timeout); log("[Page] Network idle.")
        except Exception as e: log(f"[Page] Network idle timeout (continuing): {e}")
    return True
def wait_for_element(page, selector, timeout=10000):
    try: page.wait_for_selector(selector, state="visible", timeout=timeout); log(f"[Page] Element '{selector}' visible."); return True
    except Exception: log(f"[Page] Element '{selector}' not visible."); return False
def wait_timeout(page, seconds):
    log(f"[Page] Waiting {seconds} seconds...")
    page.wait_for_timeout(seconds * 1000)
    log("[Page] Fixed wait done.")

# ==================== GIT OPERATIONS ====================
class GitRepo:
    def __init__(self, repo_path="."):
        log(f"[Git] Initialising repo at {repo_path}")
        self.repo = Repo(repo_path)
        if self.repo.bare: raise ValueError("Bare repo not supported.")
        self.origin = self.repo.remote("origin")

    def pull(self, rebase=False):
        log("[Git] Pulling...")
        try:
            before = self.repo.head.commit.hexsha
            self.origin.pull(rebase=rebase)
            after = self.repo.head.commit.hexsha
            log(f"[Git] Pull {'new commits' if before != after else 'up to date'}.")
            return before != after
        except GitCommandError as e:
            log(f"[Git] Pull error: {e}"); raise

    def shallow_pull(self, branch="main"):
        """Force local branch to match remote exactly (shallow)."""
        try:
            self.repo.git.fetch("--depth", "1", "origin", branch)
            self.repo.git.reset("--hard", f"origin/{branch}")
            log(f"[Git] Force reset to origin/{branch} (shallow).")
        except GitCommandError as e:
            log(f"[Git] Shallow reset failed for '{branch}': {e}")

    def check_branch_update(self, branch="main"):
        self.origin.fetch()
        try:
            local = self.repo.head.commit
            remote = self.repo.refs[f"origin/{branch}"].commit
            diffs = remote.diff(local); changed = [d.a_path for d in diffs]
            if changed: log(f"[Git] Remote '{branch}' changed: {changed}")
            else: log(f"[Git] Branch '{branch}' up to date.")
            return changed
        except IndexError: log(f"[Git] Remote branch origin/{branch} not found."); return []
    def check_file_update(self, file_path, branch="main"): return file_path in self.check_branch_update(branch)
    def switch_branch(self, branch_name, create=False):
        if create: self.repo.git.checkout("-b", branch_name)
        else: self.repo.git.checkout(branch_name)
        log(f"[Git] Switched to '{branch_name}'.")
    def remove_specific_file(self, file_path, commit_message=None):
        self.repo.index.remove([file_path], working_tree=True)
        if commit_message: self.repo.index.commit(commit_message)
    def clean_branch(self, commit_message="Clean branch"):
        tracked = [item.a_path for item in self.repo.index.diff(None)] or \
                  [item.a_path for item in self.repo.head.commit.diff(None)]
        if tracked: self.repo.index.remove(tracked, working_tree=True); self.repo.index.commit(commit_message)
    def add_all(self): self.repo.git.add(A=True); log("[Git] All changes staged.")
    def commit(self, msg="Automated commit"):
        if self.repo.is_dirty(untracked_files=True): self.repo.index.commit(msg)
    def push(self, force=False):
        if force: self.origin.push(force=True)
        else: self.origin.push()
    def add_commit_force_push(self, msg="Automated force push"):
        self.add_all(); self.commit(msg); self.push(force=True)

    def clear_branch_files(self, branch_name, commit_message="Clear branch files"):
        """Delete all files on the branch and commit the deletion. History remains."""
        log(f"[Git] Clearing files on branch '{branch_name}'...")
        try:
            self.repo.git.checkout(branch_name)
        except GitCommandError:
            log(f"[Git] Branch '{branch_name}' does not exist; skipping.")
            return
        for item in os.listdir('.'):
            if item != '.git':
                full = os.path.join('.', item)
                if os.path.isfile(full) or os.path.islink(full): os.remove(full)
                elif os.path.isdir(full): shutil.rmtree(full)
        self.add_all()
        if self.repo.is_dirty(untracked_files=True):
            self.repo.index.commit(commit_message)
            log(f"[Git] Committed file deletions on '{branch_name}'.")
        else:
            log(f"[Git] No files to delete on '{branch_name}'.")
        self.origin.push()
        log(f"[Git] Pushed cleared branch '{branch_name}'.")

# ==================== ORCHESTRATION LOOP ====================
def natural_sort_key(f): return int(re.match(r'(\d+)', f).group(1)) if re.match(r'(\d+)', f) else float('inf')

def orchestrate_loop(git_repo, browser, page, scheduler):
    log("=== Starting infinity task loop ===")
    executed = set()
    cursor_helpers = {}
    if page is not None:
        def move_mouse(x,y): page.mouse.move(x,y)
        def get_cursor_position():
            pos = page.evaluate("""() => ({ x: window.__cursorX || 0, y: window.__cursorY || 0 })""")
            return pos['x'], pos['y']
        def show_cursor():
            page.evaluate("""() => {
                if (document.getElementById('__custom_cursor')) return;
                let c = document.createElement('div'); c.id = '__custom_cursor';
                c.style = 'position:fixed;width:20px;height:20px;border-radius:50%;background:red;pointer-events:none;z-index:999999;transform:translate(-50%,-50%)';
                document.body.appendChild(c);
                window.__cursorX=0; window.__cursorY=0;
                window.addEventListener('mousemove', e => {
                    window.__cursorX=e.clientX; window.__cursorY=e.clientY;
                    c.style.left = e.clientX+'px'; c.style.top = e.clientY+'px';
                });
            }""")
        def hide_cursor():
            page.evaluate("""() => { let c = document.getElementById('__custom_cursor'); if(c) c.remove(); }""")
        cursor_helpers = {'move_mouse':move_mouse, 'get_cursor_position':get_cursor_position,
                          'show_cursor':show_cursor, 'hide_cursor':hide_cursor}

    while True:
        try:
            git_repo.repo.git.checkout('client')
            git_repo.shallow_pull('client')
            all_py = [f for f in os.listdir('.') if f.endswith('.py') and f != '__init__.py']
            unexecuted = [f for f in all_py if os.path.splitext(f)[0] not in executed]
            if not unexecuted:
                log("No new unexecuted scripts. Waiting 3 seconds...")
                time.sleep(3)
                continue
            unexecuted.sort(key=natural_sort_key)
            script_name = unexecuted[0]
            script_stem = os.path.splitext(script_name)[0]
            log(f"Next script: {script_name} (sequence {script_stem})")
            with open(script_name, 'r', encoding='utf-8') as f: code = f.read()

            git_repo.repo.git.checkout('server')
            git_repo.shallow_pull('server')

            task_globals = {
                'browser': browser, 'page': page, 'git_repo': git_repo,
                'scheduler': scheduler, 'log': log,
                'wait_for_page_loaded': wait_for_page_loaded,
                'wait_for_element': wait_for_element,
                'wait_timeout': wait_timeout,
                'time': time, 'os': os, 'sys': sys,
                'sequence_number': script_stem
            }
            task_globals.update(cursor_helpers)

            log(f"--- Executing {script_name} ---")
            try:
                exec(compile(code, script_name, 'exec'), task_globals)
                log(f"{script_name} completed successfully.")
            except Exception as e:
                log(f"{script_name} failed: {e}")
                traceback.print_exc()

            executed.add(script_stem)
            log(f"Marked {script_name} as executed. Total: {len(executed)}")
        except Exception as e:
            log(f"Loop error: {e}")
            traceback.print_exc()
            time.sleep(5)

# ==================== MAIN ====================
def main():
    log("===== Script started =====")
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", action="store_true")
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    os.system('git config user.name "github-actions[bot]"')
    os.system('git config user.email "github-actions[bot]@users.noreply.github.com"')

    git_repo = None
    browser = None
    page = None
    scheduler = TaskScheduler()

    try:
        git_repo = GitRepo(".")
        log("Pulling latest main...")
        git_repo.pull()

        if args.browser:
            if not HAS_PLAYWRIGHT:
                log("Playwright missing."); sys.exit(1)
            browser = StealthBrowser(headless=args.headless)
            browser.start()
            page = browser.new_page()
        else:
            log("Running without browser.")

        orchestrate_loop(git_repo, browser, page, scheduler)

    except KeyboardInterrupt:
        log("Manual stop requested.")
    except Exception as e:
        log(f"Fatal error in main: {e}")
        traceback.print_exc()
    finally:
        # Cleanup: delete all files from both branches (history preserved)
        if git_repo:
            for branch in ['client', 'server']:
                try:
                    git_repo.clear_branch_files(branch)
                except Exception as e:
                    log(f"Failed to clear branch '{branch}': {e}")
        if browser:
            try: browser.stop()
            except: pass
        log("===== Script finished =====")

if __name__ == "__main__":
    main()