from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from models.bill import BillReminder
from models.database import db
from services.validation import parse_date, parse_positive_amount

bills_bp = Blueprint('bills', __name__, template_folder='../templates')


@bills_bp.route('/bills', methods=['GET', 'POST'])
@login_required
def bills():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        amount = request.form.get('amount', '').strip()
        due_date = request.form.get('due_date', '').strip()
        category = request.form.get('category', 'Bills').strip() or 'Bills'
        recurrence = request.form.get('recurrence', 'Monthly').strip() or 'Monthly'
        payment_status = request.form.get('payment_status', 'Upcoming').strip() or 'Upcoming'

        try:
            amount_value = parse_positive_amount(amount, 'Bill amount')
            due_day = parse_date(due_date, 'Due date')
            if not name or len(name) > 120:
                raise ValueError('Enter a bill name up to 120 characters.')
            if recurrence not in {'Monthly', 'Quarterly', 'Yearly', 'None'}:
                raise ValueError('Choose a valid bill recurrence.')
            if payment_status not in {'Upcoming', 'Paid'}:
                raise ValueError('Choose Upcoming or Paid for the payment status.')
        except ValueError as exc:
            flash(str(exc), 'danger')
            return redirect(url_for('bills.bills'))

        bill = BillReminder(
            user_id=current_user.id,
            name=name,
            amount=amount_value,
            due_date=due_day,
            category=category,
            recurrence=recurrence,
            payment_status=payment_status,
        )
        db.session.add(bill)
        db.session.commit()
        flash('Bill reminder created successfully.', 'success')
        return redirect(url_for('bills.bills'))

    bills_list = BillReminder.query.filter_by(user_id=current_user.id).order_by(BillReminder.due_date.asc()).all()
    today = date.today()
    bill_rows = [
        {
            'bill': bill,
            'status': 'Overdue' if bill.payment_status != 'Paid' and bill.due_date < today else bill.payment_status,
        }
        for bill in bills_list
    ]
    return render_template('bills.html', bills=bill_rows)


@bills_bp.route('/bills/<int:bill_id>/paid', methods=['POST'])
@login_required
def mark_bill_paid(bill_id):
    bill = BillReminder.query.filter_by(id=bill_id, user_id=current_user.id).first_or_404()
    bill.payment_status = 'Paid'
    db.session.commit()
    flash(f'{bill.name} marked as paid.', 'success')
    return redirect(url_for('bills.bills'))
