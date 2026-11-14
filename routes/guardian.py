from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from models.budget import Budget
from models.database import db
from models.goal import SavingsGoal
from models.purchase import AvoidPreference, PlannedPurchase, ShoppingPreference
from models.transaction import Transaction
from services.validation import parse_positive_amount

guardian_bp = Blueprint('guardian', __name__, template_folder='../templates')
DECISIONS = ('Pending', 'Wait 24h', 'Wishlist', 'Necessary', 'Cancelled', 'Buy anyway')


def _review_purchase(user_id, item_name, category, amount):
    warnings = []
    current_month = date.today().strftime('%Y-%m')
    preferences = AvoidPreference.query.filter_by(user_id=user_id).all()
    lowered_text = f'{item_name} {category}'.casefold()
    for preference in preferences:
        if preference.term.casefold() in lowered_text:
            warnings.append(f'You added “{preference.term}” to your personal avoid list.')

    transactions = Transaction.query.filter_by(user_id=user_id, type='expense').all()
    category_spend = sum(
        transaction.amount for transaction in transactions
        if transaction.category.casefold() == category.casefold()
        and transaction.date.strftime('%Y-%m') == current_month
    )
    budget = Budget.query.filter_by(
        user_id=user_id,
        category=category.title(),
        month=current_month,
    ).first()
    if budget:
        projected = category_spend + amount
        if projected > budget.limit_amount:
            warnings.append(
                f'This purchase would exceed the {category} budget by '
                f'₹{projected - budget.limit_amount:,.2f}.'
            )
        elif projected / budget.limit_amount * 100 >= budget.alert_threshold:
            warnings.append(f'This purchase would bring the {category} budget close to its limit.')

    preference = ShoppingPreference.query.filter_by(user_id=user_id).first()
    if preference and preference.monthly_limit:
        shopping_spend = sum(
            transaction.amount for transaction in transactions
            if transaction.category.casefold() == 'shopping'
            and transaction.date.strftime('%Y-%m') == current_month
        )
        if shopping_spend + amount > preference.monthly_limit:
            warnings.append(
                f'This purchase would exceed your personal monthly shopping limit by '
                f'₹{shopping_spend + amount - preference.monthly_limit:,.2f}.'
            )

    goals = SavingsGoal.query.filter_by(user_id=user_id).all()
    for goal in goals:
        remaining = max(goal.target_amount - goal.current_amount, 0)
        if remaining and amount >= remaining:
            warnings.append(
                f'This purchase is as large as the remaining ₹{remaining:,.2f} for your “{goal.name}” goal.'
            )
            break
    if category_spend and amount > category_spend:
        warnings.append(
            f'The planned amount is above your recorded {category} spending so far this month.'
        )
    if not warnings:
        warnings.append('No saved preference or budget conflict was found; review the purchase at your discretion.')
    return warnings


@guardian_bp.route('/guardian', methods=['GET', 'POST'])
@login_required
def guardian():
    if request.method == 'POST':
        try:
            item_name = request.form.get('item_name', '').strip()
            category = request.form.get('category', 'Shopping').strip() or 'Shopping'
            amount = parse_positive_amount(request.form.get('amount', ''), 'Purchase amount')
            reason = request.form.get('reason', '').strip()
            if not item_name or len(item_name) > 120 or len(category) > 50:
                raise ValueError('Enter an item and category within the allowed length.')
        except ValueError as exc:
            flash(str(exc), 'danger')
            return redirect(url_for('guardian.guardian'))

        purchase = PlannedPurchase(
            user_id=current_user.id,
            item_name=item_name,
            category=category,
            amount=amount,
            reason=reason[:1000],
            decision='Pending',
        )
        db.session.add(purchase)
        db.session.commit()
        warnings = _review_purchase(current_user.id, item_name, category, amount)
        flash('Purchase review: ' + ' '.join(warnings), 'warning')
        flash('FinPilot will not prevent the purchase; you make the final decision.', 'info')
        return redirect(url_for('guardian.guardian'))

    purchases = PlannedPurchase.query.filter_by(
        user_id=current_user.id,
    ).order_by(PlannedPurchase.created_at.desc()).all()
    reviews = {
        purchase.id: _review_purchase(
            current_user.id,
            purchase.item_name,
            purchase.category,
            purchase.amount,
        )
        for purchase in purchases
    }
    preference = ShoppingPreference.query.filter_by(user_id=current_user.id).first()
    avoid_terms = AvoidPreference.query.filter_by(user_id=current_user.id).order_by(AvoidPreference.term).all()
    return render_template(
        'guardian.html',
        purchases=purchases,
        reviews=reviews,
        avoid_terms=avoid_terms,
        monthly_limit=preference.monthly_limit if preference else None,
    )


@guardian_bp.route('/guardian/preferences', methods=['POST'])
@login_required
def update_preferences():
    action = request.form.get('action')
    if action == 'add_avoid':
        term = request.form.get('term', '').strip()
        if not term or len(term) > 120:
            flash('Enter an avoid-list item up to 120 characters.', 'danger')
        elif AvoidPreference.query.filter_by(user_id=current_user.id, term=term).first():
            flash('That item is already on your avoid list.', 'warning')
        else:
            db.session.add(AvoidPreference(user_id=current_user.id, term=term))
            db.session.commit()
            flash('Personal avoid-list item added.', 'success')
    elif action == 'set_limit':
        try:
            limit = parse_positive_amount(request.form.get('monthly_limit', ''), 'Monthly shopping limit')
        except ValueError as exc:
            flash(str(exc), 'danger')
        else:
            preference = ShoppingPreference.query.filter_by(user_id=current_user.id).first()
            if preference is None:
                preference = ShoppingPreference(user_id=current_user.id)
                db.session.add(preference)
            preference.monthly_limit = limit
            db.session.commit()
            flash('Monthly shopping limit saved.', 'success')
    else:
        flash('Unknown preference action.', 'danger')
    return redirect(url_for('guardian.guardian'))


@guardian_bp.route('/guardian/preferences/<int:preference_id>/delete', methods=['POST'])
@login_required
def delete_avoid(preference_id):
    preference = AvoidPreference.query.filter_by(
        id=preference_id,
        user_id=current_user.id,
    ).first_or_404()
    db.session.delete(preference)
    db.session.commit()
    flash('Item removed from your avoid list.', 'success')
    return redirect(url_for('guardian.guardian'))


@guardian_bp.route('/guardian/<int:purchase_id>/decision', methods=['POST'])
@login_required
def purchase_decision(purchase_id):
    purchase = PlannedPurchase.query.filter_by(
        id=purchase_id,
        user_id=current_user.id,
    ).first_or_404()
    decision = request.form.get('decision', '')
    if decision not in DECISIONS:
        flash('Choose a valid purchase decision.', 'danger')
    else:
        purchase.decision = decision
        db.session.commit()
        flash(f'Purchase marked as {decision}. Your choice is final.', 'success')
    return redirect(url_for('guardian.guardian'))
