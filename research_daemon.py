import logging
import signal
import time
import models
import argparse
from logsetup import setup_logging

import libjobsearch
from tasks import TaskStatus, task_manager

logger = logging.getLogger(__name__)


class ResearchDaemon:

    def __init__(
        self, args: argparse.Namespace, cache_settings: libjobsearch.CacheSettings
    ):
        self.running = False
        self.task_mgr = task_manager()
        self.company_repo = models.company_repository()
        self.jobsearch = libjobsearch.JobSearch(
            args, loglevel=logging.DEBUG
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
        # Use the task manager's connection settings
        row = self.task_mgr.get_next_pending_task()

        if row:
            task_id, company_name = row
            try:
                logger.info(f"Processing task {task_id} for {company_name}")
                self.task_mgr.update_task(task_id, TaskStatus.RUNNING)
                self.do_research(company_name)
                self.task_mgr.update_task(
                    task_id, TaskStatus.COMPLETED, result={"some": "data"}
                )
                logger.info(f"Task {task_id} completed")

            except Exception as e:
                logger.exception(f"Task {task_id} failed")
                self.task_mgr.update_task(task_id, TaskStatus.FAILED, error=str(e))

    def do_research(self, company_name: str):
        existing = self.company_repo.get(company_name)
        content = company_name
        if existing:
            if existing.initial_message:
                content = existing.initial_message
                logger.info(f"Using existing initial message: {content[:400]}")
            # TODO: Update existing company
            logger.info(f"Company {company_name} already exists")
            self.company_repo.delete(existing.name)
        logger.info(f"Creating company {company_name}")
        # TODO: Pass more context from email, etc.
        MODEL = "claude-3-5-sonnet-latest"  # TODO: Make this configurable
        company_row = self.jobsearch.research_company(content, model=MODEL)
        company = models.Company(name=company_name, details=company_row)
        self.company_repo.create(company)


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
