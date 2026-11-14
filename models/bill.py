from datetime import datetime, timezone

from .database import db


class BillReminder(db.Model):
    __tablename__ = 'bill_reminders'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    due_date = db.Column(db.Date, nullable=False)
    category = db.Column(db.String(50), nullable=False, default='Bills')
    recurrence = db.Column(db.String(30), default='Monthly')
    payment_status = db.Column(db.String(20), default='Upcoming')
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
