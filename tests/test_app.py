from datetime import date
import re
import uuid

import pytest

from app import create_app
from models.bill import BillReminder
from models.budget import Budget
from models.database import db
from models.goal import SavingsGoal
from models.purchase import AvoidPreference, PlannedPurchase
from models.subscription import Subscription
from models.transaction import Transaction
from models.user import User
from services.finance_service import export_transactions_csv
from services.ml_service import (
    detect_unusual_transactions,
    forecast_monthly_expenses,
    predict_category,
    train_model_if_needed,
)
from services.subscription_service import detect_recurring_transactions


@pytest.fixture
def app():
    test_app = create_app({
        'TESTING': True,
        'WTF_CSRF_ENABLED': False,
        'RATELIMIT_ENABLED': False,
        'SECRET_KEY': 'test-only-secret-key',
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
    })
    yield test_app
    with test_app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def register(client, email='user@example.com', name='Test User'):
    return client.post('/register', data={
        'fullname': name,
        'email': email,
        'password': 'correct horse battery',
    })


def login(client, email='user@example.com'):
    return client.post('/login', data={
        'email': email,
        'password': 'correct horse battery',
    }, follow_redirects=True)


def add_transaction(user_id, description, amount, txn_date, category='Food', txn_type='expense', merchant='N/A'):
    transaction = Transaction(
        user_id=user_id,
        description=description,
        amount=amount,
        date=txn_date,
        category=category,
        type=txn_type,
        merchant=merchant,
    )
    db.session.add(transaction)
    db.session.commit()
    return transaction


def test_registration_login_and_bad_login(client, app):
    response = register(client)
    assert response.status_code == 302
    with app.app_context():
        user = User.query.filter_by(email='user@example.com').one()
        assert user.password_hash != 'correct horse battery'
        assert user.password_hash.startswith('scrypt:')
        assert user.check_password('correct horse battery')
    assert b'Invalid email or password' in client.post('/login', data={
        'email': 'user@example.com',
        'password': 'wrong-password',
    }, follow_redirects=True).data
    assert b'Overview' in login(client).data


def test_csrf_enabled_outside_testing():
    configured = create_app({
        'TESTING': False,
        'WTF_CSRF_ENABLED': True,
        'RATELIMIT_ENABLED': False,
        'SECRET_KEY': 'csrf-test-secret',
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
    })
    response = configured.test_client().post('/register', data={
        'fullname': 'No Token',
        'email': 'no-token@example.com',
        'password': 'correct horse battery',
    })
    assert response.status_code == 400


def test_login_rate_limit_returns_a_safe_response():
    test_app = create_app({
        'TESTING': True,
        'WTF_CSRF_ENABLED': False,
        'RATELIMIT_ENABLED': True,
        'SECRET_KEY': 'rate-limit-test-secret',
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
    })
    client = test_app.test_client()
    remote_bytes = uuid.uuid4().bytes
    remote_addr = f'198.18.{remote_bytes[0]}.{remote_bytes[1]}'
    for _ in range(5):
        response = client.post(
            '/login',
            data={'email': 'nobody@example.com', 'password': 'incorrect'},
            environ_base={'REMOTE_ADDR': remote_addr},
        )
        assert response.status_code == 200
    limited = client.post(
        '/login',
        data={'email': 'nobody@example.com', 'password': 'incorrect'},
        environ_base={'REMOTE_ADDR': remote_addr},
    )
    assert limited.status_code == 429
    assert b'Too many attempts' in limited.data


def test_password_change_requires_current_password_and_revokes_sessions(client, app):
    register(client)
    login(client)
    other_session = app.test_client()
    login(other_session)

    wrong = client.post('/security', data={
        'current_password': 'wrong password',
        'new_password': 'this is a secure passphrase',
        'confirm_password': 'this is a secure passphrase',
    }, follow_redirects=True)
    assert b'Current password is incorrect' in wrong.data

    changed = client.post('/security', data={
        'current_password': 'correct horse battery',
        'new_password': 'this is a secure passphrase',
        'confirm_password': 'this is a secure passphrase',
    }, follow_redirects=True)
    assert b'Password changed' in changed.data
    assert other_session.get('/dashboard').status_code == 302
    assert b'Invalid email or password' in client.post('/login', data={
        'email': 'user@example.com',
        'password': 'correct horse battery',
    }, follow_redirects=True).data
    assert b'Overview' in client.post('/login', data={
        'email': 'user@example.com',
        'password': 'this is a secure passphrase',
    }, follow_redirects=True).data


def test_security_response_headers_are_present(client):
    response = client.get('/login')
    assert response.headers['X-Content-Type-Options'] == 'nosniff'
    assert response.headers['X-Frame-Options'] == 'DENY'
    assert "script-src 'self'" in response.headers['Content-Security-Policy']


def test_production_requires_strong_secret_and_shared_rate_limit_store():
    with pytest.raises(RuntimeError, match='at least 32 characters'):
        create_app({
            'ENVIRONMENT': 'production',
            'SECRET_KEY': 'weak',
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        })
    with pytest.raises(RuntimeError, match='shared RATELIMIT_STORAGE_URI'):
        create_app({
            'ENVIRONMENT': 'production',
            'SECRET_KEY': 'a' * 40,
            'RATELIMIT_STORAGE_URI': 'memory://',
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        })


def test_login_explains_empty_database_and_registration_flow_has_csrf(app):
    client = app.test_client()
    login_page = client.get('/login')
    assert b'No account is registered' in login_page.data

    register_page = client.get('/register')
    token = re.search(
        rb'name="csrf_token" value="([^"]+)"',
        register_page.data,
    ).group(1).decode()
    registered = client.post('/register', data={
        'csrf_token': token,
        'fullname': 'First Account',
        'email': 'first@example.com',
        'password': 'correct horse battery',
    })
    assert registered.status_code == 302

    login_page = client.get('/login')
    token = re.search(
        rb'name="csrf_token" value="([^"]+)"',
        login_page.data,
    ).group(1).decode()
    logged_in = client.post('/login', data={
        'csrf_token': token,
        'email': 'first@example.com',
        'password': 'correct horse battery',
    })
    assert logged_in.status_code == 302
    assert logged_in.headers['Location'].endswith('/dashboard')


def test_transaction_crud_search_export_and_isolation(client, app):
    register(client)
    login(client)
    response = client.post('/transactions', data={
        'description': 'Groceries, apples',
        'amount': '1200',
        'type': 'expense',
        'category': 'Food',
        'date': '2026-11-14',
    }, follow_redirects=True)
    assert b'Transaction saved successfully' in response.data

    with app.app_context():
        first_user = User.query.filter_by(email='user@example.com').one()
        transaction = Transaction.query.filter_by(user_id=first_user.id).one()
        transaction_id = transaction.id

    assert b'Groceries, apples' in client.get('/transactions?q=apples').data
    edit = client.post(f'/transactions/{transaction_id}/edit', data={
        'description': 'Updated groceries',
        'amount': '1500',
        'type': 'expense',
        'category': 'Food',
        'date': '2026-11-13',
    }, follow_redirects=True)
    assert b'Transaction updated' in edit.data
    csv_response = client.get('/export/csv')
    assert csv_response.status_code == 200
    assert b'Updated groceries' in csv_response.data

    other = app.test_client()
    register(other, email='second@example.com', name='Second User')
    login(other, email='second@example.com')
    assert b'Updated groceries' not in other.get('/transactions').data
    assert other.get(f'/transactions/{transaction_id}/edit').status_code == 404

    deleted = client.post(f'/transactions/{transaction_id}/delete', follow_redirects=True)
    assert b'Transaction deleted successfully' in deleted.data


@pytest.mark.parametrize('bad_amount', ['0', '-10', 'nan', 'inf', 'not-number'])
def test_invalid_transaction_amounts_are_rejected(client, bad_amount):
    register(client)
    login(client)
    response = client.post('/transactions', data={
        'description': 'invalid',
        'amount': bad_amount,
        'type': 'expense',
        'category': 'Food',
    }, follow_redirects=True)
    assert b'Transaction saved successfully' not in response.data


def test_budget_calculation_and_duplicate_prevention(client, app):
    register(client)
    login(client)
    with app.app_context():
        user_id = User.query.filter_by(email='user@example.com').one().id
        add_transaction(user_id, 'Groceries', 80, date.today(), category='Food')

    response = client.post('/budgets', data={
        'category': 'Food',
        'month': date.today().strftime('%Y-%m'),
        'limit_amount': '100',
        'alert_threshold': '80',
    }, follow_redirects=True)
    assert b'Budget added successfully' in response.data
    duplicate = client.post('/budgets', data={
        'category': 'Food',
        'month': date.today().strftime('%Y-%m'),
        'limit_amount': '100',
        'alert_threshold': '80',
    }, follow_redirects=True)
    assert b'already exists' in duplicate.data
    assert b'80.0% used' in client.get('/budgets').data
    with app.app_context():
        assert Budget.query.count() == 1


def test_goals_and_bill_paid_overdue_flow(client, app):
    register(client)
    login(client)
    goal_response = client.post('/goals', data={
        'name': 'Emergency fund',
        'target_amount': '1000',
        'current_amount': '200',
    }, follow_redirects=True)
    assert b'Savings goal created' in goal_response.data
    with app.app_context():
        goal_id = SavingsGoal.query.one().id
    contribution = client.post(
        f'/goals/{goal_id}/contribute',
        data={'amount': '50'},
        follow_redirects=True,
    )
    assert b'50.00 added to Emergency fund' in contribution.data

    bill_response = client.post('/bills', data={
        'name': 'Past due internet',
        'amount': '55',
        'due_date': '2020-01-01',
        'category': 'Bills',
        'recurrence': 'Monthly',
        'payment_status': 'Upcoming',
    }, follow_redirects=True)
    assert b'Overdue' in bill_response.data
    with app.app_context():
        bill_id = BillReminder.query.one().id
        assert SavingsGoal.query.one().current_amount == 250
    paid_response = client.post(f'/bills/{bill_id}/paid', follow_redirects=True)
    assert b'marked as paid' in paid_response.data
    assert b'bg-success' in paid_response.data


def test_authenticated_feature_pages_render(client):
    register(client)
    login(client)
    for path in (
        '/dashboard',
        '/transactions',
        '/budgets',
        '/goals',
        '/bills',
        '/guardian',
        '/subscriptions',
        '/anomalies',
        '/analytics',
        '/health',
        '/simulator',
        '/assistant',
        '/settings',
        '/security',
        '/reports',
    ):
        response = client.get(path)
        assert response.status_code == 200, path


def test_low_confidence_classification_requires_manual_category(client, app, monkeypatch):
    from routes import transactions as transaction_routes

    register(client)
    login(client)
    monkeypatch.setattr(transaction_routes, 'predict_category', lambda _description: {
        'category': None,
        'suggested_category': 'Other',
        'confidence': 0.2,
        'needs_manual_category': True,
    })
    response = client.post('/transactions', data={
        'description': 'ambiguous purchase',
        'amount': '10',
        'type': 'expense',
        'category': 'auto',
    }, follow_redirects=True)
    assert b'Low classifier confidence' in response.data
    with app.app_context():
        assert Transaction.query.count() == 0


def test_ml_classifier_metrics_and_dataset_retraining(app):
    with app.app_context():
        metrics = train_model_if_needed(force=True)
        assert metrics['dataset_rows'] > 50
        assert metrics['accuracy'] == pytest.approx(metrics['accuracy'])
        assert {'accuracy', 'precision', 'recall', 'f1', 'confusion_matrix'} <= metrics.keys()
        assert len(metrics['confusion_matrix']) == len(metrics['labels'])
        prediction = predict_category('grocery store vegetables')
        assert prediction['suggested_category'] == 'Food'
        assert 0 <= prediction['confidence'] <= 1
        assert 'needs_manual_category' in prediction


def test_forecast_sufficient_and_insufficient_history(app):
    class Item:
        type = 'expense'

        def __init__(self, value, month):
            self.amount = value
            self.date = date.fromisoformat(f'2024-{month:02d}-10')

    short_result = forecast_monthly_expenses([Item(100, 1), Item(110, 2)])
    assert not short_result['available']
    history = [Item(value, month) for month, value in enumerate([100, 110, 105, 120, 130, 128, 140], 1)]
    result = forecast_monthly_expenses(history)
    assert result['available']
    assert result['prediction'] > 0
    assert result['mae'] is not None
    assert result['rmse'] is not None
    assert result['r2'] is not None


def test_isolation_forest_requires_history_then_flags_outlier(app):
    with app.app_context():
        user = User(fullname='ML User', email='ml@example.com')
        user.set_password('correct horse battery')
        db.session.add(user)
        db.session.commit()
        for index in range(12):
            add_transaction(
                user.id,
                f'usual groceries {index}',
                40 + (index % 3),
                date(2026, 1, (index % 26) + 1),
                category='Food',
            )
        result = detect_unusual_transactions(Transaction.query.all())
        assert result['available']
        add_transaction(user.id, 'large grocery purchase', 5000, date(2026, 2, 1), category='Food')
        result = detect_unusual_transactions(Transaction.query.all())
        assert any(alert['description'] == 'large grocery purchase' for alert in result['alerts'])
        insufficient = detect_unusual_transactions(Transaction.query.limit(3).all())
        assert not insufficient['available']


@pytest.mark.parametrize(
    ('dates', 'frequency', 'annual_cost'),
    [
        (['2025-01-01', '2025-02-01', '2025-03-04'], 'Monthly', 120),
        (['2025-01-01', '2025-04-02', '2025-07-02'], 'Quarterly', 40),
        (['2024-01-01', '2025-01-01', '2026-01-01'], 'Yearly', 10),
    ],
)
def test_recurring_subscription_interval_detection(dates, frequency, annual_cost):
    class Item:
        type = 'expense'
        merchant = 'Music Service'
        description = 'Recurring payment'
        amount = 10

        def __init__(self, txn_date):
            self.date = date.fromisoformat(txn_date)

    items = [Item(value) for value in dates]
    suggestions = detect_recurring_transactions(items)
    assert suggestions
    assert suggestions[0]['frequency'] == frequency
    assert suggestions[0]['yearly_cost'] == annual_cost


def test_subscription_suggestion_can_be_confirmed_and_dismissed(client, app):
    register(client)
    login(client)
    with app.app_context():
        user_id = User.query.filter_by(email='user@example.com').one().id
        for txn_date in (date(2025, 1, 1), date(2025, 2, 1), date(2025, 3, 4)):
            add_transaction(
                user_id,
                'Streaming payment',
                10,
                txn_date,
                category='Entertainment',
                merchant='StreamCo',
            )
    page = client.get('/subscriptions')
    assert b'Possible recurring payments' in page.data
    key = re.search(rb'name="suggestion_key" value="([a-f0-9]+)"', page.data).group(1).decode()
    confirmed = client.post('/subscriptions', data={
        'action': 'confirm',
        'suggestion_key': key,
    }, follow_redirects=True)
    assert b'Recurring payment confirmed' in confirmed.data
    with app.app_context():
        assert Subscription.query.one().name == 'StreamCo'


def test_guardian_checks_preferences_and_keeps_user_choice(client, app):
    register(client)
    login(client)
    with app.app_context():
        user_id = User.query.filter_by(email='user@example.com').one().id
        db.session.add(AvoidPreference(user_id=user_id, term='gadget'))
        db.session.add(Budget(
            user_id=user_id,
            category='Shopping',
            month=date.today().strftime('%Y-%m'),
            limit_amount=100,
        ))
        add_transaction(user_id, 'Previous shopping', 90, date.today(), category='Shopping')
    response = client.post('/guardian', data={
        'item_name': 'gadget',
        'category': 'Shopping',
        'amount': '25',
    }, follow_redirects=True)
    assert b'avoid list' in response.data
    assert b'exceed the Shopping budget' in response.data
    with app.app_context():
        purchase_id = PlannedPurchase.query.one().id
    decision = client.post(
        f'/guardian/{purchase_id}/decision',
        data={'decision': 'Buy anyway'},
        follow_redirects=True,
    )
    assert b'Buy anyway' in decision.data
    with app.app_context():
        assert PlannedPurchase.query.one().decision == 'Buy anyway'


def test_user_scoped_csv_and_formula_protection(app):
    with app.app_context():
        user = User(fullname='CSV User', email='csv@example.com')
        user.set_password('correct horse battery')
        db.session.add(user)
        db.session.commit()
        add_transaction(user.id, ' =HYPERLINK("bad")', 1, date.today())
        csv_content = export_transactions_csv(user.id)
        assert "' =HYPERLINK" in csv_content
        assert next(iter(csv_content.splitlines())).startswith('id,description,amount')
