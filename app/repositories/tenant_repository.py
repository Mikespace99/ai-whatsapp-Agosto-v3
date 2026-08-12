from app.supabase_client import supabase


def get_whatsapp_account(phone_number: str):

    response = (
        supabase
        .table("whatsapp_accounts")
        .select("id, tenant_id, phone_number, provider")
        .eq("phone_number", phone_number)
        .limit(1)
        .execute()
    )

    if not response.data:
        return None

    return response.data[0]


def get_tenant(tenant_id: str):

    response = (
        supabase
        .table("tenants")
        .select("*")
        .eq("id", tenant_id)
        .limit(1)
        .execute()
    )

    if not response.data:
        return None

    return response.data[0]


def create_tenant(
    business_name: str,
    timezone: str,
    language: str,
    assistant_name: str = None
):
    response = (
        supabase
        .table("tenants")
        .insert({
            "business_name": business_name,
            "timezone": timezone,
            "language": language,
            "assistant_name": assistant_name
        })
        .execute()
    )

    return response.data[0] if response.data else None