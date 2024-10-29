import os
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
Return ONLY the JSON object, nothing else.
"""

OFFICE_PROMPT = """
For the company {company_name}, find:
    - the city of the company's headquarters
    - the company's remote work policy
    - the URLs of the pages that contain the information above

Return these results as a valid JSON object, with the following keys:
    - headquarters_city
    - remote_work_policy
    - citation_urls

Values should be strings, if known. If value is not known, it should be null.
The remote work policy should be one of the following:
    - "hybrid"
    - "remote"
    - "in-person"
    - null

Return ONLYthe JSON object, nothing else.
"""

PROMPTS = [
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
        for prompt in PROMPTS:
            prompt = prompt.format(company_name=args.company)
            print(agent.single_search(prompt))
    else:
        print("No query or company provided")
