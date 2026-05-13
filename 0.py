'''# Example 1.py – uses cursor helpers
log(f"I am sequence {sequence_number}")

browser.goto(page, "https://www.bwgame.net/downloads/black-white-2-unofficial-patch-v1-42.1421/download")
wait_for_page_loaded(page)
show_cursor()
wait_timeout(page, 10)   # wait 2 seconds
browser.screenshot(page, f"{sequence_number} login page.png")
save_download_links(page, f"{sequence_number}download_links.xml")
save_page_as_mhtml(page, f"{sequence_number}page_single.mhtml")
show_cursor()

show_cursor()
move_mouse(1062, 263)
page.mouse.click(1062, 263)
browser.screenshot(page, f"{sequence_number} login page.png")
save_download_links(page, f"{sequence_number}download_links.xml")
save_page_as_mhtml(page, f"{sequence_number}page_single.mhtml")

wait_for_page_loaded(page)
save_download_links(page, f"{sequence_number}download_links.xml")
save_page_as_mhtml(page, f"{sequence_number}page_single.mhtml")

'''
browser.goto(page, "https://www.xvideos.com/account")
wait_for_page_loaded(page)
wait_timeout(page, 2)   # wait 2 seconds
browser.screenshot(page, f"{sequence_number} login page1.png")
save_download_links(page, f"{sequence_number}download_links1.xml")
save_page_as_mhtml(page, f"{sequence_number}page_single1.mhtml")



move_mouse(439, 141)
page.mouse.click(439, 141)
page.keyboard.type("mehregan.zare7731@gmail.com", delay=50)
move_mouse(439, 189)
page.mouse.click(439, 189)
page.keyboard.type("Mehr77311", delay=50)
move_mouse(346, 285)
page.mouse.click(346, 285)
wait_for_page_loaded(page)
wait_timeout(page, 2)   # wait 2 seconds
browser.screenshot(page, f"{sequence_number} login page2.png")
save_download_links(page, f"{sequence_number}download_links2.xml")
save_page_as_mhtml(page, f"{sequence_number}page_single3.mhtml")




'''
shutdown()
show_cursor()
move_mouse(957, 621)
page.mouse.click(957, 621)
wait_timeout(page, 1)   # wait 2 seconds
page.mouse.click(957, 621)
wait_timeout(page, 1)   # wait 2 seconds
page.mouse.click(957, 621)
wait_timeout(page, 1)   # wait 2 seconds
page.mouse.click(957, 621)
wait_timeout(page, 1)   # wait 2 seconds
page.mouse.click(957, 621)
wait_timeout(page, 10)   # wait 2 seconds
browser.screenshot(page, f"{sequence_number} login page.png")


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
'''