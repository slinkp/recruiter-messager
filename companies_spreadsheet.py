#!/Users/paul/src/finance/.direnv/python-3.12/bin/python

# Standard library imports
import abc
import argparse
import csv
import datetime
import decimal
import functools
import logging
import os
import os.path
import sys
from typing import Any, ClassVar, Generator, Iterator, Optional, Iterable

# Third-party imports
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from pydantic import BaseModel, Field, ValidationError, model_validator

# Constants
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

FIRST_DATA_ROW = 2  # 0-indexed


import dataclasses
import dateutil.parser
from typing import Generator, Optional, Union, Any, ClassVar, Iterator
import sys
import logging
from pydantic import BaseModel, Field, ValidationError, model_validator
from decimal import Decimal

# Configure logging
logger = logging.getLogger(__name__)
handler = logging.StreamHandler()


class CustomFormatter(logging.Formatter):
    def format(self, record):
        if record.levelno == logging.INFO:
            return record.getMessage()
        return f"{record.levelname}: {record.getMessage()}"


handler.setFormatter(CustomFormatter())
logger.addHandler(handler)
logger.setLevel(logging.INFO)

from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


FIRST_DATA_ROW = 2  # 0-indexed


class BaseSheetRow(BaseModel):
    """Base class for spreadsheet rows."""

    # Default values, subclasses should override

    # I can feel it, filling columns down and right, oh lord
    fill_columns: ClassVar[tuple[str, ...]] = tuple()
    sort_by_date_field: ClassVar[str] = ""

    model_config = {
        "from_attributes": True,
        "str_strip_whitespace": True,
        "coerce_numbers_to_str": False,
    }

    @model_validator(mode="before")
    @classmethod
    def normalize_base_fields(cls, data: Any) -> dict:
        """Pre-process fields before Pydantic validation"""
        if isinstance(data, dict):
            for field_name, field in cls.model_fields.items():
                # Hacky, is there a better way to handle eg Optional[date]?
                val = data.get(field_name)
                if "date" in str(field.annotation) and isinstance(val, str):
                    try:
                        data[field_name] = dateutil.parser.parse(data[field_name])
                    except (ValueError, ValidationError):
                        # TODO: only do this if optional
                        data[field_name] = None
                elif "bool" in str(field.annotation) and isinstance(val, str):
                    data[field_name] = (
                        val.strip().strip().lower() == "yes" if val else None
                    )
                elif "int" in str(field.annotation) and isinstance(val, str):
                    val = val.strip().replace(",", "")
                    val = val.split(".")[0]
                    data[field_name] = int(val) if val else None
                elif "Decimal" in str(field.annotation) and isinstance(val, str):
                    try:
                        data[field_name] = Decimal(val)
                    except decimal.InvalidOperation:
                        # TODO: only do this if optional
                        data[field_name] = None
        return data

    @classmethod
    def sort_by_date_index(cls) -> int:
        return cls.field_index(cls.sort_by_date_field)

    @classmethod
    def is_filled_col_index(cls, col_index: int) -> bool:
        """Check if a column should be filled down"""
        for fieldname in cls.fill_columns:
            if col_index == cls.field_index(fieldname):
                return True
        return False

    @classmethod
    def field_index(cls, field_name: str) -> int:
        """Get the index of a field in the row"""
        try:
            return list(cls.model_fields.keys()).index(field_name)
        except ValueError:
            raise ValueError(f"Field {field_name} not found")

    @classmethod
    def field_name(cls, index: int) -> str:
        """Get the name of a field by its index"""
        try:
            return list(cls.model_fields.keys())[index]
        except IndexError:
            raise IndexError(f"Field index {index} out of range")

    def iter_to_strs(self) -> Iterator[str]:
        """Iterate through fields as strings"""
        for field_name in self.model_fields.keys():
            value = getattr(self, field_name)
            yield str(value) if value is not None else ""

    def as_list_of_str(self) -> list[str]:
        """Convert row back to list of strings"""
        return list(self.iter_to_strs())

    def __len__(self) -> int:
        """Return the number of fields in the row"""
        return len(self.model_fields)

    def __str__(self) -> str:
        """Custom string representation showing only non-default values"""
        cls_name = self.__class__.__name__
        fields = []
        for name, field in self.model_fields.items():
            value = getattr(self, name)
            default = field.default
            if value != default:
                fields.append(f"{name}={value}")
        if fields:
            return f"{cls_name}({', '.join(fields)})"
        return f"{cls_name}()"

    @classmethod
    def fill_column_indices(cls) -> list[int]:
        """Get indices of columns that should be filled down"""
        return [
            idx
            for idx, field_name in enumerate(cls.model_fields)
            if field_name in cls.fill_columns
        ]

    @classmethod
    def from_list(cls, row_data: list[str]) -> "BaseSheetRow":
        """Convert a list of strings into a row instance"""
        field_names = [name for name in cls.model_fields.keys()]
        return cls(**dict(zip(field_names, row_data)))

    @property
    def company_identifier(self) -> str:
        if self.name and self.url:
            return f"{self.name} at {self.url}"
        elif self.name:
            return self.name
        elif self.url:
            return self.url
        return ""


class CompaniesSheetRow(BaseSheetRow):
    """
    Schema for the companies spreadsheet.
    Note, order of fields determines index of column in sheet!

    Also usable as a validated data model for company info.
    """
    name: Optional[str] = Field(default="")
    type: Optional[str] = Field(default="")
    valuation: Optional[str] = Field(default="")
    funding_series: Optional[str] = Field(default="")
    rc: Optional[bool] = Field(default=None)
    url: Optional[str] = Field(default="")

    current_state: Optional[str] = Field(default=None)  # TODO validate values
    updated: Optional[datetime.date] = Field(default=None)

    started: Optional[datetime.date] = Field(default=None)
    latest_step: Optional[str] = Field(default=None)
    next_step: Optional[str] = Field(default=None)
    next_step_date: Optional[datetime.date] = Field(default=None)
    latest_contact: Optional[str] = Field(default=None)

    end_date: Optional[datetime.date] = Field(default=None)

    maybe_referrals: Optional[str] = Field(default=None)
    referral_name: Optional[str] = Field(default=None)
    recruit_contact: Optional[str] = Field(default=None)

    total_comp: Optional[decimal.Decimal] = Field(default=None)
    base: Optional[decimal.Decimal] = Field(default=None)
    rsu: Optional[decimal.Decimal] = Field(default=None)
    bonus: Optional[decimal.Decimal] = Field(default=None)
    vesting: Optional[str] = Field(default=None)
    level_equiv: Optional[str] = Field(default=None)

    leetcode: Optional[bool] = Field(default=None)
    sys_design: Optional[bool] = Field(default=None)

    ai_notes: Optional[str] = Field(default=None)

    remote_policy: Optional[str] = Field(default=None)  # TODO validate values
    eng_size: Optional[int] = Field(default=None)
    total_size: Optional[int] = Field(default=None)
    headquarters: Optional[str] = Field(default=None)
    ny_address: Optional[str] = Field(default=None)
    commute_home: Optional[str] = Field(default=None)
    commute_lynn: Optional[str] = Field(default=None)

    notes: Optional[str] = Field(default=None)

    @model_validator(mode="before")
    @classmethod
    def normalize_fields(cls, data: Any) -> dict:
        """Normalize fields that require validation"""
        if isinstance(data, dict) and "cleared" in data:
            cleared = data["cleared"]
            if isinstance(cleared, (bool, type(None))):
                data["cleared"] = "yes" if cleared else ""
            elif cleared and str(cleared).strip().lower() == "yes":
                data["cleared"] = "yes"
            else:
                data["cleared"] = ""
        return data

    fill_columns: ClassVar[tuple[str, ...]] = ()
    sort_by_date_field: ClassVar[str] = "updated"


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


class CompaniesImporter(abc.ABC):
    """
    Importers are responsible for loading data eg. from a file,
    parsing the data, and finding new lines (that don't match prev_lines).

    generate_data_lines() is the entry point for this.
    """

    reverse_cron = True  # Default value, can be overridden in subclasses

    def __init__(self, prev_lines: list[CompaniesSheetRow] | None = None):
        self.prev_lines = prev_lines or []
        self.seen_checksums = set()
        self.out_buffer = []
        self.update_seen_checksums()

    def generate_data_lines(self) -> Generator[list[str], None, None]:
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

    def checksum_finder(self, row: CompaniesSheetRow) -> str | None:
        parts = row.name.lower().split()
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
class StubRow(BaseSheetRow):
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

    def main(self, csv_infile_name: Optional[str] = None):
        logger.info(f"Importing to range {self.range_name}")
        if csv_infile_name is not None:
            new_rows = self.read_rows_from_csv_file(csv_infile_name)
        else:
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

    @classmethod
    def read_rows_from_csv_file(cls, csv_infile_name: str | None) -> list[list[str]]:
        if csv_infile_name is None:
            return []
        with open(csv_infile_name) as infile:
            reader = csv.reader(infile)
            return list(reader)

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
        self, row_index: int, cell_updates: dict[int, Any] | BaseSheetRow
    ):
        """Update specific cells in a row, leaving others untouched."""
        # TODO test this method
        range_name = f"{self.range_name.split('!')[0]}!"
        batch_data = []

        if isinstance(cell_updates, BaseSheetRow):
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
    row_class = CompaniesSheetRow
    importer_class = CompaniesImporter


#######################################################################
# Doc IDs, Tab IDs and data ranges.


class Config:
    # My companies sheet:
    # For real:
    # https://docs.google.com/spreadsheets/d/1_MXPVn99e3i3MTGFVrBD73T-AwCKWuNS8P34eEI-SA4/edit?gid=0#gid=0
    SHEET_DOC_ID = "1_MXPVn99e3i3MTGFVrBD73T-AwCKWuNS8P34eEI-SA4"
    TAB_1_GID = "0"  # Main tab for companies
    TAB_1_RANGE = "Active!A3:AE"  # Remember ranges are half-open


class TestConfig(Config):
    # FOr testing:
    # https://docs.google.com/spreadsheets/d/1uDHheC0LnGGQfS3X7SeRGi0XM8dBwXho7bu-MfaYZpY/edit?gid=0#gid=0
    SHEET_DOC_ID = "1uDHheC0LnGGQfS3X7SeRGi0XM8dBwXho7bu-MfaYZpY"
    TAB_1_GID = "925425851"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="Spreadsheeter",
        description="Imports data to my companies google sheet",
        epilog="",
    )

    parser.add_argument(
        "-f",
        "--filename",
        action="store",
        help="CSV file to import. Must be already processed into the final expected format!",
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
        row = CompaniesSheetRow(
            name=name,
            updated=datetime.date.today(),
            current_state="10. consider applying",
            base=200,
            rsu=100,
            leetcode=True,
            sys_design=True,
            ai_notes="Something something LLM",
        )
        main_client.append_rows([row.as_list_of_str()])
        print(f"Loaded row: {row}")
        return

    csv_infile_name: Optional[str] = args.filename

    if csv_infile_name:
        main_client.main(csv_infile_name)
    else:
        main_client.main()


if __name__ == "__main__":  # pragma: no cover
    main(sys.argv[1:])
