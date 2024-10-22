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

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain.output_parsers.json import SimpleJsonOutputParser


class Researcher:

    def __init__(self, url, model):
        self.url = url
        self.data = {'url': url}
        self.model = ChatOpenAI(
            model=model,
            model_kwargs={ "response_format": { "type": "json_object" } },
            )


    @property
    def parser(self):
        return SimpleJsonOutputParser()

    def invoke_and_get_dict(self, prompt: str, data: dict|None = None) -> dict:
        data = data or self.data
        prompt = ChatPromptTemplate.from_template(prompt)
        chain = prompt | self.model | self.parser
        # Consider using https://python.langchain.com/docs/concepts/#structured-output-tool-calling
        return chain.invoke(data)

    def find_company_name(self):
        result = self.invoke_and_get_dict(
            "What is the name of the company at this URL? "
            'You must always output a valid JSON object with a "company" key. '
            "{url}"
            )
        self.data.update(result)

    def find_funding_status(self):
        result = self.invoke_and_get_dict(
            "What is the funding status of {company} at {url}? "
            'You must always output a valid JSON object with a "funding_status" key. '
            'The value must be one of "public", "private", "unicorn", "private finance". '
            '"unicorn" means a private company valued at over $1 billion US. '
            "{company} {url}"
            )
        self.data.update(result)

    def find_more_urls(self):
        result = self.invoke_and_get_dict(
            "What are some other URLs for {company} at {url}? "
            "Look for all pages that contain information about careers, team, workplace, compensation, blog. "
            'You must always output a valid JSON object with a "urls" key. '
            'The value must be a list of strings. '
            "{company} {url}"
            )
        self.data.update(result)

    def find_headcounts(self):
        result = self.invoke_and_get_dict(
            "What are the headcounts of {company} at {url}? "
            "Possible other URLs to check: {urls} "
            'You must always output a valid JSON object with the following keys: '
            '"total_employees", "total_engineers", "nyc_employees". '
            "The values must be integers, or null if unknown. "
            "{company} {url}"
            )
        self.data["headcounts"] = result

    def find_mission(self):
        result = self.invoke_and_get_dict(
            "What is the mission of {company} at {url}? "
            "Possible other URLs to check: {urls} "
            'You must always output a valid JSON object with a "mission" key. '
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
        self.find_company_name()
        self.find_more_urls()
        self.find_funding_status()
        # self.find_headcounts()
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
    parser.add_argument("--model", help="OpenAI model to use", action="store", default="gpt-4o",
                        choices=["gpt-4o", "gpt-4o-turbo", "gpt-4-turbo", "gpt-3.5-turbo"])
    args = parser.parse_args()
    data = main(args.url, model=args.model)
    import pprint
    pprint.pprint(data)


# Vetting models:
# - gpt-4o:  status = unicorn, urls = careers, team, workplace, compensation, blog
# - gpt-4-turbo: status = private, urls = careers, about, blog
# Sometimes complain about being unable to open URLs.

