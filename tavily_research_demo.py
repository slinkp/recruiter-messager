import os
from langchain_community.utilities.tavily_search import TavilySearchAPIWrapper
from langchain.agents.agent_toolkits import create_conversational_retrieval_agent
from langchain_openai import ChatOpenAI
from langchain_community.tools.tavily_search.tool import TavilySearchResults

from langchain_community.cache import SQLiteCache
from langchain_core.globals import set_llm_cache

# I set up API key via direnv


def main(query: str, verbose: bool = False):
    # set up the agent
    llm = ChatOpenAI(model_name="gpt-4", temperature=0.7)
    search = TavilySearchAPIWrapper()
    tavily_tool = TavilySearchResults(api_wrapper=search)

    # Cache to reduce LLM calls.
    set_llm_cache(SQLiteCache(database_path=".langchain-cache.db"))
    agent_chain = create_conversational_retrieval_agent(
        llm, [tavily_tool], verbose=verbose
    )

    result = agent_chain.invoke(args.query)

    return result["output"]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("query", type=str)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    print(main(args.query, args.verbose))
