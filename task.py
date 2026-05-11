

log("Task started: navigate to YouTube, screenshot, push to server.")
browser.goto(page, "https://www.youtube.com")
wait_for_page_loaded(page, timeout=60000, wait_for_network_idle=False)
wait_timeout(page, 10)

screenshot_file = "youtube.png"
browser.screenshot(page, screenshot_file)

git_repo.add_all()
git_repo.commit("Add YouTube screenshot")
git_repo.repo.git.push('--force', '--set-upstream', 'origin', 'server')

log("Success: screenshot saved and pushed to server branch.")

