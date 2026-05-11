# Example task that demonstrates every helper function and injected variable
# available in the orchestrator.
# Run it by placing this file (e.g. 1.py) on the 'client' branch.
# The auto-commit after execution will save all generated files to 'server'.

log(f"Sequence {sequence_number} – demonstrating all helpers")

# ========== PAGE NAVIGATION & LOADING ==========
browser.goto(page, "https://example.com")
loaded = wait_for_page_loaded(page, timeout=30000, wait_for_network_idle=False)
log(f"Page loaded: {loaded}")

# ========== WAIT FOR AN ELEMENT ==========
# Wait for the <h1> to become visible (if it exists)
if wait_for_element(page, "h1", timeout=5000):
    log("H1 is visible")
else:
    log("H1 not found – continuing anyway")

# ========== FIXED TIME WAIT ==========
wait_timeout(page, 2)   # wait 2 seconds

# ========== CURSOR OPERATIONS ==========
# Show the custom red cursor (visible in screenshots)
show_cursor()

# Move mouse to coordinates (300, 150)
move_mouse(300, 150)

# Get current cursor position (only works if show_cursor was called)
x, y = get_cursor_position()
log(f"Cursor is at ({x}, {y})")

# Move to another position and click (using raw page.mouse)
move_mouse(400, 200)
page.mouse.click(400, 200)          # click at absolute coordinates

# Hide the custom cursor
hide_cursor()

# ========== KEYBOARD ACTIONS ==========
# Type into an input field (if click focused on an input)
# Try to find an input and type; if not found, this will fail gracefully via try/except
try:
    # Click on the first input field (selector 'input') then type
    page.click("input")             # click the element
    page.keyboard.type("task master", delay=50)   # type with delay
    press_key("Enter")              # Press Enter
    log("Typed and pressed Enter")
except Exception as e:
    log(f"Could not interact with input field: {e}")

# ========== SCREENSHOT ==========
browser.screenshot(page, "demo_screenshot.png", full_page=False)
log("Took a screenshot (demo_screenshot.png)")

# ========== DIRECT PAGE ACTIONS (Playwright's own methods) ==========
current_url = browser.current_url(page)
log(f"Current URL: {current_url}")

# Scroll down the page by 500 pixels
browser.scroll(page, "down", 500)

# ========== SCHEDULER ==========
def periodic_task():
    log("Periodic task runs – this runs every 15 seconds, 3 times")
    # You could take another screenshot, etc.

scheduler.after(5, periodic_task, repeat=3, interval=15)
log("Scheduled a periodic task")

# ========== GIT OPERATIONS ==========
# These are available but not necessary – the orchestrator auto-commits at the end.
# However, you can manually use them if needed.
# For example, to immediately push a file:
with open("custom_file.txt", "w") as f:
    f.write("Created by task")
git_repo.add_all()
git_repo.commit("Add custom_file.txt")
git_repo.push(force=True)   # force push to avoid rejected if auto-commit will do it too
log("Manually committed and pushed custom_file.txt")

# ========== OTHER INJECTED MODULES ==========
# time.sleep is available
log("Sleeping 2 seconds with time.sleep...")
time.sleep(2)

# os and sys are available
log(f"This task file name: {os.path.basename(__file__)}")
log(f"Python version: {sys.version}")

log("Demo completed successfully.")