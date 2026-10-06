"""Genesis R0.8 provider-neutral request contract for Warden evaluation."""
from __future__ import annotations
import base64, json
from datetime import datetime, timezone
from pathlib import Path
from genesis_capability_registry import resolve_capability_candidates

REQUEST_SCHEMA="genesis.warden-evaluation-request.r0.8"
PRINCIPAL_SCHEMA="genesis.principal-authority-registry.r0.8"
SIGNING_DOMAIN="GENESIS/WARDEN/REQUEST/v1"
KEY_PURPOSE="WARDEN_REQUEST"
FORBIDDEN={"provider_id","provider_ref","selected_provider","route_ref","executor_ref"}

class WardenRequestError(ValueError): pass

def canonical_json(v):
    return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()

def _time(v):
    if not isinstance(v,str): raise WardenRequestError("INVALID_WARDEN_REQUEST_TIME")
    try:
        d=datetime.fromisoformat(v.replace("Z","+00:00"))
        if d.tzinfo is None: raise WardenRequestError("WARDEN_REQUEST_TIME_MUST_BE_OFFSET_AWARE")
        return d.astimezone(timezone.utc)
    except (ValueError,OverflowError) as e: raise WardenRequestError("INVALID_WARDEN_REQUEST_TIME") from e

def _valid_key(v):
    try:
        raw=base64.b64decode(v,validate=True)
        if len(raw)!=32:return False
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        Ed25519PublicKey.from_public_bytes(raw); return True
    except Exception:return False

def validate_principal_registry(r):
    if not isinstance(r,dict) or r.get("schema_version")!=PRINCIPAL_SCHEMA: raise WardenRequestError("INVALID_PRINCIPAL_AUTHORITY_REGISTRY")
    if r.get("state") not in {"ACTIVE","ACTIVE_EMPTY","SUSPENDED","RETIRED"}: raise WardenRequestError("INVALID_PRINCIPAL_AUTHORITY_REGISTRY_STATE")
    a=r.get("authorities")
    if not isinstance(a,list): raise WardenRequestError("PRINCIPAL_AUTHORITIES_MUST_BE_LIST")
    if r["state"]=="ACTIVE_EMPTY" and a: raise WardenRequestError("ACTIVE_EMPTY_PRINCIPAL_REGISTRY_MUST_HAVE_NO_AUTHORITIES")
    seen=set()
    for x in a:
        if not isinstance(x,dict): raise WardenRequestError("INVALID_PRINCIPAL_AUTHORITY")
        if not isinstance(x.get("principal_ref"),str) or not x["principal_ref"]: raise WardenRequestError("PRINCIPAL_REF_REQUIRED")
        kid=x.get("signer_key_id")
        if not isinstance(kid,str) or not kid or kid in seen: raise WardenRequestError("PRINCIPAL_SIGNER_KEY_REQUIRED_OR_DUPLICATE")
        seen.add(kid)
        if x.get("state") not in {"ACTIVE","SUSPENDED","RETIRED"}: raise WardenRequestError("INVALID_PRINCIPAL_SIGNER_STATE")
        if x.get("algorithm")!="Ed25519" or x.get("key_purpose")!=KEY_PURPOSE: raise WardenRequestError("INVALID_PRINCIPAL_SIGNER_CONTRACT")
        if not _valid_key(x.get("public_key_b64")): raise WardenRequestError("INVALID_PRINCIPAL_PUBLIC_KEY")
        s=x.get("scope")
        if not isinstance(s,dict): raise WardenRequestError("PRINCIPAL_AUTHORITY_SCOPE_REQUIRED")
        for f in ("capabilities","purposes"):
            vals=s.get(f)
            if not isinstance(vals,list) or not vals or any(not isinstance(v,str) or not v for v in vals): raise WardenRequestError("INVALID_PRINCIPAL_AUTHORITY_SCOPE")
    return r

def load_principal_authority_registry(env,default_path="config/principal_authorities.json"):
    return validate_principal_registry(json.loads(Path(env.get("GENESIS_PRINCIPAL_AUTHORITY_PATH",default_path)).read_text()))

def validate_warden_request(e):
    if not isinstance(e,dict) or e.get("schema_version")!=REQUEST_SCHEMA: raise WardenRequestError("INVALID_WARDEN_REQUEST")
    c,s=e.get("signed_claim"),e.get("signature_b64")
    if not isinstance(c,dict) or not isinstance(s,str) or not s: raise WardenRequestError("INVALID_WARDEN_REQUEST")
    if FORBIDDEN.intersection(c): raise WardenRequestError("PROVIDER_SELECTION_NOT_ALLOWED")
    req=("signing_domain","request_id","nonce","idempotency_key","correlation_id","principal_ref","signer_key_id","origin_ref","target_warden_ref","capability_id","requested_effect","purpose_ref")
    if any(not isinstance(c.get(f),str) or not c[f] for f in req): raise WardenRequestError("INVALID_WARDEN_REQUEST")
    if not isinstance(c.get("constraints"),dict): raise WardenRequestError("INVALID_WARDEN_REQUEST")
    ev=c.get("evidence_required")
    if not isinstance(ev,list) or not ev or any(not isinstance(v,str) or not v for v in ev): raise WardenRequestError("INVALID_WARDEN_REQUEST")
    if _time(c.get("expires_at"))<=_time(c.get("issued_at")): raise WardenRequestError("INVALID_WARDEN_REQUEST_WINDOW")
    try: base64.b64decode(s,validate=True)
    except Exception as ex: raise WardenRequestError("INVALID_WARDEN_REQUEST") from ex
    return e

def _verify(k,s,p):
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        Ed25519PublicKey.from_public_bytes(base64.b64decode(k,validate=True)).verify(base64.b64decode(s,validate=True),p); return True
    except Exception:return False

def _allows(vals,v): return "*" in vals or v in vals

def projection(reason,c=None):
    c=c if isinstance(c,dict) else {}
    return {"schema_version":REQUEST_SCHEMA,"request_validated":False,"request_state":"REJECTED","reason":reason,
      "intent_ref":("warden-request:"+c["request_id"]) if c.get("request_id") else None,
      "idempotency_key":c.get("idempotency_key"),"correlation_id":c.get("correlation_id"),"principal_ref":c.get("principal_ref"),
      "origin_ref":c.get("origin_ref"),"target_warden_ref":c.get("target_warden_ref"),"capability_id":c.get("capability_id"),
      "requested_effect":c.get("requested_effect"),"purpose_ref":c.get("purpose_ref"),"candidate_count":0,
      "route_selection":"OUT_OF_SCOPE","selected_provider":None,"admitted":False,"execution_authority":"NONE",
      "dispatch_authority":"NONE","forwarding_state":"NOT_DISPATCHED","warden_evaluation_required":True,
      "warden_decision_ref":None,"provider_effects_allowed":False,"provider_native_execution_required":True,
      "river_evidence_state":"REQUIRED_PENDING","replay_protection":"REQUIRED_AT_WARDEN_INGRESS"}

def evaluate_warden_request(e,principals,registry,env,now=None):
    c=e.get("signed_claim") if isinstance(e,dict) else None
    try: validate_warden_request(e)
    except WardenRequestError as ex:
        return projection("provider_selection_not_allowed" if str(ex)=="PROVIDER_SELECTION_NOT_ALLOWED" else "invalid_warden_request",c)
    validate_principal_registry(principals)
    if principals["state"]!="ACTIVE": return projection("principal_authority_registry_not_active",c)
    if c["signing_domain"]!=SIGNING_DOMAIN:return projection("invalid_signing_domain",c)
    signer=next((x for x in principals["authorities"] if x["principal_ref"]==c["principal_ref"] and x["signer_key_id"]==c["signer_key_id"]),None)
    if signer is None:return projection("unknown_principal_signing_key",c)
    if signer["state"]!="ACTIVE":return projection("principal_signing_key_not_active",c)
    if not _verify(signer["public_key_b64"],e["signature_b64"],canonical_json(c)):return projection("signature_verification_failed",c)
    if not _allows(signer["scope"]["capabilities"],c["capability_id"]):return projection("principal_capability_out_of_scope",c)
    if not _allows(signer["scope"]["purposes"],c["purpose_ref"]):return projection("principal_purpose_out_of_scope",c)
    current=now or datetime.now(timezone.utc)
    if current.tzinfo is None:raise WardenRequestError("NOW_MUST_BE_OFFSET_AWARE")
    current=current.astimezone(timezone.utc)
    if current<_time(c["issued_at"]):return projection("request_not_yet_valid",c)
    if current>=_time(c["expires_at"]):return projection("request_expired",c)
    candidates=resolve_capability_candidates(registry,env,c["capability_id"])
    if not candidates:return projection("capability_not_registered_or_active",c)
    out=projection("validated_for_warden_evaluation",c)
    out.update({"request_validated":True,"request_state":"VALIDATED_NOT_DISPATCHED","candidate_count":len(candidates)})
    return out
