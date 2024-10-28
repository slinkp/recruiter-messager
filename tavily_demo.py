import os
from langchain_community.utilities.tavily_search import TavilySearchAPIWrapper
from langchain.agents import initialize_agent, AgentType
from langchain_community.chat_models import ChatOpenAI
from langchain_community.tools.tavily_search.tool import TavilySearchResults

# set up API key via direnv

# set up the agent
llm = ChatOpenAI(model_name="gpt-4", temperature=0.7)
search = TavilySearchAPIWrapper()
tavily_tool = TavilySearchResults(api_wrapper=search)

# initialize the agent
agent_chain = initialize_agent(
    [tavily_tool],
    llm,
    agent=AgentType.STRUCTURED_CHAT_ZERO_SHOT_REACT_DESCRIPTION,
    verbose=True,
)


PROMPT = """
What are the headcounts of Rokt at https://rokt.com?
Look for information about the number of employees,
the number of engineers, and the number of employees in NYC.
You must always output a valid JSON object with the following keys:
"total_employees", "total_engineers", "nyc_employees".
The values must be integers, or null if unknown.
"""
# run the agent
agent_chain.run(
    PROMPT,
)
