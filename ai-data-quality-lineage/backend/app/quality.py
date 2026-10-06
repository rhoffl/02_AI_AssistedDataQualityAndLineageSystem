import json, re
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

def profile_dataframe(df: pd.DataFrame) -> dict:
    columns = {}
    for c in df.columns:
        s = df[c]
        item = {
            "dtype": str(s.dtype), "missing": int(s.isna().sum()),
            "missing_pct": round(float(s.isna().mean()), 4),
            "distinct": int(s.nunique(dropna=True)), "unique_pct": round(float(s.nunique(dropna=True) / max(len(s), 1)), 4)
        }
        if pd.api.types.is_numeric_dtype(s):
            clean = s.dropna()
            item.update({"min": safe(clean.min()), "max": safe(clean.max()), "mean": safe(clean.mean()), "median": safe(clean.median())})
        else:
            item["top_values"] = {str(k): int(v) for k, v in s.fillna("<NULL>").value_counts().head(5).items()}
        columns[str(c)] = item
    return {"rows": len(df), "columns": len(df.columns), "duplicate_rows": int(df.duplicated().sum()), "fields": columns}

def safe(v):
    return None if pd.isna(v) else round(float(v), 6)

def finding(detector, severity, title, evidence, field=None):
    return {"detector": detector, "severity": severity, "title": title, "evidence": evidence, "field": field}

def analyze(df: pd.DataFrame, rules: list[dict], baseline: dict | None = None) -> tuple[dict, list[dict], float]:
    profile = profile_dataframe(df)
    findings = []
    for c, p in profile["fields"].items():
        if p["missing"]:
            findings.append(finding("missing_values", "medium", f"{p['missing']} missing values in {c}", {"count": p["missing"], "rate": p["missing_pct"]}, c))
    if profile["duplicate_rows"]:
        findings.append(finding("duplicates", "high", f"{profile['duplicate_rows']} duplicate rows", {"count": profile["duplicate_rows"]}))
    for rule in rules:
        c, kind, params = rule["column_name"], rule["rule_type"], rule.get("parameters") or {}
        if c not in df.columns:
            findings.append(finding("schema", "critical", f"Required column {c} is missing", {"rule": kind}, c)); continue
        s = df[c]
        invalid = pd.Series(False, index=df.index)
        if kind == "not_null": invalid = s.isna()
        elif kind == "unique": invalid = s.duplicated(keep=False) & s.notna()
        elif kind == "min": invalid = pd.to_numeric(s, errors="coerce") < float(params["value"])
        elif kind == "max": invalid = pd.to_numeric(s, errors="coerce") > float(params["value"])
        elif kind == "regex": invalid = ~s.fillna("").astype(str).str.match(params["pattern"])
        elif kind == "allowed": invalid = ~s.isin(params["values"])
        count = int(invalid.sum())
        if count:
            findings.append(finding("rule", rule["severity"], f"Rule {kind} failed for {count} rows", {"rule_id": rule["id"], "count": count, "sample_rows": df.index[invalid].tolist()[:20]}, c))
    if baseline:
        for c, p in profile["fields"].items():
            old = baseline.get("fields", {}).get(c)
            if not old: continue
            delta = abs(p["missing_pct"] - old.get("missing_pct", 0))
            if delta >= .10:
                findings.append(finding("distribution_drift", "high", f"Missing-value rate drifted for {c}", {"baseline": old.get("missing_pct"), "current": p["missing_pct"], "absolute_delta": round(delta, 4)}, c))
            if "mean" in p and old.get("mean") is not None and p.get("mean") is not None:
                scale = max(abs(old["mean"]), 1.0)
                rel = abs(p["mean"] - old["mean"]) / scale
                if rel >= .25:
                    findings.append(finding("distribution_drift", "medium", f"Mean shifted for {c}", {"baseline_mean": old["mean"], "current_mean": p["mean"], "relative_shift": round(rel, 4)}, c))
    numeric = df.select_dtypes(include=np.number).replace([np.inf, -np.inf], np.nan)
    if len(df) >= 10 and numeric.shape[1]:
        x = numeric.fillna(numeric.median()).fillna(0)
        model = IsolationForest(contamination=min(.05, max(1 / len(df), .01)), random_state=42)
        scores = -model.fit(x).score_samples(x)
        labels = model.predict(x)
        idx = np.where(labels == -1)[0]
        if len(idx):
            top = sorted(({"row": int(i), "score": round(float(scores[i]), 5)} for i in idx), key=lambda z: z["score"], reverse=True)[:20]
            findings.append(finding("isolation_forest", "medium", f"{len(idx)} statistically unusual rows", {"features": list(numeric.columns), "rows": top, "model": "IsolationForest(random_state=42)"}))
    penalty = sum({"low": 1, "medium": 3, "high": 7, "critical": 20}.get(f["severity"], 3) for f in findings)
    score = max(0.0, round(100.0 - penalty, 1))
    return profile, findings, score

