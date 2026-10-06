import hashlib, json, shutil, uuid
from contextlib import asynccontextmanager
from pathlib import Path
import pandas as pd
from fastapi import FastAPI, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from .config import settings
from .db import Base, engine, get_db
from .models import Dataset, DatasetVersion, Rule, Finding, Proposal, LineageEdge, AuditEvent, Notification
from .quality import analyze
from .ai import explain

def actor(x_user: str | None): return x_user or "demo-user"
def require_reviewer(x_role: str | None):
    if x_role not in {"reviewer", "steward", "admin"}: raise HTTPException(403, "Reviewer, steward, or admin role required")

def audit(db, who, action, entity_type, entity_id, details=None):
    db.add(AuditEvent(actor=who, action=action, entity_type=entity_type, entity_id=str(entity_id), details=details or {}, correlation_id=str(uuid.uuid4())))

def serialize(obj):
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}

@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine); Path(settings.storage_path).mkdir(parents=True, exist_ok=True)
    yield

app = FastAPI(title="AI-Assisted Data Quality and Lineage", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class DatasetIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    description: str = ""
class RuleIn(BaseModel):
    column_name: str; rule_type: str; parameters: dict = {}; severity: str = "medium"
class ProposalIn(BaseModel):
    finding_id: int | None = None; action: str; parameters: dict; rationale: str; confidence: float = Field(ge=0, le=1); risk: str = "high"
class DecisionIn(BaseModel):
    decision: str; comment: str = ""

@app.get("/health")
def health(): return {"status":"ok"}

@app.post("/api/datasets")
def create_dataset(body: DatasetIn, db: Session=Depends(get_db), x_user: str|None=Header(None)):
    item=Dataset(**body.model_dump()); db.add(item); db.flush(); audit(db,actor(x_user),"dataset.created","dataset",item.id); db.commit(); return serialize(item)

@app.get("/api/datasets")
def datasets(db: Session=Depends(get_db)):
    out=[]
    for d in db.scalars(select(Dataset).order_by(Dataset.id.desc())):
        latest=db.scalar(select(DatasetVersion).where(DatasetVersion.dataset_id==d.id).order_by(DatasetVersion.version.desc()))
        x=serialize(d); x["latest_version"]=serialize(latest) if latest else None; out.append(x)
    return out

@app.post("/api/datasets/{dataset_id}/rules")
def add_rule(dataset_id:int, body:RuleIn, db:Session=Depends(get_db), x_user:str|None=Header(None)):
    if not db.get(Dataset,dataset_id): raise HTTPException(404,"Dataset not found")
    if body.rule_type not in {"not_null","unique","min","max","regex","allowed"}: raise HTTPException(400,"Unsupported rule type")
    r=Rule(dataset_id=dataset_id,**body.model_dump()); db.add(r); db.flush(); audit(db,actor(x_user),"rule.created","rule",r.id,body.model_dump()); db.commit(); return serialize(r)

@app.get("/api/datasets/{dataset_id}/rules")
def rules(dataset_id:int, db:Session=Depends(get_db)): return [serialize(x) for x in db.scalars(select(Rule).where(Rule.dataset_id==dataset_id))]

@app.post("/api/datasets/{dataset_id}/upload")
def upload(dataset_id:int, file:UploadFile=File(...), db:Session=Depends(get_db), x_user:str|None=Header(None)):
    dataset=db.get(Dataset,dataset_id)
    if not dataset: raise HTTPException(404,"Dataset not found")
    if not file.filename or not file.filename.lower().endswith(".csv"): raise HTTPException(400,"This MVP accepts CSV files")
    raw=file.file.read(); checksum=hashlib.sha256(raw).hexdigest()
    prior=db.scalar(select(DatasetVersion).where(DatasetVersion.dataset_id==dataset_id).order_by(DatasetVersion.version.desc()))
    number=(prior.version+1) if prior else 1
    path=Path(settings.storage_path)/f"dataset-{dataset_id}-v{number}-{checksum[:8]}.csv"; path.write_bytes(raw)
    try: df=pd.read_csv(path)
    except Exception as e: path.unlink(missing_ok=True); raise HTTPException(400,f"CSV parsing failed: {e}")
    rule_rows=[serialize(x) for x in db.scalars(select(Rule).where(Rule.dataset_id==dataset_id,Rule.enabled==True))]
    profile, items, score=analyze(df,rule_rows,prior.profile if prior else None)
    version=DatasetVersion(dataset_id=dataset_id,version=number,filename=file.filename,storage_path=str(path),checksum=checksum,row_count=len(df),profile=profile,quality_score=score,status="quarantined" if any(x["severity"]=="critical" for x in items) else "review_required" if items else "accepted")
    db.add(version); db.flush()
    for item in items:
        f=Finding(version_id=version.id,explanation=explain(item),**item); db.add(f); db.flush()
        # Suggestions are evidence-based proposals only. They never execute here.
        if item["detector"]=="duplicates":
            db.add(Proposal(version_id=version.id,finding_id=f.id,action="drop_exact_duplicates",parameters={},rationale="Remove exact duplicate rows while preserving every distinct record.",confidence=.99,risk="medium",proposed_by="rule-engine"))
        elif item["detector"]=="missing_values" and item.get("field") in df.select_dtypes(include="number").columns:
            db.add(Proposal(version_id=version.id,finding_id=f.id,action="fill_missing_median",parameters={"column":item["field"]},rationale=f"Replace missing {item['field']} values with the approved dataset median.",confidence=.75,risk="high",proposed_by="quality-engine"))
    db.add(LineageEdge(source=f"upload:{file.filename}",target=f"dataset:{dataset.name}:v{number}",edge_type="ingestion",transformation="CSV parse + immutable registration",version_id=version.id))
    for column in df.columns:
        db.add(LineageEdge(source=f"upload:{file.filename}.{column}",target=f"dataset:{dataset.name}:v{number}.{column}",edge_type="field_lineage",transformation="identity",version_id=version.id))
    if items:
        db.add(Notification(channel="slack",recipient="#data-quality",subject=f"{dataset.name} v{number} requires review",body=f"Quality score {score}; {len(items)} findings. No records were modified."))
        db.add(Notification(channel="email",recipient="data-stewards@example.test",subject=f"Review requested: {dataset.name} v{number}",body=f"The dataset scored {score} with {len(items)} findings. Review correction proposals before any change is executed."))
    audit(db,actor(x_user),"dataset_version.analyzed","dataset_version",version.id,{"score":score,"finding_count":len(items),"checksum":checksum}); db.commit()
    return {"version":serialize(version),"finding_count":len(items)}

@app.get("/api/versions/{version_id}")
def get_version(version_id:int, db:Session=Depends(get_db)):
    v=db.get(DatasetVersion,version_id)
    if not v: raise HTTPException(404,"Version not found")
    return {"version":serialize(v),"findings":[serialize(x) for x in db.scalars(select(Finding).where(Finding.version_id==version_id))]}

@app.get("/api/findings")
def findings(db:Session=Depends(get_db), limit:int=100): return [serialize(x) for x in db.scalars(select(Finding).order_by(Finding.id.desc()).limit(min(limit,500)))]

@app.post("/api/versions/{version_id}/proposals")
def propose(version_id:int, body:ProposalIn, db:Session=Depends(get_db), x_user:str|None=Header(None)):
    if not db.get(DatasetVersion,version_id): raise HTTPException(404,"Version not found")
    allowed={"fill_missing_median","fill_missing_value","drop_exact_duplicates","quarantine_only"}
    if body.action not in allowed: raise HTTPException(400,f"Allowed actions: {sorted(allowed)}")
    p=Proposal(version_id=version_id,proposed_by=actor(x_user),**body.model_dump()); db.add(p); db.flush(); audit(db,actor(x_user),"proposal.created","proposal",p.id,body.model_dump()); db.commit(); return serialize(p)

@app.get("/api/proposals")
def proposals(db:Session=Depends(get_db)): return [serialize(x) for x in db.scalars(select(Proposal).order_by(Proposal.id.desc()))]

@app.post("/api/proposals/{proposal_id}/decision")
def decide(proposal_id:int, body:DecisionIn, db:Session=Depends(get_db), x_user:str|None=Header(None), x_role:str|None=Header(None)):
    require_reviewer(x_role)
    if body.decision not in {"approved","rejected"}: raise HTTPException(400,"Decision must be approved or rejected")
    p=db.get(Proposal,proposal_id)
    if not p or p.status!="pending_review": raise HTTPException(409,"Proposal is unavailable or already decided")
    p.status=body.decision; p.reviewed_by=actor(x_user); p.review_comment=body.comment
    audit(db,actor(x_user),f"proposal.{body.decision}","proposal",p.id,{"comment":body.comment}); db.commit(); return serialize(p)

@app.post("/api/proposals/{proposal_id}/execute")
def execute(proposal_id:int, db:Session=Depends(get_db), x_user:str|None=Header(None), x_role:str|None=Header(None)):
    require_reviewer(x_role); p=db.get(Proposal,proposal_id)
    if not p or p.status!="approved": raise HTTPException(409,"Only approved proposals can execute")
    source=db.get(DatasetVersion,p.version_id); df=pd.read_csv(source.storage_path); params=p.parameters
    if p.action=="fill_missing_median":
        c=params.get("column");
        if c not in df or not pd.api.types.is_numeric_dtype(df[c]): raise HTTPException(400,"A numeric column is required")
        df[c]=df[c].fillna(df[c].median()); transform=f"fill {c} nulls with median"
    elif p.action=="fill_missing_value":
        c=params.get("column");
        if c not in df or "value" not in params: raise HTTPException(400,"column and value are required")
        df[c]=df[c].fillna(params["value"]); transform=f"fill {c} nulls with approved value"
    elif p.action=="drop_exact_duplicates": df=df.drop_duplicates(); transform="drop exact duplicate rows"
    elif p.action=="quarantine_only": source.status="quarantined"; p.status="executed"; audit(db,actor(x_user),"proposal.executed","proposal",p.id,{"result":"quarantined"}); db.commit(); return {"status":"quarantined","version_id":source.id}
    latest=db.scalar(select(func.max(DatasetVersion.version)).where(DatasetVersion.dataset_id==source.dataset_id)) or source.version
    out=Path(settings.storage_path)/f"dataset-{source.dataset_id}-v{latest+1}-corrected.csv"; df.to_csv(out,index=False); raw=out.read_bytes(); checksum=hashlib.sha256(raw).hexdigest()
    rule_rows=[serialize(x) for x in db.scalars(select(Rule).where(Rule.dataset_id==source.dataset_id,Rule.enabled==True))]
    profile,items,score=analyze(df,rule_rows,source.profile)
    v=DatasetVersion(dataset_id=source.dataset_id,version=latest+1,filename=out.name,storage_path=str(out),checksum=checksum,row_count=len(df),profile=profile,quality_score=score,status="review_required" if items else "accepted",parent_version_id=source.id)
    db.add(v);db.flush();db.add(LineageEdge(source=f"version:{source.id}",target=f"version:{v.id}",edge_type="correction",transformation=transform,version_id=v.id))
    for column in df.columns:
        field_transform=transform if p.parameters.get("column")==column else ("drop exact duplicate rows" if p.action=="drop_exact_duplicates" else "identity")
        db.add(LineageEdge(source=f"version:{source.id}.{column}",target=f"version:{v.id}.{column}",edge_type="field_lineage",transformation=field_transform,version_id=v.id))
    for item in items: db.add(Finding(version_id=v.id,explanation=explain(item),**item))
    p.status="executed"; audit(db,actor(x_user),"proposal.executed","proposal",p.id,{"new_version_id":v.id,"transformation":transform}); db.commit(); return {"status":"executed","new_version":serialize(v)}

@app.get("/api/lineage")
def lineage(db:Session=Depends(get_db)): return [serialize(x) for x in db.scalars(select(LineageEdge).order_by(LineageEdge.id.desc()))]
@app.get("/api/audit")
def audit_events(db:Session=Depends(get_db),limit:int=200): return [serialize(x) for x in db.scalars(select(AuditEvent).order_by(AuditEvent.id.desc()).limit(min(limit,500)))]
@app.get("/api/notifications")
def notifications(db:Session=Depends(get_db)): return [serialize(x) for x in db.scalars(select(Notification).order_by(Notification.id.desc()))]

@app.get("/api/dashboard")
def dashboard(db:Session=Depends(get_db)):
    versions=list(db.scalars(select(DatasetVersion).order_by(DatasetVersion.id.desc()).limit(30)))
    return {"datasets":db.scalar(select(func.count()).select_from(Dataset)) or 0,"versions":db.scalar(select(func.count()).select_from(DatasetVersion)) or 0,"open_proposals":db.scalar(select(func.count()).select_from(Proposal).where(Proposal.status=="pending_review")) or 0,"findings":db.scalar(select(func.count()).select_from(Finding)) or 0,"quality_trend":[{"version_id":v.id,"dataset_id":v.dataset_id,"version":v.version,"score":v.quality_score,"status":v.status,"created_at":v.created_at} for v in reversed(versions)]}
