from app.supabase_client import supabase


def get_user_by_auth_id(auth_user_id: str):
    response = (
        supabase
        .table("users")
        .select("*")
        .eq("auth_user_id", auth_user_id)
        .limit(1)
        .execute()
    )

    if not response.data:
        return None

    return response.data[0]


def create_user_record(auth_user_id: str, role: str = "owner"):
    """
    Crea la riga "users" collegata all'utente Supabase Auth appena
    registrato. tenant_id resta NULL finche' non completa lo step 2
    del wizard (dati attivita').
    """
    response = (
        supabase
        .table("users")
        .insert({
            "auth_user_id": auth_user_id,
            "tenant_id": None,
            "role": role
        })
        .execute()
    )

    return response.data[0] if response.data else None


def get_or_create_user_record(auth_user_id: str):
    existing = get_user_by_auth_id(auth_user_id)

    if existing:
        return existing

    return create_user_record(auth_user_id)


def set_user_tenant(user_id: str, tenant_id: str):
    response = (
        supabase
        .table("users")
        .update({"tenant_id": tenant_id})
        .eq("id", user_id)
        .execute()
    )

    return response.data[0] if response.data else None
