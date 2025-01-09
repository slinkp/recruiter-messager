import argparse
import logging
import pprint
import random
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List

from playwright.sync_api import expect, sync_playwright

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
            ignore_default_args=["--enable-automation", "--no-sandbox"],
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

    def main(self, company_name: str) -> Iterable[Dict]:
        """Main function to search for salary data at a company"""
        # All of these work by side effects or raising exceptions
        self.search_by_company_name(company_name)
        self.random_delay()
        # TODO: add levels extraction
        return self.find_and_extract_salaries()

    def test_company_salary(self, company_salary_url: str) -> Iterable[Dict]:
        """Test method that loads salary data when we already have the URL"""
        logger.info(f"Running test for {company_salary_url}")
        self.page.goto(company_salary_url)
        self.random_delay(1, 2)

        # Check if we need to login
        if "login" in self.page.url.lower():
            logger.info("Hit login wall, attempting login...")
            self.login()
            # Return to the Shopify page
            self.page.goto(company_salary_url)
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

    def find_and_extract_salaries(self) -> Iterable[Dict]:
        self._navigate_to_salary_page()
        searcher = SalarySearcher(self.page)
        return searcher.get_salary_data()

    def find_and_extract_levels(self, company_name: str):
        self._navigate_to_comparison_page(company_name)
        extractor = LevelsExtractor(self.page)
        return extractor.find_and_extract_levels()

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

            print("\n=== MANUAL LOGIN REQUIRED ===")
            print("1. Please complete the Google login in the browser window")
            print("2. This may include:")
            print("   - Entering your Google email")
            print("   - Entering your password")
            print("   - Completing 2FA if enabled")
            print("3. After you see you're logged into Levels.fyi, return here")

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
            # TODO:
            # Create an exception class that includes url and error message,
            # and in main() catch that exception and save the screenshot
            # before raising it again.
            # Then we can DRY all the places we are screenshotting.
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

        if "salaries/software-engineer" in self.page.url:
            logger.info("Already on salary page, skipping navigation...")
            return

        if self.page.url.endswith("/culture"):
            # TODO are there other cases of company search landing elsewhere?
            logger.debug("Landed on culture page...")
            url = self.page.url.replace("/culture", "/salaries")
            self.page.goto(url)
            self.random_delay()

        logger.info(f"Current URL: {self.page.url}")

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
            self.page.screenshot(path="swe_link_not_visible.png")
            raise RuntimeError(
                f"Software Engineer link not visible on page {self.page.url}. See screenshot swe_link_not_visible.png"
            )

    def _navigate_to_comparison_page(self, company_name: str):
        """Find the company comparison page"""
        url = f"https://www.levels.fyi/?compare={company_name},Shopify&track=Software%20Engineer"
        self.page.goto(url)


class SalarySearcher:
    def __init__(self, page):
        self.page = page
        assert "salaries/software-engineer" in self.page.url
        self.salary_table = self.page.locator(
            "table[aria-label='Salary Submissions']"
        ).first

    def get_salary_data(self) -> Iterable[Dict]:
        if not self.salary_table.is_visible(timeout=5000):
            logger.warning(
                f"Could not find salary table on page {self.page.url}, returning empty"
            )
            return []
        logger.info(f"Looking for salary table on {self.page.url}...")
        self._say_salary_data_added()
        self.random_delay()
        self._narrow_salary_search()
        for row in self._extract_salary_data():
            yield self._postprocess_salary_row(row)

    def random_delay(
        self, min_seconds: float | int = 0.6, max_seconds: float | int = 3.0
    ):
        """Add a random delay between actions"""
        delay = random.uniform(min_seconds, max_seconds)
        logger.debug(f"Waiting for {delay:.1f} seconds...")
        time.sleep(delay)

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

    def _postprocess_salary_row(self, data: Dict) -> Dict:
        """Postprocess salary data to clean up and add some derived fields."""
        logger.info("Postprocessing salary data...")
        # Example dict:
        # {'breakdown': '177K | 59K | N/A',
        #  'experience': '7 yrs',
        #  'level': 'L6',
        #  'location': 'New York, NY | 12/13/2023',
        #  'role': 'ML / AI',
        #  'total_comp': '$236,000'}
        salary, equity, bonus = data["breakdown"].split(" | ")
        salary = 0 if salary == "N/A" else float(salary.rstrip("K")) * 1000
        if equity.endswith("K"):
            equity = float(equity.rstrip("K")) * 1000
        elif equity.endswith("M"):
            equity = float(equity.rstrip("M")) * 1000000
        else:
            equity = 0
        bonus = 0 if bonus == "N/A" else float(bonus.rstrip("K")) * 1000
        tc = int(data["total_comp"].replace("$", "").replace(",", ""))

        parsed = {
            "total_comp": tc,
            "salary": salary,
            "equity": equity,
            "bonus": bonus,
        }
        location, date = data["location"].split(" | ")
        parsed["location"] = location
        parsed["date"] = date
        data.update(parsed)
        return data

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

            return filter_widget

        except Exception as e:
            logger.error(f"Failed to toggle filter menu: {e}")
            raise Exception("Could not toggle filter menu")

    def _clear_location_filters(self, filter_widget):
        logger.info("Clearing location filters...")
        # First find the list containing United States within the filter widget
        logger.info("Finding location filter list...")
        location_list = filter_widget.locator(
            "ul:has(label:has-text('United States'))"
        ).first

        # Then find and uncheck any selected locations within this list
        logger.info("Unchecking any selected locations...")
        location_checkboxes = location_list.locator("input[type='checkbox']").all()

        for checkbox in location_checkboxes:
            if checkbox.is_checked():
                logger.info("Unchecking location checkbox")
                checkbox.click()
                self.random_delay(0.2, 0.6)

    def _narrow_salary_search(self):
        logger.info("Narrowing salary search...")
        # My approximate filtering algorithm: do these filters one at a time,
        # until there are too few, and then back up one step
        # TODO: refactor to DRY up the boilerplate
        # TODO: not crazy about Cursor's exception pattern here

        MIN_RESULTS = 5
        # Get initial result count
        initial_count = self._get_salary_result_count()
        logger.info(f"Starting with {initial_count} results")
        if initial_count < MIN_RESULTS:
            logger.info("Not enough results to narrow search")
            return

        filter_widget = self._toggle_search_filters()

        try:
            self._clear_location_filters(filter_widget)
            # Click United States checkbox
            logger.info("Looking for United States checkbox...")
            us_checkbox = filter_widget.get_by_role(
                "checkbox", name="United States"
            ).first

            if not us_checkbox.is_visible(timeout=3000):
                raise Exception("United States checkbox not found")

            logger.info("Clicking United States checkbox...")
            us_checkbox.click()
            self.random_delay()

            # Verify it was selected
            if not us_checkbox.is_checked():
                raise Exception("Failed to select United States checkbox")

            # Check how many results we have after US filter
            us_count = self._get_salary_result_count()
            logger.info(f"After US filter: {us_count} results")
            if us_count < MIN_RESULTS:
                logger.info("Not enough results after US filter, unclicking...")
                us_checkbox.click()
                self.random_delay()

            # Add New Offer Only filter
            logger.info("Looking for New Offer Only checkbox...")
            new_offer_checkbox = filter_widget.get_by_role(
                "checkbox", name="New Offer Only"
            ).first

            if new_offer_checkbox.is_visible(timeout=3000):
                logger.info("Clicking New Offer Only checkbox...")
                new_offer_checkbox.click()
                self.random_delay()

                # Check results after New Offer filter
                new_offer_count = self._get_salary_result_count()
                logger.info(f"After New Offer filter: {new_offer_count} results")
                if new_offer_count < MIN_RESULTS:
                    logger.info(
                        "Not enough results after New Offer filter, unclicking..."
                    )
                    new_offer_checkbox.click()
                    self.random_delay()

            # Try Greater NYC Area filter
            logger.info("Looking for Greater NYC Area checkbox...")
            # First uncheck US if it's checked
            us_checkbox = filter_widget.get_by_role(
                "checkbox", name="United States"
            ).first
            if us_checkbox.is_checked():
                logger.info("Unchecking United States...")
                us_checkbox.click()
                self.random_delay()

            nyc_checkbox = filter_widget.get_by_role(
                "checkbox", name="Greater NYC Area"
            ).first

            if nyc_checkbox.is_visible(timeout=3000):
                logger.info("Clicking Greater NYC Area checkbox...")
                nyc_checkbox.click()
                self.random_delay()

                # Check results after NYC filter
                nyc_count = self._get_salary_result_count()
                logger.info(f"After NYC filter: {nyc_count} results")
                if nyc_count < MIN_RESULTS:
                    logger.info("Not enough results after NYC filter, unclicking...")
                    nyc_checkbox.click()
                    # If NYC didn't work, recheck US
                    us_checkbox.click()
                    self.random_delay()

            # Add Past 1 Year filter, then try Past 2 Years if needed
            logger.info("Looking for time range radio buttons...")

            # Try Past Year first
            one_year_radio = filter_widget.get_by_role("radio", name="Past Year").first
            if one_year_radio.is_visible(timeout=3000):
                logger.info("Clicking Past Year radio...")
                one_year_radio.click()
                self.random_delay()

                # Check results after 1 year filter
                time_count = self._get_salary_result_count()
                logger.info(f"After 1 Year filter: {time_count} results")

                if time_count < MIN_RESULTS:
                    logger.info(
                        "Not enough results with 1 Year filter, trying 2 Years..."
                    )

                    # Try 2 years instead
                    two_years_radio = filter_widget.get_by_role(
                        "radio", name="Past 2 Years"
                    ).first
                    if two_years_radio.is_visible(timeout=3000):
                        logger.info("Clicking Past 2 Years radio...")
                        two_years_radio.click()
                        self.random_delay()

                        # Check results after 2 years filter
                        time_count = self._get_salary_result_count()
                        logger.info(f"After 2 Years filter: {time_count} results")
                        if time_count < MIN_RESULTS:
                            logger.info(
                                "Not enough results after 2 Years filter, setting to All Time..."
                            )
                            # Reset to All Time if neither option works
                            all_time_radio = filter_widget.get_by_role(
                                "radio", name="All Time"
                            ).first
                            all_time_radio.click()
                            self.random_delay()

        except Exception as e:
            logger.error(f"Failed to set filters: {e}")
            raise Exception("Could not set filters")

        # TODO:
        # - years of experience: enter 10 in the min years field, iterate downward
        # - Sort by: total comp (have to click twice?)

    def _get_salary_result_count(self) -> int:
        """Gets the total number of salary results from the pagination text."""
        logger.info("Getting total result count...")
        try:
            # Find the pagination text within the salary table
            pagination_text = self.salary_table.locator(
                "text=/\\d+ - \\d+ of [\\d,]+/"
            ).first
            if not pagination_text.is_visible(timeout=3000):
                # TODO: just count the rows instead.
                raise Exception("Could not find pagination text")

            # Extract the total count (the last number)
            text = pagination_text.inner_text()
            total = text.split(" of ")[1].replace(",", "")
            count = int(total)

            logger.info(f"Found {count} total results")
            return count

        except Exception as e:
            logger.error(f"Failed to get result count: {e}")
            raise Exception("Could not determine number of results")


class LevelsExtractor:
    def __init__(self, page):
        self.page = page

    def find_and_extract_levels(self) -> List[str]:
        """Extract job level information from the comparison tables."""
        logger.info("Extracting job level information...")

        # Find the level container div
        level_container = self.page.locator("#levelContainer").first
        if not level_container.is_visible(timeout=5000):
            self.page.screenshot(path="level_container_not_visible.png")
            logger.error(f"No level container. Current URL: {self.page.url}")
            return []  # Return empty list instead of raising

        # Find both company columns
        company_cols = level_container.locator(".level-col").all()
        if len(company_cols) != 2:
            raise RuntimeError(f"Expected 2 company columns, found {len(company_cols)}")

        results = []
        for col in company_cols:
            # Get company name from the button
            company_button = col.locator(".company-detail-button").first
            company_name = company_button.get_attribute("company-name")

            # Find the table and get all rows
            table = col.locator(".levelTable").first

            # Extract table height from style attribute
            style = table.get_attribute("style")
            height = None
            if style and "height:" in style:
                # Extract height value (could be in % or px)
                height_part = [p for p in style.split(";") if "height:" in p][0]
                height_str = height_part.split("height:")[1].strip()
                if height_str.endswith("%"):
                    height = float(height_str.rstrip("%"))

            rows = table.locator("tr.position-row").all()

            levels = []
            table_height_pixels = 0
            cumulative_height = 0
            for row in rows:
                # Get all span elements in the row
                spans = row.locator("span.span-f").all()

                # First span is always the level/title
                level_title = spans[0].inner_text()

                # Second span (if exists) is the role description
                role_description = spans[1].inner_text() if len(spans) > 1 else None

                # Extract row height from style attribute
                row_style = row.get_attribute("style")
                row_height = None
                if row_style and "height:" in row_style:
                    # Extract height value (in px)
                    height_part = [p for p in row_style.split(";") if "height:" in p][0]
                    height_str = height_part.split("height:")[1].strip()
                    if height_str.endswith("px"):
                        row_height = float(height_str.rstrip("px"))
                        table_height_pixels += row_height

                # Track distance from top of table to this row
                if row_height is not None:
                    if level_title == "L7":
                        logger.info(
                            f"Found L7 row at {cumulative_height}px from table top"
                        )
                    levels.append(
                        {
                            "level": level_title,
                            "role": role_description,
                            "row_height": row_height,
                            "distance_from_top": cumulative_height,
                        }
                    )
                    cumulative_height += row_height
                else:
                    levels.append(
                        {
                            "level": level_title,
                            "role": role_description,
                            "row_height": row_height,
                            "distance_from_top": None,
                        }
                    )

            results.append(
                {
                    "company": company_name,
                    "levels": levels,
                    "table_height_percentage": height,
                    "table_height_pixels": table_height_pixels,
                }
            )

        # Find L7 position in second table
        shopify_data = results[1] if results[1]["company"] == "Shopify" else results[0]
        l7_data = next(
            (level for level in shopify_data["levels"] if level["level"] == "L7"), None
        )

        relevant_levels = []

        if l7_data:
            l7_start = l7_data["distance_from_top"]
            l7_end = (
                l7_start + l7_data["row_height"]
                if l7_start is not None and l7_data["row_height"] is not None
                else None
            )

            if l7_end is None:
                logger.warning("Could not determine L7 position in table")
                return []

            logger.info(f"L7 spans from {l7_start}px to {l7_end}px")

            # Find overlapping rows in first table
            first_company = results[0]
            for level in first_company["levels"]:
                level_start = level["distance_from_top"]
                level_end = (
                    level_start + level["row_height"]
                    if level_start is not None and level["row_height"] is not None
                    else None
                )

                if level_start is None or level_end is None:
                    logger.warning(
                        f"Skipping level {level['level']} - missing position data"
                    )
                    continue

                # Check for overlap
                if level_start <= l7_end and level_end >= l7_start:
                    relevant_levels.append(level["level"])

            logger.info(f"Levels overlapping with L7: {relevant_levels}")

        return relevant_levels


def main(company_name: str = "", company_salary_url: str = ""):
    searcher = LevelsFyiSearcher()
    try:
        if company_name:
            # If company name provided as argument
            logger.info(f"Searching for company: {company_name}")
            # Convert generator to list before cleanup
            results = list(searcher.main(company_name))
        elif company_salary_url:
            logger.info("Directly extracting salaries from url")
            results = list(searcher.test_company_salary(company_salary_url))
        else:
            raise ValueError(
                "Either company name or company salary URL must be provided"
            )
        return results
    finally:
        searcher.cleanup()


def extract_levels(company_name: str):
    searcher = LevelsFyiSearcher()
    try:
        return searcher.find_and_extract_levels(company_name)
    finally:
        searcher.cleanup()


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="Search Levels at Work")
    parser.add_argument(
        "--company",
        help="Company name",
        action="store",
        default=None,
    )
    parser.add_argument(
        "--test",
        help="Test shopify salary page",
        action="store_true",
    )

    parser.add_argument(
        "--test-levels-extraction",
        help="Find and extract levels comparing Shopify to named company",
        action="store_true",
    )

    args = parser.parse_args()

    company_salary_url = ""

    if args.test_levels_extraction:
        assert args.company, "Company name must be provided for levels extraction"
        result = extract_levels(args.company)
        pprint.pprint(result)
        sys.exit(0)
    elif args.test:
        company_salary_url = "https://www.levels.fyi/companies/shopify/salaries/software-engineer?country=43"

    for i, result in enumerate(main(args.company, company_salary_url)):
        print(f"{i+1}:")
        pprint.pprint(result)
