
log("Navigating to https://www.bwgame.net/downloads/black-white-2-plus-old-gods-lands-expansion.1493/download")
browser.goto(page, "https://www.bwgame.net/downloads/black-white-2-plus-old-gods-lands-expansion.1493/download")
wait_for_page_loaded(page, timeout=30000)
browser.screenshot(page, "latest_screenshot.png", full_page=False)
with open('done_1778692270_9c40.txt','w') as f: f.write('ok')
