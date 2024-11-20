from collections import defaultdict
import os.path
import company_researcher
from rag import RecruitmentRAG
import email_client
import logging
import argparse
import json
import functools

logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))


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
    logger.info(f"Doing followup research on: {company_info}")
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


class EmailResponder:
    def __init__(
        self, reply_rag_model: str, reply_rag_limit: int, use_cache: bool, loglevel: int
    ):
        self.reply_rag_model = reply_rag_model
        self.reply_rag_limit = reply_rag_limit
        self.use_cache = use_cache
        self.loglevel = loglevel
        old_replies = self.load_previous_replies_to_recruiters()
        self.rag = self._build_reply_rag(old_replies)
        self.email_client = email_client.GmailRepliesSearcher()
        self.email_client.authenticate()

    def _build_reply_rag(
        self, old_messages: list[tuple[str, str, str]]
    ) -> RecruitmentRAG:  # Set up the RAG pipeline
        rag = RecruitmentRAG(old_messages, loglevel=self.loglevel)
        rag.prepare_data(clear_existing=not self.use_cache)
        rag.setup_chain(llm_type=self.reply_rag_model)
        logger.info(f"RAG setup complete")
        return rag

    def load_previous_replies_to_recruiters(self) -> list[tuple[str, str, str]]:
        cachefile = os.path.join(HERE, "processed_messages.json")
        old_replies = []
        if self.use_cache:
            try:
                with open(cachefile, "r") as f:
                    old_replies = json.load(f)
                    logger.info(f"Loaded {len(old_replies)} old replies from cache")
            except FileNotFoundError:
                logger.warning("No cache found, rebuilding...")
        if not old_replies:
            logger.info("Fetching my previous replies from mail...")
            old_replies = self.email_client.get_my_replies_to_recruiters(
                max_results=self.reply_rag_limit
            )
            logger.info(f"Got my replies from mail: {len(old_replies)}")
            with open(cachefile, "w") as f:
                json.dump(old_replies, f, indent=2)

        return old_replies

    def generate_reply(self, msg: str) -> str:
        return self.rag.generate_reply(msg)

    def get_new_recruiter_messages(
        self, max_results: int = 500
    ) -> list[tuple[str, str, str]]:
        messsage_dicts = self.email_client.get_new_recruiter_messages(
            max_results=max_results
        )
        # TODO: Move this to email_client.py
        # TODO: optionally cache it
        # TODO: solve for linkedin's failure to thread emails from DMs
        # TODO: solve for linkedin's stupidly threading "join your network" emails from different people

        # Combine messages in each thread
        content_by_thread = defaultdict(list)
        for msg in messsage_dicts:
            thread_id = msg["threadId"]
            content = self.email_client.extract_message_content(msg)
            content = self.email_client.clean_quoted_text(content)
            date = msg["internalDate"]
            content_by_thread[thread_id].append((date, content, msg))

        combined_messages = []
        for thread_id, msg_list in content_by_thread.items():
            # Sort a thread by date, oldest first.
            msg_list.sort(key=lambda x: x[0])
            combined_msg = msg_list[-1][-1].copy()  # Use the latest dict
            # Concatenate the text content of all messages in the thread
            combined_content = [mdict[1] for mdict in msg_list]
            if len(combined_content) > 1:
                for i, content in enumerate(combined_content):
                    logger.debug(f"Thread {thread_id} content {i}:\n{content[:200]}...")
            else:
                # HACK: For test purposes i'm only interested in combined messages
                continue

            combined_msg["combined_content"] = "\n\n".join(combined_content)
            combined_messages.append(combined_msg)

        logger.info(
            f"Got {len(messsage_dicts)} new recruiter messages in {len(combined_messages)} threads"
        )
        combined_messages.sort(key=lambda x: int(x["internalDate"]), reverse=True)
        return combined_messages


def main(args, loglevel: int = logging.INFO):
    email_responder = EmailResponder(
        reply_rag_model=args.model,
        reply_rag_limit=args.limit,
        use_cache=not args.no_cache,
        loglevel=loglevel,
    )
    # TODO: Read new recruiter email from gmail.
    # The email_client code doesn't have this yet.
    # It should combine multiple emails from the same recruiter.

    if args.test_messages:
        # TODO: These are just raw strings. Fake some dicts for them.
        new_recruiter_email = args.test_messages
    else:
        new_recruiter_email = email_responder.get_new_recruiter_messages()

    for msg in new_recruiter_email:
        # Log the subject
        content = msg.get("combined_content")
        logger.info(
            f"==============================\n\nProcessing message:\n\n{content}\n"
        )
        # TODO: pass subject too?
        company_info = initial_research_company(content)
        logger.info(f"Company info: {company_info}\n\n")
        reply = email_responder.generate_reply(content)
        logger.info(f"------ GENERATED REPLY:\n{reply}\n\n")
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
    parser.add_argument(
        "--model", action="store", choices=["openai", "claude"], default="claude"
    )
    parser.add_argument(
        "--limit",
        action="store",
        type=int,
        default=10,
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        default=False,
        help="Do not use cached messages from Gmail",
    )

    parser.add_argument(
        "--test-messages",
        action="append",
        help="Test messages to use instead of fetching from Gmail",
    )
    args = parser.parse_args()
    loglevel = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=loglevel)
    main(args, loglevel=loglevel)
