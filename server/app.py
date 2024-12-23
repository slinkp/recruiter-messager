from datetime import date
from pyramid.config import Configurator
from pyramid.response import Response
from pyramid.view import view_config
from pyramid.scripts.pserve import PServeCommand
import os

from companies_spreadsheet import CompaniesSheetRow

# Sample data (same as before)
SAMPLE_COMPANIES = [
    CompaniesSheetRow(
        name="TechCorp AI",
        type="Startup",
        valuation="1B",
        funding_series="Series B",
        url="https://techcorp.ai",
        current_state="Active",
        updated=date(2024, 3, 15),
        eng_size=50,
        total_size=120,
        headquarters="San Francisco",
        remote_policy="Hybrid"
    ),
    CompaniesSheetRow(
        name="DataDrive Systems",
        type="Public",
        valuation="10B",
        url="https://datadrive.com",
        current_state="Active",
        updated=date(2024, 3, 10),
        eng_size=500,
        total_size=2000,
        headquarters="New York",
        remote_policy="Remote First"
    )
]

@view_config(route_name='companies', renderer='json', request_method='GET')
def get_companies(request):
    companies = [
        {
            k: (v.isoformat() if isinstance(v, date) else v)
            for k, v in company.model_dump().items()
            if v is not None
        }
        for company in SAMPLE_COMPANIES
    ]
    return companies


@view_config(route_name="home")
def home(request):
    # Read and return the index.html file
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, 'static', 'index.html')) as f:
        return Response(f.read(), content_type="text/html")


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
        config.add_static_view(name='static', path='static')
        config.scan()

        return config.make_wsgi_app()


if __name__ == "__main__":
    cmd = PServeCommand(["development.ini", "--reload"])
    cmd.run()
