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


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("query", type=str)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    agent = ResearchAgent(verbose=args.verbose)
    print(agent.single_search(args.query))
