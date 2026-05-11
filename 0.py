# Example 1.py – uses cursor helpers
log(f"I am sequence {sequence_number}")

browser.goto(page, "https://www.youtube.com")
wait_for_page_loaded(page)


show_cursor()


wait_timeout(page, 10)   # wait 2 seconds
move_mouse(614, 25)
page.mouse.click(614, 25)
page.keyboard.type("taskmaster", delay=50)
press_key("Enter")
wait_for_page_loaded(page)
wait_timeout(page, 10) 
browser.screenshot(page, f"{sequence_number} taskmaster.png")
save_download_links(page, f"{sequence_number}download_links.xml")
save_page_as_mhtml(page, f"{sequence_number}page_single.mhtml")

# Save the page as a folder with separate resources
save_page_as_folder(page, f"{sequence_number}saved_page_complete")
log("Done with cursor demo.")