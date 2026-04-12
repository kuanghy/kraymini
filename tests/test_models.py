from kraymini.models import Node


class TestNode:
    def test_create_node(self):
        node = Node(
            raw_uri="vless://uuid@host:443?type=ws#remark",
            remark="remark",
            protocol="vless",
            address="host",
            port=443,
            credentials={"uuid": "test-uuid"},
            transport={"network": "ws"},
            source="provider-a",
        )
        assert node.protocol == "vless"
        assert node.port == 443
        assert node.credentials["uuid"] == "test-uuid"
        assert node.source == "provider-a"

    def test_dedup_same_endpoint(self):
        node1 = Node(
            raw_uri="vless://uuid@host:443?type=tcp#a",
            remark="a",
            protocol="vless",
            address="host",
            port=443,
            credentials={"uuid": "same-uuid"},
            transport={},
            source="src1",
        )
        node2 = Node(
            raw_uri="vless://uuid@host:443?type=ws#b",
            remark="b",
            protocol="vless",
            address="host",
            port=443,
            credentials={"uuid": "same-uuid"},
            transport={},
            source="src2",
        )
        assert node1.dedup_key == node2.dedup_key

    def test_dedup_different_endpoint(self):
        node1 = Node(
            raw_uri="vless://uri-1",
            remark="a",
            protocol="vless",
            address="host1",
            port=443,
            credentials={"uuid": "uuid-1"},
            transport={},
            source="",
        )
        node2 = Node(
            raw_uri="vless://uri-2",
            remark="a",
            protocol="vless",
            address="host2",
            port=443,
            credentials={"uuid": "uuid-2"},
            transport={},
            source="",
        )
        assert node1.dedup_key != node2.dedup_key

    def test_node_to_dict_and_from_dict(self):
        node = Node(
            raw_uri="trojan://pw@host:443#name",
            remark="name",
            protocol="trojan",
            address="host",
            port=443,
            credentials={"password": "pw"},
            transport={"network": "tcp"},
            source="sub1",
        )
        d = node.to_dict()
        restored = Node.from_dict(d)
        assert restored.raw_uri == node.raw_uri
        assert restored.remark == node.remark
        assert restored.credentials == node.credentials
