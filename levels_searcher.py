from playwright.sync_api import sync_playwright, expect
import os
import time
from typing import List, Dict
import json
from pathlib import Path


class LevelsFyiSearcher:
    def __init__(self):
        # Get credentials from environment
        self.email = os.environ.get("LEVELSFYI_EMAIL")
        self.password = os.environ.get("LEVELSFYI_PASSWORD")

        if not all([self.email, self.password]):
            raise ValueError("Levels.fyi credentials not found in environment")

        playwright = sync_playwright().start()

        # Create a persistent context with a user data directory
        user_data_dir = Path.home() / ".playwright-levels-chrome"
        self.browser = playwright.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=False,
            channel="chrome",  # Use installed Chrome instead of Chromium
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",  # Hide automation
                "--disable-dev-shm-usage",
            ],
            ignore_default_args=["--enable-automation"],  # Hide automation flags
        )
        self.page = self.browser.new_page()

        # Modify navigator.webdriver flag
        self.page.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """
        )

    def save_cookies(self):
        """Save cookies to file after successful login"""
        cookies = self.page.context.cookies()
        self.cookie_file.write_text(json.dumps(cookies))
        print("Cookies saved successfully")

    def load_cookies(self) -> bool:
        """Load cookies if they exist. Returns True if loaded successfully."""
        try:
            if self.cookie_file.exists():
                cookies = json.loads(self.cookie_file.read_text())
                self.page.context.add_cookies(cookies)
                print("Cookies loaded successfully")
                return True
        except Exception as e:
            print(f"Error loading cookies: {e}")
        return False

    def check_login_status(self) -> bool:
        """Check if we're logged in"""
        try:
            self.page.goto("https://www.levels.fyi")
            # Wait briefly for avatar
            return self.page.locator(".avatar, .user-avatar").is_visible(timeout=3000)
        except:
            return False

    def login(self) -> None:
        """Login to Levels.fyi with cookie handling"""
        # Try loading cookies first
        if self.load_cookies() and self.check_login_status():
            print("Successfully logged in with cookies!")
            return

        print("Need to login manually - please use Google auth...")
        self.page.goto("https://www.levels.fyi/login")

        # Wait for Google auth button and click it
        google_button = self.page.get_by_role("button", name="Sign in with Google")
        google_button.click()

        # Wait for successful login (longer timeout for manual auth)
        print("Waiting for manual Google login completion...")
        self.page.wait_for_selector(".avatar, .user-avatar", timeout=60000)
        print("Login successful!")

        # Save cookies for next time
        self.save_cookies()

    def search_company(self, company_name: str) -> List[Dict]:
        """Search for salary data at specified company"""
        try:
            # Make sure we're logged in first
            if "login" in self.page.url:
                self.login()

            # Go to levels.fyi
            self.page.goto("https://www.levels.fyi/")

            # Find and click the search box
            search_box = self.page.get_by_placeholder("Search for a company")
            search_box.click()
            search_box.fill(company_name)

            # Wait for and click the company in dropdown
            company_option = self.page.get_by_text(company_name, exact=True).first
            company_option.click()

            # Wait for salary data to load
            self.page.wait_for_selector(".table-container")

            # Extract salary data
            # Note: You'll need to adjust selectors based on what data you want
            rows = self.page.locator("tr.table-row")

            results = []
            for row in rows.all():
                try:
                    data = {
                        "title": row.locator(".title-cell").inner_text(),
                        "level": row.locator(".level-cell").inner_text(),
                        "total_comp": row.locator(".total-cell").inner_text(),
                    }
                    results.append(data)
                except Exception as e:
                    print(f"Error parsing row: {e}")
                    continue

            return results

        except Exception as e:
            self.page.screenshot(path="search_error.png")
            raise Exception(f"Error searching {company_name}: {e}")

    def cleanup(self) -> None:
        """Clean up browser resources"""
        try:
            if self.page.context:
                self.page.context.close()
            if self.browser:
                self.browser.close()
        except Exception as e:
            print(f"Error during cleanup: {e}")


def main():
    searcher = LevelsFyiSearcher()
    try:
        # Login (will use cookies if available)
        searcher.login()

        # Then search
        results = searcher.search_company("Shopify")

        # Print results
        for result in results:
            print(f"{result['title']} ({result['level']}): {result['total_comp']}")

    finally:
        searcher.cleanup()


if __name__ == "__main__":
    main()
