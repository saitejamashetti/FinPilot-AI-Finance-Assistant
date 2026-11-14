from collections import defaultdict
from datetime import timedelta
import hashlib
import re
import statistics


def _normalized_name(transaction):
    merchant = (transaction.merchant or '').strip()
    value = merchant if merchant and merchant.lower() != 'n/a' else transaction.description
    return re.sub(r'[^a-z0-9]+', ' ', value.lower()).strip()


def detect_recurring_transactions(transactions):
    groups = defaultdict(list)
    for transaction in transactions:
        if transaction.type != 'expense':
            continue
        name = _normalized_name(transaction)
        if name:
            groups[name].append(transaction)

    suggestions = []
    for normalized_name, items in groups.items():
        ordered = sorted(items, key=lambda item: item.date)
        amount_center = statistics.median(item.amount for item in ordered)
        comparable = [
            item for item in ordered
            if amount_center and abs(item.amount - amount_center) / amount_center <= 0.10
        ]
        if len(comparable) < 2:
            continue
        dates = sorted(item.date for item in comparable)
        intervals = [(dates[idx] - dates[idx - 1]).days for idx in range(1, len(dates))]
        average_days = sum(intervals) / len(intervals)

        if 25 <= average_days <= 35 and len(dates) >= 3:
            frequency, months_per_year = 'Monthly', 1
        elif 75 <= average_days <= 105 and len(dates) >= 2:
            frequency, months_per_year = 'Quarterly', 3
        elif 330 <= average_days <= 400 and len(dates) >= 2:
            frequency, months_per_year = 'Yearly', 12
        else:
            continue

        average_amount = sum(item.amount for item in comparable) / len(comparable)
        suggestion_key = hashlib.sha256(
            f'{normalized_name}|{round(average_amount, 2)}|{frequency}'.encode('utf-8')
        ).hexdigest()
        suggestions.append({
            'key': suggestion_key,
            'name': comparable[-1].merchant if comparable[-1].merchant and comparable[-1].merchant.lower() != 'n/a'
            else comparable[-1].description,
            'amount': round(average_amount, 2),
            'frequency': frequency,
            'next_due_date': dates[-1] + timedelta(days=round(average_days)),
            'yearly_cost': round(average_amount * 12 / months_per_year, 2),
        })
    return suggestions
