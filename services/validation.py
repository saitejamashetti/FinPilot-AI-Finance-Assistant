from datetime import date
from decimal import Decimal, InvalidOperation
import re


def parse_positive_amount(value, field_name='Amount'):
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, AttributeError):
        raise ValueError(f'{field_name} must be a valid number.') from None
    if not amount.is_finite() or amount <= 0:
        raise ValueError(f'{field_name} must be greater than zero.')
    return float(amount)


def parse_nonnegative_amount(value, field_name='Amount'):
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, AttributeError):
        raise ValueError(f'{field_name} must be a valid number.') from None
    if not amount.is_finite() or amount < 0:
        raise ValueError(f'{field_name} cannot be negative.')
    return float(amount)


def parse_date(value, field_name='Date', required=True):
    cleaned = (value or '').strip()
    if not cleaned:
        if required:
            raise ValueError(f'{field_name} is required.')
        return None
    try:
        return date.fromisoformat(cleaned)
    except ValueError:
        raise ValueError(f'{field_name} must be a valid date.') from None


def parse_month(value, field_name='Month'):
    cleaned = (value or '').strip()
    if not re.fullmatch(r'\d{4}-\d{2}', cleaned):
        raise ValueError(f'{field_name} must be in YYYY-MM format.')
    year, month = (int(part) for part in cleaned.split('-'))
    if not 1 <= month <= 12 or year < 1900:
        raise ValueError(f'{field_name} must be a valid calendar month.')
    return cleaned


def normalize_email(value):
    email = (value or '').strip().lower()
    if len(email) > 120 or not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email):
        raise ValueError('Enter a valid email address.')
    return email
