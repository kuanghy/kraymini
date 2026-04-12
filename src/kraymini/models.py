from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class Node:
    raw_uri: str
    remark: str
    protocol: str
    address: str
    port: int
    credentials: dict = field(default_factory=dict)
    transport: dict = field(default_factory=dict)
    source: str = ""

    @property
    def dedup_key(self) -> str:
        cred = self.credentials.get("uuid") or self.credentials.get("password", "")
        return f"{self.protocol}://{self.address}:{self.port}:{cred}"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Node:
        return cls(**data)
