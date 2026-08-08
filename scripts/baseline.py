"""
Thực nghiệm 1 - Baseline: TF-IDF + Logistic Regression.

Mô hình truyền thống dùng để đối chứng với Transformer:
- TF-IDF với n-gram (1,2) ở mức từ.
- Logistic Regression (solver lbfgs, max_iter 2000).
"""

import time

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

from .evaluate import (
    compute_metrics,
    print_metrics_table,
    save_confusion_matrix,
    save_metrics_json,
    save_pr_curve,
)

MODEL_NAME = "TF-IDF + Logistic Regression"


def run_baseline(
    splits: dict[str, pd.DataFrame],
    max_features: int = 50000,
    ngram_range: tuple[int, int] = (1, 2),
) -> dict:
    """
    Huấn luyện baseline trên train, đánh giá trên test.
    Trả về dict metrics đầy đủ (dùng cho bảng so sánh).
    """
    X_train = splits["train"]["text_clean"].tolist()
    y_train = splits["train"]["label_id"].to_numpy()
    X_test = splits["test"]["text_clean"].tolist()
    y_test = splits["test"]["label_id"].to_numpy()

    print("[baseline] Vector hoá TF-IDF (ngram_range={}, max_features={})...".format(
        ngram_range, max_features
    ))
    vectorizer = TfidfVectorizer(
        ngram_range=ngram_range,
        min_df=2,
        sublinear_tf=True,
        max_features=max_features,
    )
    X_train_tfidf = vectorizer.fit_transform(X_train)
    X_test_tfidf = vectorizer.transform(X_test)
    print(f"[baseline] Kích thước ma trận TF-IDF: {X_train_tfidf.shape}")

    clf = LogisticRegression(max_iter=2000, C=1.0, solver="lbfgs", random_state=42)

    t0 = time.time()
    clf.fit(X_train_tfidf, y_train)
    train_time = time.time() - t0

    y_pred = clf.predict(X_test_tfidf)
    proba = clf.predict_proba(X_test_tfidf)

    metrics = compute_metrics(
        y_test, y_pred, model_name=MODEL_NAME, train_time=train_time
    )
    print_metrics_table(metrics)

    save_confusion_matrix(
        y_test, y_pred, "baseline_tfidf_lr", "Confusion Matrix - TF-IDF + Logistic Regression"
    )
    save_pr_curve(
        y_test, proba, "baseline_tfidf_lr", "Precision-Recall - TF-IDF + Logistic Regression"
    )
    save_metrics_json(metrics, "baseline_tfidf_lr")
    return metrics
