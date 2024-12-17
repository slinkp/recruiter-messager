from playwright.sync_api import (
    sync_playwright,
    expect,
    TimeoutError as PlaywrightTimeout,
)
import os
from typing import List, Dict
import json
from datetime import datetime
import time
import random


class LinkedInSearcher:
    def __init__(self):
        # Fetch credentials from environment
        self.email = os.environ.get("LINKEDIN_EMAIL")
        self.password = os.environ.get("LINKEDIN_PASSWORD")

        if not all([self.email, self.password]):
            raise ValueError("LinkedIn credentials not found in environment")

        playwright = sync_playwright().start()

        # Define path for persistent context
        user_data_dir = os.path.abspath("./playwright-linkedin-chrome")

        self.context = playwright.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,
            channel="chrome",  # Use regular Chrome instead of Chromium
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--enable-sandbox",
            ],
            ignore_default_args=["--enable-automation", "--no-sandbox"],
        )
        self.page = self.context.new_page()

        # Add webdriver detection bypass
        self.page.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """
        )

        self.delay = 1  # seconds between actions

    def _wait(self):
        """Add random delay between actions"""
        time.sleep(self.delay + random.random())

    def login(self) -> None:
        """Login to LinkedIn with 2FA handling"""
        try:
            # First check if we're already logged in
            self.page.goto("https://www.linkedin.com/feed/")
            self._wait()
            try:
                # If we can access the feed within 3 seconds, we're already logged in
                self.page.wait_for_url("https://www.linkedin.com/feed/", timeout=3000)
                print("Already logged in!")
                return
            except PlaywrightTimeout:
                # Not logged in, proceed with login process
                pass

            self.page.goto("https://www.linkedin.com/login")
            self._wait()
            # Fill login form
            self.page.get_by_label("Email or Phone").fill(self.email)
            self._wait()
            self.page.get_by_label("Password").fill(self.password)
            self._wait()
            # Click sign in
            self.page.locator(
                "button[type='submit'][data-litms-control-urn='login-submit']"
            ).click()

            print("\nWaiting for 2FA verification or successful login...")

            # Try to detect 2FA page
            try:
                # Look for common 2FA elements using role-based selectors
                self.page.wait_for_selector("input[name='pin']", timeout=6000)
                print("2FA required - Please enter code from your authenticator app...")

                # Wait for successful login after 2FA
                # Give plenty of time to enter the code
                self.page.wait_for_url("https://www.linkedin.com/feed/", timeout=30000)
                print("Login successful!")

            except PlaywrightTimeout:
                # If no 2FA prompt is found, check if we're already logged in
                try:
                    self.page.wait_for_url(
                        "https://www.linkedin.com/feed/", timeout=3000
                    )
                    print("Login successful (no 2FA required)!")
                except PlaywrightTimeout:
                    self.page.screenshot(path="login_state.png")
                    raise Exception("Failed to detect login state")

        except Exception as e:
            self.page.screenshot(
                path=f"login_failure_{datetime.now():%Y%m%d_%H%M%S}.png"
            )
            raise Exception(f"LinkedIn login failed: {str(e)}")

    def search_company_connections(self, company: str) -> List[Dict]:
        """
        Search for 1st-degree connections at specified company.
        Returns list of found connections with their details.
        """
        connections = []
        try:
            # Navigate to network-filtered search (starting with just network filter)
            search_url = (
                "https://www.linkedin.com/search/results/people/"
                "?network=[%22F%22]"  # F = 1st degree connections
                "&origin=FACETED_SEARCH"
            )
            self.page.goto(search_url)
            self._wait()

            # Click the Current company filter button
            self.page.get_by_role("button", name="Current company filter").click()
            self._wait()
            self.page.screenshot(
                path=f"debug_after_clicking_company_filter_{datetime.now():%Y%m%d_%H%M%S}.png"
            )

            # Enter company name and wait for dropdown
            company_input = self.page.get_by_placeholder("Add a company")
            company_input.fill(company)
            company_input.press("Enter")
            self._wait()
            self.page.screenshot(
                path=f"debug_after_entering_company_{datetime.now():%Y%m%d_%H%M%S}.png"
            )

            # Wait for and click the Shopify option
            company_option = (
                self.page.locator("div[role='option']")
                .filter(has_text="Shopify")
                .filter(has_text="Company • Software Development")
                .first
            )
            show_results = self.page.get_by_role("button", name="Show results").first

            print("Waiting for company option and Show results to be visible...")
            company_option.wait_for(state="visible", timeout=5000)
            company_option.click()
            self._wait()
            self.page.screenshot(
                path=f"debug_after_clicking_company_option_{datetime.now():%Y%m%d_%H%M%S}.png"
            )

            show_results.wait_for(state="visible", timeout=5000)

            # Click Show results directly (it should use the currently highlighted option)
            print("Clicking Show results button...")
            show_results.click()
            self._wait()

            self.page.screenshot(
                path=f"debug_after_clicking_show_results_{datetime.now():%Y%m%d_%H%M%S}.png"
            )

            print("Waiting for search results...")
            try:
                results_container = self.page.locator("div.search-results-container")
                results_container.wait_for(state="visible", timeout=30000)
                with open(
                    f"debug_search_results_container_{datetime.now():%Y%m%d_%H%M%S}.html",
                    "w",
                    encoding="utf-8",
                ) as f:
                    f.write(results_container.evaluate("el => el.outerHTML"))
            except PlaywrightTimeout:
                self.page.screenshot(
                    path=f"debug_search_results_timeout_{datetime.now():%Y%m%d_%H%M%S}.png"
                )
                # Also capture page content for debugging
                with open(
                    f"debug_page_content_{datetime.now():%Y%m%d_%H%M%S}.html", "w"
                ) as f:
                    f.write(self.page.content())
                raise

            # Take screenshot after waiting
            self.page.screenshot(
                path=f"debug_post_wait_{datetime.now():%Y%m%d_%H%M%S}.png"
            )

            # Check for no results first
            no_results = self.page.get_by_text("No results found")
            if no_results.is_visible():
                print(f"No connections found at {company}")
                return connections

            # Get all result cards within search results container
            results = results_container.get_by_role("list").first.locator("li")
            count = results.count()

            for i in range(count):
                result = results.nth(i)
                try:
                    connection = {
                        "name": result.get_by_role("link").first.inner_text(),
                        "title": result.locator(
                            '[class*="entity-result__primary-subtitle"]'
                        ).inner_text(),
                        "location": result.locator(
                            '[class*="entity-result__secondary-subtitle"]'
                        ).inner_text(),
                        "profile_url": result.get_by_role("link").first.get_attribute(
                            "href"
                        ),
                    }
                    connections.append(connection)
                except Exception as e:
                    print(f"Error parsing result {i}: {e}")
                    with open(
                        f"debug_result_{i}_{datetime.now():%Y%m%d_%H%M%S}.html",
                        "w",
                        encoding="utf-8",
                    ) as f:
                        f.write(result.evaluate("el => el.outerHTML"))
                    raise

            return connections

        except Exception as e:
            self.page.screenshot(
                path=f"search_error_{datetime.now():%Y%m%d_%H%M%S}.png"
            )
            raise Exception(f"Error searching {company}: {e}")

    def cleanup(self) -> None:
        """Clean up browser resources"""
        try:
            if self.context:
                self.context.close()
        except Exception as e:
            print(f"Error during cleanup: {e}")


def main():
    searcher = LinkedInSearcher()
    try:
        searcher.login()

        # Example companies
        companies = ["Shopify"]

        all_results = {}
        for company in companies:
            print(f"\nSearching connections at {company}...")
            connections = searcher.search_company_connections(company)
            all_results[company] = connections

            print(f"Found {len(connections)} connections at {company}")
            for conn in connections:
                print(f"- {conn['name']}: {conn['title']}")

        # Save results to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        with open(f"linkedin_results_{timestamp}.json", "w") as f:
            json.dump(all_results, f, indent=2)

    finally:
        searcher.cleanup()


if __name__ == "__main__":
    main()
