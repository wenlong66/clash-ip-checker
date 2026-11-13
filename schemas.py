from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional

class StartRequest(BaseModel):
    yaml_content: str
    config: Dict[str, Any] = {}

class UpdateNodeRequest(BaseModel):
    name: str

class ExportRequest(BaseModel):
    node_ids: List[int]

class RecheckRequest(BaseModel):
    config: Dict[str, Any] = {}


class FailoverNode(BaseModel):
    profile_id: str = Field(min_length=1)
    node_name: str = Field(min_length=1)


class FailoverRequest(BaseModel):
    primary: FailoverNode
    backup: FailoverNode
    backup2: Optional[FailoverNode] = None
    interval: int = Field(default=30, ge=10, le=3600)
    target_profile_id: str = ''
