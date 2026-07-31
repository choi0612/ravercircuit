"""Create the ravercircuit table (base + 2 GSIs). Works on Local and, later, real AWS."""
import sys
from pathlib import Path

import boto3

sys.path.append(str(Path(__file__).resolve().parents[1]))
from app.config import get_settings

TABLE = "ravercircuit"

def resource():
    cfg = get_settings()
    if cfg.dynamodb_endpoint:
        # local practice mode: fully self-contained, no machine config needed
        return boto3.resource("dynamodb",
                              endpoint_url=cfg.dynamodb_endpoint,
                              region_name="us-west-2",
                              aws_access_key_id="local",
                              aws_secret_access_key="local")
    # real AWS mode (Day 7+): use the machine's configured credentials
    return boto3.resource("dynamodb")

def main():
    db = resource()
    if TABLE in [t.name for t in db.tables.all()]:
        print(f"table '{TABLE}' already exists")
        return
    table = db.create_table(
        TableName=TABLE,
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[
            {"AttributeName": "PK",     "AttributeType": "S"},
            {"AttributeName": "SK",     "AttributeType": "S"},
            {"AttributeName": "GSI1PK", "AttributeType": "S"},
            {"AttributeName": "GSI1SK", "AttributeType": "S"},
            {"AttributeName": "GSI2PK", "AttributeType": "S"},
            {"AttributeName": "GSI2SK", "AttributeType": "S"},
        ],
        KeySchema=[
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "GSI1",
                "KeySchema": [{"AttributeName": "GSI1PK", "KeyType": "HASH"},
                              {"AttributeName": "GSI1SK", "KeyType": "RANGE"}],
                "Projection": {"ProjectionType": "ALL"},
            },
            {
                "IndexName": "GSI2",
                "KeySchema": [{"AttributeName": "GSI2PK", "KeyType": "HASH"},
                              {"AttributeName": "GSI2SK", "KeyType": "RANGE"}],
                "Projection": {"ProjectionType": "ALL"},
            },
        ],
    )
    table.wait_until_exists()
    print(f"created '{TABLE}' with GSI1 + GSI2")

if __name__ == "__main__":
    main()