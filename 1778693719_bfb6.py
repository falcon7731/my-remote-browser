
log("Navigating to http://largedownloads.ea.com/pub/patches/BW2Patch1_1.exe")
show_cursor()
browser.goto(page, "http://largedownloads.ea.com/pub/patches/BW2Patch1_1.exe")
wait_for_page_loaded(page, timeout=30000)
wait_timeout(page, 2.0)
browser.screenshot(page, "latest_screenshot.png", full_page=False)
with open('done_1778693719_bfb6.txt','w') as f: f.write('ok')
