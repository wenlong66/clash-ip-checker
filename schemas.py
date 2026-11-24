from pydantic import BaseModel, Field
from typing import Dict, Any, List, Literal, Optional

ExportKind = Literal['failover', 'checked', 'qingyunti']


class SubscriptionRefreshRequest(BaseModel):
    kind: ExportKind
    filename: str = Field(min_length=1, max_length=100)


class StartRequest(BaseModel):
    yaml_content: str
    config: Dict[str, Any] = {}

class SelectedCheckRequest(StartRequest):
    node_ids: List[int] = Field(min_length=1)

class UpdateNodeRequest(BaseModel):
    name: str

class ExportRequest(BaseModel):
    node_ids: List[int]
    target_profile_id: str = ''

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
    policy: Literal['loyalsoldier', 'qingyunti'] = 'loyalsoldier'
    target_profile_id: str = ''
