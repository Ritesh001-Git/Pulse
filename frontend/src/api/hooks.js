import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import * as api from "./client.js";

/** Standard query wrapper: { data, isPending, isError, error, refetch } */
export function useApi(queryFn, params = null, options = {}) {
  return useQuery({
    queryKey: [queryFn.name, params],
    queryFn: () => queryFn(params),
    ...options,
  });
}

const incidentKeys = {
  list: ["listIncidents"],
  detail: (id) => ["getIncident", id],
};

export function useIncident(id) {
  return useQuery({
    queryKey: incidentKeys.detail(id),
    queryFn: () => api.getIncident(id),
    enabled: !!id,
  });
}

function useIncidentMutation(mutationFn, id) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn,
    // Mutation responses are summary-shaped (no timeline); refetch the detail
    // so the timeline stays authoritative and consistent.
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: incidentKeys.detail(id) });
      qc.invalidateQueries({ queryKey: incidentKeys.list });
      qc.invalidateQueries({ queryKey: ["listServices"] });
      qc.invalidateQueries({ queryKey: ["getPublicStatus"] });
    },
  });
}

export const useAckIncident = (id) =>
  useIncidentMutation((vars) => api.acknowledgeIncident(vars.id), id);

export const useAddIncidentNote = (id) =>
  useIncidentMutation((vars) => api.addIncidentNote(vars.id, vars.body), id);

export const useResolveIncident = (id) =>
  useIncidentMutation((vars) => api.resolveIncident(vars.id), id);

export const useRunCheck = (id) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.runServiceCheck(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["getService", id] });
      qc.invalidateQueries({ queryKey: ["listServices"] });
    },
  });
};

export const useUpdateService = (id) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => api.updateService(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["getService", id] });
      qc.invalidateQueries({ queryKey: ["listServices"] });
      qc.invalidateQueries({ queryKey: ["getPublicStatus"] });
    },
  });
};
