def lambda_handler(event, context):
    """The sample every builder-made function runs: it answers with the event it was given."""
    return {"statusCode": 200, "body": {"hello": "cloudy-labs", "event": event}}
