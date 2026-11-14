from collections import defaultdict
import csv
from datetime import date
from io import StringIO

from models.bill import BillReminder
from models.budget import Budget
from models.goal import SavingsGoal
from models.transaction import Transaction


def _month_key(date_value):
    return date_value.strftime('%Y-%m') if hasattr(date_value, 'strftime') else str(date_value)[:7]


def get_recent_transactions(user_id, limit=5):
    return Transaction.query.filter_by(user_id=user_id).order_by(Transaction.date.desc(), Transaction.id.desc()).limit(limit).all()


def get_category_breakdown(user_id):
    totals = defaultdict(float)
    for transaction in Transaction.query.filter_by(user_id=user_id, type='expense').all():
        totals[transaction.category] += transaction.amount
    return [{'label': label, 'value': round(value, 2)} for label, value in sorted(totals.items(), key=lambda item: item[1], reverse=True)]


def get_dashboard_summary(user_id):
    transactions = Transaction.query.filter_by(user_id=user_id).all()
    income = sum(item.amount for item in transactions if item.type == 'income')
    expenses = sum(item.amount for item in transactions if item.type == 'expense')
    balance = income - expenses
    current_month = date.today().strftime('%Y-%m')
    monthly_expenses = sum(
        item.amount for item in transactions
        if item.type == 'expense' and _month_key(item.date) == current_month
    )
    monthly_income = sum(
        item.amount for item in transactions
        if item.type == 'income' and _month_key(item.date) == current_month
    )
    budgets = Budget.query.filter_by(user_id=user_id, month=current_month).all()
    budget_total = sum(item.limit_amount for item in budgets)
    budgeted_spend = sum(
        item.amount for item in transactions
        if item.type == 'expense'
        and _month_key(item.date) == current_month
        and any(item.category == budget.category for budget in budgets)
    )
    savings_rate = ((monthly_income - monthly_expenses) / monthly_income * 100) if monthly_income else 0
    return {
        'income': round(income, 2),
        'expenses': round(expenses, 2),
        'balance': round(balance, 2),
        'monthly_income': round(monthly_income, 2),
        'monthly_expenses': round(monthly_expenses, 2),
        'budget_usage': round((budgeted_spend / budget_total * 100) if budget_total else 0, 2),
        'savings_rate': round(savings_rate, 2),
    }


def get_upcoming_bills(user_id, limit=5):
    return BillReminder.query.filter_by(user_id=user_id).filter(
        BillReminder.payment_status != 'Paid',
    ).order_by(BillReminder.due_date.asc()).limit(limit).all()


def get_insights(user_id):
    insights = []
    transactions = Transaction.query.filter_by(user_id=user_id).all()
    if not transactions:
        return ['Add some transactions to unlock personalized insights.']

    expenses = [t for t in transactions if t.type == 'expense']
    if not expenses:
        return ['No expense data yet. Track spending to get AI recommendations.']

    current_month = date.today().strftime('%Y-%m')
    month_expenses = [
        transaction for transaction in expenses
        if _month_key(transaction.date) == current_month
    ]
    highest_category = max(
        ((category, sum(t.amount for t in month_expenses if t.category == category)) for category in {t.category for t in month_expenses}),
        key=lambda item: item[1],
        default=(None, 0),
    )
    if highest_category[0]:
        insights.append(f"Your highest spending category is {highest_category[0]}.")

    income_total = sum(
        t.amount for t in transactions
        if t.type == 'income' and _month_key(t.date) == current_month
    )
    expense_total = sum(t.amount for t in month_expenses)
    if income_total:
        insights.append(f"Your current-month savings rate is {((income_total - expense_total) / income_total * 100):.1f}%.")

    goals = SavingsGoal.query.filter_by(user_id=user_id).all()
    if goals:
        goal_names = ', '.join(goal.name for goal in goals)
        insights.append(f"You are tracking progress toward {goal_names}.")

    monthly_budgets = Budget.query.filter_by(user_id=user_id, month=current_month).all()
    for budget in monthly_budgets:
        spent = sum(
            item.amount for item in month_expenses if item.category == budget.category
        )
        usage = spent / budget.limit_amount * 100 if budget.limit_amount else 0
        if usage >= budget.alert_threshold:
            insights.append(
                f'{budget.category} is at {usage:.1f}% of its monthly budget.'
            )

    return insights


def export_transactions_csv(user_id):
    output = StringIO()
    writer = csv.writer(output)
    transactions = Transaction.query.filter_by(user_id=user_id).order_by(Transaction.date.desc(), Transaction.id.desc()).all()
    writer.writerow(['id', 'description', 'amount', 'date', 'type', 'category', 'merchant', 'payment_method'])
    for tx in transactions:
        cells = [
            tx.id, tx.description, tx.amount, tx.date, tx.type, tx.category,
            tx.merchant or '', tx.payment_method or '',
        ]
        safe_cells = [
            f"'{value}"
            if isinstance(value, str) and value.lstrip(' \t\r\n').startswith(('=', '+', '-', '@'))
            else value
            for value in cells
        ]
        writer.writerow(safe_cells)
    return output.getvalue()
