from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from .database import db


class User(db.Model, UserMixin):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    fullname = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    session_version = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    transactions = db.relationship('Transaction', backref='user', lazy=True)
    budgets = db.relationship('Budget', backref='user', lazy=True)
    goals = db.relationship('SavingsGoal', backref='user', lazy=True)
    bills = db.relationship('BillReminder', backref='user', lazy=True)
    purchases = db.relationship('PlannedPurchase', backref='user', lazy=True)
    subscriptions = db.relationship('Subscription', backref='user', lazy=True)
    notifications = db.relationship('Notification', backref='user', lazy=True)
    insights = db.relationship('Insight', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_id(self):
        return f'{self.id}:{self.session_version}'
