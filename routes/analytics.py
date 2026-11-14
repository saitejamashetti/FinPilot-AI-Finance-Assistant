from datetime import date
import math

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required

from models.budget import Budget
from models.database import db
from models.goal import SavingsGoal
from models.subscription import DismissedSubscription, Subscription
from models.transaction import Transaction
from services.finance_service import get_category_breakdown, get_dashboard_summary
from services.ml_service import detect_unusual_transactions, forecast_monthly_expenses
from services.subscription_service import detect_recurring_transactions
from services.validation import parse_date, parse_positive_amount

analytics_bp = Blueprint('analytics', __name__, template_folder='../templates')


@analytics_bp.route('/analytics')
@login_required
def analytics():
    summary = get_dashboard_summary(current_user.id)
    categories = get_category_breakdown(current_user.id)
    expenses = Transaction.query.filter_by(
        user_id=current_user.id,
        type='expense',
    ).order_by(Transaction.date.asc()).all()
    forecast = forecast_monthly_expenses(expenses)
    budget_alerts = []
    current_month = date.today().strftime('%Y-%m')
    monthly_expenses = [
        item for item in expenses if item.date.strftime('%Y-%m') == current_month
    ]
    for budget in Budget.query.filter_by(user_id=current_user.id, month=current_month).all():
        spent = sum(item.amount for item in monthly_expenses if item.category == budget.category)
        usage = spent / budget.limit_amount * 100 if budget.limit_amount else 0
        if usage >= budget.alert_threshold:
            budget_alerts.append({
                'category': budget.category,
                'usage': round(usage, 1),
                'remaining': round(budget.limit_amount - spent, 2),
            })
    return render_template(
        'analytics.html',
        summary=summary,
        categories=categories,
        budget_alerts=budget_alerts,
        forecast=forecast,
    )


def _current_suggestions(user_id):
    expenses = Transaction.query.filter_by(user_id=user_id, type='expense').all()
    dismissed_keys = {
        row.suggestion_key
        for row in DismissedSubscription.query.filter_by(user_id=user_id).all()
    }
    saved = Subscription.query.filter_by(user_id=user_id).all()
    saved_names = {row.name.strip().casefold() for row in saved}
    return [
        suggestion for suggestion in detect_recurring_transactions(expenses)
        if suggestion['key'] not in dismissed_keys
        and suggestion['name'].strip().casefold() not in saved_names
    ]


@analytics_bp.route('/subscriptions', methods=['GET', 'POST'])
@login_required
def subscriptions():
    if request.method == 'POST':
        action = request.form.get('action', 'add')
        key = request.form.get('suggestion_key', '')
        if action in {'confirm', 'dismiss'}:
            suggestion = next(
                (item for item in _current_suggestions(current_user.id) if item['key'] == key),
                None,
            )
            if suggestion is None:
                flash('That recurring pattern is no longer available. Refresh and try again.', 'warning')
            elif action == 'confirm':
                db.session.add(Subscription(
                    user_id=current_user.id,
                    name=suggestion['name'],
                    amount=suggestion['amount'],
                    frequency=suggestion['frequency'],
                    next_due_date=suggestion['next_due_date'],
                    confirmed=True,
                ))
                db.session.commit()
                flash('Recurring payment confirmed as a subscription.', 'success')
            else:
                db.session.add(DismissedSubscription(
                    user_id=current_user.id,
                    suggestion_key=key,
                ))
                db.session.commit()
                flash('Recurring pattern dismissed.', 'success')
            return redirect(url_for('analytics.subscriptions'))

        try:
            name = request.form.get('name', '').strip()
            amount = parse_positive_amount(request.form.get('amount', ''), 'Subscription amount')
            frequency = request.form.get('frequency', 'Monthly')
            due_date = parse_date(request.form.get('next_due_date', ''), 'Next due date')
            if not name or len(name) > 120:
                raise ValueError('Enter a subscription name up to 120 characters.')
            if frequency not in {'Monthly', 'Quarterly', 'Yearly'}:
                raise ValueError('Choose a valid subscription frequency.')
        except ValueError as exc:
            flash(str(exc), 'danger')
            return redirect(url_for('analytics.subscriptions'))
        db.session.add(Subscription(
            user_id=current_user.id,
            name=name,
            amount=amount,
            frequency=frequency,
            next_due_date=due_date,
            confirmed=True,
        ))
        db.session.commit()
        flash('Subscription saved.', 'success')
        return redirect(url_for('analytics.subscriptions'))

    detected = _current_suggestions(current_user.id)
    saved = Subscription.query.filter_by(user_id=current_user.id).order_by(Subscription.next_due_date.asc()).all()
    return render_template('subscriptions.html', detected=detected, subscriptions=saved)


@analytics_bp.route('/subscriptions/<int:subscription_id>/edit', methods=['POST'])
@login_required
def edit_subscription(subscription_id):
    subscription = Subscription.query.filter_by(
        id=subscription_id,
        user_id=current_user.id,
    ).first_or_404()
    try:
        name = request.form.get('name', '').strip()
        amount = parse_positive_amount(request.form.get('amount', ''), 'Subscription amount')
        frequency = request.form.get('frequency', '')
        due_date = parse_date(request.form.get('next_due_date', ''), 'Next due date')
        if not name or len(name) > 120 or frequency not in {'Monthly', 'Quarterly', 'Yearly'}:
            raise ValueError('Enter a valid name and subscription frequency.')
    except ValueError as exc:
        flash(str(exc), 'danger')
    else:
        subscription.name = name
        subscription.amount = amount
        subscription.frequency = frequency
        subscription.next_due_date = due_date
        db.session.commit()
        flash('Subscription updated.', 'success')
    return redirect(url_for('analytics.subscriptions'))


@analytics_bp.route('/subscriptions/<int:subscription_id>/delete', methods=['POST'])
@login_required
def delete_subscription(subscription_id):
    subscription = Subscription.query.filter_by(
        id=subscription_id,
        user_id=current_user.id,
    ).first_or_404()
    db.session.delete(subscription)
    db.session.commit()
    flash('Subscription removed.', 'success')
    return redirect(url_for('analytics.subscriptions'))


@analytics_bp.route('/anomalies')
@login_required
def anomalies():
    expenses = Transaction.query.filter_by(user_id=current_user.id, type='expense').all()
    result = detect_unusual_transactions(expenses)
    return render_template(
        'anomalies.html',
        alerts=result['alerts'],
        available=result['available'],
        reason=result['reason'],
    )


@analytics_bp.route('/health')
@login_required
def health_score():
    user_transactions = Transaction.query.filter_by(user_id=current_user.id).all()
    current_month = date.today().strftime('%Y-%m')
    income = sum(
        item.amount for item in user_transactions
        if item.type == 'income' and item.date.strftime('%Y-%m') == current_month
    )
    expenses = sum(
        item.amount for item in user_transactions
        if item.type == 'expense' and item.date.strftime('%Y-%m') == current_month
    )
    savings_score = max(0.0, min(100.0, (income - expenses) / income * 100)) if income else None
    budgets = Budget.query.filter_by(user_id=current_user.id, month=current_month).all()
    if budgets:
        total_limits = sum(item.limit_amount for item in budgets)
        overage = sum(
            max(
                sum(
                    transaction.amount for transaction in user_transactions
                    if transaction.type == 'expense'
                    and transaction.category == budget.category
                    and transaction.date.strftime('%Y-%m') == current_month
                ) - budget.limit_amount,
                0,
            )
            for budget in budgets
        )
        budget_score = max(0.0, 100 - overage / total_limits * 100) if total_limits else None
    else:
        budget_score = None

    components = [value for value in (savings_score, budget_score) if value is not None]
    score = round(sum(components) / len(components)) if components else None
    suggestions = []
    if savings_score is not None and savings_score < 20:
        suggestions.append('Review expenses against your income and consider setting a realistic savings target.')
    if budget_score is not None and budget_score < 100:
        suggestions.append('Review categories that are above their monthly budget.')
    if not suggestions:
        suggestions.append('Keep recording income and expenses to make this educational indicator more useful.')
    return render_template(
        'health.html',
        score=score,
        savings_rate=savings_score,
        budget_score=budget_score,
        suggestions=suggestions,
        current_month=current_month,
    )


@analytics_bp.route('/simulator', methods=['GET', 'POST'])
@login_required
def simulator():
    daily_value = 0.0
    target_value = 0.0
    if request.method == 'POST':
        try:
            daily_value = parse_positive_amount(request.form.get('daily_saving', ''), 'Daily savings')
            target_value = parse_positive_amount(request.form.get('goal_amount', ''), 'Goal amount')
        except ValueError as exc:
            flash(str(exc), 'danger')
            return redirect(url_for('analytics.simulator'))
    weekly = daily_value * 7
    monthly = daily_value * 30
    yearly = daily_value * 365
    months_to_goal = math.ceil(target_value / monthly) if daily_value and target_value else None
    return render_template(
        'simulator.html',
        daily_saving=daily_value,
        goal_amount=target_value,
        weekly=weekly,
        monthly=monthly,
        yearly=yearly,
        months_to_goal=months_to_goal,
    )


@analytics_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings_page():
    if request.method == 'POST':
        theme = request.form.get('theme', 'light')
        if theme not in {'light', 'dark'}:
            flash('Choose a valid theme.', 'danger')
        else:
            session['theme'] = theme
            flash('Preferences saved.', 'success')
    return render_template('settings.html', theme=session.get('theme', 'light'))


@analytics_bp.route('/reports')
@login_required
def reports():
    summary = get_dashboard_summary(current_user.id)
    category_data = get_category_breakdown(current_user.id)
    recent = Transaction.query.filter_by(
        user_id=current_user.id,
    ).order_by(Transaction.date.desc(), Transaction.id.desc()).limit(10).all()
    goals = SavingsGoal.query.filter_by(user_id=current_user.id).all()
    return render_template('reports.html', summary=summary, categories=category_data, recent=recent, goals=goals)
