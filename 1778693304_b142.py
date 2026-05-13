
log("Navigating to https://www.gamefront.com/games/black-and-white-2/file/black-white-2-retail-v1-1-to-v1-2-patch")
show_cursor()
browser.goto(page, "https://www.gamefront.com/games/black-and-white-2/file/black-white-2-retail-v1-1-to-v1-2-patch")
wait_for_page_loaded(page, timeout=30000)
browser.screenshot(page, "latest_screenshot.png", full_page=False)
with open('done_1778693304_b142.txt','w') as f: f.write('ok')
