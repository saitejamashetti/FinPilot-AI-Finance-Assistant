from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from models.budget import Budget
from models.database import db
from models.transaction import Transaction
from services.validation import parse_month, parse_positive_amount

budgets_bp = Blueprint('budgets', __name__, template_folder='../templates')


def _monthly_spending(user_id, category, month):
    return sum(
        item.amount for item in Transaction.query.filter_by(user_id=user_id, type='expense').all()
        if item.category == category and item.date.strftime('%Y-%m') == month
    )


@budgets_bp.route('/budgets', methods=['GET', 'POST'])
@login_required
def budgets():
    if request.method == 'POST':
        category = request.form.get('category', '').strip().title()
        try:
            month = parse_month(request.form.get('month', date.today().strftime('%Y-%m')))
            limit_amount = parse_positive_amount(request.form.get('limit_amount', ''), 'Budget limit')
            threshold = float(request.form.get('alert_threshold', '80'))
            if not category or len(category) > 50:
                raise ValueError('Enter a budget category up to 50 characters.')
            if not 1 <= threshold <= 100:
                raise ValueError('Alert threshold must be between 1 and 100.')
        except ValueError as exc:
            flash(str(exc), 'danger')
            return redirect(url_for('budgets.budgets'))

        duplicate = Budget.query.filter_by(
            user_id=current_user.id,
            category=category,
            month=month,
        ).first()
        if duplicate:
            flash('A budget already exists for this category and month.', 'warning')
            return redirect(url_for('budgets.budgets'))

        budget = Budget(
            user_id=current_user.id,
            category=category,
            month=month,
            limit_amount=limit_amount,
            alert_threshold=threshold,
        )
        try:
            db.session.add(budget)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash('Could not save this budget. Check whether it already exists.', 'danger')
            return redirect(url_for('budgets.budgets'))
        flash('Budget added successfully.', 'success')
        return redirect(url_for('budgets.budgets'))

    current_month = date.today().strftime('%Y-%m')
    budgets = Budget.query.filter_by(user_id=current_user.id).order_by(Budget.month.desc()).all()
    budget_rows = []
    for budget in budgets:
        spent = _monthly_spending(current_user.id, budget.category, budget.month)
        remaining = budget.limit_amount - spent
        usage = (spent / budget.limit_amount * 100) if budget.limit_amount else 0
        budget_rows.append({
            'budget': budget,
            'spent': spent,
            'remaining': remaining,
            'usage': usage,
            'status': 'Exceeded' if usage >= 100 else ('Warning' if usage >= budget.alert_threshold else 'On track'),
        })

    return render_template('budgets.html', budgets=budget_rows, current_month=current_month)
