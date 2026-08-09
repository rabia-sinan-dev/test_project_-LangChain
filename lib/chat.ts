export type ChatRole = "user" | "assistant";

export type ChatMessage = {
  id: string;
  role: ChatRole;
  content: string;
};

export type AgentSseEvent = {
  type: "status" | "token" | "done" | "error";
  content?: string;
};

export type StreamHandlers = {
  onStatus: (status: string) => void;
  onToken: (token: string) => void;
  onError: (message: string) => void;
  onDone: () => void;
};

function parseSseChunk(buffer: string): { events: AgentSseEvent[]; rest: string } {
  const events: AgentSseEvent[] = [];
  const parts = buffer.split("\n\n");
  const rest = parts.pop() ?? "";

  for (const part of parts) {
    const lines = part.split("\n");
    for (const line of lines) {
      if (!line.startsWith("data:")) continue;
      const raw = line.slice(5).trim();
      if (!raw) continue;
      try {
        events.push(JSON.parse(raw) as AgentSseEvent);
      } catch {
        // Ignore malformed SSE payloads.
      }
    }
  }

  return { events, rest };
}

export async function streamChat(
  message: string,
  threadId: string,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch("/api", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({ message, thread_id: threadId }),
    signal,
  });

  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(text || `Request failed (${response.status})`);
  }

  if (!response.body) {
    throw new Error("No response body from agent.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const parsed = parseSseChunk(buffer);
    buffer = parsed.rest;

    for (const event of parsed.events) {
      if (event.type === "status" && event.content) {
        handlers.onStatus(event.content);
      } else if (event.type === "token" && event.content) {
        handlers.onToken(event.content);
      } else if (event.type === "error") {
        handlers.onError(event.content || "Unknown agent error");
      } else if (event.type === "done") {
        handlers.onDone();
      }
    }
  }

  // Flush any trailing event without a final blank line.
  if (buffer.trim()) {
    const parsed = parseSseChunk(`${buffer}\n\n`);
    for (const event of parsed.events) {
      if (event.type === "status" && event.content) handlers.onStatus(event.content);
      else if (event.type === "token" && event.content) handlers.onToken(event.content);
      else if (event.type === "error") handlers.onError(event.content || "Unknown agent error");
      else if (event.type === "done") handlers.onDone();
    }
  }

  handlers.onDone();
}

export function getOrCreateThreadId(): string {
  if (typeof window === "undefined") return "server";
  const key = "rabia-thread-id";
  const existing = sessionStorage.getItem(key);
  if (existing) return existing;
  const id = crypto.randomUUID();
  sessionStorage.setItem(key, id);
  return id;
}
