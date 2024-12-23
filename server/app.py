from datetime import date, datetime
from pyramid.config import Configurator
from pyramid.response import Response
from pyramid.view import view_config
from pyramid.scripts.pserve import PServeCommand
import os
import json

from companies_spreadsheet import CompaniesSheetRow


class Company:
    def __init__(
        self, name: str, details: CompaniesSheetRow, initial_message: str | None = None
    ):
        self.name = name
        self.details = details
        self.initial_message = initial_message
        self.reply_message = ""


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
    return {
        "name": company.name,
        "initial_message": company.initial_message,
        "reply_message": company.reply_message,  # Add this line
        "details": {
            k: (v.isoformat() if isinstance(v, date) else v)
            for k, v in company.details.model_dump().items()
            if v is not None
        },
    }


@view_config(route_name="companies", renderer="json", request_method="GET")
def get_companies(request):
    companies = [serialize_company(company) for company in SAMPLE_COMPANIES]
    return companies


@view_config(route_name="home")
def home(request):
    # Read and return the index.html file
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, 'static', 'index.html')) as f:
        return Response(f.read(), content_type="text/html")


@view_config(route_name="generate_message", renderer="json", request_method="POST")
def generate_message(request):
    company_name = request.matchdict["company_name"]
    # For now, just return a hardcoded message with timestamp
    return {"message": f"generated reply {company_name} {datetime.now().isoformat()}"}


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
        config.add_route("generate_message", "/api/{company_name}/generate_message")
        config.add_static_view(name='static', path='static')
        config.scan()

        return config.make_wsgi_app()


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    config_file = os.path.join(os.path.dirname(here), "development.ini")
    print(f"Looking for config file at: {config_file}")
    if not os.path.exists(config_file):
        print(f"Config file not found at {config_file}")
    else:
        print(f"Found config file at {config_file}")
    cmd = PServeCommand(["pserve", config_file])
    cmd.run()
