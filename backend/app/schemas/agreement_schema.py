"""Pydantic schema for the AI-generated agreement draft.

The checks below are plain Python validators (not JSON-schema keywords), so they
always run on whatever Gemini returns.
"""
from pydantic import BaseModel, field_validator, model_validator


class MilestoneDraft(BaseModel):
    name: str
    percentage: int  # whole number: 30 means 30% of the budget

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("milestone name is empty")
        return value

    @field_validator("percentage")
    @classmethod
    def percentage_in_range(cls, value):
        if not 1 <= value <= 100:
            raise ValueError("milestone percentage must be between 1 and 100")
        return value


class AgreementDraft(BaseModel):
    project_title: str
    deliverables: list[str]  # 1 to 15 items
    exclusions: list[str]
    budget_amount: float | None  # the number stated in the description, None if no budget
    budget_currency: str | None  # "USD" or "INR", None if no budget. Never converted.
    timeline_days: int | None  # None when the description states no timeline
    milestones: list[MilestoneDraft]  # percentages must add up to exactly 100

    @field_validator("project_title")
    @classmethod
    def title_not_empty(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("project_title is empty")
        return value

    @field_validator("deliverables")
    @classmethod
    def deliverables_1_to_15(cls, items):
        items = [item.strip() for item in items if item.strip()]  # drop blank items
        if not 1 <= len(items) <= 15:
            raise ValueError("deliverables must contain 1 to 15 items")
        return items

    @field_validator("exclusions")
    @classmethod
    def clean_exclusions(cls, items):
        return [item.strip() for item in items if item.strip()]

    @field_validator("budget_amount")
    @classmethod
    def budget_positive(cls, value):
        if value is not None and value <= 0:
            raise ValueError("budget_amount must be more than 0, or null")
        return None if value is None else round(value, 2)

    @field_validator("budget_currency")
    @classmethod
    def currency_known(cls, value):
        value = (value or "").strip().upper()
        if not value:
            return None
        if value not in ("USD", "INR"):
            raise ValueError('budget_currency must be "USD", "INR" or null')
        return value

    @field_validator("timeline_days")
    @classmethod
    def timeline_positive(cls, value):
        if value is not None and value <= 0:
            raise ValueError("timeline_days must be more than 0, or null")
        return value

    @model_validator(mode="after")
    def milestones_add_up_to_100(self):
        if not self.milestones:
            raise ValueError("at least one milestone is required")
        total = sum(m.percentage for m in self.milestones)
        if total != 100:
            raise ValueError(f"milestone percentages add up to {total}, not 100")
        return self

    @model_validator(mode="after")
    def budget_fields_agree(self):
        if self.budget_amount is None:
            self.budget_currency = None  # no amount, so no currency
        elif self.budget_currency is None:
            self.budget_currency = "USD"  # a plain number means US dollars (the app's currency)
        return self

    @property
    def budget_usd(self):
        """Budget in US dollars, or None if there is none or it is in another currency.

        Use this (not budget_amount) when building the agreement: it never lets
        rupees be mistaken for dollars. No currency conversion happens anywhere.
        """
        return self.budget_amount if self.budget_currency == "USD" else None