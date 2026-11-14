from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from models.database import db
from models.transaction import Transaction
from services.ml_service import predict_category
from services.validation import parse_date, parse_positive_amount

transactions_bp = Blueprint('transactions', __name__, template_folder='../templates')
CATEGORIES = ('Food', 'Transport', 'Shopping', 'Bills', 'Entertainment', 'Health', 'Education', 'Other')


@transactions_bp.route('/transactions', methods=['GET', 'POST'])
@login_required
def transactions():
    if request.method == 'POST':
        description = request.form.get('description', '').strip()
        amount = request.form.get('amount', '').strip()
        txn_type = request.form.get('type', 'expense').strip().lower()
        category = request.form.get('category', '').strip()
        merchant = request.form.get('merchant', '').strip() or 'N/A'
        payment_method = request.form.get('payment_method', '').strip() or 'Cash'
        date_str = request.form.get('date', '').strip() or date.today().isoformat()

        if not description or not amount:
            flash('Please provide a transaction description and amount.', 'danger')
            return redirect(url_for('transactions.transactions'))
        if len(description) > 255 or txn_type not in {'income', 'expense'}:
            flash('Enter a shorter description and choose a valid transaction type.', 'danger')
            return redirect(url_for('transactions.transactions'))
        try:
            amount_value = parse_positive_amount(amount)
            transaction_date = parse_date(date_str)
        except ValueError as exc:
            flash(str(exc), 'danger')
            return redirect(url_for('transactions.transactions'))

        predicted_label = None
        if txn_type == 'expense':
            if not category or category.lower() == 'auto':
                prediction = predict_category(description)
                if prediction['needs_manual_category']:
                    flash(
                        f"Low classifier confidence ({prediction['confidence']:.0%}). "
                        'Please choose a category manually.',
                        'warning',
                    )
                    return redirect(url_for('transactions.transactions'))
                category = prediction['category']
                predicted_label = prediction['suggested_category']
            elif category not in CATEGORIES:
                flash('Choose one of the available expense categories.', 'danger')
                return redirect(url_for('transactions.transactions'))

        if txn_type == 'income':
            category = 'Income'

        transaction = Transaction(
            user_id=current_user.id,
            description=description,
            amount=amount_value,
            date=transaction_date,
            type=txn_type,
            category=category,
            merchant=merchant,
            payment_method=payment_method,
            predicted_category=predicted_label,
        )
        db.session.add(transaction)
        db.session.commit()

        flash('Transaction saved successfully.', 'success')
        return redirect(url_for('transactions.transactions'))

    query = Transaction.query.filter_by(user_id=current_user.id)
    q = request.args.get('q', '').strip()
    txn_type_filter = request.args.get('type', '').strip().lower()
    category_filter = request.args.get('category', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    sort = request.args.get('sort', 'date_desc')
    if q:
        query = query.filter(
            or_(
                Transaction.description.ilike(f'%{q}%'),
                Transaction.merchant.ilike(f'%{q}%'),
                Transaction.category.ilike(f'%{q}%'),
            )
        )
    if txn_type_filter in {'income', 'expense'}:
        query = query.filter_by(type=txn_type_filter)
    if category_filter in CATEGORIES:
        query = query.filter_by(category=category_filter)
    try:
        if date_from:
            query = query.filter(Transaction.date >= parse_date(date_from, 'Start date'))
        if date_to:
            query = query.filter(Transaction.date <= parse_date(date_to, 'End date'))
        if date_from and date_to and date_from > date_to:
            raise ValueError('Start date must not be later than end date.')
    except ValueError as exc:
        flash(str(exc), 'warning')
    if sort == 'amount_asc':
        query = query.order_by(Transaction.amount.asc(), Transaction.date.desc())
    elif sort == 'amount_desc':
        query = query.order_by(Transaction.amount.desc(), Transaction.date.desc())
    elif sort == 'date_asc':
        query = query.order_by(Transaction.date.asc(), Transaction.id.asc())
    else:
        sort = 'date_desc'
        query = query.order_by(Transaction.date.desc(), Transaction.id.desc())

    transactions = query.all()
    return render_template(
        'transactions.html',
        transactions=transactions,
        active_filter=txn_type_filter,
        search=q,
        category_filter=category_filter,
        date_from=date_from,
        date_to=date_to,
        sort=sort,
        categories=CATEGORIES,
    )


@transactions_bp.route('/transactions/<int:transaction_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_transaction(transaction_id):
    transaction = Transaction.query.filter_by(id=transaction_id, user_id=current_user.id).first_or_404()

    if request.method == 'POST':
        description = request.form.get('description', '').strip()
        txn_type = request.form.get('type', '').strip().lower()
        category = request.form.get('category', '').strip()
        try:
            if not description or len(description) > 255 or txn_type not in {'income', 'expense'}:
                raise ValueError('Provide a description and a valid transaction type.')
            transaction.amount = parse_positive_amount(request.form.get('amount', ''))
            transaction.date = parse_date(request.form.get('date', ''), 'Transaction date')
            if txn_type == 'expense' and category not in CATEGORIES:
                raise ValueError('Choose one of the available expense categories.')
        except ValueError as exc:
            flash(str(exc), 'danger')
            return redirect(url_for('transactions.edit_transaction', transaction_id=transaction.id))
        transaction.description = description
        transaction.type = txn_type
        transaction.category = category if txn_type == 'expense' else 'Income'
        transaction.merchant = request.form.get('merchant', '').strip()[:120] or 'N/A'
        transaction.payment_method = request.form.get('payment_method', '').strip()[:50] or 'Cash'
        db.session.commit()
        flash('Transaction updated.', 'success')
        return redirect(url_for('transactions.transactions'))

    return render_template('transactions_edit.html', transaction=transaction)


@transactions_bp.route('/transactions/<int:transaction_id>/delete', methods=['POST'])
@login_required
def delete_transaction(transaction_id):
    transaction = Transaction.query.filter_by(id=transaction_id, user_id=current_user.id).first_or_404()
    db.session.delete(transaction)
    db.session.commit()
    flash('Transaction deleted successfully.', 'success')
    return redirect(url_for('transactions.transactions'))
