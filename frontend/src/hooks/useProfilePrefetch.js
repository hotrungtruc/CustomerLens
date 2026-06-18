"use client";

import { useCallback, useEffect, useRef } from "react";
import { fetchCustomerProfileById } from "../services/api";

const PREFETCH_TTL_MS = 60_000; // 60 seconds before re-fetching a profile

/**
 * useProfilePrefetch — background-fetches customer profiles for faces
 * currently detected by the WebSocket stream.
 *
 * When a recognized customer_id arrives in the `customers` array,
 * we immediately fetch their full profile from the API and cache it.
 * When the admin clicks a customer card, the data is already ready.
 *
 * @param {Array} customers — the live customer array from the WebSocket
 * @returns {{ getProfile: (id: string) => object|null }}
 */
export function useProfilePrefetch(customers) {
  // Map<id, { data: object, fetchedAt: number }>
  const cacheRef = useRef(new Map());
  // Set of IDs currently being fetched (prevents duplicate in-flight requests)
  const inflightRef = useRef(new Set());

  useEffect(() => {
    if (!customers || customers.length === 0) return;

    // Only prefetch for admin users (the endpoint requires admin auth)
    const role = typeof window !== "undefined" ? localStorage.getItem("role") : null;
    if (role !== "admin") return;

    for (const c of customers) {
      const id = c.id;
      if (!id) continue;

      // Skip guest/unrecognized faces — only prefetch real customers
      const idStr = String(id);
      if (idStr.startsWith("GUEST_") || idStr.startsWith("T")) continue;

      // Skip if already in-flight
      if (inflightRef.current.has(idStr)) continue;

      // Skip if recently cached
      const cached = cacheRef.current.get(idStr);
      if (cached && Date.now() - cached.fetchedAt < PREFETCH_TTL_MS) continue;

      // Fire background fetch
      inflightRef.current.add(idStr);
      fetchCustomerProfileById(idStr)
        .then((res) => {
          if (res?.customer || res?.status === "success") {
            cacheRef.current.set(idStr, {
              data: res.customer,
              fetchedAt: Date.now(),
            });
          }
        })
        .catch(() => {
          // Silently ignore — this is best-effort prefetching
        })
        .finally(() => {
          inflightRef.current.delete(idStr);
        });
    }
  }, [customers]);

  /**
   * Look up a prefetched profile by customer ID.
   * Returns the profile object or null if not yet cached.
   */
  const getProfile = useCallback(
    (id) => cacheRef.current.get(String(id))?.data ?? null,
    []
  );

  return { getProfile };
}
