from collections import defaultdict
import os.path
import company_researcher
from rag import RecruitmentRAG
import email_client
import datetime
import logging
import argparse
import json
import functools
from diskcache import Cache
from functools import wraps
from enum import Enum, auto
from companies_spreadsheet import CompaniesSheetRow, MainTabCompaniesClient
import companies_spreadsheet
import decimal
import linkedin_searcher


logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))

cache = Cache(os.path.join(HERE, ".cache"))


class CacheStep(Enum):
    RAG_CONTEXT = auto()
    GET_MESSAGES = auto()
    BASIC_RESEARCH = auto()
    FOLLOWUP_RESEARCH = auto()
    REPLY = auto()

    def includes(self, other: "CacheStep") -> bool:
        return other.value <= self.value


def disk_cache(step: CacheStep):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, use_cache=True, clear_cache=False, **kwargs):
            if not use_cache:
                return func(*args, **kwargs)

            key = f"{func.__name__}:{str(args)}:{str(kwargs)}"

            if clear_cache:
                cache.delete(key)

            result = cache.get(key)
            if result is None:
                result = func(*args, **kwargs)
                cache.set(key, result)
            return result

        return wrapper

    return decorator


def should_cache_step(args, step: CacheStep) -> bool:
    if args.no_cache:
        return False
    if args.cache_until is None:
        return True
    return args.cache_until.includes(step)


def should_clear_cache(args, step: CacheStep) -> bool:
    if args.clear_all_cache:
        return True
    if not args.clear_cache:
        return False
    return step in args.clear_cache


@disk_cache(CacheStep.BASIC_RESEARCH)
def initial_research_company(message: str, model: str) -> CompaniesSheetRow:
    row = company_researcher.main(url_or_message=message, model=model, is_url=False)
    # TODO: Implement this:
    # - If there are attachments to the message (eg .doc or .pdf), extract the text from them
    #   and pass that to company_researcher.py too
    # - use levels_searcher.py to find salary data
    import levels_searcher

    now = datetime.datetime.now()
    logger.info("Firing up levels searcher ...")
    # TODO: handle case of company not found

    # equivalent_levels = list(levels_searcher.extract_levels(company_name=row.name))
    salary_data = list(levels_searcher.main(company_name=row.name))
    delta = datetime.datetime.now() - now
    logger.info(
        f"Got {len(salary_data)} rows of salary data for {row.name} in {delta.seconds} seconds"
    )

    if salary_data:
        # Calculate averages from all salary entries.
        # TODO: We don't actually want an average, we want the best fit.
        total_comps = [entry["total_comp"] for entry in salary_data]
        base_salaries = [entry["salary"] for entry in salary_data if entry["salary"]]
        equities = [entry["equity"] for entry in salary_data if entry["equity"]]
        bonuses = [entry["bonus"] for entry in salary_data if entry["bonus"]]

        row.total_comp = (
            decimal.Decimal(int(sum(total_comps) / len(total_comps)))
            if total_comps
            else None
        )
        row.base = (
            decimal.Decimal(int(sum(base_salaries) / len(base_salaries)))
            if base_salaries
            else None
        )
        row.rsu = (
            decimal.Decimal(int(sum(equities) / len(equities))) if equities else None
        )
        row.bonus = (
            decimal.Decimal(int(sum(bonuses) / len(bonuses))) if bonuses else None
        )
    else:
        logger.warning(f"No salary data found for {row.name}")

    # - Enhance the response with whether the company is a good fit for me
    # - Add the research to the RAG context for email generation
    return row


@disk_cache(CacheStep.FOLLOWUP_RESEARCH)
def followup_research_company(company_info: CompaniesSheetRow) -> CompaniesSheetRow:
    logger.info(f"Doing followup research on: {company_info}")

    linkedin_contacts = linkedin_searcher.main(company_info.name)[:4]
    company_info.maybe_referrals = "\n".join(
        [f"{c['name']} - {c['title']}" for c in linkedin_contacts]
    )
    return company_info


def is_good_fit(company_info: CompaniesSheetRow) -> bool:
    # TODO: basic heuristic for now
    return True


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
        logger.info("Initializing EmailResponder...")
        self.reply_rag_model = reply_rag_model
        self.reply_rag_limit = reply_rag_limit
        self.use_cache = use_cache
        self.loglevel = loglevel
        self.email_client = email_client.GmailRepliesSearcher()
        self.email_client.authenticate()
        old_replies = self.load_previous_replies_to_recruiters()
        self.rag = self._build_reply_rag(old_replies)
        logger.info("...EmailResponder initialized")

    def _build_reply_rag(
        self, old_messages: list[tuple[str, str, str]]
    ) -> RecruitmentRAG:  # Set up the RAG pipeline
        logger.info("Building RAG...")
        rag = RecruitmentRAG(old_messages, loglevel=self.loglevel)
        rag.prepare_data(clear_existing=not self.use_cache)
        rag.setup_chain(llm_type=self.reply_rag_model)
        logger.info(f"...RAG setup complete")
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
        logger.info("Generating reply...")
        result = self.rag.generate_reply(msg)
        logger.info("Reply generated")
        return result

    def get_new_recruiter_messages(
        self, max_results: int = 100
    ) -> list[tuple[str, str, str]]:
        logger.info(f"Getting {max_results} new recruiter messages")
        message_dicts = self.email_client.get_new_recruiter_messages(
            max_results=max_results
        )
        logger.debug(f" Email client got {len(message_dicts)} new recruiter messages")
        # TODO: Move this to email_client.py
        # TODO: optionally cache it
        # TODO: solve for linkedin's failure to thread emails from DMs
        # TODO: solve for linkedin's stupidly threading "join your network" emails from different people

        # Combine messages in each thread
        content_by_thread = defaultdict(list)
        for msg in message_dicts:
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

            combined_msg["combined_content"] = "\n\n".join(combined_content)
            combined_messages.append(combined_msg)

        combined_messages.sort(key=lambda x: int(x["internalDate"]), reverse=True)
        logger.info(
            f"Got {len(message_dicts)} new recruiter messages in {len(combined_messages)} threads"
        )
        return combined_messages


def add_company_to_spreadsheet(
    company_info: CompaniesSheetRow, args: argparse.Namespace
):
    logger.info(f"Adding company to spreadsheet: {company_info.name}")
    if args.sheet == "test":
        config = companies_spreadsheet.TestConfig
    else:
        config = companies_spreadsheet.Config
    client = MainTabCompaniesClient(
        doc_id=config.SHEET_DOC_ID,
        sheet_id=config.TAB_1_GID,
        range_name=config.TAB_1_RANGE,
    )

    # TODO: Check if the company already exists in the sheet, and update instead of appending
    client.append_rows([company_info.as_list_of_str()])
    logger.info(f"Added company to spreadsheet: {company_info.name}")


def main(args, loglevel: int = logging.INFO):
    email_responder = EmailResponder(
        reply_rag_model=args.model,
        reply_rag_limit=args.limit,
        use_cache=not args.no_cache,
        loglevel=loglevel,
    )
    if args.test_messages:
        new_recruiter_email = [
            {"combined_content": msg, "internalDate": "0"} for msg in args.test_messages
        ]
    else:
        new_recruiter_email = email_responder.get_new_recruiter_messages(
            max_results=args.limit
        )

    for i, msg in enumerate(new_recruiter_email):
        logger.info(f"Processing message {i+1} of {len(new_recruiter_email)}...")
        content = msg.get("combined_content").strip()
        if not content:
            logger.warning("Empty message, skipping")
            continue

        logger.info(
            f"==============================\n\nProcessing message:\n\n{content}\n"
        )
        # TODO: pass subject too?
        company_info = initial_research_company(
            content, model=args.model, use_cache=not args.no_cache
        )
        logger.debug(f"Company info after initial research: {company_info}\n\n")
        reply = email_responder.generate_reply(content)
        logger.info(f"------ GENERATED REPLY:\n{reply[:400]}\n\n")
        if is_good_fit(company_info):
            company_info = followup_research_company(company_info)

        reply = maybe_edit_reply(reply)
        send_reply(reply)
        archive_message(msg)
        add_company_to_spreadsheet(company_info, args)
        logger.info(f"Processed message {i+1} of {len(new_recruiter_email)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Print verbose logging"
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
        help="Do not use any caching",
    )

    parser.add_argument(
        "--cache-until",
        type=lambda s: CacheStep[s.upper()],
        choices=list(CacheStep),
        help="Cache steps up to and including this step (RAG_CONTEXT, GET_MESSAGES, RESEARCH, FOLLOWUP, REPLY)",
    )

    # Clear cache options
    parser.add_argument(
        "--clear-all-cache",
        action="store_true",
        help="Clear all cached data before running",
    )
    parser.add_argument(
        "--clear-cache",
        type=lambda s: CacheStep[s.upper()],
        choices=list(CacheStep),
        nargs="+",
        help="Clear cache for specific steps before running",
    )

    parser.add_argument(
        "--test-messages",
        action="append",
        help="Test messages to use instead of fetching from Gmail",
    )

    parser.add_argument(
        "-s",
        "--sheet",
        action="store",
        choices=["test", "prod"],
        default="prod",
        help="Use the test or production spreadsheet",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.INFO)
        logger.setLevel(logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)
        logger.setLevel(logging.INFO)

    # Clear all cache if requested (do this before any other operations)
    if args.clear_all_cache:
        logger.info("Clearing all cache...")
        cache.clear()

    main(args, loglevel=logger.level)
