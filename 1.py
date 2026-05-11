# Example 1.py – uses cursor helpers
log(f"I am sequence {sequence_number}")

browser.goto(page, "https://www.youtube.com")
wait_for_page_loaded(page)

show_cursor()
move_mouse(200, 300)
browser.screenshot(page, "cursor_visible.png")

hide_cursor()
browser.screenshot(page, "cursor_hidden.png")

log("Done with cursor demo.")