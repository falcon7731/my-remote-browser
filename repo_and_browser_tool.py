#!/usr/bin/env python3
"""
Remote‑driven automation orchestrator with cursor helpers, shallow updates,
automatic commit after each task, and startup branch cleaning.
Browser profile is kept outside the repo.
After manual stop, all files are deleted from both branches (history kept).
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
    def __init__(self, user_data_dir=None, headless=False):
        if not HAS_PLAYWRIGHT: raise RuntimeError("Playwright not installed.")
        if user_data_dir is None:
            user_data_dir = os.path.join(os.getcwd(), '..', 'browser_profile')
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
        log("[Browser] Started.")

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

    def shallow_pull(self, branch="main"):
        """Force local branch to exactly match remote (shallow)."""
        try:
            self.repo.git.fetch("--depth", "1", "origin", branch)
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

    def add_all(self):
        self.repo.git.add(A=True)
        try:
            self.repo.git.rm('-r', '--cached', 'browser_profile')
        except:
            pass
        log("[Git] All changes staged (browser_profile excluded).")

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
                if os.path.isfile(full) or os.path.islink(full):
                    os.remove(full)
                elif os.path.isdir(full):
                    shutil.rmtree(full)
        self.add_all()
        if self.repo.is_dirty(untracked_files=True):
            self.repo.index.commit(commit_message)
            log(f"[Git] Committed file deletions on '{branch_name}'.")
        else:
            log(f"[Git] No files to delete on '{branch_name}'.")
        self.origin.push()
        log(f"[Git] Pushed cleared branch '{branch_name}'.")


# ==================== TASK ORCHESTRATION LOOP ====================
def natural_sort_key(filename):
    m = re.match(r'(\d+)', filename)
    return int(m.group(1)) if m else float('inf')

def orchestrate_loop(git_repo, browser, page, scheduler):
    log("=== Starting infinity task loop ===")
    executed = {'task', 'repo_and_browser_tool'}

    # ---------- Build helper functions ----------
    cursor_helpers = {}
    if page is not None:
        # Cursor helpers (as before)
        def _move_mouse(x, y): page.mouse.move(x, y)
        def _get_cursor_position():
            pos = page.evaluate("""() => ({ x: window.__cursorX || 0, y: window.__cursorY || 0 })""")
            return pos['x'], pos['y']
        def _show_cursor():
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
        def _hide_cursor():
            page.evaluate("""() => { let c = document.getElementById('__custom_cursor'); if(c) c.remove(); }""")
        def _press_key(key):
            page.keyboard.press(key)
            log(f"[Browser] Pressed key: {key}")

        # ---- New helper: download links as XML ----
        def _get_download_links(page_obj):
            data = page_obj.evaluate("""() => {
                const elements = Array.from(document.querySelectorAll(
                    'a[href], img[src], link[href], script[src], video[src], audio[src], source[src]'
                ));
                return elements.map(el => {
                    let url = '';
                    if (el.tagName === 'A') url = el.href;
                    else url = el.src || el.href || '';
                    try { url = new URL(url, document.baseURI).href; } catch(e) {}
                    return { tag: el.tagName, url: url };
                });
            }""")
            import xml.etree.ElementTree as ET
            root = ET.Element("downloads")
            for item in data:
                elem = ET.SubElement(root, "link")
                elem.set("element", item['tag'])
                elem.text = item['url']
            return ET.tostring(root, encoding='unicode')

        def _save_download_links(page_obj, filepath):
            xml_str = _get_download_links(page_obj)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(xml_str)
            log(f"Download links XML saved to {filepath}")

        # ---- New helper: save complete page ----
        def _save_page_as_mhtml(page_obj, filepath):
            cdp = page_obj.context.new_cdp_session(page_obj)
            result = cdp.send('Page.captureSnapshot', {'format': 'mhtml'})
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(result['data'])
            log(f"MHTML saved to {filepath}")

        def _save_page_as_folder(page_obj, folder_path):
            import requests as req
            from urllib.parse import urlparse
            os.makedirs(folder_path, exist_ok=True)
            html_content = page_obj.content()

            resources = page_obj.evaluate("""() => {
                const resources = [];
                const elements = Array.from(document.querySelectorAll(
                    'img[src], link[href], script[src], video[src], audio[src], source[src], '
                    + 'iframe[src], embed[src], object[data]'
                ));
                elements.forEach(el => {
                    let url = '';
                    if (el.src) url = el.src;
                    else if (el.href) url = el.href;
                    else if (el.data) url = el.data;
                    if (!url) return;
                    try { url = new URL(url, document.baseURI).href; } catch(e) { return; }
                    if (new URL(url).origin === window.location.origin) {
                        resources.push(url);
                    }
                });
                return [...new Set(resources)];
            }""")

            cookies = page_obj.context.cookies()
            session = req.Session()
            for c in cookies:
                session.cookies.set(c['name'], c['value'],
                                    domain=c.get('domain', None))

            url_map = {}
            for res_url in resources:
                try:
                    resp = session.get(res_url, timeout=10)
                    if resp.status_code == 200:
                        parsed = urlparse(res_url)
                        fname = os.path.basename(parsed.path)
                        if not fname or '.' not in fname:
                            fname = f"resource_{abs(hash(res_url))}.bin"
                        fname = "".join(c for c in fname if c.isalnum() or c in '._-')
                        local_path = os.path.join(folder_path, fname)
                        with open(local_path, 'wb') as f:
                            f.write(resp.content)
                        url_map[res_url] = fname
                        log(f"Saved: {fname}")
                except Exception as e:
                    log(f"Failed to download {res_url}: {e}")

            for url, fname in url_map.items():
                html_content = html_content.replace(url, fname)

            parsed_base = urlparse(page_obj.url)
            base_name = "".join(c for c in parsed_base.netloc if c.isalnum() or c in '._-')
            html_file = os.path.join(folder_path, f"{base_name}.html")
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
            log(f"Complete page saved to folder {folder_path}")

        # Assemble all helpers
        cursor_helpers = {
            'move_mouse': _move_mouse,
            'get_cursor_position': _get_cursor_position,
            'show_cursor': _show_cursor,
            'hide_cursor': _hide_cursor,
            'press_key': _press_key,
            'get_download_links': _get_download_links,
            'save_download_links': _save_download_links,
            'save_page_as_mhtml': _save_page_as_mhtml,
            'save_page_as_folder': _save_page_as_folder,
        }

    # ---------- Main loop ----------
    while True:
        try:
            git_repo.repo.git.checkout('client')
            git_repo.shallow_pull('client')

            all_py = [f for f in os.listdir('.') if f.endswith('.py') and f != '__init__.py']
            unexecuted = [f for f in all_py if os.path.splitext(f)[0] not in executed]

            if not unexecuted:
                log("No new scripts. Waiting 3 seconds...")
                time.sleep(3)
                continue

            unexecuted.sort(key=natural_sort_key)
            script_name = unexecuted[0]
            script_stem = os.path.splitext(script_name)[0]
            log(f"Next script: {script_name} (sequence {script_stem})")

            with open(script_name, 'r', encoding='utf-8') as f:
                code = f.read()

            git_repo.repo.git.checkout('server')
            git_repo.shallow_pull('server')

            task_globals = {
                'browser': browser, 'page': page, 'git_repo': git_repo,
                'scheduler': scheduler, 'log': log,
                'wait_for_page_loaded': wait_for_page_loaded,
                'wait_for_element': wait_for_element,
                'wait_timeout': wait_timeout,
                'time': time, 'os': os, 'sys': sys,
                'sequence_number': script_stem,
            }
            task_globals.update(cursor_helpers)

            log(f"--- Executing {script_name} ---")
            try:
                exec(compile(code, script_name, 'exec'), task_globals)
                log(f"{script_name} completed successfully.")
            except Exception as e:
                log(f"{script_name} failed: {e}")
                traceback.print_exc()

            # Auto‑commit whatever the script created
            git_repo.add_all()
            git_repo.commit(f"Auto-commit after {script_name}")
            git_repo.push(force=True)
            log("Pushed changes to server branch.")

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

        # ---- Clean client and server branches at startup ----
        log("Cleaning client and server branches at startup...")
        git_repo.clear_branch_files('client')
        git_repo.clear_branch_files('server')

        if args.browser:
            if not HAS_PLAYWRIGHT:
                log("Playwright missing.")
                sys.exit(1)
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