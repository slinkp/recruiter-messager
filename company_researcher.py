"""
Leverage AI to find info about prospective company / role.
"""

import json
import os
import logging
from langchain_chroma import Chroma
from langchain_community.document_loaders import RecursiveUrlLoader
from langchain_core.runnables import RunnablePassthrough
from langchain_anthropic import ChatAnthropic
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.prompts import ChatPromptTemplate
from langchain.output_parsers.json import SimpleJsonOutputParser
from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator
import datetime
import os

from langchain_community.utilities.tavily_search import TavilySearchAPIWrapper
from langchain.agents.agent_toolkits import create_conversational_retrieval_agent
from langchain_openai import ChatOpenAI
from langchain_community.tools.tavily_search.tool import TavilySearchResults

from tavily import TavilyClient

from langchain_community.cache import SQLiteCache
from langchain_core.globals import set_llm_cache

from companies_spreadsheet import CompaniesSheetRow

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")

logger = logging.getLogger(__name__)


# Tavily API has undocumented input limit of 400 for get_search_context(query)
# HACK: We have to be very careful to keep prompts under this limit.
GET_SEARCH_CONTEXT_INPUT_LIMIT = 400

# PROMPT_LIMIT
BASIC_COMPANY_PROMPT = """
For the company at {company_url}, find:
 - City and country of the company's headquarters.
 - Address of the company's NYC office, if there is one.
 - Total number of employees worldwide. 
 - Number of employees at NYC office, if any.
 - Number of employees who are egineers.
"""

BASIC_COMPANY_FORMAT_PROMPT = """
Return these results as a valid JSON object, with the following keys and data types:
 - headquarters_city: string or null
 - nyc_office_address: string or null
 - total_employees: integer or null
 - nyc_employees: integer or null
 - total_engineers: integer or null

The value of nyc_office_address, if known, must be returned as a valid US mailing address with a street address, 
city, state, and zip code.
The value of headquarters_city must be the city, state/province, and country of the company's headquarters, if known.
"""
# - the URLs of the pages that contain the information above
# """

FUNDING_STATUS_PROMPT = """
For the company at {company_url}, find:
 - The company's public/private status.  If there is a stock symbol, it's public.
   If private and valued at over $1B, call it a "unicorn".
 - The company's latest valuation, in millions of dollars, if known.
 - The most recent funding round (eg "Series A", "Series B", etc.) if private.
"""

FUNDING_STATUS_FORMAT_PROMPT = """
Return these results as a valid JSON object, with the following keys and data types:
 - public_status: string "public", "private", "private unicorn" or null
 - valuation: integer or null
 - funding_series: string or null
 """

EMPLOYMENT_PROMPT = """
For the company at {company_url}, find:
    - the company's remote work policy
    - whether the company is currently hiring backend engineers
    - whether the company is hiring backend engineers with AI experience
    - the URL of the company's primary jobs page, preferably on their own website, if known.
"""

EMPLOYMENT_FORMAT_PROMPT = """
Return these results as a valid JSON object, with the following keys and data types:
    - remote_work_policy: string "hybrid", "remote", "in-person", or null
    - hiring_status: boolean or null
    - hiring_status_ai: boolean or null
    - jobs_homepage_url: string or null
    - citation_urls: list of strings
"""

INTERVIEW_STYLE_PROMPT = """
For the company at {company_url}, find:
    - whether engineers are expected to do a systems design interview
    - whether engineers are expected to do a leetcode style coding interview
"""

INTERVIEW_STYLE_FORMAT_PROMPT = """
Return these results as a valid JSON object, with the following keys and data types:
    - interview_style_systems: boolean or null
    - interview_style_leetcode: boolean or null
    - citation_urls: list of strings
"""

AI_MISSION_PROMPT = """
Is the company at {company_url} a company that uses AI?
Look for blog posts, press releases, news articles, etc. about whether and how AI 
is used for the company's products or services, whether as public-facing features or
internal implementation. Another good clue is whether the company is hiring AI engineers.
"""

AI_MISSION_FORMAT_PROMPT = """
Return the result as a valid JSON object with the following keys and data types:
  - uses_ai: boolean or null
  - ai_notes: string or null
  - citation_urls: list of strings

ai_notes should be a short summary (no more than 100 words)
of how AI is used by the company, or null if the company does not use AI.
"""

COMPANY_PROMPTS = [
    BASIC_COMPANY_PROMPT,
    FUNDING_STATUS_PROMPT,
    INTERVIEW_STYLE_PROMPT,
    EMPLOYMENT_PROMPT,
    AI_MISSION_PROMPT,
]

COMPANY_PROMPTS_WITH_FORMAT_PROMPT = [
    (BASIC_COMPANY_PROMPT, BASIC_COMPANY_FORMAT_PROMPT),
    (FUNDING_STATUS_PROMPT, FUNDING_STATUS_FORMAT_PROMPT),
    (INTERVIEW_STYLE_PROMPT, INTERVIEW_STYLE_FORMAT_PROMPT),
    (EMPLOYMENT_PROMPT, EMPLOYMENT_FORMAT_PROMPT),
    (AI_MISSION_PROMPT, AI_MISSION_FORMAT_PROMPT),
]


class TavilyRAGResearchAgent:

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
        self.verbose = verbose

    def make_prompt(
        self, search_prompt: str, format_prompt: str, extra_context: str = "", **kwargs
    ):
        prompt = search_prompt.format(**kwargs)
        parts = [
            "You are a helpful research agent researching companies.",
            "You may use any context you have gathered in previous queries to answer the current question.",
            prompt,
        ]

        if extra_context:
            parts.append("Use this additional JSON context to answer the question:")
            parts.append(extra_context)

        parts.extend(
            [
                "You must always output a valid JSON object with exactly the keys specified.",
                "citation_urls should always be a list of strings of URLs that contain the information above.",
                "If any string json value other than a citation url is longer than 80 characters, write a shorter summary of the value",
                "unless otherwise clearly specified in the prompt.",
                "Return ONLY the valid JSON object, nothing else.",
                format_prompt,
            ]
        )

        return "\n".join(parts)

    def main(self, url: str) -> CompaniesSheetRow:
        tavily_client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])

        # Initialize with URL and today's date
        data = CompaniesSheetRow(
            url=url,
            updated=datetime.date.today(),
            current_state="10. consider applying",  # Default initial state
        )

        for prompt, format_prompt in COMPANY_PROMPTS_WITH_FORMAT_PROMPT:
            prompt = prompt.format(company_url=url)
            if len(prompt) > GET_SEARCH_CONTEXT_INPUT_LIMIT:
                logger.warning(
                    f"Truncating prompt from {len(prompt)} to {GET_SEARCH_CONTEXT_INPUT_LIMIT} characters"
                )
                prompt = prompt[:GET_SEARCH_CONTEXT_INPUT_LIMIT]
                logger.debug(f"Prompt truncated: {prompt}")
            else:
                logger.debug(f"Prompt not truncated: {prompt}")

            try:
                context = tavily_client.get_search_context(
                    query=prompt,
                    max_tokens=1000 * 20,
                    max_results=10,
                    search_depth="advanced",
                )
                logger.debug(f"  Got Context: {len(context)}")
                full_prompt = self.make_prompt(
                    prompt, format_prompt, extra_context=context
                )
                logger.debug(f"  Full prompt:\n\n {full_prompt}\n\n")
                result = self.llm.invoke(full_prompt)
                content = json.loads(result.content)

                # Map the API response fields to CompaniesSheetRow fields
                if "total_employees" in content:
                    data.total_size = content["total_employees"]
                if "total_engineers" in content:
                    data.eng_size = content["total_engineers"]
                if "nyc_office_address" in content:
                    data.ny_address = content["nyc_office_address"]
                if "remote_work_policy" in content:
                    # Map remote work policy to expected values
                    policy = content["remote_work_policy"].lower()
                    if "remote" in policy:
                        data.remote_policy = "remote"
                    elif "hybrid" in policy:
                        data.remote_policy = "hybrid"
                    elif "in-person" in policy:
                        data.remote_policy = "onsite"
                if "interview_style_systems" in content:
                    data.sys_design = content["interview_style_systems"]
                if "interview_style_leetcode" in content:
                    data.leetcode = content["interview_style_leetcode"]
                if "ai_notes" in content:
                    data.ai_notes = content["ai_notes"]
                if "public_status" in content:
                    # Map funding status to company type
                    status = content["public_status"]
                    if status == "public":
                        data.type = "public"
                    elif status == "private unicorn":
                        data.type = "unicorn"
                    elif status == "private":
                        data.type = "private"

                logger.info(f"  DATA SO FAR:\n{data}\n\n")

            except Exception as e:
                logger.error(f"Error processing prompt: {e}")
                continue

        return data


def main(
    url, model, refresh_rag_db: bool = False, verbose: bool = False
) -> CompaniesSheetRow:
    researcher = TavilyRAGResearchAgent(verbose=verbose)
    return researcher.main(url)


if __name__ == '__main__':
    import argparse
    import sys

    if len(sys.argv) < 2:
        sys.argv.append("https://rokt.com")  # HACK for testing

    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="URL of the company to research")
    parser.add_argument(
        "--model",
        help="AI model to use",
        action="store",
        default="gpt-4o",
        choices=[
            "gpt-4o",
            "gpt-4-turbo",
            "gpt-3.5-turbo",
            "claude-3-5-sonnet-latest",
        ],
    )
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--refresh-rag-db",
        action="store_true",
        default=False,
        help="Force fetching data and refreshing the RAG database for this URL. Default is to use existing data.",
    )

    args = parser.parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    data = main(
        args.url,
        model=args.model,
        refresh_rag_db=args.refresh_rag_db,
        verbose=args.verbose,
    )
    import pprint
    pprint.pprint(data)


# Vetting models:
# - gpt-4o:  status = unicorn, urls = careers, team, workplace, compensation, blog
# - gpt-4-turbo: status = private, urls = careers, about, blog
# Sometimes complain about being unable to open URLs.
