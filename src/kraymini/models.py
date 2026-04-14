from __future__ import annotations

import json
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
        if self.raw_uri:
            return self.raw_uri
        return json.dumps(
            {
                "protocol": self.protocol,
                "address": self.address,
                "port": self.port,
                "credentials": self.credentials,
                "transport": self.transport,
            },
            sort_keys=True,
            ensure_ascii=False,
        )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Node:
        return cls(**data)
