import datetime
import decimal
import enum
import json
import multiprocessing
import os
import sqlite3
from contextlib import contextmanager
from typing import Any, ClassVar, Iterator, List, Optional

import dateutil.parser
from pydantic import BaseModel, Field, ValidationError, model_validator


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
                        data[field_name] = decimal.Decimal(val)
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

    @property
    def company_identifier(self) -> str:
        if self.name and self.url:
            return f"{self.name} at {self.url}"
        elif self.name:
            return self.name
        elif self.url:
            return f"with unknown name at {self.url}"
        return ""


class Company(BaseModel):
    name: str
    details: CompaniesSheetRow
    initial_message: Optional[str] = None
    reply_message: str = ""


class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime.date, datetime.datetime)):
            return obj.isoformat()
        if isinstance(obj, decimal.Decimal):
            return str(obj)
        if isinstance(obj, enum.Enum):
            return obj.value
        return super().default(obj)


class CompanyRepository:

    def __init__(
        self,
        db_path: str = "data/companies.db",
        load_sample_data: bool = False,
        clear_data: bool = False,
    ):
        self.db_path = db_path
        self.lock = multiprocessing.Lock()
        self._ensure_db_dir()
        self._init_db(load_sample_data, clear_data)

    def _ensure_db_dir(self):
        """Ensure the database directory exists."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    def _init_db(self, load_sample_data: bool, clear_data: bool):
        with self.lock:
            with self._get_connection() as conn:
                if clear_data:
                    conn.execute("DROP TABLE IF EXISTS companies")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS companies (
                        name TEXT PRIMARY KEY,
                        details TEXT NOT NULL,
                        initial_message TEXT,
                        reply_message TEXT NOT NULL DEFAULT ''
                    )
                """
                )
        if load_sample_data:
            for company in SAMPLE_COMPANIES:
                self.create(company)

    @contextmanager
    def _get_connection(self):
        # Create a new connection each time, don't store in thread local
        connection = sqlite3.connect(self.db_path, timeout=60.0)
        try:
            yield connection
        finally:
            connection.close()

    def get(self, name: str) -> Optional[Company]:
        # Reads can happen without the lock
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT name, details, initial_message, reply_message FROM companies WHERE name = ?",
                (name,),
            )
            row = cursor.fetchone()
            return self._deserialize_company(row) if row else None

    def get_all(self) -> List[Company]:
        # Reads can happen without the lock
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT name, details, initial_message, reply_message FROM companies"
            )
            return [self._deserialize_company(row) for row in cursor.fetchall()]

    def create(self, company: Company) -> Company:
        with self.lock:
            with self._get_connection() as conn:
                try:
                    conn.execute(
                        "INSERT INTO companies (name, details, initial_message, reply_message) VALUES (?, ?, ?, ?)",
                        (
                            company.name,
                            json.dumps(
                                company.details.model_dump(), cls=CustomJSONEncoder
                            ),
                            company.initial_message,
                            company.reply_message,
                        ),
                    )
                    conn.commit()
                    return company
                except sqlite3.IntegrityError:
                    raise ValueError(f"Company {company.name} already exists")

    def update(self, company: Company) -> Company:
        with self.lock:  # Lock for writes
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    UPDATE companies 
                    SET details = ?, initial_message = ?, reply_message = ?
                    WHERE name = ?
                    """,
                    (
                        json.dumps(company.details.model_dump(), cls=CustomJSONEncoder),
                        company.initial_message,
                        company.reply_message,
                        company.name,
                    ),
                )
                if cursor.rowcount == 0:
                    raise ValueError(f"Company {company.name} not found")
                conn.commit()
                return company

    def delete(self, name: str) -> None:
        with self.lock:  # Lock for writes
            with self._get_connection() as conn:
                cursor = conn.execute("DELETE FROM companies WHERE name = ?", (name,))
                if cursor.rowcount == 0:
                    raise ValueError(f"Company {name} not found")
                conn.commit()

    def _deserialize_company(self, row: tuple[str, str, str, str]) -> Company:
        """Convert a database row into a Company object."""
        assert row is not None
        name, details_json, initial_message, reply_message = row
        details_dict = json.loads(details_json)

        # Convert ISO format dates back to datetime.date
        for key, value in details_dict.items():
            if isinstance(value, str) and "date" in key:
                try:
                    details_dict[key] = dateutil.parser.parse(value).date()
                except (ValueError, TypeError):
                    details_dict[key] = None

        return Company(
            name=name,
            details=CompaniesSheetRow(**details_dict),
            initial_message=initial_message,
            reply_message=reply_message,
        )


# Sample data
SAMPLE_COMPANIES = [
    Company(
        name="Shopify",
        details=CompaniesSheetRow(
            name="Shopify",
            type="Public",
            valuation="10B",
            url="https://shopify.com",
            current_state="Active",
            updated=datetime.date(2024, 12, 15),
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
            updated=datetime.date(2024, 10, 10),
            headquarters="New York",
        ),
        initial_message="Hi Paul! Interested in a senior backend role at Rippling? - Mark Marker",
    ),
]

# Module-level singleton
_company_repository = None


def company_repository(
    db_path: str = "data/companies.db",
    load_sample_data: bool = False,
    clear_data: bool = False,
) -> CompanyRepository:
    # This is a bit hacky: the args only matter when creating the singleton
    global _company_repository
    if _company_repository is None:
        _company_repository = CompanyRepository(
            db_path=db_path,
            load_sample_data=load_sample_data,
            clear_data=clear_data,
        )
    return _company_repository


def serialize_company(company: Company):
    data = company.model_dump()
    data["details"] = {
        k: (v.isoformat() if isinstance(v, datetime.date) else v)
        for k, v in company.details.model_dump().items()
        if v is not None
    }
    return data


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--clear-data", action="store_true", help="Clear existing data")
    parser.add_argument("--sample-data", action="store_true", help="Load sample data")
    args = parser.parse_args()

    company_repository(clear_data=args.clear_data, load_sample_data=args.sample_data)
