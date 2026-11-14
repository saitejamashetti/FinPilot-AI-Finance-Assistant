from datetime import date, datetime, timezone

from .database import db


class Transaction(db.Model):
    __tablename__ = 'transactions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    type = db.Column(db.String(20), nullable=False)  # income / expense
    category = db.Column(db.String(50), nullable=False, default='Other')
    merchant = db.Column(db.String(120), nullable=True)
    payment_method = db.Column(db.String(50), nullable=True)
    predicted_category = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
