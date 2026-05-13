
log("Navigating to https://www.bwgame.net/downloads/bw2-v1-1-patch.587/")
show_cursor()
try:
    browser.goto(page, "https://www.bwgame.net/downloads/bw2-v1-1-patch.587/")
    wait_for_page_loaded(page, timeout=30000)
except Exception as e:
    log(f"Navigation failed (download likely): {e}")
save_download_info('downloads.json')
browser.screenshot(page, "latest_screenshot.png", full_page=False)
with open('done_1778695246_2a17.txt','w') as f: f.write('ok')
