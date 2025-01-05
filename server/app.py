from datetime import date, datetime
from pyramid.config import Configurator
from pyramid.response import Response
from pyramid.view import view_config
from pyramid.scripts.pserve import PServeCommand
import os
import json
from pydantic import BaseModel
from typing import Dict, List, Optional


import logging
from colorama import Fore, Style
import colorama
from pyramid.renderers import JSON

import models
import tasks


class ColoredFormatter(logging.Formatter):
    COLORS = {
        "DEBUG": Fore.CYAN,
        "INFO": Fore.GREEN,
        "WARNING": Fore.YELLOW,
        "ERROR": Fore.RED,
        "CRITICAL": Fore.RED + Style.BRIGHT,
    }

    def format(self, record):
        # Save original levelname
        orig_levelname = record.levelname
        # Color the levelname
        color = self.COLORS.get(record.levelname, "")
        record.levelname = f"{color}{record.levelname}{Style.RESET_ALL}"

        # Color the name and message differently for different loggers
        if record.name.startswith("pyramid"):
            record.name = f"{Fore.MAGENTA}{record.name}{Style.RESET_ALL}"
        else:
            record.name = f"{Fore.BLUE}{record.name}{Style.RESET_ALL}"

        # Format with colors
        result = super().format(record)
        # Restore original levelname
        record.levelname = orig_levelname
        return result


def setup_colored_logging():
    # Initialize colorama
    colorama.init()

    # Set up handler with our custom formatter
    handler = logging.StreamHandler()
    handler.setFormatter(ColoredFormatter("%(levelname)-8s %(name)s: %(message)s"))

    # Configure root logger
    root_logger = logging.getLogger()
    # Remove any existing handlers
    for h in root_logger.handlers[:]:
        root_logger.removeHandler(h)
    # Add our handler
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)


# Get our application logger
logger = logging.getLogger(__name__)


@view_config(route_name="companies", renderer="json", request_method="GET")
def get_companies(request):
    companies = models.company_repository().get_all()
    return [models.serialize_company(company) for company in companies]


@view_config(route_name="home")
def home(request):
    # Read and return the index.html file
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, 'static', 'index.html')) as f:
        return Response(f.read(), content_type="text/html")


def create_stub_message(company_name: str) -> str:
    return f"generated reply {company_name} {datetime.now().isoformat()}"


@view_config(route_name="generate_message", renderer="json", request_method="POST")
def generate_message(request):
    company_name = request.matchdict["company_name"]
    message = create_stub_message(company_name)
    logger.info(f"Generated message for {company_name}: {message}")
    return {"message": message}


@view_config(route_name="generate_message", renderer="json", request_method="PUT")
def update_message(request):
    company_name = request.matchdict["company_name"]
    try:
        body = request.json_body
        message = body.get("message")
        if not message:
            request.response.status = 400
            return {"error": "Message is required"}

        company = models.company_repository().get(company_name)
        if not company:
            request.response.status = 404
            return {"error": "Company not found"}

        company.reply_message = message
        models.company_repository().update(company)

        logger.info(f"Updated message for {company_name}: {message}")
        return models.serialize_company(company)
    except json.JSONDecodeError:
        request.response.status = 400
        return {"error": "Invalid JSON"}


@view_config(route_name="research", renderer="json", request_method="POST")
def research_company(request):
    company_name = request.matchdict["company_name"]
    company = models.company_repository().get(company_name)

    if not company:
        request.response.status = 404
        return {"error": "Company not found"}

    # Create a new task
    task_id = tasks.task_manager().create_task(company_name)
    logger.info(f"Research requested for {company_name}, task_id: {task_id}")

    return {"task_id": task_id, "status": tasks.TaskStatus.PENDING.value}


@view_config(route_name="research_status", renderer="json", request_method="GET")
def get_research_status(request):
    task_id = request.matchdict["task_id"]
    task = tasks.task_manager().get_task(task_id)

    if not task:
        request.response.status = 404
        return {"error": "Task not found"}

    return task


def main(global_config, **settings):
    with Configurator(settings=settings) as config:
        # Enable debugtoolbar for development
        config.include("pyramid_debugtoolbar")

        # Static files configuration
        here = os.path.dirname(os.path.abspath(__file__))
        static_path = os.path.join(here, 'static')

        # Create static directory if it doesn't exist
        if not os.path.exists(static_path):
            os.makedirs(static_path)

        # Routes
        config.add_route('home', '/')
        config.add_route('companies', '/api/companies')
        config.add_route("generate_message", "/api/{company_name}/reply_message")
        config.add_route("research", "/api/{company_name}/research")
        config.add_route("research_status", "/api/research/{task_id}")
        config.add_static_view(name='static', path='static')
        config.scan()

        setup_colored_logging()

        # Initialize repository
        models.company_repository()

        # Configure JSON renderer to use our custom encoder
        config.add_renderer(
            "json",
            JSON(
                serializer=lambda v, **kw: json.dumps(v, cls=models.CustomJSONEncoder)
            ),
        )

        return config.make_wsgi_app()


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    config_file = os.path.join(os.path.dirname(here), "development.ini")
    if not os.path.exists(config_file):
        raise Exception(f"Config file not found at {config_file}")

    cmd = PServeCommand(["pserve", config_file])
    cmd.run()
