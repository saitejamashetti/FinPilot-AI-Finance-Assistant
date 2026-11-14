from datetime import date

from flask import Blueprint, Response, flash, jsonify, render_template, request
from flask_login import current_user, login_required

from models.budget import Budget
from models.bill import BillReminder
from models.goal import SavingsGoal
from models.transaction import Transaction
from services.finance_service import (
    export_transactions_csv,
    get_category_breakdown,
    get_dashboard_summary,
    get_insights,
    get_recent_transactions,
    get_upcoming_bills,
)
from services.ml_service import (
    forecast_monthly_expenses,
    get_model_metrics,
    predict_category,
)

main_bp = Blueprint('main', __name__, template_folder='../templates')


@main_bp.route('/dashboard')
@login_required
def dashboard():
    summary = get_dashboard_summary(current_user.id)
    category_data = get_category_breakdown(current_user.id)
    recent_transactions = get_recent_transactions(current_user.id, limit=5)
    upcoming_bills = get_upcoming_bills(current_user.id, limit=4)
    insights = get_insights(current_user.id)
    metrics = get_model_metrics()
    forecast = forecast_monthly_expenses(
        Transaction.query.filter_by(user_id=current_user.id, type='expense').all()
    )

    return render_template(
        'dashboard.html',
        summary=summary,
        categories=category_data,
        recent_transactions=recent_transactions,
        upcoming_bills=upcoming_bills,
        insights=insights,
        metrics=metrics,
        forecast=forecast,
        current_month=date.today().strftime('%B %Y'),
        today=date.today(),
    )


@main_bp.route('/insights')
@login_required
def insights_page():
    insights = get_insights(current_user.id)
    return render_template('insights.html', insights=insights)


@main_bp.route('/assistant', methods=['GET', 'POST'])
@login_required
def finance_assistant():
    response = None
    if request.method == 'POST':
        question = request.form.get('question', '').strip()
        if not question:
            flash('Please enter a question about your finances.', 'warning')
        else:
            current_month = date.today().strftime('%Y-%m')
            income_rows = Transaction.query.filter_by(user_id=current_user.id, type='income').all()
            expense_rows = Transaction.query.filter_by(user_id=current_user.id, type='expense').all()
            total_income = sum(
                t.amount for t in income_rows if t.date.strftime('%Y-%m') == current_month
            )
            total_expense = sum(
                t.amount for t in expense_rows if t.date.strftime('%Y-%m') == current_month
            )
            txns = Transaction.query.filter_by(user_id=current_user.id).order_by(Transaction.date.desc()).limit(5).all()
            lower_q = question.lower()
            if 'income' in lower_q:
                response = f"Your total income is ₹{total_income:,.2f}."
            elif 'expense' in lower_q or 'spent' in lower_q:
                response = f"Your total spending is ₹{total_expense:,.2f}."
            elif 'budget' in lower_q:
                budgets = Budget.query.filter_by(user_id=current_user.id, month=current_month).all()
                if budgets:
                    statuses = []
                    for budget in budgets:
                        spent = sum(
                            row.amount for row in expense_rows
                            if row.category == budget.category and row.date.strftime('%Y-%m') == current_month
                        )
                        statuses.append(
                            f'{budget.category}: ₹{spent:,.2f} of ₹{budget.limit_amount:,.2f}'
                        )
                    response = 'Current-month budgets — ' + '; '.join(statuses) + '.'
                else:
                    response = 'You have not set any budgets for this month.'
            elif 'category' in lower_q or 'categor' in lower_q:
                category_totals = {}
                for transaction in expense_rows:
                    if transaction.date.strftime('%Y-%m') == current_month:
                        category_totals[transaction.category] = (
                            category_totals.get(transaction.category, 0) + transaction.amount
                        )
                if category_totals:
                    response = 'Current-month categories: ' + '; '.join(
                        f'{name}: ₹{amount:,.2f}'
                        for name, amount in sorted(category_totals.items(), key=lambda item: item[1], reverse=True)
                    ) + '.'
                else:
                    response = 'No expenses have been recorded this month.'
            elif 'goal' in lower_q:
                goals = SavingsGoal.query.filter_by(user_id=current_user.id).all()
                if goals:
                    response = 'You currently have ' + ', '.join(g.name for g in goals) + ' as active savings goals.'
                else:
                    response = 'No savings goals have been added yet.'
            elif 'bill' in lower_q:
                bills = BillReminder.query.filter_by(user_id=current_user.id).filter(
                    BillReminder.payment_status != 'Paid'
                ).order_by(BillReminder.due_date.asc()).limit(5).all()
                response = (
                    'Upcoming unpaid bills: ' + ', '.join(
                        f'{bill.name} due {bill.due_date} (₹{bill.amount:,.2f})'
                        for bill in bills
                    ) if bills else 'You have no unpaid bill reminders.'
                )
            elif 'recent' in lower_q or 'transaction' in lower_q:
                sample = ', '.join(f'{t.description} ({t.type})' for t in txns) or 'No recent transactions yet.'
                response = f"Recent activity: {sample}"
            else:
                response = 'I can help with income, expenses, budget status, goals, recent transactions, and bill reminders, based on your actual records.'

    return render_template('assistant.html', response=response)


@main_bp.route('/export/csv')
@login_required
def export_transactions():
    csv_data = export_transactions_csv(current_user.id)
    return Response(
        csv_data,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=finpilot_transactions.csv'}
    )


@main_bp.route('/api/predict-category', methods=['POST'])
@login_required
def predict_category_api():
    data = request.get_json(silent=True) or {}
    description = str(data.get('description', '')).strip()
    if not description:
        return jsonify({'error': 'Description is required.'}), 400
    result = predict_category(description)
    return jsonify(result)
