"""Train the reason classifier from Tweets.csv (Kaggle Twitter US Airline Sentiment)."""
import sys, json, joblib, pandas as pd
from sklearn.pipeline import Pipeline, FeatureUnion
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score, classification_report
from triage import clean_for_model, THRESHOLD

csv = sys.argv[1]
df = pd.read_csv(csv)
df = df[(df.airline_sentiment == "negative") & df.negativereason.notna()].copy()
df["clean"] = df.text.map(clean_for_model)
df = df.drop_duplicates("clean")
X_tr, X_te, y_tr, y_te = train_test_split(df.clean, df.negativereason, test_size=0.2, stratify=df.negativereason, random_state=42)
feats = FeatureUnion([("w", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)),
                      ("c", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True))])
pipe = Pipeline([("f", feats), ("m", LogisticRegression(max_iter=2000, C=4, class_weight="balanced"))])
pipe.fit(X_tr, y_tr)
pred = pipe.predict(X_te)
proba = pipe.predict_proba(X_te)
conf = proba.max(1)
res = {"n_train": len(X_tr), "n_test": len(X_te), "accuracy": accuracy_score(y_te, pred),
       "baseline": float((y_te == y_tr.value_counts().idxmax()).mean()),
       "f1": {k: round(v["f1-score"], 2) for k, v in classification_report(y_te, pred, output_dict=True).items() if k in pipe.classes_},
       "counts": df.negativereason.value_counts().to_dict(), "threshold": THRESHOLD, "thresholds": {}}
for t in (0.0, 0.5, 0.6, 0.7):
    m = conf >= t
    res["thresholds"][str(t)] = {"coverage": float(m.mean()), "accuracy": float((pred[m] == y_te[m]).mean())}
joblib.dump(pipe, "model/reason_model.joblib")
json.dump(res, open("model/metrics.json", "w"), indent=2)
# small sample for replay (masked at display time); not the full dataset
df.sample(200, random_state=1)[["text", "airline", "negativereason"]].to_csv("data/replay_sample.csv", index=False)
print(json.dumps({k: res[k] for k in ("n_train", "n_test", "accuracy", "baseline", "thresholds")}, indent=1))
