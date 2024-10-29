import os
from langchain_community.utilities.tavily_search import TavilySearchAPIWrapper
from langchain.agents.agent_toolkits import create_conversational_retrieval_agent
from langchain_openai import ChatOpenAI
from langchain_community.tools.tavily_search.tool import TavilySearchResults

# I set up API key via direnv

# set up the agent
llm = ChatOpenAI(model_name="gpt-4", temperature=0.7)
search = TavilySearchAPIWrapper()
tavily_tool = TavilySearchResults(api_wrapper=search)

agent_chain = create_conversational_retrieval_agent(llm, [tavily_tool], verbose=True)

QUESTION = """
What are the headcounts of Rokt at https://rokt.com?
Look for information about the number of employees,
the number of engineers, and the number of employees in NYC.
You must always output a valid JSON object with the following keys:
"total_employees", "total_engineers", "nyc_employees".
The values must be integers, or null if unknown.
"""
# run the agent
agent_chain.invoke(
    QUESTION,
)
