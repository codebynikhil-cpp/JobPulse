"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import * as Dropdown from "@radix-ui/react-dropdown-menu";
import { request } from "@/lib/client-api";
import { Button } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/feedback";
export default function Logout({ menu = false }: { menu?: boolean }) {
  const router = useRouter(),
    toast = useToast();
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function logout() {
    setBusy(true);
    setError("");
    try {
      await request("/api/auth/logout", "POST");
      router.push("/login");
      router.refresh();
    } catch {
      const message = "Logout failed. Please retry.";
      setError(message);
      toast(message);
    } finally {
      setBusy(false);
    }
  }
  return menu ? (
    <Dropdown.Item disabled={busy} onSelect={() => void logout()}>
      {busy ? "Logging out..." : "Log out"}
    </Dropdown.Item>
  ) : (
    <>
      <Button disabled={busy} onClick={logout}>
        {busy ? "Logging out..." : "Log out"}
      </Button>
      {error && <p role="alert">{error}</p>}
    </>
  );
}
