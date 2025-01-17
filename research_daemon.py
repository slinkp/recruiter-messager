import argparse
import logging
import signal
import time

import libjobsearch
import models
from logsetup import setup_logging
from tasks import TaskManager, TaskStatus, TaskType, task_manager

logger = logging.getLogger(__name__)


class TaskStatusContext:

    def __init__(self, task_mgr: TaskManager, task_id: str, task_type: TaskType):
        self.task_mgr = task_mgr
        self.task_id = task_id
        self.task_type = task_type

    def __enter__(self):
        self.task_mgr.update_task(self.task_id, TaskStatus.RUNNING)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None:
            self.task_mgr.update_task(self.task_id, TaskStatus.COMPLETED)
        else:
            self.task_mgr.update_task(
                self.task_id, TaskStatus.FAILED, error=str(exc_value)
            )


class ResearchDaemon:

    def __init__(
        self, args: argparse.Namespace, cache_settings: libjobsearch.CacheSettings
    ):
        self.running = False
        self.task_mgr = task_manager()
        self.company_repo = models.company_repository()
        self.jobsearch = libjobsearch.JobSearch(
            args, loglevel=logging.DEBUG, cache_settings=cache_settings
        )

    def start(self):
        self.running = True
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)

        logger.info("Research daemon starting")
        while self.running:
            try:
                self.process_next_task()
                time.sleep(1)  # Polling interval
            except Exception:
                logger.exception("Error processing task")
                time.sleep(5)  # Back off on errors

    def stop(self, signum=None, frame=None):
        logger.info("Research daemon stopping")
        self.running = False

    def process_next_task(self):
        row = self.task_mgr.get_next_pending_task()

        if row:
            task_id, task_type, task_args = row
            logger.info(
                f"Processing task {task_id} of type {task_type} with args:\n{task_args}"
            )
            with TaskStatusContext(self.task_mgr, task_id, task_type):
                if task_type == TaskType.COMPANY_RESEARCH:
                    self.do_research(task_args)
                elif task_type == TaskType.GENERATE_REPLY:
                    self.do_generate_reply(task_args)
                else:
                    logger.error(f"Ignoring unsupported task type: {task_type}")
                logger.info(f"Task {task_id} completed")

    def do_research(self, args: dict):
        company_name = args["company_name"]
        existing = self.company_repo.get(company_name)
        content = company_name
        initial_message = None
        if existing:
            initial_message = existing.initial_message
            if initial_message:
                content = initial_message
                logger.info(f"Using existing initial message: {content[:400]}")
            # TODO: Update existing company
            logger.info(f"Company {company_name} already exists")
            self.company_repo.delete(existing.name)
        logger.info(f"Creating company {company_name}")
        # TODO: Pass more context from email, etc.
        MODEL = "claude-3-5-sonnet-latest"  # TODO: Make this configurable
        company_row = self.jobsearch.research_company(content, model=MODEL)
        company = models.Company(
            name=company_name,
            details=company_row,
            initial_message=initial_message,
        )
        self.company_repo.create(company)

    def do_generate_reply(self, args: dict):
        # TODO: Use LLM to generate reply
        assert "company_name" in args
        company = self.company_repo.get(args["company_name"])
        assert company is not None
        assert company.initial_message is not None
        logger.info(f"Generating reply for {args['company_name']}")
        # TODO: Include more company info context in reply args
        reply = self.jobsearch.generate_reply(company.initial_message)
        company.reply_message = reply
        self.company_repo.update(company)
        logger.info(f"Updated reply for {args['company_name']}")


if __name__ == "__main__":
    args = libjobsearch.arg_parser().parse_args()

    setup_logging(args.verbose)
    cache_args = libjobsearch.CacheSettings(
        clear_all_cache=args.clear_all_cache,
        clear_cache=args.clear_cache,
        cache_until=args.cache_until,
        no_cache=args.no_cache,
    )
    daemon = ResearchDaemon(args, cache_settings=cache_args)
    daemon.start()
