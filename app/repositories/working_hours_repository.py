from app.supabase_client import supabase


WEEKDAYS = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]

DAY_TO_NUMBER = {
    "monday": 1,
    "tuesday": 2,
    "wednesday": 3,
    "thursday": 4,
    "friday": 5,
    "saturday": 6,
    "sunday": 7,
}

NUMBER_TO_DAY = {
    value: key
    for key, value in DAY_TO_NUMBER.items()
}


def get_working_hours(tenant_id: str):
    response = (
        supabase
        .table("working_hours")
        .select("*")
        .eq("tenant_id", tenant_id)
        .order("day_of_week")
        .execute()
    )

    rows = response.data or []

    for row in rows:
        day_number = row.get("day_of_week")

        # Conversione dal formato database
        # al formato utilizzato dalla pagina web.
        row["day"] = NUMBER_TO_DAY.get(day_number)

        row["open_time"] = row.get("start_time")
        row["close_time"] = row.get("end_time")

        row["closed"] = (
            row.get("start_time") is None
            and row.get("end_time") is None
        )

    return rows


def upsert_working_hours(
    tenant_id: str,
    day: str,
    open_time: str,
    close_time: str,
    closed: bool,
):
    day_number = DAY_TO_NUMBER.get(day)

    if day_number is None:
        raise ValueError(
            f"Giorno della settimana non valido: {day}"
        )

    existing = (
        supabase
        .table("working_hours")
        .select("id")
        .eq("tenant_id", tenant_id)
        .eq("day_of_week", day_number)
        .limit(1)
        .execute()
    )

    payload = {
        "tenant_id": tenant_id,
        "day_of_week": day_number,
        "start_time": None if closed else open_time,
        "end_time": None if closed else close_time,
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
