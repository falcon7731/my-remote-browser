
log("Navigating to https://www.bwgame.net/downloads/black-white-2-plus-old-gods-lands-expansion.1493/")
browser.goto(page, "https://www.bwgame.net/downloads/black-white-2-plus-old-gods-lands-expansion.1493/")
wait_for_page_loaded(page, timeout=30000)
wait_timeout(page, 1.0)
browser.screenshot(page, "latest_screenshot.png", full_page=True)
