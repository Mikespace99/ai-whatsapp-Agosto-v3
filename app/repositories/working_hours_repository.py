from app.supabase_client import supabase


WEEKDAYS = [
    "monday", "tuesday", "wednesday",
    "thursday", "friday", "saturday", "sunday"
]


def get_working_hours(tenant_id: str):
    response = (
        supabase
        .table("working_hours")
        .select("*")
        .eq("tenant_id", tenant_id)
        .execute()
    )

    return response.data or []


def upsert_working_hours(tenant_id: str, day: str, open_time: str, close_time: str, closed: bool):
    existing = (
        supabase
        .table("working_hours")
        .select("id")
        .eq("tenant_id", tenant_id)
        .eq("day_of_week", day)
        .limit(1)
        .execute()
    )

    payload = {
        "tenant_id": tenant_id,
        "day_of_week": day,
        "open_time": None if closed else open_time,
        "close_time": None if closed else close_time,
        "closed": closed
    }

    if existing.data:
        response = (
            supabase
            .table("working_hours")
            .update(payload)
            .eq("id", existing.data[0]["id"])
            .execute()
        )
    else:
        response = (
            supabase
            .table("working_hours")
            .insert(payload)
            .execute()
        )

    return response.data[0] if response.data else None
