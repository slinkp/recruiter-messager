from playwright.sync_api import sync_playwright, expect
import os
import time
import logging
from typing import List, Dict
from pathlib import Path
import random
import sys

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

    def main(self, company_name: str) -> List[Dict]:
        """Main function to search for salary data at a company"""
        # All of these work by side effects or raising exceptions
        self.search_by_company_name(company_name)
        self.random_delay()
        self._navigate_to_salary_page()
        self.random_delay()
        return self.find_and_extract_salaries()

    def test_shopify_salary(self) -> List[Dict]:
        """Test method that loads Shopify salary data for Canada"""
        logger.info("Running Shopify salary test for Canada")
        url = "https://www.levels.fyi/companies/shopify/salaries/software-engineer?country=43"
        self.page.goto(url)
        self.random_delay(1, 2)

        # Check if we need to login
        if "login" in self.page.url.lower():
            logger.info("Hit login wall, attempting login...")
            self.login()
            # Return to the Shopify page
            self.page.goto(url)
            self.random_delay()

        return self.find_and_extract_salaries()

    def cleanup(self) -> None:
        """Clean up browser resources"""
        try:
            if self.page.context:
                self.page.context.close()
            if self.browser:
                self.browser.close()
        except Exception as e:
            print(f"Error during cleanup: {e}")

    def random_delay(self, min_seconds=0.5, max_seconds=2):
        """Add a random delay between actions"""
        delay = random.uniform(min_seconds, max_seconds)
        logger.debug(f"Waiting for {delay:.1f} seconds...")
        time.sleep(delay)

    def find_and_extract_salaries(self):
        logger.info(f"Looking for salary table on {self.page.url}...")
        self.salary_table = self.page.locator(
            "table[aria-label='Salary Submissions']"
        ).first
        if not self.salary_table.is_visible(timeout=5000):
            raise Exception(f"Could not find salary table on page {self.page.url}")
        self._say_salary_data_added()
        self.random_delay()
        self._narrow_salary_search()
        return self._extract_salary_data()

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

    def search_by_company_name(self, company_name: str) -> None:
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
            search_box = self.page.get_by_role(
                "searchbox", name="Search by Company, Title, or City", exact=False
            ).first

            # If that doesn't work, fallback to:
            if not search_box.is_visible(timeout=1000):
                logger.info("Trying alternate selector...")
                search_box = self.page.locator("input.omnisearch-input").first

            logger.info(
                f"Found search box with placeholder: {search_box.get_attribute('placeholder')}"
            )

            logger.info("Attempting to click search box...")
            search_box.click()
            logger.info("Search box clicked successfully")

            logger.info(f"Filling search box with: {company_name}")
            search_box.fill(company_name)
            logger.info("Search box filled")
            self.random_delay()  # Wait for dropdown to appear

            # Wait for and click the company in dropdown
            logger.info("Waiting for dropdown to appear...")
            dropdown = self.page.wait_for_selector(".omnisearch-results", timeout=5000)
            if not dropdown:
                raise Exception("Dropdown menu never appeared")

            logger.info(f"Looking for company option: {company_name}")
            company_option = self.page.get_by_role(
                "link", name=company_name, exact=False
            ).first

            if not company_option.is_visible(timeout=5000):
                raise Exception(f"Could not find match for {company_name} in dropdown")

            self.random_delay()  # Default delay before clicking

            logger.info("Clicking company option...")
            company_option.click()

            logger.info("Company option clicked")
            self.random_delay()
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

    def _navigate_to_salary_page(self):
        # Wait for either the Software Engineer link or the salary page
        logger.info("Checking if we're on the main company page or salary page...")

        try:
            # Look for Software Engineer link by its heading and href pattern
            swe_link = (
                self.page.get_by_role("link", name="Software Engineer", exact=False)
                .filter(has=self.page.locator("h6:has-text('Software Engineer')"))
                .first
            )

            if swe_link.is_visible(timeout=5000):
                logger.info("Found Software Engineer link, clicking it...")
                swe_link.click()
                self.random_delay()  # Wait for navigation
            else:
                raise Exception("Software Engineer link not visible")
        except Exception as e:
            logger.error(f"Could not find Software Engineer link: {e}")
            raise Exception("Could not find Software Engineer role on company page")

        self.random_delay()  # Wait for table to update
        self._say_salary_data_added()

    def _say_salary_data_added(self):
        # Click the "Added mine already" button to reveal full salary data
        logger.info("Looking for 'Added mine already' button...")
        already_added_button = self.page.get_by_role(
            "button", name="Added mine already within last 1 year"
        ).first
        if already_added_button.is_visible(timeout=3000):
            logger.info("Clicking 'Added mine already' button...")
            already_added_button.click()
            self.random_delay()
        # Secondary button that sometimes appears with "Thank you"
        ive_shared_button = self.page.get_by_role("button", name="I've Shared").first
        if ive_shared_button.is_visible(timeout=3000):
            logger.info("Clicking 'I've Shared' button...")
            ive_shared_button.click()
            self.random_delay()

    def _extract_salary_data(self) -> List[Dict]:
        """Extract salary data from the salary table,
        assuming we've already navigated to the salary page
        and narrowed the search to roles of interest.
        """
        logger.info("Extracting salary data...")

        table = self.salary_table
        rows = table.locator("tbody tr")

        logger.info(f"Found {len(rows.all())} total rows")

        results = []
        for i, row in enumerate(rows.all()):
            try:
                # Quick check if this is a valid salary row - look for the level
                level_element = row.locator("td:nth-child(2) p").first
                if not level_element.is_visible(timeout=1000):
                    logger.info(
                        f"Skipping row {i+1} - appears to be an ad or invalid row"
                    )
                    continue

                data = {
                    "location": row.locator(
                        "td:nth-child(1) .MuiTypography-caption"
                    ).inner_text(timeout=5000),
                    "level": level_element.inner_text(timeout=5000),
                    "role": row.locator(
                        "td:nth-child(2) .MuiTypography-caption"
                    ).inner_text(timeout=5000),
                    "experience": row.locator("td:nth-child(3) p").inner_text(
                        timeout=5000
                    ),
                    "total_comp": row.locator("td:nth-child(4) p").inner_text(
                        timeout=5000
                    ),
                    "breakdown": row.locator(
                        "td:nth-child(4) .MuiTypography-caption"
                    ).inner_text(timeout=5000),
                }

                # Additional validation that we got all required fields
                if all(data.values()):
                    results.append(data)
                    logger.info(f"Parsed row {i+1}: {data}")
                else:
                    logger.info(f"Skipping row {i+1} - missing required data")

            except Exception as e:
                logger.info(f"Skipping row {i+1} - not a valid salary row: {str(e)}")
                continue

        logger.info(f"Successfully extracted {len(results)} valid salary entries")
        return results

    def _toggle_search_filters(self):
        """Opens or closes the salary search filters menu."""
        logger.info("Toggling search filters...")

        # First check if filters are already open
        try:
            # Look for the filter widget by ID
            filter_widget = self.page.locator("#search-filters").first
            is_open = filter_widget.is_visible(timeout=1000)
            logger.info(f"Filter menu is currently {'open' if is_open else 'closed'}")

            if not is_open:
                # Try multiple selectors to find and click the filter button
                filter_button = None
                # Try by ID first (most reliable)
                filter_button = self.page.locator("#toggle-search-filters").first
                if not filter_button.is_visible(timeout=1000):
                    # Try by aria-label
                    filter_button = self.page.get_by_role(
                        "button", name="Toggle Search Filters"
                    ).first
                if not filter_button.is_visible(timeout=1000):
                    # Try by text content
                    filter_button = self.page.get_by_role(
                        "button", name="Table Filter"
                    ).first

                logger.info("Clicking filter button to open menu...")
                filter_button.click()
                self.random_delay()

                # Verify it opened
                if not filter_widget.is_visible(timeout=3000):
                    raise Exception("Filter menu did not open after clicking")

        except Exception as e:
            logger.error(f"Failed to toggle filter menu: {e}")
            raise Exception("Could not toggle filter menu")

    def _narrow_salary_search(self):
        logger.info("Narrowing salary search...")
        self._toggle_search_filters()

        try:
            # 1. Click United States checkbox
            logger.info("Looking for United States checkbox...")
            us_checkbox = self.page.get_by_role("checkbox", name="United States").first

            if not us_checkbox.is_visible(timeout=3000):
                raise Exception("United States checkbox not found")

            logger.info("Clicking United States checkbox...")
            us_checkbox.click()
            self.random_delay()

            # Verify it was selected
            if not us_checkbox.is_checked():
                raise Exception("Failed to select United States checkbox")

        except Exception as e:
            logger.error(f"Failed to set United States filter: {e}")
            raise Exception("Could not set location filter")

        # 0. need an algorithm to count results.
        # My approximate filtering algorithm: do these one at a time,
        # until there are too few, and then back up one step
        # 2. years of experience: click Senior.
        # 3. experience: click New Offer Only.
        # 4. location: unclick US, click Greater NYC Area.
        # 5. time range: click past 2 years.
        # 6. time range: click past 1 year.
        # 7. Sort by: total comp (have to click twice?)


def main():
    searcher = LevelsFyiSearcher()
    try:
        results = []
        if len(sys.argv) > 1:
            # If company name provided as argument
            company_name = sys.argv[1].lower()
            logger.info(f"Searching for company: {company_name}")
            results = searcher.main(company_name)
        else:
            # Default to Shopify test case
            logger.info("No company specified, running Shopify test")
            results = searcher.test_shopify_salary()

        # Print results
        for result in results:
            print(
                f"{result['level']} {result['role']} ({result['experience']}): {result['total_comp']} - {result['location']}"
            )
        time.sleep(10)

    finally:
        searcher.cleanup()


if __name__ == "__main__":
    main()
