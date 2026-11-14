from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from models.database import db
from models.goal import SavingsGoal
from services.validation import parse_date, parse_nonnegative_amount, parse_positive_amount


goals_bp = Blueprint('goals', __name__, template_folder='../templates')


@goals_bp.route('/goals', methods=['GET', 'POST'])
@login_required
def savings_goals():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        target_amount = request.form.get('target_amount', '0').strip()
        current_amount = request.form.get('current_amount', '0').strip()
        target_date = request.form.get('target_date', '').strip()

        try:
            target_value = parse_positive_amount(target_amount, 'Target amount')
            current_value = parse_nonnegative_amount(current_amount, 'Saved amount')
            target_day = parse_date(target_date, 'Target date', required=False)
            if not name or len(name) > 120:
                raise ValueError('Enter a goal name up to 120 characters.')
        except ValueError as exc:
            flash(str(exc), 'danger')
            return redirect(url_for('goals.savings_goals'))

        goal = SavingsGoal(
            user_id=current_user.id,
            name=name,
            target_amount=target_value,
            current_amount=current_value,
            target_date=target_day,
        )
        db.session.add(goal)
        db.session.commit()
        flash('Savings goal created.', 'success')
        return redirect(url_for('goals.savings_goals'))

    goals = SavingsGoal.query.filter_by(user_id=current_user.id).all()
    goal_rows = []
    for goal in goals:
        progress = (goal.current_amount / goal.target_amount * 100) if goal.target_amount else 0
        remaining = max(goal.target_amount - goal.current_amount, 0)
        goal_rows.append({
            'goal': goal,
            'progress': min(progress, 100),
            'remaining': remaining,
        })

    return render_template('goals.html', goals=goal_rows)


@goals_bp.route('/goals/<int:goal_id>/contribute', methods=['POST'])
@login_required
def contribute_to_goal(goal_id):
    goal = SavingsGoal.query.filter_by(
        id=goal_id,
        user_id=current_user.id,
    ).first_or_404()
    try:
        contribution = parse_positive_amount(
            request.form.get('amount', ''),
            'Contribution amount',
        )
    except ValueError as exc:
        flash(str(exc), 'danger')
    else:
        goal.current_amount += contribution
        db.session.commit()
        flash(f'₹{contribution:,.2f} added to {goal.name}.', 'success')
    return redirect(url_for('goals.savings_goals'))
