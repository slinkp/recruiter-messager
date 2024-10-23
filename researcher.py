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

import os
import re
import logging
from langchain_chroma import Chroma
from langchain_community.document_loaders import WebBaseLoader
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_anthropic import ChatAnthropic
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.prompts import ChatPromptTemplate
from langchain.output_parsers.json import SimpleJsonOutputParser
from typing import Optional, Literal, List
from pydantic import BaseModel, Field, field_validator

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")

logger = logging.getLogger(__name__)


class CompanyInfo(BaseModel):
    model_config = {
        "strict": True,
        "extra": "forbid",
    }

    company: Optional[str] = Field(description="The name of the company")
    funding_status: Optional[
        Literal["public", "private", "unicorn", "private finance"]
    ] = Field(description="The funding status of the company")
    mission: Optional[str] = Field(description="The mission of the company")
    work_policy: Optional[Literal["remote", "hybrid", "onsite"]] = Field(
        description="The work policy of the company"
    )
    total_employees: Optional[int] = Field(description="The total number of employees")
    total_engineers: Optional[int] = Field(description="The total number of engineers")
    nyc_employees: Optional[int] = Field(description="The number of employees in NYC")
    urls: Optional[List[str]] = Field(description="Additional URLs for the company")

    @field_validator("*", mode="before")
    @classmethod
    def handle_unknown(cls, v):
        if v == "<UNKNOWN>":
            return None
        return v


class Researcher:

    def __init__(self, url, model):
        self.url = url
        self.data = {'url': url}
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
        splits, ids = self.get_text_splits_from_urls(url)
        self.vectorstore = None
        self.populate_vector_db(splits, ids)

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

    def get_text_splits_from_urls(self, *urls: list[str]):
        logger.debug(f"Fetching and splitting contents of {urls}")
        loader = WebBaseLoader(web_paths=urls)
        docs = loader.load()
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000, chunk_overlap=200
        )
        splits = text_splitter.split_documents(docs)
        base_id = hash(tuple(urls))
        ids = []
        for i, split in enumerate(splits):
            _id = str(hash((base_id, i)))
            split.metadata["id"] = _id
            ids.append(_id)
        return splits, ids

    def populate_vector_db(self, splits, ids):
        embeddings = OpenAIEmbeddings(model="text-embedding-3-large")
        self.vectorstore = self.vectorstore or Chroma(
            collection_name=self.collection_name,
            embedding_function=embeddings,
            persist_directory=DATA_DIR,
        )
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
            "If unknown, set it to null. "
            "{company} {url}"
        )
        self.data.update(result)

    def find_more_urls(self) -> list[str]:
        result = self.invoke_and_get_dict(
            "What are some other URLs for the company at {url}? "
            "Look for all pages that contain information about careers, team, workplace, compensation, blog. "
            'You must always output a valid JSON object with a "urls" key. '
            "The value must be a list of strings. "
            "{url}"
        )
        self.data.update(result)
        return result["urls"]

    def update_vector_db_from_urls(self, urls: list[str]):
        logger.debug(f"  Getting text splits from more URLs: {urls}")
        splits, ids = self.get_text_splits_from_urls(*urls)
        logger.debug(f"  Updating vector database with {len(splits)} new splits")
        self.populate_vector_db(splits, ids)

    def find_headcounts(self):
        result = self.invoke_and_get_dict(
            "What are the headcounts of {company} at {url}? "
            "Possible other URLs to check: {urls} "
            "You must always output a valid JSON object with the following keys: "
            '"total_employees", "total_engineers", "nyc_employees". '
            "The values must be integers, or null if unknown. "
            "{company} {url} {urls}"
        )
        self.data.update(result)

    def find_mission(self):
        result = self.invoke_and_get_dict(
            "What is the mission of {company} at {url}? "
            "Possible other URLs to check: {urls} "
            'You must always output a valid JSON object with a "mission" key. '
            "Set it to null if unknown. "
            "{company} {url} {urls}"
        )
        self.data.update(result)

    def find_work_policy(self):
        result = self.invoke_and_get_dict(
            "What is the remote work policy of {company} at {url}? "
            "Possible other URLs to check: {urls} "
            'You must always output a valid JSON object with the key "work_policy". '
            'The value must be one of "remote", "hybrid", "onsite", or null if cannot be determined. '
            "{company} {url} {urls}"
            )
        self.data.update(result)

    def main(self) -> dict:
        urls = self.find_more_urls()
        # TODO only update vector db if there are new URLs
        self.update_vector_db_from_urls(urls)
        self.find_company_name()
        self.find_funding_status()
        self.find_headcounts()
        self.find_mission()
        self.find_work_policy()
        return self.data


def main(url, model):
    researcher = Researcher(url, model)
    return researcher.main()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="URL of the company to research")
    parser.add_argument(
        "--model",
        help="AI model to use",
        action="store",
        default="gpt-4o",
        choices=[
            "gpt-4o",
            "gpt-4o-turbo",
            "gpt-4-turbo",
            "gpt-3.5-turbo",
            "claude-3-5-sonnet-latest",
            "claude-3-haiku-latest",
        ],
    )
    parser.add_argument("--verbose", action="store_true")

    args = parser.parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    data = main(args.url, model=args.model)
    import pprint
    pprint.pprint(data)


# Vetting models:
# - gpt-4o:  status = unicorn, urls = careers, team, workplace, compensation, blog
# - gpt-4-turbo: status = private, urls = careers, about, blog
# Sometimes complain about being unable to open URLs.
