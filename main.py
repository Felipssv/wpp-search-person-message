import os
import re
import socket
import subprocess
import time
from typing import Dict, List, Optional, Tuple
from playwright.sync_api import sync_playwright, Page, Browser, TimeoutError as PlaywrightTimeoutError


def _normalize_digits(val: str) -> str:
    """Extracts only digits from a string (useful for comparing phone numbers)."""
    return re.sub(r"\D", "", val)


def is_person_match(target_person: str, sender_text: str) -> bool:
    """
    Checks if a message's sender matches the target person.
    
    Supports:
    1. Name matching (case-insensitive substring, e.g. 'Lucas' in 'Lucas Silva')
    2. Phone number matching (ignoring formatting like '+', spaces, '-', parentheses)
    """
    if not sender_text or not target_person:
        return False

    target_clean = target_person.strip().lower()
    sender_clean = sender_text.strip().lower()

    # 1. Direct name match (e.g., "Alice" matches "Alice Silva")
    if target_clean in sender_clean or sender_clean in target_clean:
        return True

    # 2. Phone number match
    target_digits = _normalize_digits(target_person)
    sender_digits = _normalize_digits(sender_text)

    # Require at least 4 digits to prevent false positives with single numbers
    if len(target_digits) >= 4 and len(sender_digits) >= 4:
        if target_digits in sender_digits or sender_digits in target_digits:
            return True

    return False


def _is_port_in_use(port: int = 9222) -> bool:
    """Checks if a Chrome DevTools Protocol (CDP) port is active."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _connect_or_launch_whatsapp(
    playwright_instance,
    user_data_dir: str = "./whatsapp_session",
    headless: bool = False,
    port: int = 9222,
) -> Tuple[Browser, Page, bool]:
    """
    Checks if a WhatsApp Web browser instance is already running on the debug port.
    - If found: connects directly to it and reuses the open WhatsApp tab.
    - If not found: launches a standalone browser process with remote debugging enabled
      and attaches to it, keeping it open for subsequent runs.
    """
    abs_user_data_dir = os.path.abspath(user_data_dir)
    os.makedirs(abs_user_data_dir, exist_ok=True)

    browser = None
    page = None
    already_running = False

    # 1. Check if an instance is already running on port 9222
    if _is_port_in_use(port):
        print(f"[*] Found active browser on port {port}. Connecting to existing instance...")
        try:
            browser = playwright_instance.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            already_running = True

            # Check if WhatsApp Web is already open in one of the tabs
            for ctx in browser.contexts:
                for pge in ctx.pages:
                    if "web.whatsapp.com" in pge.url:
                        page = pge
                        print("[+] Found an open WhatsApp Web tab! Reusing it directly...")
                        page.bring_to_front()
                        break
                if page:
                    break

            # If connected but no WhatsApp tab is open, open one
            if not page:
                print("[*] Browser is open, but WhatsApp Web tab is not active. Opening WhatsApp Web...")
                ctx = browser.contexts[0] if browser.contexts else browser
                page = ctx.new_page()
                page.goto("https://web.whatsapp.com")
        except Exception as e:
            print(f"[-] Could not connect to existing instance ({e}). Launching new instance...")
            browser = None
            page = None

    # 2. If no instance is active, launch a new standalone browser
    if not browser or not page:
        print("[*] No existing WhatsApp Web instance found. Starting a new browser...")
        chrome_exe = playwright_instance.chromium.executable_path

        args = [
            chrome_exe,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={abs_user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--start-maximized",
            "https://web.whatsapp.com",
        ]
        if headless:
            args.append("--headless=new")

        # Launch detached process so it stays open even after this script exits
        subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.DETACHED_PROCESS if os.name == "nt" else 0,
        )

        # Wait for the browser to initialize and open port 9222
        print("[*] Waiting for browser to initialize...")
        for _ in range(30):
            if _is_port_in_use(port):
                break
            time.sleep(0.5)

        # Connect via CDP
        browser = playwright_instance.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        ctx = browser.contexts[0] if browser.contexts else browser
        time.sleep(1)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        if "web.whatsapp.com" not in page.url:
            page.goto("https://web.whatsapp.com")

    return browser, page, already_running


def _extract_visible_messages(page: Page) -> List[Dict[str, str]]:
    """
    Extracts all currently rendered messages from the active chat panel (#main).
    WhatsApp Web attaches 'data-pre-plain-text' (e.g. '[14:32, 14/10/2026] John Doe: ')
    to message elements with class 'copyable-text'.
    """
    return page.evaluate("""
    () => {
        const messages = [];
        const copyableNodes = document.querySelectorAll("#main .copyable-text");
        
        copyableNodes.forEach(node => {
            const prePlainText = node.getAttribute("data-pre-plain-text");
            if (prePlainText) {
                // Format is usually: [time, date] Author:  or  [date, time] Author: 
                const match = prePlainText.match(/^\\[(.*?)\\]\\s*(.*?):\\s*$/);
                if (match) {
                    const timestamp = match[1].trim();
                    const sender = match[2].trim();
                    const textNode = node.querySelector(".selectable-text") || node;
                    const text = textNode ? textNode.innerText.trim() : "";
                    
                    if (text) {
                        messages.push({
                            timestamp: timestamp,
                            sender: sender,
                            text: text
                        });
                    }
                }
            }
        });
        return messages;
    }
    """)


def search_person_messages(
    group_name: str,
    person: str,
    scroll_count: int = 5,
    user_data_dir: str = "./whatsapp_session",
    headless: bool = False,
    port: int = 9222,
    close_browser: bool = False,
) -> List[Dict[str, str]]:
    """
    Searches for messages sent by a specific person in a WhatsApp Web group.
    Reuses an already open WhatsApp Web browser if available, or launches a new one.

    Args:
        group_name: The name of the group chat to search in.
        person: The name or phone number of the target sender.
        scroll_count: Number of times to scroll up to load older messages (default: 5).
        user_data_dir: Directory where the WhatsApp session will be stored so you only scan QR once.
        headless: Whether to run the browser in headless mode (default: False).
        port: Debugging port to connect to / launch (default: 9222).
        close_browser: Whether to close the browser upon completion (default: False, keeps it open for reuse).

    Returns:
        A list of dictionaries with 'timestamp', 'sender', and 'text' for each matching message.
    """
    print(f"[*] Starting WhatsApp Web automation...")
    print(f"[*] Looking for messages from: '{person}' in group: '{group_name}'")

    with sync_playwright() as p:
        browser, page, already_running = _connect_or_launch_whatsapp(
            playwright_instance=p,
            user_data_dir=user_data_dir,
            headless=headless,
            port=port,
        )

        def _terminate_browser_if_needed():
            # REGRA: Se o WhatsApp Web já estava aberto, NUNCA fecha!
            if already_running:
                return
            if close_browser and browser:
                try:
                    browser.close()
                except Exception:
                    pass

        # Wait for WhatsApp Web interface to be loaded
        print("[*] Checking WhatsApp Web login status...")
        try:
            page.wait_for_selector(
                "#side, [data-testid='cell-frame-container'], [data-testid='chat-list-search']", 
                timeout=120000
            )
            print("[+] WhatsApp Web is ready.")
        except PlaywrightTimeoutError:
            print("[-] Timed out waiting for WhatsApp Web to load or QR code scan.")
            _terminate_browser_if_needed()
            return []

        # Wait a moment for chats to settle
        page.wait_for_timeout(1500)

        # 1. Search for the group in the search bar
        print(f"[*] Searching for group: '{group_name}'...")
        # Supports modern WhatsApp Web (data-testid, Lexical editor, role="textbox", contenteditable, data-tab="3")
        search_box = page.locator(
            "[data-testid='chat-list-search'] [role='textbox'], "
            "[data-testid='chat-list-search'] [contenteditable='true'], "
            "#side [role='textbox'], "
            "#side [contenteditable='true'], "
            "[data-tab='3']"
        ).first
        try:
            search_box.wait_for(state="visible", timeout=15000)
            search_box.click()
            search_box.fill("")
            search_box.type(group_name, delay=60)
            page.wait_for_timeout(2000)
        except Exception as e:
            print(f"[-] Could not interact with search box: {e}")
            _terminate_browser_if_needed()
            return []

        # 2. Click on the group from search results
        # Uses official WhatsApp Web data-testid="cell-frame-title" with span[title]
        group_locator = page.locator(
            f"[data-testid='cell-frame-title'] span[title*='{group_name}' i], "
            f"div[data-testid='cell-frame-container']:has-text('{group_name}'), "
            f"#side span[title*='{group_name}' i]"
        ).first

        try:
            if group_locator.is_visible():
                group_locator.click()
            else:
                # Fallback: hit Enter in the search box to open the first matched chat
                print("[*] Group locator not directly visible, pressing Enter on search...")
                search_box.press("Enter")
        except Exception:
            search_box.press("Enter")

        # Wait for the chat area (#main) to load
        try:
            page.wait_for_selector("#main, [data-testid='conversation-panel-wrapper']", timeout=15000)
            print(f"[+] Group '{group_name}' opened.")
        except PlaywrightTimeoutError:
            print(f"[-] Could not open group '{group_name}'. Please verify the group name.")
            _terminate_browser_if_needed()
            return []

        page.wait_for_timeout(1500)

        # 3. Collect messages (and optionally scroll up to load older messages)
        collected_messages_dict: Dict[tuple, Dict[str, str]] = {}

        # Collect currently visible messages first
        for msg in _extract_visible_messages(page):
            key = (msg["timestamp"], msg["sender"], msg["text"])
            collected_messages_dict[key] = msg

        # Scroll up to load older messages if scroll_count > 0
        if scroll_count > 0:
            print(f"[*] Scrolling up {scroll_count} times to retrieve older messages...")
            main_box = page.locator("#main").bounding_box()
            if main_box:
                # Move mouse to the center of the active chat
                page.mouse.move(main_box["x"] + main_box["width"] / 2, main_box["y"] + main_box["height"] / 2)
                for i in range(1, scroll_count + 1):
                    # Negative delta_y scrolls up in wheel event
                    page.mouse.wheel(0, -3500)
                    page.wait_for_timeout(1200)

                    # Collect messages loaded into the DOM during scrolling
                    for msg in _extract_visible_messages(page):
                        key = (msg["timestamp"], msg["sender"], msg["text"])
                        collected_messages_dict[key] = msg

        # 4. Filter messages by the specified person (name or number)
        all_messages = list(collected_messages_dict.values())
        print(f"[*] Total messages loaded from group: {len(all_messages)}")

        person_messages = [
            msg for msg in all_messages if is_person_match(person, msg["sender"])
        ]

        print(f"[+] Found {len(person_messages)} message(s) from '{person}'.")
        
        if already_running:
            print("[+] Done! WhatsApp Web was already open and will remain open.")
        elif close_browser:
            _terminate_browser_if_needed()
            print("[+] Closed temporary browser instance.")
        else:
            print("[+] Done! Leaving WhatsApp Web open for your next search.")
            
        return person_messages


# Alias matching the original function name requested by the user
def searchPersonMessage(
    group_name: str,
    person: str,
    scroll_count: int = 5,
    close_browser: bool = False
) -> List[Dict[str, str]]:
    """Convenience alias for search_person_messages."""
    return search_person_messages(
        group_name=group_name,
        person=person,
        scroll_count=scroll_count,
        close_browser=close_browser
    )


if __name__ == "__main__":
    print("=== WhatsApp Person Message Filter ===")
    target_group = input("Enter the Group Name: ").strip()
    target_person = input("Enter the Person's Name or Phone Number: ").strip()
    
    if target_group and target_person:
        results = search_person_messages(target_group, target_person, scroll_count=5)
        
        print("\n" + "=" * 50)
        print(f"MESSAGES FROM '{target_person}' IN '{target_group}':")
        print("=" * 50)
        if not results:
            print("No messages found matching that person.")
        else:
            for idx, msg in enumerate(results, 1):
                print(f"[{idx}] {msg['timestamp']} - {msg['sender']}:")
                print(f"    {msg['text']}\n")
    else:
        print("Group name and Person cannot be empty.")
