import argparse
import datetime
import decimal
import logging
import os
import os.path
import subprocess
import tempfile
from collections import defaultdict
from enum import IntEnum
from functools import wraps
from multiprocessing import Process, Queue
import re

from diskcache import Cache
from colorama import Fore, Style

import companies_spreadsheet
import company_researcher
import email_client
import levels_searcher
import linkedin_searcher
from companies_spreadsheet import CompaniesSheetRow, MainTabCompaniesClient
from rag import RecruitmentRAG

logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))

cache = Cache(os.path.join(HERE, ".cache"))


class CacheStep(IntEnum):
    RAG_CONTEXT = 0
    GET_MESSAGES = 1
    BASIC_RESEARCH = 2
    FOLLOWUP_RESEARCH = 3
    REPLY = 4


class CacheSettings:
    no_cache = False
    clear_cache = None
    cache_until = None
    clear_all_cache = False

    def should_cache_step(self, step: CacheStep) -> bool:
        if self.no_cache:
            return False
        if self.cache_until is None:
            return True
        return self.cache_until >= step

    def should_clear_cache(self, step: CacheStep) -> bool:
        if self.clear_all_cache:
            return True
        if not self.clear_cache:
            return False
        return step in self.clear_cache


# TODO: Redesign this to not be global
cache_args = CacheSettings()

def disk_cache(step: CacheStep):

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            use_cache = cache_args.should_cache_step(step)
            clear_cache = cache_args.should_clear_cache(step)

            # Remove memory addresses from string representations
            args_str = re.sub(r" at 0x[0-9a-fA-F]+", "", str(args))
            kwargs_str = re.sub(r" at 0x[0-9a-fA-F]+", "", str(kwargs))
            key = f"{func.__name__}:{args_str}:{kwargs_str}"
            result = None

            if clear_cache:
                cache.delete(key)

            if use_cache:
                result = cache.get(key)
                if result is None:
                    logger.debug(f"Cache miss for {key}")
                else:
                    logger.debug(f"Cache hit for {key}")

            if result is None:
                logger.debug(f"No cached result, running function for {key}...")
                result = func(*args, **kwargs)
                logger.debug(f"... Ran function for {key}")
            if use_cache:
                cache.set(key, result)

            return result

        return wrapper

    return decorator


def process_wrapper(queue: Queue, func, args, kwargs):
    """Helper function to run a function in a process and put its result in a queue."""
    result = func(*args, **kwargs)
    queue.put(result)


def run_in_process(func, *args, **kwargs):
    """
    Run a function in a separate process and return its result.

    Args:
        func: The function to run
        *args, **kwargs: Arguments to pass to the function

    Returns:
        The result of running the function
    """
    result_queue = Queue()
    process = Process(target=process_wrapper, args=(result_queue, func, args, kwargs))
    process.start()
    process.join()
    return result_queue.get()


@disk_cache(CacheStep.BASIC_RESEARCH)
def initial_research_company(message: str, model: str) -> CompaniesSheetRow:
    logger.info("Starting initial research...")
    # TODO: Implement this:
    # - If there are attachments to the message (eg .doc or .pdf), extract the text from them
    #   and pass that to company_researcher.py too
    # - use levels_searcher.py to find salary data
    row = company_researcher.main(url_or_message=message, model=model, is_url=False)

    now = datetime.datetime.now()
    # TODO: handle case of company not found

    logger.info("Finding equivalent job levels ...")
    equivalent_levels = list(
        run_in_process(levels_searcher.extract_levels, row.name) or []
    )
    if equivalent_levels:
        row.level_equiv = ", ".join(equivalent_levels)
        delta = datetime.datetime.now() - now
        logger.info(
            f"Found equivalent job levels: {row.level_equiv} in {delta.seconds} seconds"
        )
    else:
        logger.info(f"No equivalent job levels found for {row.name}")

    logger.info("Finding salary data ...")
    now = datetime.datetime.now()
    salary_data = run_in_process(levels_searcher.main, company_name=row.name)
    if salary_data:
        salary_data = list(salary_data)  # Convert generator to list if needed

    delta = datetime.datetime.now() - now
    logger.info(
        f"Got {len(salary_data) if salary_data else 0} rows of salary data for {row.name} in {delta.seconds} seconds"
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

    return row


@disk_cache(CacheStep.FOLLOWUP_RESEARCH)
def followup_research_company(company_info: CompaniesSheetRow) -> CompaniesSheetRow:
    logger.info(f"Doing followup research on: {company_info}")

    linkedin_contacts = run_in_process(linkedin_searcher.main, company_info.name) or []
    linkedin_contacts = linkedin_contacts[:4]

    company_info.maybe_referrals = "\n".join(
        [f"{c['name']} - {c['title']}" for c in linkedin_contacts]
    )
    return company_info


def is_good_fit(company_info: CompaniesSheetRow) -> bool:
    # TODO: basic heuristic for now
    logger.info(f"Checking if {company_info.name} is a good fit...")
    return True


def send_reply(reply: str):
    # TODO: Implement this
    logger.info(f"Sending reply: {reply[:200]}...")
    pass


def maybe_edit_reply(reply: str) -> str:
    """
    Open reply text in user's preferred editor for optional modification.
    Similar to git commit message editing experience.
    """

    # Get editor from environment, defaulting to vim
    editor = os.environ.get("EDITOR", "vim")

    # Create temporary file with the reply text
    with tempfile.NamedTemporaryFile(mode="w+", suffix=".txt", delete=False) as tf:
        tf.write(reply)
        temp_path = tf.name

    try:
        logger.debug(f"Opening editor {editor} on {temp_path}...")
        # Split editor command to handle arguments properly
        editor_cmd = editor.split()

        # Open editor and wait for it to close
        result = subprocess.run(
            editor_cmd + [temp_path],
            check=True,
        )

        # Read potentially modified content
        with open(temp_path, "r") as f:
            edited_reply = f.read()
        logger.debug(f"...Editor returned {len(edited_reply)} chars")
        return edited_reply.strip()
    except subprocess.CalledProcessError as e:
        logger.error(f"Editor returned error: {e}")
        return reply  # Return original on error
    finally:
        # Clean up temporary file
        os.unlink(temp_path)


def archive_message(msg: str):
    # TODO: re-label the message AND my reply in the archive label
    # TODO: maybe if it's a good fit, we make a new label for that company?
    # eh, probably leave that manual for now.
    # TODO: add that reply to the RAG context
    logger.info(f"Archiving message")
    pass


class EmailResponder:

    def __init__(self, reply_rag_model: str, reply_rag_limit: int, loglevel: int):
        logger.info("Initializing EmailResponder...")
        self.reply_rag_model = reply_rag_model
        self.reply_rag_limit = reply_rag_limit
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
        # TODO: Granular cache control here.
        rag.prepare_data(clear_existing=cache_args.no_cache)
        rag.setup_chain(llm_type=self.reply_rag_model)
        logger.info(f"...RAG setup complete")
        return rag

    @disk_cache(CacheStep.GET_MESSAGES)
    def load_previous_replies_to_recruiters(self) -> list[tuple[str, str, str]]:
        logger.info("Fetching my previous replies from mail...")
        old_replies = self.email_client.get_my_replies_to_recruiters(
            max_results=self.reply_rag_limit
        )
        logger.info(f"Got my replies from mail: {len(old_replies)}")

        return old_replies

    def generate_reply(self, msg: str) -> str:
        logger.info("Generating reply...")
        result = self.rag.generate_reply(msg)
        logger.info("Reply generated")
        return result

    @disk_cache(CacheStep.GET_MESSAGES)
    def get_new_recruiter_messages(
        self, max_results: int = 100
    ) -> list[tuple[str, str, str]]:
        logger.info(f"Getting {max_results} new recruiter messages")
        message_dicts = self.email_client.get_new_recruiter_messages(
            max_results=max_results
        )
        logger.debug(f" Email client got {len(message_dicts)} new recruiter messages")
        # TODO: Move this to email_client.py
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
        loglevel=loglevel,
    )
    if args.test_messages:
        new_recruiter_email = [
            {"combined_content": msg, "internalDate": "0"} for msg in args.test_messages
        ]
    else:
        logger.debug("Getting new recruiter messages...")
        new_recruiter_email = email_responder.get_new_recruiter_messages(
            max_results=args.limit
        )
        logger.debug("...Got new recruiter messages")

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
        company_info = initial_research_company(content, model=args.model)
        logger.debug(f"Company info after initial research: {company_info}\n\n")
        generated_reply = email_responder.generate_reply(content)
        logger.info(f"------ GENERATED REPLY:\n{generated_reply[:400]}\n\n")
        if is_good_fit(company_info):
            company_info = followup_research_company(company_info)

        reply = maybe_edit_reply(generated_reply)
        logger.info(f"------ EDITED REPLY:\n{reply}\n\n")
        send_reply(reply)
        archive_message(msg)
        add_company_to_spreadsheet(company_info, args)
        logger.info(f"Processed message {i+1} of {len(new_recruiter_email)}")


class ColoredLogFormatter(logging.Formatter):
    """Custom formatter that adds colors based on log level"""

    COLORS = {
        logging.DEBUG: Fore.BLUE,
        logging.INFO: Fore.GREEN,
        logging.WARNING: Fore.YELLOW,
        logging.ERROR: Fore.RED,
        logging.CRITICAL: Fore.RED + Style.BRIGHT,
    }

    def format(self, record):
        # Add color to the level name
        color = self.COLORS.get(record.levelno, Fore.WHITE)
        record.levelname = f"{color}{record.levelname}{Style.RESET_ALL}"

        # Add color to the module name
        record.name = f"{Fore.CYAN}{record.name}{Style.RESET_ALL}"

        return super().format(record)


def setup_logging(args: argparse.Namespace):
    import colorama

    colorama.init()

    # Create console handler with custom formatter
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        ColoredLogFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
    )

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if args.verbose else logging.INFO)
    root_logger.addHandler(console_handler)

    # Configure this module's logger
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG if args.verbose else logging.INFO)


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
        help=f"Cache steps up to and including this step",
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

    setup_logging(args)
    # Clear all cache if requested (do this before any other operations)
    if args.clear_all_cache:
        logger.info("Clearing all cache...")
        cache.clear()
    # Update the global cache settings.
    cache_args.clear_all_cache = args.clear_all_cache
    cache_args.clear_cache = args.clear_cache
    cache_args.cache_until = args.cache_until
    cache_args.no_cache = args.no_cache

    main(args, loglevel=logger.level)