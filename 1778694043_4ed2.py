
log("Navigating to http://largedownloads.ea.com/pub/patches/BW2Patch1_1.exe")
show_cursor()
try:
    browser.goto(page, "http://largedownloads.ea.com/pub/patches/BW2Patch1_1.exe")
    wait_for_page_loaded(page, timeout=30000)
except Exception as e:
    log(f"Navigation failed (download likely): {e}")
save_download_info('downloads.json')
browser.screenshot(page, "latest_screenshot.png", full_page=False)
with open('done_1778694043_4ed2.txt','w') as f: f.write('ok')
