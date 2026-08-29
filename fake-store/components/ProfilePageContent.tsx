"use client";

import { FormEvent, useEffect, useState } from "react";
import { AccountShell } from "@/components/AccountMenu";
import { useAuth } from "@/lib/auth-context";
import {
  EMPTY_SHIPPING_ADDRESS,
  type ShippingAddress,
  type UserProfile,
} from "@/lib/account-types";
import { useToast } from "@/lib/toast-context";

function parseAddress(raw: unknown): ShippingAddress {
  if (!raw || typeof raw !== "object") {
    return { ...EMPTY_SHIPPING_ADDRESS };
  }
  const value = raw as Record<string, string>;
  return {
    line1: value.line1 ?? "",
    line2: value.line2 ?? "",
    city: value.city ?? "",
    state: value.state ?? "",
    postalCode: value.postalCode ?? "",
    country: value.country ?? "India",
  };
}

export function ProfilePageContent() {
  const { user } = useAuth();
  const { showToast } = useToast();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [displayName, setDisplayName] = useState("");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState<ShippingAddress>({
    ...EMPTY_SHIPPING_ADDRESS,
  });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadProfile() {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch("/api/profile");
        const payload = (await res.json()) as {
          profile?: UserProfile;
          error?: string;
        };
        if (!res.ok) {
          throw new Error(payload.error || "Could not load profile.");
        }
        if (cancelled || !payload.profile) {
          return;
        }
        setDisplayName(payload.profile.display_name ?? "");
        setPhone(payload.profile.phone ?? "");
        setAddress(parseAddress(payload.profile.shipping_address));
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load profile.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadProfile();
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const res = await fetch("/api/profile", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          displayName,
          phone,
          shippingAddress: address,
        }),
      });
      const payload = (await res.json()) as { error?: string };
      if (!res.ok) {
        throw new Error(payload.error || "Could not save profile.");
      }
      showToast("Profile saved.", "success");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Could not save profile.";
      setError(message);
      showToast(message, "error");
    } finally {
      setSaving(false);
    }
  }

  function updateAddress<K extends keyof ShippingAddress>(key: K, value: string) {
    setAddress((current) => ({ ...current, [key]: value }));
  }

  if (loading) {
    return (
      <AccountShell title="Profile" description="Manage your account details.">
        <p className="text-sm text-gray-500">Loading profile…</p>
      </AccountShell>
    );
  }

  return (
    <AccountShell
      title="Profile"
      description="Manage your name, contact info, and default shipping address."
    >
      <form onSubmit={handleSubmit} className="max-w-xl space-y-6">
        <div>
          <label className="block text-sm font-medium text-gray-700">Email</label>
          <input
            type="email"
            value={user?.email ?? ""}
            disabled
            className="mt-1.5 w-full rounded-lg border border-gray-200 bg-gray-50 px-3 py-2.5 text-sm text-gray-500"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700">Display name</label>
          <input
            type="text"
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
            className="mt-1.5 w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-gray-900 focus:outline-none focus:ring-2 focus:ring-gray-900/10"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700">Phone</label>
          <input
            type="tel"
            value={phone}
            onChange={(event) => setPhone(event.target.value)}
            placeholder="+91 98765 43210"
            className="mt-1.5 w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-gray-900 focus:outline-none focus:ring-2 focus:ring-gray-900/10"
          />
        </div>

        <fieldset className="space-y-4 rounded-xl border border-gray-200 p-4">
          <legend className="px-1 text-sm font-semibold text-gray-900">
            Default shipping address
          </legend>

          <div>
            <label className="block text-sm font-medium text-gray-700">Address line 1</label>
            <input
              type="text"
              value={address.line1}
              onChange={(event) => updateAddress("line1", event.target.value)}
              className="mt-1.5 w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-gray-900 focus:outline-none focus:ring-2 focus:ring-gray-900/10"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700">
              Address line 2 (optional)
            </label>
            <input
              type="text"
              value={address.line2 ?? ""}
              onChange={(event) => updateAddress("line2", event.target.value)}
              className="mt-1.5 w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-gray-900 focus:outline-none focus:ring-2 focus:ring-gray-900/10"
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="block text-sm font-medium text-gray-700">City</label>
              <input
                type="text"
                value={address.city}
                onChange={(event) => updateAddress("city", event.target.value)}
                className="mt-1.5 w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-gray-900 focus:outline-none focus:ring-2 focus:ring-gray-900/10"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">State</label>
              <input
                type="text"
                value={address.state}
                onChange={(event) => updateAddress("state", event.target.value)}
                className="mt-1.5 w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-gray-900 focus:outline-none focus:ring-2 focus:ring-gray-900/10"
              />
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="block text-sm font-medium text-gray-700">Postal code</label>
              <input
                type="text"
                value={address.postalCode}
                onChange={(event) => updateAddress("postalCode", event.target.value)}
                className="mt-1.5 w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-gray-900 focus:outline-none focus:ring-2 focus:ring-gray-900/10"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">Country</label>
              <input
                type="text"
                value={address.country}
                onChange={(event) => updateAddress("country", event.target.value)}
                className="mt-1.5 w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-gray-900 focus:outline-none focus:ring-2 focus:ring-gray-900/10"
              />
            </div>
          </div>
        </fieldset>

        {error ? (
          <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
        ) : null}

        <button
          type="submit"
          disabled={saving}
          className="inline-flex rounded-lg bg-gray-900 px-5 py-2.5 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-60"
        >
          {saving ? "Saving…" : "Save profile"}
        </button>
      </form>
    </AccountShell>
  );
}
