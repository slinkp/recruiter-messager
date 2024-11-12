from playwright.sync_api import sync_playwright, expect
import os
import time
import logging
from typing import List, Dict
from pathlib import Path
import random

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

class LevelsFyiSearcher:
    def __init__(self):
        logger.info("Initializing LevelsFyiSearcher")
        playwright = sync_playwright().start()

        # Create a persistent context with a user data directory
        user_data_dir = Path.home() / ".playwright-levels-chrome"
        logger.info(f"Using Chrome profile directory: {user_data_dir}")

        self.browser = playwright.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=False,
            channel="chrome",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--enable-sandbox",
            ],
            ignore_default_args=["--enable-automation"],
        )
        logger.info("Browser context launched")

        self.page = self.browser.new_page()
        logger.info("New page created")

        # Modify navigator.webdriver flag
        self.page.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """
        )
        logger.info("Webdriver detection bypass added")

    def check_login_status(self) -> bool:
        """Check if we're logged in"""
        try:
            current_url = self.page.url
            logger.info(f"Checking login status at URL: {current_url}")

            # If we're already on a valid page (not login or error), assume logged in
            if (
                "login" not in current_url.lower()
                and "error" not in current_url.lower()
                and current_url.startswith("https://www.levels.fyi")
            ):
                logger.info("On valid page, assuming logged in")
                return True

            # Check for various login indicators
            logger.info("Checking for login elements...")
            selectors = [
                ".MuiAvatar-root",
                "button[aria-label='User menu']",
                "[data-testid='AccountCircleIcon']",
                "button:has-text('Sign Out')",
                ".user-menu-button",
            ]

            for selector in selectors:
                try:
                    logger.info(f"Checking selector: {selector}")
                    element = self.page.locator(selector).first
                    if element.is_visible(timeout=1000):
                        logger.info(f"Found login indicator: {selector}")
                        return True
                except Exception as e:
                    logger.info(f"Selector {selector} not found: {str(e)}")

            # Check for login button
            try:
                login_button = self.page.get_by_role(
                    "button", name="Sign in with Google"
                )
                if login_button.is_visible(timeout=1000):
                    logger.info("Found login button, not logged in")
                    return False
            except Exception as e:
                logger.info(f"Login button check failed: {str(e)}")

            logger.info("No definitive login status found, assuming logged in")
            return True

        except Exception as e:
            logger.error(f"Error checking login status: {e}")
            return True

    def login(self) -> None:
        """Login to Levels.fyi with profile persistence"""
        try:
            logger.info("Starting login process")
            if self.check_login_status():
                logger.info("Already logged in!")
                return

            logger.info("Opening login page")
            self.page.goto(
                "https://www.levels.fyi/login", wait_until="domcontentloaded"
            )
            time.sleep(3)

            logger.info("Looking for Google login button")
            google_button = self.page.get_by_role("button", name="Sign in with Google")
            google_button.click()
            logger.info("Clicked Google login button")

            logger.info("\n=== MANUAL LOGIN REQUIRED ===")
            logger.info("1. Please complete the Google login in the browser window")
            logger.info("2. This may include:")
            logger.info("   - Entering your Google email")
            logger.info("   - Entering your password")
            logger.info("   - Completing 2FA if enabled")
            logger.info("3. After you see you're logged into Levels.fyi, return here")

            input("\nPress Enter ONLY after you're fully logged into Levels.fyi... ")
            logger.info("User indicated login is complete")

            time.sleep(3)
            logger.info("Checking final login status")

            if self.check_login_status():
                logger.info("Login successful!")
                return
            else:
                logger.warning("Initial login check failed, trying again...")
                time.sleep(5)
                if self.check_login_status():
                    logger.info("Login successful on second check!")
                    return
                else:
                    raise Exception("Login failed - could not verify login status")

        except Exception as e:
            logger.error(f"Login attempt failed: {str(e)}")
            logger.error(f"Current URL: {self.page.url}")
            raise Exception(f"Levels.fyi login failed: {str(e)}")

    def random_delay(self, min_seconds=0.5, max_seconds=2):
        """Add a random delay between actions"""
        delay = random.uniform(min_seconds, max_seconds)
        logger.debug(f"Waiting for {delay:.1f} seconds...")
        time.sleep(delay)

    def search_company(self, company_name: str) -> List[Dict]:
        """Search for salary data at specified company"""
        try:
            logger.info(f"Starting search for company: {company_name}")

            # Go to levels.fyi
            logger.info("Navigating to levels.fyi homepage")
            self.page.goto("https://www.levels.fyi/")
            self.random_delay(1, 2)  # Slightly longer delay after page load

            # Log current URL and login status
            logger.info(f"Current URL: {self.page.url}")
            is_logged_in = self.check_login_status()
            logger.info(
                f"Login status check result: {'Logged in' if is_logged_in else 'Not logged in'}"
            )

            # Only try to login if we hit a login wall
            if "login" in self.page.url.lower():
                logger.info("Hit login wall, attempting login...")
                self.login()

            # Find and click the search box
            logger.info("Looking for search box...")
            search_box = self.page.get_by_placeholder("Search for a company")
            logger.info("Attempting to click search box...")
            search_box.click()
            logger.info("Search box clicked successfully")

            logger.info(f"Filling search box with: {company_name}")
            search_box.fill(company_name)
            logger.info("Search box filled")

            # Wait for and click the company in dropdown
            logger.info(f"Looking for company option: {company_name}")
            company_option = self.page.get_by_text(company_name, exact=True).first
            logger.info("Clicking company option...")
            company_option.click()
            logger.info("Company option clicked")

            # Wait for salary data to load
            logger.info("Waiting for salary data table...")
            self.page.wait_for_selector(".table-container")
            logger.info("Salary data table found")

            # Extract salary data
            logger.info("Extracting salary data...")
            rows = self.page.locator("tr.table-row")
            logger.info(f"Found {len(rows.all())} salary entries")

            results = []
            for i, row in enumerate(rows.all()):
                try:
                    data = {
                        "title": row.locator(".title-cell").inner_text(),
                        "level": row.locator(".level-cell").inner_text(),
                        "total_comp": row.locator(".total-cell").inner_text(),
                    }
                    results.append(data)
                    logger.debug(f"Parsed row {i+1}: {data}")
                except Exception as e:
                    logger.error(f"Error parsing row {i+1}: {e}")
                    continue

            logger.info(f"Successfully extracted {len(results)} salary entries")
            return results

        except Exception as e:
            logger.error(f"Error during company search: {e}")
            logger.error(f"Current URL when error occurred: {self.page.url}")
            try:
                logger.info("Attempting to save error screenshot...")
                self.page.screenshot(path="search_error.png")
                logger.info("Error screenshot saved as search_error.png")
            except Exception as screenshot_error:
                logger.error(f"Failed to save error screenshot: {screenshot_error}")
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
        # Then search
        results = searcher.search_company("Shopify")

        # Print results
        for result in results:
            print(f"{result['title']} ({result['level']}): {result['total_comp']}")

    finally:
        searcher.cleanup()


if __name__ == "__main__":
    main()
