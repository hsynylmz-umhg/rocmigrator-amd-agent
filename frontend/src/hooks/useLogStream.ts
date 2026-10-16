"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { parseLogEvent, type LogEvent } from "../lib/contracts";

const MAX_BUFFERED_EVENTS = 1_000;
const MAX_REPORTED_INVALID_EVENTS = 1_000;

export type LogStreamConnection =
  | "connecting"
  | "connected"
  | "reconnecting"
  | "closed";

export interface LogStream {
  readonly connection: LogStreamConnection;
  readonly events: readonly LogEvent[];
  readonly error: string | null;
  readonly connectionEpoch: number;
  readonly resetForNewJob: () => void;
  readonly reconnect: () => void;
}

/**
 * Subscribe before submitting a migration so fast background jobs are captured.
 * The endpoint broadcasts every job: consumers must filter by the exact job_id.
 *
 * There are no server event IDs or replay. Consumers should request one status
 * snapshot after accepting a job and whenever connectionEpoch changes. This
 * reconciles the state after a connection gap without polling or inventing logs.
 */
export function useLogStream(): LogStream {
  const [connection, setConnection] =
    useState<LogStreamConnection>("connecting");
  const [events, setEvents] = useState<readonly LogEvent[]>([]);
  const [transportError, setTransportError] = useState<string | null>(null);
  const [invalidEvents, setInvalidEvents] = useState(0);
  const [connectionEpoch, setConnectionEpoch] = useState(0);
  const [reconnectAttempt, setReconnectAttempt] = useState(0);
  const sourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    let active = true;
    setConnection("connecting");
    setTransportError(null);

    if (typeof EventSource === "undefined") {
      setConnection("closed");
      setTransportError("This browser does not support the live log connection.");
      return;
    }

    let source: EventSource;
    try {
      source = new EventSource("/api/logs/stream");
    } catch {
      setConnection("closed");
      setTransportError("The live log connection could not be opened. Retry to reconnect.");
      return;
    }
    sourceRef.current = source;

    source.onopen = () => {
      if (!active) return;
      setConnection("connected");
      setTransportError(null);
      setConnectionEpoch((previous) => previous + 1);
    };

    source.onmessage = (message: MessageEvent<string>) => {
      if (!active) return;
      try {
        const input: unknown = JSON.parse(message.data);
        const event = parseLogEvent(input);
        setEvents((previous) => [
          ...previous.slice(-(MAX_BUFFERED_EVENTS - 1)),
          event,
        ]);
      } catch {
        // Keep valid events flowing and expose a bounded warning, not raw input.
        setInvalidEvents((previous) =>
          Math.min(previous + 1, MAX_REPORTED_INVALID_EVENTS),
        );
      }
    };

    source.onerror = () => {
      if (!active) return;
      if (source.readyState === EventSource.CLOSED) {
        setConnection("closed");
        setTransportError("The live log connection closed. Retry to reconnect.");
      } else {
        // EventSource owns its retry timing; creating another source duplicates logs.
        setConnection("reconnecting");
        setTransportError("Live logs were interrupted. Reconnecting automatically.");
      }
    };

    return () => {
      active = false;
      source.onopen = null;
      source.onmessage = null;
      source.onerror = null;
      source.close();
      if (sourceRef.current === source) sourceRef.current = null;
    };
  }, [reconnectAttempt]);

  const resetForNewJob = useCallback(() => {
    // Call immediately BEFORE POST /api/migrate. Clearing after its response
    // would discard events emitted while the request was still in flight.
    setEvents([]);
    setInvalidEvents(0);
  }, []);

  const reconnect = useCallback(() => {
    if (connection !== "closed") return;
    sourceRef.current?.close();
    setReconnectAttempt((previous) => previous + 1);
  }, [connection]);

  const invalidEventError = invalidEvents
    ? `Skipped ${invalidEvents === MAX_REPORTED_INVALID_EVENTS ? "at least " : ""}${invalidEvents} invalid log event${invalidEvents === 1 ? "" : "s"}. Valid log events are retained.`
    : null;
  const error = [transportError, invalidEventError].filter(Boolean).join(" ") || null;

  return {
    connection,
    events,
    error,
    connectionEpoch,
    resetForNewJob,
    reconnect,
  };
}
