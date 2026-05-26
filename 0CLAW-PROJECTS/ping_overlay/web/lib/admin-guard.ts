const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";

export type GuardResult = { banned: boolean; strike_count: number };

export async function logUnauthorizedAccess(
  userId: string | null,
  route: string,
): Promise<GuardResult> {
  try {
    const res = await fetch(`${SUPABASE_URL}/functions/v1/admin-guard`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "log", user_id: userId, route }),
    });
    if (!res.ok) return { banned: false, strike_count: 1 };
    return res.json();
  } catch {
    return { banned: false, strike_count: 1 };
  }
}

export async function checkBan(userId: string | null): Promise<boolean> {
  try {
    const res = await fetch(`${SUPABASE_URL}/functions/v1/admin-guard`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "check", user_id: userId }),
    });
    if (!res.ok) return false;
    const data = await res.json();
    return data.banned === true;
  } catch {
    return false;
  }
}
