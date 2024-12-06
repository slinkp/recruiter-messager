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

# Add new prompt for extracting company info from email
EXTRACT_COMPANY_PROMPT = """
From this recruiter message, extract:
 - The company name being recruited for
 - The company's website URL, if mentioned
 - The role/position being recruited for
 - The recruiter's name and contact info

----- Recruiter message follows -----
 {message}
----- End of recruiter message -----
"""

EXTRACT_COMPANY_FORMAT_PROMPT = """
Return these results as a valid JSON object, with the following keys and data types:
 - company_name: string or null
 - company_url: string or null  
 - role: string or null
 - recruiter_name: string or null
 - recruiter_contact: string or null
"""
class TavilyRAGResearchAgent:

    def __init__(self, verbose: bool = False, llm: Optional[object] = None):

        # set up the agent
        self.llm = llm or ChatOpenAI(model_name="gpt-4", temperature=0.7)
        # Cache to reduce LLM calls.
        set_llm_cache(SQLiteCache(database_path=".langchain-cache.db"))
        self.verbose = verbose
        self.tavily_client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])

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

    def extract_initial_company_info(self, message: str) -> dict:
        """Extract basic company info from recruiter message"""
        try:
            full_prompt = self.make_prompt(
                EXTRACT_COMPANY_PROMPT.format(message=message),
                EXTRACT_COMPANY_FORMAT_PROMPT,
                extra_context="",  # No need for search context when parsing message directly
            )
            result = self.llm.invoke(full_prompt)
            return json.loads(result.content)
        except Exception as e:
            logger.error(f"Error extracting company info: {e}")
            return {}

    def main(self, *, url: str = None, message: str = None) -> CompaniesSheetRow:
        """
        Research a company based on either a URL or a recruiter message.
        One of url or message must be provided.

        Args:
            url: Company URL to research
            message: Recruiter message to analyze
        """
        if all([url, message]) or not any([url, message]):
            raise ValueError("Exactly one of url or message must be provided")

        data = CompaniesSheetRow(
            url=url,
            updated=datetime.date.today(),
            current_state="10. consider applying",  # Default initial state
        )

        if message:
            company_info = self.extract_initial_company_info(message)
            data.name = company_info.get("company_name", "")
            data.url = company_info.get("company_url", "")
            data.recruit_contact = company_info.get("recruiter_name", "")
            print(f"Company info: {data}")

        for prompt, format_prompt in COMPANY_PROMPTS_WITH_FORMAT_PROMPT:
            # If we're working with a message, include it in the context
            if message:
                prompt = f"""
                Using this recruiter message as part of the context:
                --- Recruiter message follows ---
                {message}
                --- End of recruiter message ---
                {prompt}
                """

            # Use URL if we have it, otherwise use company name
            company_identifier = data.url or data.name
            prompt = prompt.format(company_url=company_identifier)

            if len(prompt) > GET_SEARCH_CONTEXT_INPUT_LIMIT:
                logger.warning(
                    f"Truncating prompt from {len(prompt)} to {GET_SEARCH_CONTEXT_INPUT_LIMIT} characters"
                )
                prompt = prompt[:GET_SEARCH_CONTEXT_INPUT_LIMIT]
                logger.debug(f"Prompt truncated: {prompt}")
            else:
                logger.debug(f"Prompt not truncated: {prompt}")

            try:
                context = self.tavily_client.get_search_context(
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
                    data.type = content["public_status"]

                logger.info(f"  DATA SO FAR:\n{data}\n\n")

            except Exception as e:
                logger.error(f"Error processing prompt: {e}")
                continue

        return data


def main(
    url_or_message: str,
    model: str,
    refresh_rag_db: bool = False,  # TODO: Unused
    verbose: bool = False,
    is_url: bool | None = None,
) -> CompaniesSheetRow:
    """
    Research a company based on either a URL or a recruiter message.

    Args:
        url_or_message: Either a company URL or a recruiter message
        model: The LLM model to use
        refresh_rag_db: Whether to refresh the RAG database
        verbose: Whether to enable verbose logging
        is_url: Force interpretation as URL (True) or message (False). If None, will try to auto-detect.
    """
    TEMPERATURE = 0.7
    if model.startswith("gpt-"):
        llm = ChatOpenAI(model_name=model, temperature=TEMPERATURE)
    elif model.startswith("claude"):
        llm = ChatAnthropic(model_name=model, temperature=TEMPERATURE)
    else:
        raise ValueError(f"Unknown model: {model}")

    researcher = TavilyRAGResearchAgent(verbose=verbose, llm=llm)

    # Auto-detect if not specified
    if is_url is None:
        is_url = url_or_message.startswith(("http://", "https://"))

    if is_url:
        return researcher.main(url=url_or_message)
    else:
        return researcher.main(message=url_or_message)


if __name__ == '__main__':
    import argparse
    import sys

    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="URL of company or recruiter message to research")
    parser.add_argument(
        "--type",
        choices=["url", "message"],
        help="Force interpretation as URL or message. If not specified, will auto-detect.",
    )
    parser.add_argument(
        "--model",
        help="AI model to use",
        action="store",
        default="claude-3-5-sonnet-latest",
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

    is_url = None if args.type is None else (args.type == "url")

    data = main(
        args.input,
        model=args.model,
        refresh_rag_db=args.refresh_rag_db,
        verbose=args.verbose,
        is_url=is_url,
    )
    import pprint
    pprint.pprint(data)


# Vetting models:
# - gpt-4o:  status = unicorn, urls = careers, team, workplace, compensation, blog
# - gpt-4-turbo: status = private, urls = careers, about, blog
# Sometimes complain about being unable to open URLs.
