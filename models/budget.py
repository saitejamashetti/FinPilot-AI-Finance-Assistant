from datetime import datetime, timezone

from sqlalchemy import UniqueConstraint

from .database import db


class Budget(db.Model):
    __tablename__ = 'budgets'
    __table_args__ = (
        UniqueConstraint('user_id', 'category', 'month', name='uq_budget_user_category_month'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    month = db.Column(db.String(7), nullable=False)
    limit_amount = db.Column(db.Float, nullable=False)
    alert_threshold = db.Column(db.Float, default=80.0)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
