import csv
import hashlib
import json
import logging
from collections import defaultdict
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.feature_extraction import DictVectorizer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

BASE_DIR = Path(__file__).resolve().parent.parent
DATASET_PATH = BASE_DIR / 'dataset' / 'expense_dataset.csv'
MODEL_PATH = BASE_DIR / 'ml' / 'expense_classifier.joblib'
METRICS_PATH = BASE_DIR / 'ml' / 'model_metrics.json'
CATEGORY_OPTIONS = (
    'Food', 'Transport', 'Shopping', 'Bills', 'Entertainment', 'Health',
    'Education', 'Other',
)
MIN_CLASSIFICATION_CONFIDENCE = 0.45
logger = logging.getLogger(__name__)


def _read_dataset():
    with DATASET_PATH.open('r', newline='', encoding='utf-8-sig') as handle:
        rows = [
            {
                'description': ' '.join(row.get('description', '').split()),
                'category': row.get('category', '').strip(),
            }
            for row in csv.DictReader(handle)
        ]
    rows = [
        row for row in rows
        if row['description'] and row['category'] in CATEGORY_OPTIONS
    ]
    if not rows:
        raise ValueError('Expense training dataset has no valid labelled rows.')
    return rows


def _dataset_digest():
    return hashlib.sha256(DATASET_PATH.read_bytes()).hexdigest()


def train_model_if_needed(force=False):
    DATASET_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not DATASET_PATH.exists():
        raise FileNotFoundError(f'Training dataset was not found: {DATASET_PATH}')

    dataset_hash = _dataset_digest()
    metadata = None
    if not force and MODEL_PATH.exists() and METRICS_PATH.exists():
        try:
            metadata = json.loads(METRICS_PATH.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            metadata = None
        if metadata and metadata.get('dataset_sha256') == dataset_hash:
            try:
                joblib.load(MODEL_PATH)
            except (OSError, EOFError, ImportError, AttributeError, ValueError):
                logger.warning('Saved classifier could not be loaded; retraining it.')
            else:
                return metadata

    rows = _read_dataset()
    descriptions = [row['description'] for row in rows]
    categories = [row['category'] for row in rows]
    counts = defaultdict(int)
    for label in categories:
        counts[label] += 1
    if len(counts) < 2 or min(counts.values()) < 2:
        raise ValueError('At least two examples per category are required to evaluate the classifier.')

    test_fraction = max(0.25, len(counts) / len(rows))
    X_train, X_test, y_train, y_test = train_test_split(
        descriptions,
        categories,
        test_size=test_fraction,
        random_state=42,
        stratify=categories,
    )
    model = Pipeline([
        ('tfidf', TfidfVectorizer(lowercase=True, stop_words='english', ngram_range=(1, 2))),
        ('classifier', LogisticRegression(max_iter=500, class_weight='balanced')),
    ])
    model.fit(X_train, y_train)
    predictions = model.predict(X_test)
    labels = sorted(set(categories))
    metrics = {
        'status': 'trained',
        'algorithm': 'TF-IDF + Logistic Regression',
        'dataset_sha256': dataset_hash,
        'dataset_rows': len(rows),
        'train_rows': len(X_train),
        'test_rows': len(X_test),
        'labels': labels,
        'accuracy': round(float(accuracy_score(y_test, predictions)), 4),
        'precision': round(float(precision_score(y_test, predictions, average='weighted', zero_division=0)), 4),
        'recall': round(float(recall_score(y_test, predictions, average='weighted', zero_division=0)), 4),
        'f1': round(float(f1_score(y_test, predictions, average='weighted', zero_division=0)), 4),
        'confusion_matrix': confusion_matrix(y_test, predictions, labels=labels).tolist(),
    }

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    METRICS_PATH.write_text(json.dumps(metrics, indent=2), encoding='utf-8')
    return metrics


def predict_category(description):
    cleaned = ' '.join(str(description).split())
    if not cleaned:
        raise ValueError('A non-empty transaction description is required.')
    metrics = train_model_if_needed()
    model = joblib.load(MODEL_PATH)
    probabilities = model.predict_proba([cleaned])[0]
    index = int(np.argmax(probabilities))
    confidence = float(probabilities[index])
    suggestion = str(model.classes_[index])
    accepted = confidence >= MIN_CLASSIFICATION_CONFIDENCE
    return {
        'category': suggestion if accepted else None,
        'suggested_category': suggestion,
        'confidence': round(confidence, 4),
        'minimum_confidence': MIN_CLASSIFICATION_CONFIDENCE,
        'needs_manual_category': not accepted,
        'model_accuracy': metrics['accuracy'],
    }


def get_model_metrics():
    return train_model_if_needed()


def forecast_monthly_expenses(transactions, minimum_months=4):
    monthly_totals = defaultdict(float)
    for transaction in transactions:
        if transaction.type == 'expense':
            monthly_totals[transaction.date.strftime('%Y-%m')] += transaction.amount

    if not monthly_totals:
        return {'available': False, 'reason': 'No expense history is available.'}

    first_month = min(monthly_totals)
    last_month = max(monthly_totals)
    year, month = (int(value) for value in first_month.split('-'))
    labels = []
    values = []
    while (year, month) <= tuple(int(value) for value in last_month.split('-')):
        label = f'{year:04d}-{month:02d}'
        labels.append(label)
        values.append(float(monthly_totals.get(label, 0.0)))
        month += 1
        if month == 13:
            year += 1
            month = 1

    if len(labels) < minimum_months:
        return {
            'available': False,
            'reason': f'At least {minimum_months} months of expense history are needed; {len(labels)} found.',
            'labels': labels,
            'values': values,
        }

    x_values = np.arange(len(values), dtype=float).reshape(-1, 1)
    model = LinearRegression().fit(x_values, values)
    prediction = max(0.0, float(model.predict([[len(values)]])[0]))
    result = {
        'available': True,
        'next_month': _next_month_label(labels[-1]),
        'prediction': round(prediction, 2),
        'labels': labels,
        'values': [round(value, 2) for value in values],
        'mae': None,
        'rmse': None,
        'r2': None,
        'explanation': 'A linear trend fitted to your recorded monthly expense totals; this is an estimate, not a guarantee.',
    }
    if len(values) >= 7:
        split_at = len(values) - 3
        test_model = LinearRegression().fit(x_values[:split_at], values[:split_at])
        test_predictions = test_model.predict(x_values[split_at:])
        result['mae'] = round(float(mean_absolute_error(values[split_at:], test_predictions)), 2)
        result['rmse'] = round(float(np.sqrt(mean_squared_error(values[split_at:], test_predictions))), 2)
        result['r2'] = round(float(r2_score(values[split_at:], test_predictions)), 4)
    return result


def _next_month_label(month_label):
    year, month = (int(value) for value in month_label.split('-'))
    if month == 12:
        return f'{year + 1:04d}-01'
    return f'{year:04d}-{month + 1:02d}'


def detect_unusual_transactions(transactions, minimum_samples=10):
    expenses = [item for item in transactions if item.type == 'expense']
    if len(expenses) < minimum_samples:
        return {
            'available': False,
            'reason': f'At least {minimum_samples} expense transactions are needed; {len(expenses)} found.',
            'alerts': [],
        }

    features = [
        {
            'log_amount': float(np.log1p(max(item.amount, 0))),
            f'category={item.category.lower()}': 1.0,
            'weekday': float(item.date.weekday()),
            'day_of_month': float(item.date.day),
        }
        for item in expenses
    ]
    vectorizer = DictVectorizer()
    matrix = vectorizer.fit_transform(features)
    detector = IsolationForest(contamination='auto', random_state=42)
    labels = detector.fit_predict(matrix)
    scores = detector.decision_function(matrix)
    category_amounts = defaultdict(list)
    for item in expenses:
        category_amounts[item.category].append(item.amount)

    alerts = []
    for idx, label in enumerate(labels):
        if label != -1:
            continue
        item = expenses[idx]
        history = category_amounts[item.category]
        average = sum(history) / len(history)
        alerts.append({
            'id': item.id,
            'category': item.category,
            'description': item.description,
            'amount': round(item.amount, 2),
            'average': round(average, 2),
            'difference': round(item.amount - average, 2),
            'anomaly_score': round(float(scores[idx]), 4),
            'reason': (
                'Isolation Forest identified this transaction as an unusual pattern in your own recorded expenses. '
                f'The {item.category.lower()} category average is ₹{average:,.2f}. This is not evidence of fraud.'
            ),
        })
    return {'available': True, 'reason': None, 'alerts': alerts}
