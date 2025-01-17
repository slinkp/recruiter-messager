#!/Users/paul/src/finance/.direnv/python-3.12/bin/python

# Standard library imports
import abc
import argparse
import dataclasses
import datetime
import functools
import logging
import os
import os.path
import sys
from decimal import Decimal
from typing import Any, Iterable, Optional

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

import models

# Constants
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

FIRST_DATA_ROW = 2  # 0-indexed


# Configure logging
logger = logging.getLogger(__name__)

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


FIRST_DATA_ROW = 2  # 0-indexed


@functools.cache
def authorize() -> Credentials:
    creds: Optional[Credentials] = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    scriptname: str = os.path.realpath(__file__)
    dirname: str = os.path.dirname(scriptname)
    credfile: str = "token.json"
    os.chdir(dirname)
    if os.path.exists(credfile):
        creds = Credentials.from_authorized_user_file(credfile, SCOPES)

    # If there are no (valid) credentials available, let the user log in.
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        logger.info("Refreshing expired credentials")
        try:
            creds.refresh(Request())
            assert creds.valid
            return creds
        except RefreshError:
            logger.error("Refreshing failed")
            pass

    logger.info("New credentials needed, forcing auth via browser")
    flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
    creds = flow.run_local_server(port=0)

    assert creds is not None and creds.valid
    # Save the credentials for the next run
    with open("token.json", "w") as token:
        token.write(creds.to_json())
    return creds


def checksum(line: list[str]):
    import hashlib

    md5 = hashlib.md5()
    md5.update("".join(line).encode("utf8"))
    checksum = md5.hexdigest()
    return checksum


class BaseImporter(abc.ABC):
    @abc.abstractmethod
    def generate_data_lines(self) -> Iterable[list[str]]:
        pass

    def __init__(self, prev_lines: list[Any] | None = None):
        pass


class CompaniesImporter(BaseImporter):
    """
    Importers are responsible for loading data eg. from a file,
    parsing the data, and finding new lines (that don't match prev_lines).

    generate_data_lines() is the entry point for this.
    """

    reverse_cron = True  # Default value, can be overridden in subclasses

    def __init__(self, prev_lines: list[models.CompaniesSheetRow] | None = None):
        self.prev_lines = prev_lines or []
        self.seen_checksums = set()
        self.out_buffer = []
        self.update_seen_checksums()

    def generate_data_lines(self) -> Iterable[list[str]]:
        """
        Yields arrays of parsed line data.
        Skips lines that have a checksum that's already been seen.
        """
        for line in self.out_buffer:
            checksum = self.checksum_finder(line)
            if checksum and checksum in self.seen_checksums:
                continue
            self.seen_checksums.add(checksum)
            yield [str(item) for item in line]

    def checksum_finder(self, row: models.CompaniesSheetRow) -> str | None:
        parts = row.name.lower().split() if row.name else []
        return checksum(parts)

    def update_seen_checksums(self) -> None:
        for row in self.prev_lines:
            checksum = self.checksum_finder(row)
            if checksum:
                self.seen_checksums.add(checksum)


##############################################################################################
# Clients
#


@dataclasses.dataclass(kw_only=True)
class StubRow(models.BaseSheetRow):
    blah: str = "blahblah"
    fill_columns = tuple()
    sort_by_date_field = "blah"


class BaseGoogleSheetClient:
    """
    Base class for Google Sheet clients.
    Client classes are responsible for:
    - Delegating to an Importer to get new input data
    - Appending new rows to the Google Sheet
    - Ensuring the Google sheet is correctly sorted, data filled, empty rows cleaned up,
      and formatting preserved.

    Its behavior is configured by input args, and by declaring a concrete Importer class as `importer_class`
    and a BaseSheetRow subclass as `row_class`.

    main() is the entry point.
    """

    row_class: type[Any] = StubRow
    importer_class: type[BaseImporter] = BaseImporter

    def __init__(
        self,
        doc_id: str,
        sheet_id: str,
        range_name: str,
    ):
        self.doc_id = doc_id
        creds = authorize()
        self.range_name = range_name
        self.sheet_id = sheet_id
        self.service = build("sheets", "v4", credentials=creds)

    def main(self):
        logger.info(f"Importing to range {self.range_name}")
        new_rows = self.get_new_rows()
        self.append_rows(new_rows)
        self.cleanup_after_changes()

    def cleanup_after_changes(self):
        """
        Call this after adding or changing or clearing rows,
        or anytime the sheet is in a messy state.
        """
        # Order matters: If we sort before autofill, it apparently breaks autofill.
        self.fill_down()
        self.sort_by_date()
        self.delete_trailing_empty_rows()
        self.update_formatting()

    def delete_trailing_empty_rows(self):
        """
        Delete any rows at the bottom of the sheet that are empty
        (not counting values in filled balance columns).
        This must be done after sorting, to avoid deleting filled rows after
        an empty row.
        """
        # Get the sheet metadata to find the actual number of rows
        sheet_metadata = (
            self.service.spreadsheets()
            .get(
                spreadsheetId=self.doc_id,
                ranges=[self.range_name],
                fields="sheets(properties(sheetId,title,gridProperties))",
            )
            .execute()
        )

        sheet_properties = sheet_metadata["sheets"][0]["properties"]
        total_rows = sheet_properties["gridProperties"]["rowCount"]

        # Get the data for all rows
        result = (
            self.service.spreadsheets()
            .values()
            .get(
                spreadsheetId=self.doc_id,
                range=f"{self.range_name.split('!')[0]}!A{FIRST_DATA_ROW + 1}:Z{total_rows}",
            )
            .execute()
        )
        values = result.get("values", [])

        # Find the last non-empty row
        # but ignore values in filled balance columns
        last_non_empty_row = FIRST_DATA_ROW
        for i, row in enumerate(values, start=FIRST_DATA_ROW):
            for j, col in enumerate(row):
                if col.strip() and not self.row_class.is_filled_col_index(j):
                    logger.debug(
                        f"Row {i} column {j} is filled but not in fill_columns: {self.row_class.field_name(j)}"
                    )
                    last_non_empty_row = i
                    break
        # Delete the rest
        if last_non_empty_row < total_rows - 1:
            requests = [
                {
                    "deleteDimension": {
                        "range": {
                            "sheetId": self.sheet_id,
                            "dimension": "ROWS",
                            "startIndex": last_non_empty_row + 1,
                            "endIndex": total_rows,
                        }
                    }
                }
            ]
            self._batch_update(requests)
            logger.info(
                f"Deleted {total_rows - last_non_empty_row - 1} trailing empty rows."
            )
        else:
            logger.debug("No trailing empty rows to delete.")

    def append_rows(self, rows: list[list[str]]):
        """
        Add rows of data to the end of the sheet.
        """
        # See https://developers.google.com/sheets/api/guides/values#python_4
        # for example code.
        body = {
            "values": rows,
            "majorDimension": "ROWS",
            # range: range in a1 notation. Not needed though?
        }
        values = self.service.spreadsheets().values()
        result = values.append(
            spreadsheetId=self.doc_id,
            range=self.range_name,
            valueInputOption="USER_ENTERED",  # TODO: what's this?
            body=body,
        ).execute()
        logger.info(f"{len(rows)} rows appended.")

    def read_rows_from_google(self):
        values = self.service.spreadsheets().values()
        result = values.get(spreadsheetId=self.doc_id, range=self.range_name).execute()
        values = result.get("values", [])
        return [self.row_class.from_list(line) for line in values]

    def get_new_rows(self) -> list[list[str]]:
        prev_line_data = self.read_rows_from_google()
        importer = self.importer_class(prev_lines=prev_line_data)
        lines = list(importer.generate_data_lines())
        return lines

    def sort_by_date(self):
        # See https://developers.google.com/sheets/api/samples/data#sort-range
        date_col_index = self.row_class.sort_by_date_index()
        requests = [
            {
                "sortRange": {
                    "range": {
                        "sheetId": self.sheet_id,
                        "startRowIndex": FIRST_DATA_ROW,
                        "startColumnIndex": 0,
                    },
                    "sortSpecs": [
                        {
                            "dimensionIndex": date_col_index,
                            "sortOrder": "ASCENDING",
                        },
                    ],
                }
            }
        ]
        self._batch_update(requests)

    def update_formatting(self):
        # https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets/request#updateconditionalformatrulerequest
        sheets = self.service.spreadsheets()
        sheet = sheets.get(spreadsheetId=self.doc_id).execute()
        # We want the first tab
        tab = sheet["sheets"][0]
        formats = tab["conditionalFormats"]

        # Now we just push those back up, WITHOUT the row end index.
        requests = []
        for i, format_rule in enumerate(formats):
            for grid_range in format_rule["ranges"]:
                grid_range.pop("endRowIndex")
            requests.append(
                {
                    "updateConditionalFormatRule": {
                        "index": i,
                        "sheetId": self.sheet_id,
                        "rule": format_rule,
                    }
                }
            )
        self._batch_update(requests)

    def fill_down(self):
        # Autofill yay
        # https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets/request#autofillrequest
        requests = []
        fill_columns = self.row_class.fill_column_indices()
        for column in fill_columns:
            requests.append(
                {
                    "autoFill": {
                        "range": {
                            "sheetId": self.sheet_id,
                            "startRowIndex": FIRST_DATA_ROW,
                            # Leave out "endRowIndex" to mean "end of sheet".
                            "startColumnIndex": column,
                            "endColumnIndex": column + 1,  # Ends are exclusive.
                        },
                        "useAlternateSeries": False,
                    }
                }
            )
        self._batch_update(requests)

    def _batch_update(self, requests):
        body = {"requests": requests}
        request = self.service.spreadsheets().batchUpdate(
            spreadsheetId=self.doc_id, body=body
        )
        request.execute()

    def update_row_partial(
        self, row_index: int, cell_updates: dict[int, Any] | models.BaseSheetRow
    ):
        """Update specific cells in a row, leaving others untouched."""
        # TODO test this method
        range_name = f"{self.range_name.split('!')[0]}!"
        batch_data = []

        if isinstance(cell_updates, models.BaseSheetRow):
            cell_updates = dict(enumerate(cell_updates.as_list_of_str()))

        for col_index, value in cell_updates.items():
            # Convert non-JSON-serializable types to strings
            if isinstance(value, datetime.date):
                value = value.strftime("%Y-%m-%d")
            elif isinstance(value, Decimal):
                value = str(value)

            col_letter = self.column_letter(col_index)
            cell_range = f"{col_letter}{row_index + 1}"
            batch_data.append(
                {"range": f"{range_name}{cell_range}", "values": [[value]]}
            )

        body = {"valueInputOption": "USER_ENTERED", "data": batch_data}

        self.service.spreadsheets().values().batchUpdate(
            spreadsheetId=self.doc_id, body=body
        ).execute()

        logger.debug(f"Row {row_index + 1} partially updated.")

    @classmethod
    def column_letter(cls, n):
        """Convert a 0-based column number to A1 notation letter."""
        result = ""
        while n >= 0:
            n, remainder = divmod(n, 26)
            result = chr(65 + remainder) + result
            n -= 1
        return result

    def clear_row(self, row_index: int) -> None:
        """Clear a row in the spreadsheet."""
        # Get the sheet name from the range_name (everything before the !)
        sheet_name = self.range_name.split("!")[0]

        num_columns = len(self.row_class())
        end_col_index = num_columns - 1

        end_col = self.column_letter(end_col_index)

        # Format the range as "SheetName!A5:R5" for row 5
        range_name = f"{sheet_name}!A{row_index + 1}:{end_col}{row_index + 1}"
        empty_row = [""] * num_columns

        self.service.spreadsheets().values().update(
            spreadsheetId=self.doc_id,
            range=range_name,
            valueInputOption="RAW",
            body={"values": [empty_row]},
        ).execute()


class MainTabCompaniesClient(BaseGoogleSheetClient):
    row_class = models.CompaniesSheetRow
    importer_class = CompaniesImporter


#######################################################################
# Doc IDs, Tab IDs and data ranges.


class Config:
    # My companies sheet
    SHEET_DOC_ID = os.environ["SHEET_DOC_ID"]
    TAB_1_GID = os.environ["TAB_1_GID"]
    TAB_1_RANGE = os.environ["TAB_1_RANGE"]


class TestConfig(Config):
    # Separate spreadsheet for experimenting with new features
    SHEET_DOC_ID = os.environ["TEST_SHEET_DOC_ID"]
    TAB_1_GID = os.environ["TEST_TAB_1_GID"]
    TAB_1_RANGE = os.environ["TEST_TAB_1_RANGE"]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="Spreadsheeter",
        description="Imports data to my companies google sheet",
        epilog="",
    )

    parser.add_argument(
        "-d", "--dump", action="store_true", help="Dump the existing data to stdout"
    )
    parser.add_argument(
        "-s", "--sheet", action="store", choices=["test", "prod"], default="prod"
    )
    parser.add_argument(
        "-t", "--test-fake-row", action="store_true", help="Test adding a fake row"
    )

    return parser.parse_args(argv)


def main(argv: list[str]):
    args = parse_args(argv)

    config = TestConfig if args.sheet == "test" else Config

    main_client = MainTabCompaniesClient(
        doc_id=config.SHEET_DOC_ID,
        sheet_id=config.TAB_1_GID,
        range_name=config.TAB_1_RANGE,
    )

    if args.dump:
        for row in main_client.read_rows_from_google():
            print(row)
        return

    if args.test_fake_row:
        import uuid

        name = f"Test Company {uuid.uuid4()}"
        row = models.CompaniesSheetRow(
            name=name,
            updated=datetime.date.today(),
            base=Decimal(200),
            rsu=Decimal(100),
            leetcode=True,
            sys_design=True,
            ai_notes="Something something LLM",
        )
        main_client.append_rows([row.as_list_of_str()])
        print(f"Loaded row: {row}")
        return

    main_client.main()


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    main(sys.argv[1:])
