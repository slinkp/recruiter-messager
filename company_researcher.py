"""
Leverage AI to find info about prospective company / role.

Info to find:

- Funding status
  - public / private / unicorn / private finance

- Levels (compared to shopify)

- Compensation
 - base salary
 - RSUs
   - vesting schedule
 - bonus

- Interview style
  - leetcode?
  - system design

- Remote / hybrid / onsite?

- AI relevance
  - what is the AI team like?
  - what is the AI team working on?

- Size
  - total employees
  - total engineers
  - NYC employees

- NY office location

Based on https://python.langchain.com/docs/concepts/#json-mode
"""

import json
import os
import re
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
from bs4 import BeautifulSoup

import os

from langchain_community.utilities.tavily_search import TavilySearchAPIWrapper
from langchain.agents.agent_toolkits import create_conversational_retrieval_agent
from langchain_openai import ChatOpenAI
from langchain_community.tools.tavily_search.tool import TavilySearchResults

from tavily import TavilyClient

from langchain_community.cache import SQLiteCache
from langchain_core.globals import set_llm_cache

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")

logger = logging.getLogger(__name__)


blankline_re = re.compile(r"\n\s*\n+")


def bs4_extractor(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    text = blankline_re.sub(r"\n\n", soup.text).strip()
    return text


class CompanyInfo(BaseModel):
    model_config = {
        "strict": True,
        "extra": "forbid",
    }

    company: Optional[str] = Field(default=None, description="The name of the company")
    funding_status: Optional[
        Literal["public", "private", "unicorn", "private finance"]
    ] = Field(default=None, description="The funding status of the company")
    mission: Optional[str] = Field(
        default=None, description="The mission of the company"
    )
    work_policy: Optional[Literal["remote", "hybrid", "onsite"]] = Field(
        default=None, description="The work policy of the company"
    )
    total_employees: Optional[int] = Field(
        default=None, description="The total number of employees"
    )
    total_engineers: Optional[int] = Field(
        default=None, description="The total number of engineers"
    )
    nyc_employees: Optional[int] = Field(
        default=None, description="The number of employees in NYC"
    )

    @field_validator("*", mode="before")
    @classmethod
    def handle_unknown(cls, v):
        # Some models return "UNKNOWN" or "<UNKNOWN>" for unknown values, disregarding
        # our instructions to use null.
        if isinstance(v, str) and "UNKNOWN" in v:
            return None
        return v


class BasicRagResearchAgent:

    def __init__(self, url, model, refresh_rag_db: bool = False):
        self.url = url
        self.urls = [url]
        self.data = {"url": url, "urls": self.urls}
        if model.startswith("gpt-"):
            chatclass = ChatOpenAI
            kwargs = {"response_format": {"type": "json_object"}}
            structured_output = False
            self.use_parser = True
        elif model.startswith("claude-"):
            chatclass = ChatAnthropic
            kwargs = {}
            structured_output = True
            self.use_parser = False
        else:
            raise ValueError(f"Unsupported model: {model}")

        self.model = chatclass(
            model=model,
            model_kwargs=kwargs,
        )
        if structured_output:
            self.model = self.model.with_structured_output(CompanyInfo)

        self.collection_name = self.get_collection_name(url)
        self.setup_rag_db(refresh=refresh_rag_db)

    def setup_rag_db(self, refresh: bool = False):
        embeddings = OpenAIEmbeddings(model="text-embedding-3-large")
        self.vectorstore = Chroma(
            collection_name=self.collection_name,
            embedding_function=embeddings,
            persist_directory=DATA_DIR,
        )
        has_data = bool(self.vectorstore.get(limit=1, include=[])["ids"])
        if has_data and not refresh:
            logger.info(f"Loaded existingvector store for {self.collection_name}")
            return

        self.vectorstore.delete_collection()
        self.vectorstore = Chroma(
            collection_name=self.collection_name,
            embedding_function=embeddings,
            persist_directory=DATA_DIR,
        )
        logger.info(
            f" Fetching and splitting documents from {self.url} to the vector store {self.collection_name}"
        )
        splits, ids = self.get_text_splits_from_url(self.url)
        logger.info(
            f" Adding {len(splits)} splits to the vector store {self.collection_name}"
        )
        self.populate_vector_db(splits, ids)
        logger.info(f"Done setting up vector store {self.collection_name}")

    @property
    def parser(self):
        return SimpleJsonOutputParser()

    def get_collection_name(self, url: str):
        url = re.sub(r"https?://", "", url)
        url = re.sub(r"\W+", "-", url)
        url = url.strip("-_")
        url = url[:63]
        logger.debug(f"Collection name: {url}")
        return url

    def get_text_splits_from_url(self, url: str):
        logger.debug(f"Fetching and splitting contents of {url}")
        loader = RecursiveUrlLoader(url=url, max_depth=2, extractor=bs4_extractor)

        docs_limit = 100

        docs = []
        for doc in loader.lazy_load():
            url = doc.metadata["source"].rstrip("/#")
            if url in self.urls:
                logger.error(f" Already seen {url}, skipping")
                continue
            self.urls.append(url)
            logger.info(f" Got {url}: {doc.page_content[:100]}")
            docs.append(doc)
            if len(docs) >= docs_limit:
                break

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000, chunk_overlap=200
        )
        splits = text_splitter.split_documents(docs)
        base_id = hash(url)
        ids = []
        for i, split in enumerate(splits):
            _id = str(hash((base_id, i)))
            split.metadata["id"] = _id
            ids.append(_id)
        return splits, ids

    def populate_vector_db(self, splits, ids):
        logging.info(
            f"Adding or updating documents to the vector store {self.collection_name}"
        )
        self.vectorstore.add_documents(documents=splits, ids=ids)

    def format_docs(self, docs):
        return "\n\n".join(doc.page_content for doc in docs)

    def rag_prompt(self):
        text = """\
        You are an assistant for question-answering tasks,
        researching information about companies that are potential employers
        for the asker.
        Use the following pieces of retrieved context to answer the question.
        The question will include directions about formatting the output
        and how to respond if you don't know the answer.
        Question: {question} 
        Context: {context} 
        Answer:"""
        return ChatPromptTemplate([text], input_variables=["context", "question"])

    def invoke_and_get_dict(self, prompt: str, data: dict|None = None) -> dict:
        data = data or self.data
        prompt_template = ChatPromptTemplate.from_template(prompt)
        retriever = self.vectorstore.as_retriever()
        rag_prompt = self.rag_prompt()

        rag_chain = (
            {"context": retriever | self.format_docs, "question": RunnablePassthrough()}
            | rag_prompt
            | self.model
        )
        if self.use_parser:
            rag_chain = rag_chain | self.parser

        result = rag_chain.invoke(prompt_template.format(**data))

        # The result should already be a CompanyInfo object
        if isinstance(result, CompanyInfo):
            return result.model_dump()
        elif isinstance(result, dict):
            return result
        else:
            raise ValueError(
                f"Unexpected result type: {type(result)}. Expected CompanyInfo or dict."
            )

    def find_company_name(self):
        result = self.invoke_and_get_dict(
            "What is the name of the company at this URL? "
            'You must always output a valid JSON object with a "company" key. '
            " If unknown, set it to null."
            "{url}"
        )
        self.data.update(result)

    def find_funding_status(self):
        result = self.invoke_and_get_dict(
            "What is the funding status of {company} at {url}? "
            'You must always output a valid JSON object with a "funding_status" key. '
            'The value must be one of "public", "private", "unicorn", "private finance". '
            '"unicorn" means a private company valued at over $1 billion US. '
            '"private finance" means a private company that works primarily on fintech or other financial services. '
            "If unknown, set it to null. "
            "{company} {url}"
        )
        self.data.update(result)

    def find_headcounts(self):
        result = self.invoke_and_get_dict(
            "What are the headcounts of {company} at {url}? "
            "Look for information about the number of employees, "
            "the number of engineers, and the number of employees in NYC. "
            "You must always output a valid JSON object with the following keys: "
            '"total_employees", "total_engineers", "nyc_employees". '
            "The values must be integers, or null if unknown. "
            "{company} {url}"
        )
        self.data.update(result)

    def find_mission(self):
        result = self.invoke_and_get_dict(
            "What is the mission of {company} at {url}? "
            'You must always output a valid JSON object with a "mission" key. '
            "Set it to null if unknown. "
            "{company} {url}"
        )
        self.data.update(result)

    def find_work_policy(self):
        result = self.invoke_and_get_dict(
            "What is the remote work policy of {company} at {url}? "
            'You must always output a valid JSON object with the key "work_policy". '
            'The value must be one of "remote", "hybrid", "onsite", or null if cannot be determined. '
            "{company} {url}"
        )
        self.data.update(result)

    def main(self) -> dict:
        self.find_company_name()
        self.find_funding_status()
        self.find_headcounts()
        self.find_mission()
        self.find_work_policy()
        return self.data


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
# - the URLs of the pages that contain the information above
# """

FUNDING_STATUS_PROMPT = """
 - the company's latest valuation, in millions of dollars, if known.
 - the company's public/private status.  If private and valued at over $1B, call it a "unicorn".
 - the most recent funding round (eg "Series A", "Series B", etc.) if private.
"""
BASIC_COMPANY_FORMAT_PROMPT = """
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
For the company at {company_url}, find:
    - the company's remote work policy
    - whether the company is currently hiring backend engineers
    - whether the company is hiring backend engineers with AI experience
    - whether engineers are expected to do a systems design interview
    - whether engineers are expected to do a leetcode style coding interview
    - the URL of the company's primary jobs page, preferably on their own website, if known.
    - the URLs of the pages that contain the information above
"""

EMPLOYMENT_FORMAT_PROMPT = """
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
    EMPLOYMENT_PROMPT,
    AI_MISSION_PROMPT,
]

COMPANY_PROMPTS_WITH_FORMAT_PROMPT = [
    (BASIC_COMPANY_PROMPT, BASIC_COMPANY_FORMAT_PROMPT),
    (EMPLOYMENT_PROMPT, EMPLOYMENT_FORMAT_PROMPT),
    (AI_MISSION_PROMPT, AI_MISSION_FORMAT_PROMPT),
]

class TavilyResearchAgent:

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

    def single_search(self, query: str):
        result = self.agent_chain.invoke(query)
        return result["output"]

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

    def main(self, url: str):
        data = {}
        for prompt, format_prompt in COMPANY_PROMPTS_WITH_FORMAT_PROMPT:
            prompt = self.make_prompt(prompt, format_prompt, company_url=url)
            result = self.single_search(prompt)
            data.update(result)
        return data


class TavilyRAGResearchAgent(TavilyResearchAgent):

    def main(self, url: str) -> dict:

        tavily_client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])

        data = {}
        for prompt, format_prompt in COMPANY_PROMPTS_WITH_FORMAT_PROMPT:
            prompt = prompt.format(company_url=url)
            if len(prompt) > GET_SEARCH_CONTEXT_LIMIT:
                logger.warning(
                    f"Truncating prompt from {len(prompt)} to {GET_SEARCH_CONTEXT_INPUT_LIMIT} characters"
                )
                prompt = prompt[:GET_SEARCH_CONTEXT_INPUT_LIMIT]
                logger.debug(f"Prompt truncated: {prompt}")
            else:
                logger.debug(f"Prompt not truncated: {prompt}")

            context = tavily_client.get_search_context(
                query=prompt, max_tokens=1000 * 10
            )
            logger.debug(f"  Got Context: {len(context)}")
            full_prompt = self.make_prompt(prompt, format_prompt, extra_context=context)
            logger.debug(f"  Full prompt:\n\n {full_prompt}\n\n")
            result = self.llm.invoke(full_prompt)
            data.update(result)
            break
        return data


def main(url, model, refresh_rag_db: bool = False, verbose: bool = False):
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
