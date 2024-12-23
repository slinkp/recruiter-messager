from datetime import date, datetime
from pyramid.config import Configurator
from pyramid.response import Response
from pyramid.view import view_config
from pyramid.scripts.pserve import PServeCommand
import os
import json
from pydantic import BaseModel
from typing import Dict, List, Optional

from companies_spreadsheet import CompaniesSheetRow

import logging
from colorama import Fore, Style
import colorama


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


class Company(BaseModel):
    name: str
    details: CompaniesSheetRow
    initial_message: Optional[str] = None
    reply_message: str = ""


class CompanyRepository:
    def __init__(self):
        self._companies: Dict[str, Company] = {
            company.name: company for company in SAMPLE_COMPANIES
        }

    def get(self, name: str) -> Optional[Company]:
        logger.info(f"Getting company {name}")
        return self._companies.get(name)

    def get_all(self) -> List[Company]:
        logger.info(f"Getting all companies")
        return list(self._companies.values())

    def create(self, company: Company) -> Company:
        if company.name in self._companies:
            raise ValueError(f"Company {company.name} already exists")
        logger.info(f"Creating and saving company {company.name}")
        self._companies[company.name] = company
        return company

    def update(self, company: Company) -> Company:
        if company.name not in self._companies:
            raise ValueError(f"Company {company.name} not found")
        logger.info(f"Updating company {company.name}")
        self._companies[company.name] = company
        return company

    def delete(self, name: str) -> None:
        if name not in self._companies:
            raise ValueError(f"Company {name} not found")
        logger.info(f"Deleting company {name}")
        del self._companies[name]


# Sample data (same as before)
SAMPLE_COMPANIES = [
    Company(
        name="Shopify",
        details=CompaniesSheetRow(
            name="Shopify",
            type="Public",
            valuation="10B",
            url="https://shopify.com",
            current_state="Active",
            updated=date(2024, 12, 15),
            eng_size=4000,
            total_size=10000,
            headquarters="Ottawa",
            remote_policy="Remote",
        ),
        initial_message="Hi Paul, are you interested in working as a staff developer at Shopify? Regards, Bobby Bobberson",
    ),
    Company(
        name="Rippling",
        details=CompaniesSheetRow(
            name="Rippling",
            type="Private Unicorn",
            valuation="1500M",
            url="https://rippling.com",
            current_state="Active",
            updated=date(2024, 10, 10),
            headquarters="New York",
        ),
        initial_message="Hi Paul! Interested in a senior backend role at Rippling? - Mark Marker",
    ),
]


def serialize_company(company: Company):
    data = company.model_dump()
    data["details"] = {
        k: (v.isoformat() if isinstance(v, date) else v)
        for k, v in company.details.model_dump().items()
        if v is not None
    }
    return data


# Module-level singleton storage
_company_repository = None


def company_repository() -> CompanyRepository:
    global _company_repository
    if _company_repository is None:
        _company_repository = CompanyRepository()
    return _company_repository


@view_config(route_name="companies", renderer="json", request_method="GET")
def get_companies(request):
    companies = company_repository().get_all()
    return [serialize_company(company) for company in companies]


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

        company = company_repository().get(company_name)
        if not company:
            request.response.status = 404
            return {"error": "Company not found"}

        company.reply_message = message
        company_repository().update(company)

        logger.info(f"Updated message for {company_name}: {message}")
        return {"message": message}
    except json.JSONDecodeError:
        request.response.status = 400
        return {"error": "Invalid JSON"}


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
        config.add_static_view(name='static', path='static')
        config.scan()

        setup_colored_logging()

        # Initialize repository
        company_repository()

        return config.make_wsgi_app()


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    config_file = os.path.join(os.path.dirname(here), "development.ini")
    if not os.path.exists(config_file):
        raise Exception(f"Config file not found at {config_file}")

    cmd = PServeCommand(["pserve", config_file])
    cmd.run()
