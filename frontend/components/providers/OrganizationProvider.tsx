"use client";

import { createContext, useContext, useState, useEffect, useCallback, useRef, type ReactNode } from "react";
import { useAuth } from "@/lib/auth";
import { getClientOrganizations, type ClientOrganization } from "@/lib/api";

type OrgContextValue = {
  organizations: ClientOrganization[];
  currentOrg: ClientOrganization | null;
  setCurrentOrg: (org: ClientOrganization | null) => void;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
};

const OrgContext = createContext<OrgContextValue | null>(null);

export function OrganizationProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();
  const [organizations, setOrganizations] = useState<ClientOrganization[]>([]);
  const [currentOrg, setCurrentOrg] = useState<ClientOrganization | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fetched = useRef(false);

  const refresh = useCallback(async () => {
    if (!isAuthenticated) {
      setOrganizations([]);
      setCurrentOrg(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const resp = await getClientOrganizations();
      setOrganizations(resp.organizations ?? []);
      if (!currentOrg && resp.organizations?.length > 0) {
        setCurrentOrg(resp.organizations[0]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load organizations");
    } finally {
      setLoading(false);
    }
  }, [isAuthenticated, currentOrg]);

  useEffect(() => {
    if (fetched.current) return;
    fetched.current = true;
    refresh();
  }, [refresh]);

  return (
    <OrgContext.Provider
      value={{
        organizations,
        currentOrg,
        setCurrentOrg,
        loading,
        error,
        refresh,
      }}
    >
      {children}
    </OrgContext.Provider>
  );
}

export function useOrganization(): OrgContextValue {
  const ctx = useContext(OrgContext);
  if (!ctx) throw new Error("useOrganization must be used within OrganizationProvider");
  return ctx;
}
