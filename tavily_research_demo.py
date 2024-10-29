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
        self.agent_chain = create_conversational_retrieval_agent(
            self.llm, [self.tavily_tool], verbose=verbose
        )

    def single_search(self, query: str):
        result = self.agent_chain.invoke(query)
        return result["output"]


HEADCOUNT_PROMPT = """
For the company {company_name}, find:
   - the number of employees
   - the number of employees at the NYC office, if there is one.
   - the number of employees who are egineers, if known.
   - the URLs of the pages that contain the information above
Return these results as a valid JSON object, with the following keys:
    - headcount
    - headcount_nyc
    - headcount_engineers
    - citation_urls

Value of citation_urls should be a list of strings.
Values of other keys should be integers, if known. If value is not known, it should be null.
"""

OFFICE_PROMPT = """
For the company {company_name}, find:
    - the city of the company's headquarters
    - address of the company's New York City metro area office, if there is one
    - the company's remote work policy
    - the URLs of the pages that contain the information above

Return these results as a valid JSON object, with the following keys:
    - headquarters_city
    - nyc_office_address
    - remote_work_policy
    - citation_urls

Values should be strings, if known. If value is not known, it should be null.
The remote work policy should be one of the following:
    - "hybrid"
    - "remote"
    - "in-person"
    - null

The value of nyc_office_address should be a valid US mailing address, if known.
"""

MISSION_PROMPT = """
What is the homepage, industry and mission of {company_name}?
You must always output a valid JSON object with keys:
  - "homepage"
  - "mission"
  - "industry"
  - "citation_urls"

citation_urls should be a list of strings of URLs that contain the information above.
Set other values to null if unknown.
"""

FUNDING_PROMPT = """
What is the funding status of {company_name}?
You must output JSON with these keys:
    - funding_status
    - funding_series
    - valuation
    - valuation_date
    - stock_symbol
    - unicorn_status
    - citation_urls

citation_urls should be a list of strings of URLs that contain the information above.
funding_status must be one of "public" or "private", or null if unkown.
funding_series should be a string such as "Series A", "Series B", etc. if known and the company is private, otherwise null.
"valuation" should be an integer in millions of dollars if known.
"valuation_date" should be a string in YYYY-MM-DD format if known, otherwise null.
"stock_symbol" should be a string if known, otherwise null.
"unicorn_status" should be a boolean that's true, if the company is worth over $1 billion USD, false if less, null if unknown.
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
            "If any string json value other than a citation url is longer than 80 characters, write a shorter summary of the value.",
            "Return ONLY the JSON object, nothing else.",
        ]
    )


COMPANY_PROMPTS = [
    MISSION_PROMPT,
    FUNDING_PROMPT,
    OFFICE_PROMPT,
    HEADCOUNT_PROMPT,
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
