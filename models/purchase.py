from datetime import datetime, timezone

from .database import db


class PlannedPurchase(db.Model):
    __tablename__ = 'planned_purchases'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    item_name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    reason = db.Column(db.Text, nullable=True)
    decision = db.Column(db.String(20), default='Pending')
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class AvoidPreference(db.Model):
    __tablename__ = 'avoid_preferences'
    __table_args__ = (db.UniqueConstraint('user_id', 'term', name='uq_avoid_user_term'),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    term = db.Column(db.String(120), nullable=False)


class ShoppingPreference(db.Model):
    __tablename__ = 'shopping_preferences'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    monthly_limit = db.Column(db.Float, nullable=True)
