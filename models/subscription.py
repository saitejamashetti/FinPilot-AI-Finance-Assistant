from datetime import datetime, timezone

from .database import db


class Subscription(db.Model):
    __tablename__ = 'subscriptions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    frequency = db.Column(db.String(30), default='Monthly')
    next_due_date = db.Column(db.Date, nullable=False)
    confirmed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class DismissedSubscription(db.Model):
    __tablename__ = 'dismissed_subscriptions'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'suggestion_key', name='uq_dismissed_subscription_key'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    suggestion_key = db.Column(db.String(64), nullable=False)
