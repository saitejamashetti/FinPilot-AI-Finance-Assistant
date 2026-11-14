import time

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_user, logout_user, login_required
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from models.database import db
from models.user import User
from services.password_policy import validate_new_password
from services.security import limiter
from services.validation import normalize_email


auth_bp = Blueprint('auth', __name__, template_folder='../templates')
_DUMMY_PASSWORD_HASH = generate_password_hash('not-a-real-finpilot-account-password')


@auth_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit('5 per hour', methods=['POST'])
def register():
    if request.method == 'POST':
        fullname = request.form.get('fullname', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        try:
            email = normalize_email(email)
            if not fullname or len(fullname) > 120:
                raise ValueError('Enter your name (up to 120 characters).')
            validate_new_password(password)
        except ValueError as exc:
            flash(str(exc), 'danger')
            return render_template('auth/register.html', fullname=fullname, email=email)
        if User.query.filter_by(email=email).first():
            flash('Could not create an account with those details. Try signing in if you already registered.', 'danger')
            return render_template('auth/register.html', fullname=fullname, email=email)

        user = User(fullname=fullname, email=email)
        user.set_password(password)
        try:
            db.session.add(user)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash('Could not create an account with those details. Try signing in if you already registered.', 'danger')
            return render_template('auth/register.html', fullname=fullname, email=email)
        flash('Registration successful. Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit('5 per minute', methods=['POST'])
@limiter.limit('20 per hour', methods=['POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user = User.query.filter_by(email=email).first() if len(email) <= 120 else None

        if user and len(password) <= 128 and user.check_password(password):
            session.clear()
            login_user(user, remember=False, fresh=True)
            session.permanent = True
            session['_last_activity'] = time.time()
            flash('Welcome back to FinPilot.', 'success')
            return redirect(url_for('main.dashboard'))

        if user is None:
            check_password_hash(_DUMMY_PASSWORD_HASH, password[:128])
        flash('Invalid email or password.', 'danger')

    if request.args.get('expired'):
        flash('Your session expired. Please sign in again.', 'info')
    return render_template('auth/login.html', has_accounts=db.session.query(User.id).first() is not None)


@auth_bp.route('/security', methods=['GET', 'POST'])
@login_required
def account_security():
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirmation = request.form.get('confirm_password', '')

        if len(current_password) > 128 or not current_user.check_password(current_password):
            flash('Current password is incorrect.', 'danger')
        elif new_password != confirmation:
            flash('New password confirmation does not match.', 'danger')
        elif current_password == new_password:
            flash('Choose a new password that differs from your current password.', 'danger')
        else:
            try:
                validate_new_password(new_password)
            except ValueError as exc:
                flash(str(exc), 'danger')
            else:
                current_user.set_password(new_password)
                current_user.session_version += 1
                db.session.commit()
                logout_user()
                session.clear()
                flash('Password changed. Sign in again with your new password.', 'success')
                return redirect(url_for('auth.login'))
    return render_template('security.html')


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('auth.login'))
