from app.supabase_client import supabase


def get_faq(tenant_id: str):
    response = (
        supabase
        .table("faq")
        .select("*")
        .eq("tenant_id", tenant_id)
        .execute()
    )

    return response.data or []


def create_faq(tenant_id: str, question: str, answer: str):
    response = (
        supabase
        .table("faq")
        .insert({
            "tenant_id": tenant_id,
            "question": question,
            "answer": answer
        })
        .execute()
    )

    return response.data[0] if response.data else None


def delete_faq(tenant_id: str, faq_id: str):
    response = (
        supabase
        .table("faq")
        .delete()
        .eq("tenant_id", tenant_id)
        .eq("id", faq_id)
        .execute()
    )

    return response.data[0] if response.data else None
