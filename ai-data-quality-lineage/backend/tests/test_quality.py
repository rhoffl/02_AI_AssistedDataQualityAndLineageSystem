import pandas as pd
from app.quality import analyze

def test_detects_missing_duplicates_and_rules():
    df=pd.DataFrame({"id":[1,1,2],"amount":[10,10,None]})
    rules=[{"id":1,"column_name":"amount","rule_type":"not_null","parameters":{},"severity":"high"}]
    profile,findings,score=analyze(df,rules)
    detectors={x["detector"] for x in findings}
    assert "missing_values" in detectors
    assert "duplicates" in detectors
    assert "rule" in detectors
    assert score < 100

def test_clean_data_scores_100():
    df=pd.DataFrame({"id":[1,2,3],"amount":[10,20,30]})
    _,findings,score=analyze(df,[])
    assert findings == []
    assert score == 100

