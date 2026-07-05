"use client";

import { useEffect, useRef } from "react";

export type WorkflowEvent =
  | "TargetCreated" | "TargetUpdated" | "TargetDeleted"
  | "ContainerStarted" | "ContainerStopped" | "ContainerRestarted"
  | "IncidentCreated" | "IncidentAcknowledged" | "IncidentResolved" | "IncidentReopened" | "IncidentDeleted"
  | "NotificationSent" | "NotificationTested"
  | "SettingsUpdated"
  | "ApiKeyCreated" | "ApiKeyRevoked"
  | "IntegrationConnected" | "IntegrationDisconnected"
  | "SearchReindexed"
  | "ReportGenerated";

export type WorkflowPayload = Record<string, unknown>;

type WorkflowSubscriber = (event: WorkflowEvent, payload: WorkflowPayload) => void;

const subscribers = new Map<WorkflowEvent, Set<WorkflowSubscriber>>();
const wildcardSubscribers = new Set<WorkflowSubscriber>();

export function publish(event: WorkflowEvent, payload: WorkflowPayload = {}) {
  const set = subscribers.get(event);
  if (set) set.forEach((fn) => fn(event, payload));
  wildcardSubscribers.forEach((fn) => fn(event, payload));
}

export function subscribe(event: WorkflowEvent, fn: WorkflowSubscriber): () => void {
  if (!subscribers.has(event)) subscribers.set(event, new Set());
  subscribers.get(event)!.add(fn);
  return () => { subscribers.get(event)?.delete(fn); };
}

export function subscribeAll(fn: WorkflowSubscriber): () => void {
  wildcardSubscribers.add(fn);
  return () => { wildcardSubscribers.delete(fn); };
}

export function useWorkflowEvent(event: WorkflowEvent, fn: (event: WorkflowEvent, payload: WorkflowPayload) => void) {
  const fnRef = useRef(fn);
  fnRef.current = fn;
  useEffect(() => {
    return subscribe(event, (e, p) => fnRef.current(e, p));
  }, [event]);
}

export function useWorkflowAll(fn: (event: WorkflowEvent, payload: WorkflowPayload) => void) {
  const fnRef = useRef(fn);
  fnRef.current = fn;
  useEffect(() => {
    return subscribeAll((e, p) => fnRef.current(e, p));
  }, []);
}
