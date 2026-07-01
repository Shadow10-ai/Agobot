/**
 * WebSocketContext — single shared WS connection for the whole app.
 *
 * Usage:
 *   const { lastMessage, connected } = useWS();
 *   useEffect(() => {
 *     if (lastMessage?.type === 'scan_update') { ... }
 *   }, [lastMessage]);
 *
 * Message types broadcast by the backend:
 *   scan_update  — emitted after every bot scan (~10s)
 *     { type, bot, positions, prices }
 *   ml_update    — emitted after ML model retrains
 *     { type, status, accuracy, training_samples }
 */
import { createContext, useContext, useEffect, useRef, useState, useCallback } from "react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

const WebSocketContext = createContext({ lastMessage: null, connected: false });

export function WebSocketProvider({ children }) {
  const [lastMessage, setLastMessage] = useState(null);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef(null);
  const timerRef = useRef(null);
  const mountedRef = useRef(true);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;

    const token = localStorage.getItem("token");
    if (!token) return;

    // Close any existing connection before re-connecting
    if (wsRef.current && wsRef.current.readyState !== WebSocket.CLOSED) {
      wsRef.current.onclose = null; // prevent reconnect loop from old socket
      wsRef.current.close();
    }

    const wsUrl = BACKEND_URL.replace(/^http/, "ws") + `/api/ws?token=${encodeURIComponent(token)}`;

    let ws;
    try {
      ws = new WebSocket(wsUrl);
    } catch {
      // Schedule reconnect if WS constructor itself throws (bad URL, etc.)
      timerRef.current = setTimeout(connect, 5000);
      return;
    }

    wsRef.current = ws;

    ws.onopen = () => {
      if (mountedRef.current) setConnected(true);
    };

    ws.onmessage = (event) => {
      if (!mountedRef.current) return;
      try {
        setLastMessage(JSON.parse(event.data));
      } catch {
        // ignore malformed JSON
      }
    };

    ws.onclose = () => {
      if (!mountedRef.current) return;
      setConnected(false);
      // Reconnect after 5s — silently retry forever
      timerRef.current = setTimeout(connect, 5000);
    };

    ws.onerror = () => {
      ws.close(); // onclose will schedule reconnect
    };
  }, []); // no deps — connect is stable

  useEffect(() => {
    mountedRef.current = true;
    connect();

    // Keep-alive ping every 30s to prevent proxy timeouts
    const pingInterval = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        try { wsRef.current.send("ping"); } catch {}
      }
    }, 30000);

    return () => {
      mountedRef.current = false;
      clearInterval(pingInterval);
      if (timerRef.current) clearTimeout(timerRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
    };
  }, [connect]);

  return (
    <WebSocketContext.Provider value={{ lastMessage, connected }}>
      {children}
    </WebSocketContext.Provider>
  );
}

export const useWS = () => useContext(WebSocketContext);
