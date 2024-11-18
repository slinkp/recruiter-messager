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
        self.browser = playwright.firefox.launch(
            headless=False,  # Helpful for development
        )
        self.context = self.browser.new_context()
        self.page = self.context.new_page()

        self.delay = 1  # seconds between actions

    def _wait(self):
        """Add random delay between actions"""
        time.sleep(self.delay + random.random())

    def login(self) -> None:
        """Login to LinkedIn with 2FA handling"""
        try:
            self.page.goto("https://www.linkedin.com/login")

            # Fill login form
            self.page.get_by_label("Email or Phone").fill(self.email)
            self.page.get_by_label("Password").fill(self.password)

            # Click sign in
            self.page.locator(
                "button[type='submit'][data-litms-control-urn='login-submit']"
            ).click()

            print("\nWaiting for 2FA verification or successful login...")

            # Try to detect 2FA page
            try:
                # Look for common 2FA elements using role-based selectors
                self.page.wait_for_selector("input[name='pin']", timeout=5000)
                print("2FA required - Please enter code from your authenticator app...")

                # Wait for successful login after 2FA
                # Give plenty of time to enter the code
                self.page.wait_for_url("https://www.linkedin.com/feed/", timeout=30000)
                # self.page.wait_for_selector("div.feed-identity-module", timeout=60000)
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
            # Navigate to network-filtered search
            search_url = (
                "https://www.linkedin.com/search/results/people/"
                f"?currentCompany=[%22{company}%22]"
                "&network=[%22F%22]"  # F = 1st degree connections
                "&origin=FACETED_SEARCH"
            )
            self.page.goto(search_url)

            # Wait for results or "no results" message
            self.page.wait_for_selector('div[class*="search-results__container"]')

            # Check for no results first
            no_results = self.page.get_by_text("No results found")
            if no_results.is_visible():
                print(f"No connections found at {company}")
                return connections

            # Get all result cards
            results = self.page.locator("li.reusable-search__result-container")
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
                    continue

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
            if self.browser:
                self.browser.close()
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
