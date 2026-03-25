"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { EmptyState, SectionCard, StatusBadge } from "../../_components/ui";
import type {
  CopilotChatMessage,
  CopilotChatResponse,
  CopilotReference,
  CopilotToolCall,
  CopilotUsage,
  RecoveryIssue,
} from "../../_lib/api-types";
import { chatWithBrowserCopilot } from "../../_lib/copilot-client";
import {
  formatCurrency,
  formatNumber,
  formatPercent,
  formatStatusLabel,
} from "../../_lib/format";

type PromptStarter = {
  label: string;
  note: string;
  text: string;
};

type CopilotWorkspaceProps = {
  apiHealthError: string | null;
  initialHighSeverityIssues: RecoveryIssue[];
  initialHighSeverityIssuesError: string | null;
  isApiReady: boolean;
  starterPrompts: PromptStarter[];
};

type TranscriptMessage = {
  content: string;
  id: string;
  latencyMs?: number;
  providerName?: string;
  references?: CopilotReference[];
  role: "assistant" | "user";
  status?: string;
  toolCalls?: CopilotToolCall[];
  traceId?: string;
  usage?: CopilotUsage | null;
};

function buildRequestMessages(messages: TranscriptMessage[]): CopilotChatMessage[] {
  return messages.map((message) => ({
    content: message.content,
    role: message.role,
  }));
}

function buildAssistantMessage(
  id: string,
  response: CopilotChatResponse,
): TranscriptMessage {
  return {
    content: response.message,
    id,
    latencyMs: response.latency_ms,
    providerName: response.provider_name,
    references: response.references,
    role: "assistant",
    status: response.status,
    toolCalls: response.tool_calls,
    traceId: response.trace_id,
    usage: response.usage,
  };
}

function buildAssistantMeta(message: TranscriptMessage) {
  const parts: string[] = [];

  if (message.providerName) {
    parts.push(message.providerName);
  }

  if (typeof message.latencyMs === "number") {
    parts.push(`${formatNumber(message.latencyMs)} ms`);
  }

  if (message.traceId) {
    parts.push(`trace ${message.traceId.slice(0, 8)}`);
  }

  return parts.join(" · ");
}

function buildReferenceHref(reference: CopilotReference) {
  if (reference.kind === "issue") {
    return `/issues/${reference.id}`;
  }

  if (reference.kind === "shipment") {
    return `/issues?shipment_id=${encodeURIComponent(reference.id)}`;
  }

  return null;
}

function resolveAssistantStatusTone(status: string | undefined) {
  return status === "completed" ? "good" : "warning";
}

export function CopilotWorkspace({
  apiHealthError,
  initialHighSeverityIssues,
  initialHighSeverityIssuesError,
  isApiReady,
  starterPrompts,
}: CopilotWorkspaceProps) {
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [messages, setMessages] = useState<TranscriptMessage[]>([]);

  const nextMessageIdRef = useRef(0);
  const transcriptRef = useRef<HTMLDivElement | null>(null);
  const connectionNotice = apiHealthError
    ? apiHealthError
    : !isApiReady
      ? "Backend health is not reporting ready. Copilot responses may fail until the API recovers."
      : null;

  function nextMessageId(prefix: "assistant" | "user") {
    nextMessageIdRef.current += 1;
    return `${prefix}-${nextMessageIdRef.current}`;
  }

  useEffect(() => {
    const transcript = transcriptRef.current;

    if (!transcript) {
      return;
    }

    transcript.scrollTop = transcript.scrollHeight;
  }, [isSubmitting, messages]);

  async function submitPrompt(rawPrompt: string) {
    const prompt = rawPrompt.trim();

    if (!prompt || isSubmitting) {
      return;
    }

    const nextMessages = messages.concat({
      content: prompt,
      id: nextMessageId("user"),
      role: "user",
    });

    setMessages(nextMessages);
    setDraft("");
    setError(null);
    setIsSubmitting(true);

    const result = await chatWithBrowserCopilot({
      messages: buildRequestMessages(nextMessages),
    });

    if (result.data) {
      setMessages(
        nextMessages.concat(
          buildAssistantMessage(nextMessageId("assistant"), result.data),
        ),
      );
    } else {
      setMessages(messages);
      setDraft(prompt);
      setError(result.error ?? "Copilot request failed.");
    }

    setIsSubmitting(false);
  }

  function clearChat() {
    if (isSubmitting) {
      return;
    }

    setDraft("");
    setError(null);
    setMessages([]);
  }

  return (
    <section className="content-grid content-grid--two copilot-layout">
      <SectionCard
        action={
          <button
            className="button button-secondary"
            disabled={isSubmitting || messages.length === 0}
            onClick={clearChat}
            type="button"
          >
            Clear chat
          </button>
        }
        className="span-8"
        description="Ask grounded operational questions. Each response returns as a single answer and shows which issue or shipment records it used."
        kicker="Chat"
        title="Grounded copilot"
      >
        <div className="copilot-chat-panel">
          {connectionNotice ? (
            <div className="inline-notice inline-notice--warning" role="status">
              {connectionNotice}
            </div>
          ) : null}

          <div
            aria-label="Copilot conversation"
            aria-live="polite"
            aria-relevant="additions"
            className="copilot-transcript"
            ref={transcriptRef}
            role="log"
          >
            {messages.length === 0 ? (
              <div className="copilot-empty-transcript">
                <h3 className="copilot-empty-title">Ask a grounded question</h3>
                <p className="copilot-empty-description">
                  Start with a prompt on the right or ask about a specific issue,
                  shipment, provider trend, or billing anomaly. Responses will cite
                  the ParcelOps records they inspected.
                </p>
              </div>
            ) : null}

            {messages.map((message) => {
              const assistantMeta = buildAssistantMeta(message);
              const totalTokens = message.usage?.total_tokens ?? null;

              return (
                <article
                  className={`copilot-message copilot-message--${message.role}`}
                  key={message.id}
                >
                  <div className="copilot-message-header">
                    <div className="copilot-message-heading">
                      <p className="copilot-message-label">
                        {message.role === "assistant" ? "Copilot" : "You"}
                      </p>

                      {message.role === "assistant" && message.status ? (
                        <div className="copilot-message-badges">
                          <StatusBadge
                            label={formatStatusLabel(message.status)}
                            tone={resolveAssistantStatusTone(message.status)}
                          />
                          {message.references?.length ? (
                            <StatusBadge
                              label={`${formatNumber(message.references.length)} refs`}
                              tone="muted"
                            />
                          ) : null}
                        </div>
                      ) : null}
                    </div>

                    {message.role === "assistant" && assistantMeta ? (
                      <p className="copilot-message-meta">{assistantMeta}</p>
                    ) : null}
                  </div>

                  <p className="copilot-message-text">{message.content}</p>

                  {message.role === "assistant" && message.references?.length ? (
                    <div className="copilot-reference-list">
                      {message.references.map((reference) => {
                        const href = buildReferenceHref(reference);
                        const referenceBody = (
                          <>
                            <p className="copilot-reference-kicker">
                              {formatStatusLabel(reference.kind)}
                            </p>
                            <p className="copilot-reference-label">{reference.label}</p>
                            <p className="copilot-reference-detail">
                              {reference.detail ?? reference.id}
                            </p>
                          </>
                        );

                        return href ? (
                          <Link
                            className="copilot-reference"
                            href={href}
                            key={`${reference.kind}-${reference.id}`}
                          >
                            {referenceBody}
                          </Link>
                        ) : (
                          <div
                            className="copilot-reference"
                            key={`${reference.kind}-${reference.id}`}
                          >
                            {referenceBody}
                          </div>
                        );
                      })}
                    </div>
                  ) : null}

                  {message.role === "assistant" &&
                  ((message.toolCalls?.length ?? 0) > 0 || totalTokens !== null) ? (
                    <div className="copilot-message-footer">
                      {message.toolCalls?.map((toolCall, index) => (
                        <span
                          className="chip chip-muted"
                          key={`${toolCall.name}-${index}`}
                        >
                          {formatStatusLabel(toolCall.name)}
                        </span>
                      ))}
                      {totalTokens !== null ? (
                        <span className="chip chip-muted">
                          {formatNumber(totalTokens)} tokens
                        </span>
                      ) : null}
                    </div>
                  ) : null}
                </article>
              );
            })}

            {isSubmitting ? (
              <article
                aria-hidden="true"
                className="copilot-message copilot-message--assistant"
              >
                <div className="copilot-message-header">
                  <div className="copilot-message-heading">
                    <p className="copilot-message-label">Copilot</p>
                    <div className="copilot-message-badges">
                      <StatusBadge label="Working" tone="warning" />
                    </div>
                  </div>
                </div>
                <div className="copilot-loading-lines">
                  <div className="loading-line" />
                  <div className="loading-line copilot-loading-line--short" />
                </div>
              </article>
            ) : null}
          </div>

          {error ? (
            <div className="inline-notice inline-notice--danger" role="alert">
              {error}
            </div>
          ) : null}

          <form
            className="copilot-compose-form"
            onSubmit={(event) => {
              event.preventDefault();
              void submitPrompt(draft);
            }}
          >
            <label className="field-label" htmlFor="copilot-draft">
              Ask the copilot
            </label>
            <textarea
              className="field-input field-textarea copilot-textarea"
              disabled={isSubmitting}
              id="copilot-draft"
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void submitPrompt(draft);
                }
              }}
              placeholder="Ask about open issues, spend shifts, or specific shipment evidence."
              value={draft}
            />
            <div className="copilot-composer-footer">
              <p className="copilot-helper-text">
                Grounded questions only. Press Enter to send and Shift+Enter for a
                new line.
              </p>
              <div className="button-row">
                <button
                  className="button button-primary"
                  disabled={isSubmitting || draft.trim().length === 0}
                  type="submit"
                >
                  {isSubmitting ? "Working..." : "Send question"}
                </button>
              </div>
            </div>
          </form>
        </div>
      </SectionCard>

      <div className="copilot-side-column span-4">
        <SectionCard
          description="One-click questions for the most common evidence-backed analyses."
          kicker="Prompts"
          title="Starter prompts"
        >
          <div className="copilot-starter-grid">
            {starterPrompts.map((prompt) => (
              <button
                className="prompt-card prompt-card--button"
                disabled={isSubmitting}
                key={prompt.label}
                onClick={() => void submitPrompt(prompt.text)}
                type="button"
              >
                <span className="prompt-label">{prompt.label}</span>
                <p className="prompt-text">{prompt.text}</p>
                <p className="prompt-note">{prompt.note}</p>
                <StatusBadge
                  label={isSubmitting ? "Busy" : "Ask now"}
                  tone={isSubmitting ? "muted" : undefined}
                />
              </button>
            ))}
          </div>
        </SectionCard>

        <SectionCard
          description="Current high-severity issues available for the first grounded turns."
          kicker="Context"
          title="Issue references"
        >
          {initialHighSeverityIssuesError ? (
            <EmptyState
              description={initialHighSeverityIssuesError}
              title="Issue context could not be loaded."
              tone="danger"
            />
          ) : initialHighSeverityIssues.length ? (
            <div className="stack-list">
              {initialHighSeverityIssues.map((issue) => (
                <Link
                  className="copilot-context-link"
                  href={`/issues/${issue.id}`}
                  key={issue.id}
                >
                  <div className="copilot-context-header">
                    <p className="list-row-title">
                      {formatStatusLabel(issue.issue_type)}
                    </p>
                    <StatusBadge label={formatStatusLabel(issue.severity)} />
                  </div>
                  <p className="list-row-detail">{issue.summary}</p>
                  <div className="copilot-context-footer">
                    <span className="copilot-context-meta">
                      {formatCurrency(issue.estimated_recoverable_amount)}
                    </span>
                    <span className="copilot-context-meta">
                      {formatPercent(issue.confidence)} confidence
                    </span>
                    <code className="copilot-context-id">{issue.id}</code>
                  </div>
                </Link>
              ))}
            </div>
          ) : (
            <EmptyState
              description="Once issue detection produces high-severity findings, they will show up here as ready-to-inspect grounding records."
              title="No issue references yet"
            />
          )}
        </SectionCard>
      </div>
    </section>
  );
}
