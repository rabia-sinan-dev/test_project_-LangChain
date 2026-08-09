"use client";

import { useEffect, useRef, useState, useTransition } from "react";
import { ArrowUp, LoaderCircle, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  getOrCreateThreadId,
  streamChat,
  type ChatMessage,
} from "@/lib/chat";
import { cn } from "@/lib/utils";

function createId() {
  return crypto.randomUUID();
}

export function ChatInterface() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [agentStatus, setAgentStatus] = useState<string[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [threadId, setThreadId] = useState<string>("");
  const [, startTransition] = useTransition();

  const bottomRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    setThreadId(getOrCreateThreadId());
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, agentStatus, isStreaming]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const text = input.trim();
    if (!text || isStreaming || !threadId) return;

    setError(null);
    setInput("");
    setAgentStatus([]);
    setIsStreaming(true);

    const userMessage: ChatMessage = {
      id: createId(),
      role: "user",
      content: text,
    };
    const assistantId = createId();

    startTransition(() => {
      setMessages((prev) => [
        ...prev,
        userMessage,
        { id: assistantId, role: "assistant", content: "" },
      ]);
    });

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await streamChat(
        text,
        threadId,
        {
          onStatus: (status) => {
            setAgentStatus((prev) =>
              prev[prev.length - 1] === status ? prev : [...prev, status],
            );
          },
          onToken: (token) => {
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === assistantId
                  ? { ...msg, content: `${msg.content}${token}` }
                  : msg,
              ),
            );
          },
          onError: (message) => {
            setError(message);
          },
          onDone: () => {
            setIsStreaming(false);
          },
        },
        controller.signal,
      );
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        setError((err as Error).message || "Failed to reach the agent.");
        setMessages((prev) =>
          prev.filter((msg) => !(msg.id === assistantId && !msg.content)),
        );
      }
    } finally {
      setIsStreaming(false);
    }
  }

  const latestStatus = agentStatus[agentStatus.length - 1];

  return (
    <div className="relative flex min-h-full flex-1 flex-col">
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="atmosphere-orb atmosphere-orb-a" />
        <div className="atmosphere-orb atmosphere-orb-b" />
        <div className="atmosphere-grid" />
      </div>

      <header className="relative z-10 mx-auto flex w-full max-w-3xl items-end justify-between px-5 pb-2 pt-10 sm:px-6 sm:pt-14">
        <div className="animate-fade-rise">
          <p className="font-display text-5xl tracking-tight text-[var(--ink)] sm:text-6xl">
            Rabia
          </p>
          <p className="mt-2 max-w-sm text-sm leading-relaxed text-[var(--ink-muted)] sm:text-base">
            A stateful deep agent that plans, researches, and streams its thinking.
          </p>
        </div>
        <div className="animate-fade-rise-delay hidden items-center gap-2 text-xs text-[var(--ink-muted)] sm:flex">
          <Sparkles className="size-3.5 text-[var(--sea)]" />
          <span className="font-mono tracking-wide">thread live</span>
        </div>
      </header>

      <main className="relative z-10 mx-auto flex w-full max-w-3xl flex-1 flex-col px-5 pb-6 sm:px-6">
        <ScrollArea className="mt-6 h-[min(58vh,640px)] rounded-none border-0 bg-transparent">
          <div className="flex flex-col gap-5 pr-3 pb-4">
            {messages.length === 0 && (
              <div className="animate-fade-rise rounded-2xl border border-[var(--line)] bg-[var(--panel)]/70 px-5 py-8 backdrop-blur-sm">
                <p className="font-display text-2xl text-[var(--ink)]">
                  Ask anything.
                </p>
                <p className="mt-2 max-w-md text-sm leading-relaxed text-[var(--ink-muted)]">
                  Try a calculation, a quick lookup, or a deeper research question —
                  status updates appear as the agent routes through tools and
                  sub-agents.
                </p>
              </div>
            )}

            {messages.map((message) => (
              <div
                key={message.id}
                className={cn(
                  "animate-fade-rise max-w-[92%] text-sm leading-relaxed sm:text-[0.95rem]",
                  message.role === "user"
                    ? "ml-auto rounded-2xl bg-[var(--ink)] px-4 py-3 text-[var(--foam)]"
                    : "mr-auto text-[var(--ink)]",
                )}
              >
                {message.role === "assistant" && (
                  <p className="mb-1 font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--sea)]">
                    Agent
                  </p>
                )}
                <p className="whitespace-pre-wrap">
                  {message.content ||
                    (isStreaming ? (
                      <span className="inline-flex items-center gap-2 text-[var(--ink-muted)]">
                        <LoaderCircle className="size-3.5 animate-spin" />
                        Composing…
                      </span>
                    ) : (
                      ""
                    ))}
                </p>
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
        </ScrollArea>

        <div
          className={cn(
            "mt-3 min-h-10 overflow-hidden border-l-2 border-[var(--sea)] pl-3 transition-opacity duration-300",
            latestStatus || isStreaming ? "opacity-100" : "opacity-40",
          )}
          aria-live="polite"
        >
          <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-[var(--ink-muted)]">
            Agent status
          </p>
          <p className="mt-1 text-sm text-[var(--ink)]">
            {latestStatus || (isStreaming ? "Working…" : "Idle — waiting for your next message")}
          </p>
          {agentStatus.length > 1 && (
            <ul className="mt-2 space-y-1">
              {agentStatus.slice(-4, -1).map((status, index) => (
                <li
                  key={`${status}-${index}`}
                  className="text-xs text-[var(--ink-muted)]"
                >
                  {status}
                </li>
              ))}
            </ul>
          )}
        </div>

        {error && (
          <p className="mt-3 text-sm text-red-700" role="alert">
            {error}
          </p>
        )}

        <form
          onSubmit={handleSubmit}
          className="mt-4 flex items-center gap-2 border-t border-[var(--line)] pt-4"
        >
          <Input
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="Message Rabia…"
            disabled={isStreaming || !threadId}
            className="h-12 flex-1 border-[var(--line)] bg-[var(--panel)]/80 text-base shadow-none backdrop-blur-sm focus-visible:ring-[var(--sea)]/40"
            autoComplete="off"
          />
          <Button
            type="submit"
            size="icon-lg"
            disabled={isStreaming || !input.trim() || !threadId}
            className="size-12 rounded-xl bg-[var(--sea)] text-[var(--foam)] hover:bg-[var(--sea-deep)]"
            aria-label="Send message"
          >
            {isStreaming ? (
              <LoaderCircle className="size-4 animate-spin" />
            ) : (
              <ArrowUp className="size-4" />
            )}
          </Button>
        </form>
      </main>
    </div>
  );
}
