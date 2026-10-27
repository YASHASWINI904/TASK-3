from pathlib import Path
import csv
import re
import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_recall_fscore_support

BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "data" / "reviews.csv"
MODEL_PATH = BASE_DIR / "model" / "sentiment_pipeline.joblib"
MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)

class SentimentModel:
    def __init__(self):
        self.pipeline = None
        self.metrics = None
        self.trained_at = None

    def train(self):
        # Use Python's built-in CSV reader. This avoids requiring pandas' compiled
        # extensions while preserving the same text/label training workflow.
        texts, labels = [], []
        with DATA_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or not {"text", "label"}.issubset(set(reader.fieldnames)):
                raise ValueError("Dataset must contain 'text' and 'label' columns.")
            for row in reader:
                raw_text, raw_label = row.get("text"), row.get("label")
                if raw_text is None or raw_label is None:
                    continue
                text = str(raw_text).strip()
                label = str(raw_label).lower().strip()
                if text and label:
                    texts.append(text)
                    labels.append(label)

        unique_labels = sorted(set(labels))
        if len(unique_labels) < 2:
            raise ValueError("Training data must contain at least two sentiment labels.")
        from collections import Counter
        counts = Counter(labels)
        stratify = labels if min(counts.values()) >= 2 else None
        X_train, X_test, y_train, y_test = train_test_split(
            texts, labels, test_size=0.20, random_state=42, stratify=stratify
        )
        pipeline = Pipeline([
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), max_features=12000,
                                      lowercase=True, strip_accents="unicode")),
            ("classifier", LogisticRegression(max_iter=1000, class_weight="balanced"))
        ])
        pipeline.fit(X_train, y_train)
        predictions = pipeline.predict(X_test)
        self.pipeline = pipeline
        precision, recall, f1, _ = precision_recall_fscore_support(
            y_test, predictions, labels=unique_labels, average="macro", zero_division=0
        )
        self.metrics = {
            "accuracy": round(float(accuracy_score(y_test, predictions)), 4),
            "macro_precision": round(float(precision), 4),
            "macro_recall": round(float(recall), 4),
            "macro_f1": round(float(f1), 4),
            "training_samples": int(len(X_train)),
            "test_samples": int(len(X_test)),
            "labels": unique_labels,
            "dataset_samples": int(len(texts)),
            "evaluation_note": "Scores use a stratified hold-out split of synthetic educational examples and may overestimate real-world performance."
        }
        joblib.dump({"pipeline": pipeline, "metrics": self.metrics}, MODEL_PATH)
        from datetime import datetime, timezone
        self.trained_at = datetime.now(timezone.utc).isoformat()
        return self.metrics

    def load(self):
        if MODEL_PATH.exists():
            saved = joblib.load(MODEL_PATH)
            self.pipeline = saved["pipeline"]
            self.metrics = saved.get("metrics")
            return True
        return False

    @staticmethod
    def _negation_sentiment(text):
        """Handle common negated sentiment phrases that bag-of-words models miss.

        Examples: “not bad” is positive, while “not good” is negative.
        This is a small, explicit rule layer on top of the trained model, not a
        replacement for the model; ambiguous sarcasm still needs context.
        """
        normalized = re.sub(r"[^a-z0-9' ]+", " ", text.lower())
        normalized = re.sub(r"\s+", " ", normalized).strip()
        positive_patterns = (
            r"\bnot\s+(?:so\s+)?bad\b",
            r"\bnot\s+(?:at all\s+)?terrible\b",
            r"\bnot\s+(?:at all\s+)?awful\b",
            r"\bnot\s+horrible\b",
            r"\bnot\s+the\s+worst\b",
            r"\bnot\s+disappointing\b",
            r"\bnot\s+useless\b",
            r"\b(?:isn't|isnt|wasn't|wasnt)\s+bad\b",
            r"\bcan't\s+complain\b",
        )
        negative_patterns = (
            r"\bnot\s+(?:very\s+)?good\b",
            r"\bnot\s+great\b",
            r"\bnot\s+excellent\b",
            r"\bnot\s+amazing\b",
            r"\bnot\s+happy\b",
            r"\bnot\s+satisfied\b",
            r"\bnot\s+impressed\b",
            r"\b(?:don't|dont|do not|doesn't|doesnt|didn't|didnt)\s+like\b",
            r"\bnever\s+(?:good|great|reliable|helpful)\b",
        )
        # Check the more direct phrase rules first. “Not only good” is not a
        # negation, so explicitly avoid interpreting it as a negative review.
        if re.search(r"\bnot\s+only\b", normalized):
            return None
        if any(re.search(pattern, normalized) for pattern in positive_patterns):
            return "positive"
        if any(re.search(pattern, normalized) for pattern in negative_patterns):
            return "negative"

        # The training set is intentionally compact and contains fewer common
        # everyday words such as “good” and “love”. Use a conservative lexical
        # fallback for clear single-polarity wording when no negation rule fired.
        positive_words = r"\b(?:good|great|excellent|amazing|wonderful|fantastic|love|loved|lovely|happy|satisfied|helpful|awesome|perfect|enjoy|enjoyed|like|liked)\b"
        negative_words = r"\b(?:bad|terrible|awful|horrible|hate|hated|poor|disappointing|disappointed|worst|broken|useless|unhelpful|angry|unhappy)\b"
        has_positive = bool(re.search(positive_words, normalized))
        has_negative = bool(re.search(negative_words, normalized))
        if has_positive and not has_negative:
            return "positive"
        if has_negative and not has_positive:
            return "negative"
        return None

    def predict(self, text):
        if self.pipeline is None:
            raise RuntimeError("Model is not trained. Call /api/train first.")
        probabilities = self.pipeline.predict_proba([text])[0]
        classes = [str(c) for c in self.pipeline.named_steps["classifier"].classes_]
        scores = {c: float(p) for c, p in zip(classes, probabilities)}

        # TF-IDF models often miss compositional meaning: “not bad” contains
        # the negative token “bad” but usually expresses a positive sentiment.
        override = self._negation_sentiment(text)
        if override in scores:
            # Keep the probabilities calibrated to a clear but not absolute
            # prediction and preserve a valid distribution across all labels.
            target_confidence = 0.80
            other_labels = [c for c in classes if c != override]
            remaining = 1.0 - target_confidence
            other_total = sum(scores[c] for c in other_labels)
            scores[override] = target_confidence
            for c in other_labels:
                scores[c] = remaining * (scores[c] / other_total) if other_total else remaining / max(1, len(other_labels))

        label = max(scores, key=scores.get)
        confidence = scores[label]
        rounded_scores = {c: round(float(v), 4) for c, v in scores.items()}
        return {"sentiment": label, "confidence": round(float(confidence), 4), "scores": rounded_scores}
