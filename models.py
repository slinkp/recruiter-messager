import datetime
from typing import Any, ClassVar, Dict, Iterator, List, Optional
import dateutil.parser
import decimal

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
        return self._companies.get(name)

    def get_all(self) -> List[Company]:
        return list(self._companies.values())

    def create(self, company: Company) -> Company:
        if company.name in self._companies:
            raise ValueError(f"Company {company.name} already exists")
        self._companies[company.name] = company
        return company

    def update(self, company: Company) -> Company:
        if company.name not in self._companies:
            raise ValueError(f"Company {company.name} not found")
        self._companies[company.name] = company
        return company

    def delete(self, name: str) -> None:
        if name not in self._companies:
            raise ValueError(f"Company {name} not found")
        del self._companies[name]


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


def company_repository() -> CompanyRepository:
    global _company_repository
    if _company_repository is None:
        _company_repository = CompanyRepository()
    return _company_repository


def serialize_company(company: Company):
    data = company.model_dump()
    data["details"] = {
        k: (v.isoformat() if isinstance(v, datetime.date) else v)
        for k, v in company.details.model_dump().items()
        if v is not None
    }
    return data
