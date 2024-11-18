import company_researcher
import rag
import email_client
import logging
import argparse

logger = logging.getLogger(__name__)


def initial_research_company(message: str) -> company_researcher.CompanyInfo:
    # TODO: Implement this:
    # - Enhance company_researcher.py to work with a blob of data (not just a company name)
    # - If there are attachments to the message (eg .doc or .pdf), extract the text from them
    #   and pass that to company_researcher.py too
    # - Use company_researcher.py to research the company, if possible
    # - use levels_searcher.py to find salary data
    # - Enhance the response with whether the company is a good fit for me
    # - Add the research to the RAG context
    # - Add the structured research data to my spreadsheet
    # - TBD:Maybe we just return CompanyInfo? And all the other stuff is done elsewhere?
    return company_researcher.CompanyInfo()


def followup_research_company(company_info: company_researcher.CompanyInfo):
    # TODO: Implement this:
    # - use linkedin_searcher.py to find contacts
    # - Store those somewhere.  Where? Spreadsheet - update existing row?
    return company_info


def is_good_fit(company_info: company_researcher.CompanyInfo):
    # TODO: basic heuristic for now
    return False


def send_reply(reply: str):
    # TODO: Implement this
    pass


def maybe_edit_reply(reply: str):
    # TODO:
    # Leverage EDITOR similar to how git commit does
    return reply


def archive_message(msg: str):
    # TODO: re-label the message AND my reply in the archive label
    # TODO: maybe if it's a good fit, we make a new label for that company?
    # eh, probably leave that manual for now.
    # TODO: add that reply to the RAG context
    pass


def main():
    # Build RAG context from recruiter replies
    processed_messages = email_client.get_recruiter_replies()
    recruiter_rag = rag.RecruitmentRAG(processed_messages)

    # TODO: Read new recruiter email from gmail.
    # The email_client code doesn't have this yet.
    # It should combine multiple emails from the same recruiter.

    new_recruiter_email = []
    for msg in new_recruiter_email:
        company_info = initial_research_company(msg)
        reply = recruiter_rag.get_reply(msg)
        logger.info(reply)
        if is_good_fit(company_info):
            company_info = followup_research_company(company_info)

        reply = maybe_edit_reply(reply)
        send_reply(reply)
        archive_message(msg)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Print verbose logging"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    main()
