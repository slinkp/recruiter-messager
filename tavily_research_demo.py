import os
import json

from langchain_community.utilities.tavily_search import TavilySearchAPIWrapper
from langchain.agents.agent_toolkits import create_conversational_retrieval_agent
from langchain_openai import ChatOpenAI
from langchain_community.tools.tavily_search.tool import TavilySearchResults

from langchain_community.cache import SQLiteCache
from langchain_core.globals import set_llm_cache

# I set up API key via direnv


class ResearchAgent:
    def __init__(self, verbose: bool = False):

        # set up the agent
        self.llm = ChatOpenAI(model_name="gpt-4", temperature=0.7)
        self.search_wrapper = TavilySearchAPIWrapper()
        self.tavily_tool = TavilySearchResults(api_wrapper=self.search_wrapper)

        # Cache to reduce LLM calls.
        set_llm_cache(SQLiteCache(database_path=".langchain-cache.db"))
        # Note this chain can ONLY use ChatOpenAI, not ChatAnthropic.
        # Is there a workaround?
        self.agent_chain = create_conversational_retrieval_agent(
            self.llm, [self.tavily_tool], verbose=verbose
        )

    def single_search(self, query: str):
        result = self.agent_chain.invoke(query)
        return result["output"]


BASIC_COMPANY_PROMPT = """
For the company {company_name}, find:
   - the total number of employees worldwide 
   - the number of employees at the NYC office, if there is one.
   - the number of employees who are egineers, if known.
   - the company's latest valuation, in millions of dollars, if known.
   - the company's public/private status.  If private and valued at over $1B, call it a "unicorn".
   - the most recent funding round (eg "Series A", "Series B", etc.) if private.
   - the city and country of the company's headquarters
   - the address of the company's NYC office, if there is one
   - the URLs of the pages that contain the information above

Return these results as a valid JSON object, with the following keys and data types:
    - headcount: integer or null
    - headcount_nyc: integer or null
    - headcount_engineers: integer or null
    - valuation: integer or null
    - public_status: string "public", "private", "private unicorn" or null
    - funding_series: string or null
    - headquarters_city: string or null
    - nyc_office_address: string or null
    - citation_urls: list of strings

The value of nyc_office_address, if known, must be returned as a valid US mailing address with a street address, 
city, state, and zip code.
The value of headquarters_city must be the city, state/province, and country of the company's headquarters, if known.
"""

EMPLOYMENT_PROMPT = """
For the company {company_name}, find:
    - the company's remote work policy
    - whether the company is currently hiring backend engineers
    - whether the company is hiring backend engineers with AI experience
    - whether engineers are expected to do a systems design interview
    - whether engineers are expected to do a leetcode style coding interview
    - the URL of the company's primary jobs page, preferably on their own website, if known.
    - the URLs of the pages that contain the information above

Return these results as a valid JSON object, with the following keys and data types:
    - remote_work_policy: string "hybrid", "remote", "in-person", or null
    - hiring_status: boolean or null
    - hiring_status_ai: boolean or null
    - interview_style_systems: boolean or null
    - interview_style_leetcode: boolean or null
    - jobs_homepage_url: string or null
    - citation_urls: list of strings
"""

AI_MISSION_PROMPT = """
Is {company_name} a company that uses AI?
Look for blog posts, press releases, news articles, etc. about whether and how AI 
is used for the company's products or services, whether as public-facing features or
internal implementation. Another good clue is whether the company is hiring AI engineers.

Return the result as a valid JSON object with the following keys and data types:
  - uses_ai: boolean or null
  - ai_notes: string or null
  - citation_urls: list of strings

ai_notes should be a short summary (no more than 100 words)
of how AI is used by the company, or null if the company does not use AI.
"""


def make_prompt(prompt: str, **kwargs):
    prompt = prompt.format(**kwargs)
    return "\n".join(
        [
            "You are a helpful research agent researching companies.",
            "You may use any context you have gathered in previous queries to answer the current question.",
            prompt,
            "",
            "You must always output a valid JSON object with exactly the keys specified in the prompt.",
            "citation_urls should always be a list of strings of URLs that contain the information above.",
            "If any string json value other than a citation url is longer than 80 characters, write a shorter summary of the value",
            "unless otherwise clearly specified in the prompt.",
            "Return ONLY the valid JSON object, nothing else.",
        ]
    )


COMPANY_PROMPTS = [
    BASIC_COMPANY_PROMPT,
    EMPLOYMENT_PROMPT,
    AI_MISSION_PROMPT,
]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--query", type=str, default="")
    parser.add_argument("--company", type=str, default="")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    agent = ResearchAgent(verbose=args.verbose)
    if args.query:
        print(agent.single_search(args.query))
    elif args.company:
        data = {
            "citation_urls": set(),
        }
        for prompt in COMPANY_PROMPTS:
            prompt = make_prompt(prompt, company_name=args.company)
            result = agent.single_search(prompt)
            chunk = json.loads(result)
            citation_urls = chunk.pop("citation_urls", set())
            data["citation_urls"].update(citation_urls)
            data.update(chunk)
        data["citation_urls"] = sorted(data["citation_urls"])
        print(json.dumps(data, indent=2))
    else:
        print("No query or company provided")
