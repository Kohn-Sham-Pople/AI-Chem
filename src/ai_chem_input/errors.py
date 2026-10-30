from dataclasses import dataclass


class InputError(Exception):
    def __init__(self, code, field="", exit_code=3):
        self.code, self.field, self.exit_code = code, field, exit_code
        super().__init__(code + (":" + field if field else ""))


def require(condition, code, field="", exit_code=3):
    if not condition:
        raise InputError(code, field, exit_code)


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    severity: str = "ERROR"
    field: str = ""
    source_alias: str = ""
    local_detail_ref: str = ""
    review_required: bool = True


def result(request=None, status="REJECTED", codes=(), digest=None, bundle=None, committed=False):
    r = request or {}
    return dict(schema_version=1, request_id=r.get("request_id"),
                calculation_id=r.get("calculation_id"), stage_id=r.get("stage_id"),
                result=status, committed=committed, issue_codes=list(codes),
                request_digest=digest, bundle_path=str(bundle) if bundle else None)
