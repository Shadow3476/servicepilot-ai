"""Optional: rewrite legacy status "Completed" to "Resolved" in DynamoDB.

The app already reads "Completed" as "Resolved", so this is cosmetic and
never required. It is a dry run unless --apply is passed, and it only touches
items whose stored status is exactly "Completed".

Usage:
  python scripts/migrate_status.py            # list what would change
  python scripts/migrate_status.py --apply    # perform the update
Uses SERVICEPILOT_AWS_REGION / SERVICEPILOT_TABLE_NAME / SERVICEPILOT_AWS_PROFILE.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from boto3.dynamodb.conditions import Attr  # noqa: E402

from servicepilot.config import boto_session, load_settings  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--apply", action="store_true")
args = parser.parse_args()

settings = load_settings()
print(f"Region={settings.region} Table={settings.table_name} "
      f"Profile={settings.profile or '(default)'} Mode={'APPLY' if args.apply else 'DRY RUN'}")
table = boto_session(settings).resource("dynamodb").Table(settings.table_name)

kwargs = {"FilterExpression": Attr("status").eq("Completed")}
found = 0
while True:
    page = table.scan(**kwargs)
    for item in page["Items"]:
        found += 1
        print(f"  {item['ticket_id']}: Completed -> Resolved")
        if args.apply:
            table.update_item(
                Key={"ticket_id": item["ticket_id"]},
                UpdateExpression="SET #s = :r",
                ConditionExpression="#s = :c",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":r": "Resolved", ":c": "Completed"},
            )
    if "LastEvaluatedKey" not in page:
        break
    kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
print(f"{found} ticket(s) {'updated' if args.apply else 'would be updated'}.")
