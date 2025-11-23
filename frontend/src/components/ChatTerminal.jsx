import { useState, useRef, useEffect, useCallback } from 'react';
import { API_BASE, REFRESH_INTERVALS } from '../config';

const ensureDate = (value) => {
  if (value instanceof Date && !Number.isNaN(value.getTime())) {
    return value;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return new Date();
  }
  return date;
};

const normalizePercent = (value) => {
  const parsed = Number.parseFloat(value);
  if (!Number.isFinite(parsed)) {
    return null;
  }
  return Math.max(0, Math.min(100, parsed));
};

const formatPercentLabel = (value) => {
  const percent = normalizePercent(value);
  if (percent === null) {
    return null;
  }
  return `${percent.toFixed(0)}%`;
};

const buildAgentMessage = (record) => {
  if (!record || record.id === undefined || record.id === null) {
    return null;
  }

  const timestamp = ensureDate(record.timestamp);
  const progressPercent = normalizePercent(record.progress_percent);
  // Ensure message is a string before calling trim
  const messageStr = record.message ? String(record.message) : '';
  const text = (messageStr && messageStr.trim().length > 0)
    ? messageStr
    : (progressPercent !== null
      ? `Progress update: ${progressPercent.toFixed(0)}% complete.`
      : 'Progress update received.');

  return {
    id: `agent-response-${record.id}`,
    sender: 'agent',
    agentId: record.agent_id || 'agent',
    text,
    timestamp,
    taskId: record.task_id ?? null,
    progressPercent,
    taskTitle: record.task?.title ?? null,
    taskStatus: record.task?.status ?? null,
  };
};

const formatTime = (date) => {
  if (!date) {
    return '—';
  }
  const safeDate = ensureDate(date);
  return safeDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
};

const getSenderLabel = (message) => {
  if (message.sender === 'user') {
    return 'You';
  }
  if (message.sender === 'system') {
    return 'System';
  }
  return message.agentId || 'Agent';
};

const ChatTerminal = () => {
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState(null);
  const messagesEndRef = useRef(null);
  const abortRef = useRef(false);

  const upsertMessages = useCallback((incoming = []) => {
    if (!incoming.length) {
      return;
    }

    setMessages((prev) => {
      const map = new Map(prev.map((msg) => [msg.id, msg]));
      incoming.forEach((msg) => {
        if (!msg || msg.id === undefined || msg.id === null) {
          return;
        }
        const timestamp = ensureDate(msg.timestamp);
        map.set(msg.id, { ...msg, timestamp });
      });

      return Array.from(map.values()).sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime());
    });
  }, []);

  const fetchAgentResponses = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/chat/agent-responses?limit=60`);
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'Failed to load agent responses');
      }

      if (abortRef.current) {
        return;
      }

      const normalized = (Array.isArray(data.messages) ? data.messages : [])
        .map(buildAgentMessage)
        .filter(Boolean);

      if (normalized.length) {
        upsertMessages(normalized);
      }
      setHistoryError(null);
    } catch (error) {
        if (abortRef.current) {
          return;
        }
        console.error('Error loading agent responses:', error);
        setHistoryError(error?.message ? String(error.message) : 'Unable to load agent responses');
    } finally {
      if (!abortRef.current) {
        setHistoryLoading(false);
      }
    }
  }, [upsertMessages]);

  useEffect(() => {
    abortRef.current = false;

    fetchAgentResponses();
    const intervalId = setInterval(fetchAgentResponses, REFRESH_INTERVALS.chat);

    return () => {
      abortRef.current = true;
      clearInterval(intervalId);
    };
  }, [fetchAgentResponses]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!inputValue.trim() || isLoading) return;

    const taskText = inputValue.trim();
    const taskTimestamp = new Date();

    const userMessage = {
      id: `user-${Date.now()}`,
      sender: 'user',
      text: taskText,
      timestamp: new Date(),
    };

    upsertMessages([userMessage]);
    setInputValue('');
    setIsLoading(true);

    const thinkingMessage = {
      id: `thinking-${Date.now()}`,
      sender: 'system',
      text: 'Sending task to agents...',
      timestamp: new Date(),
      isThinking: true,
    };

    upsertMessages([thinkingMessage]);

    try {
      const response = await fetch(`${API_BASE}/task`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: taskText, timestamp: taskTimestamp.toISOString() }),
      });
      const data = await response.json();

      setMessages((prev) => prev.filter((msg) => !msg.isThinking));

      if (response.ok) {
        const taskMessage = {
          id: `task-${data.task_id}`,
          sender: 'system',
          text: `[Task created] ${taskText}`,
          timestamp: new Date(),
          taskId: data.task_id,
        };
        upsertMessages([taskMessage]);
        fetchAgentResponses();
      } else {
        throw new Error(data.detail || 'Failed to create task');
      }
    } catch (error) {
      setMessages((prev) => prev.filter((msg) => !msg.isThinking));

      const errorMessage = {
        id: `error-${Date.now()}`,
        sender: 'system',
        text: `Error: ${error?.message ? String(error.message) : String(error)}`,
        timestamp: new Date(),
        isError: true,
      };
      upsertMessages([errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="chat-terminal">
      <header className="chat-terminal__header">
        <div>
          <div className="chat-terminal__title">Agent Playground</div>
          <div className="chat-terminal__subtitle">Share a task and watch the agents report back.</div>
        </div>
      </header>

      <div style={{
        flex: 1,
        overflowY: 'auto',
        padding: '20px',
        display: 'flex',
        flexDirection: 'column',
        gap: '15px',
        backgroundColor: '#151c19'
      }}>
        {historyLoading && (
          <div style={{ color: '#a9b0c5', fontSize: '0.95rem' }}>
            Loading conversation…
          </div>
        )}

        {!historyLoading && messages.length === 0 && !historyError && (
          <div style={{ color: '#a9b0c5', fontSize: '0.95rem' }}>
            Waiting for agent responses…
          </div>
        )}

        {historyError && (
          <div style={{
            color: '#ff6b6b',
            backgroundColor: 'rgba(255, 107, 107, 0.1)',
            border: '1px solid rgba(255, 107, 107, 0.3)',
            borderRadius: '8px',
            padding: '12px 16px'
          }}>
            {historyError}
          </div>
        )}

        {messages.map((message) => {
          const accentColor = message.sender === 'user'
            ? '#f4bf67'
            : message.sender === 'system'
              ? '#7ab8ff'
              : '#88d6a4';

          return (
            <div
              key={message.id}
              style={{
                padding: '12px 16px',
                borderRadius: '12px',
                backgroundColor: message.sender === 'user'
                  ? 'rgba(244, 191, 103, 0.16)'
                  : message.sender === 'system'
                    ? 'rgba(122, 184, 255, 0.14)'
                    : 'rgba(136, 214, 164, 0.14)',
                borderLeft: `3px solid ${accentColor}`,
                color: '#f6f1e6',
                display: 'flex',
                flexDirection: 'column',
                gap: '8px'
              }}
            >
              <div style={{
                fontSize: '0.85rem',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                opacity: 0.86
              }}>
                <span style={{ fontWeight: 'bold' }}>
                  {getSenderLabel(message)}
                </span>
                {!message.isThinking && (
                  <span style={{ fontSize: '0.75rem', color: '#868ea4' }}>{formatTime(message.timestamp)}</span>
                )}
              </div>
              <div style={{
                fontSize: '0.95rem',
                wordBreak: 'break-word',
                display: 'flex',
                flexWrap: 'wrap',
                gap: '10px',
                alignItems: 'center'
              }}>
                <span>{message.text ? String(message.text) : ''}</span>
                {message.isThinking && (
                  <span style={{ display: 'inline-flex', gap: '4px', marginLeft: '8px' }}>
                    <span style={{ animation: 'blink 1.4s infinite' }}>.</span>
                    <span style={{ animation: 'blink 1.4s infinite 0.2s' }}>.</span>
                    <span style={{ animation: 'blink 1.4s infinite 0.4s' }}>.</span>
                  </span>
                )}
                {!message.isThinking && formatPercentLabel(message.progressPercent) && (
                  <span style={{
                    padding: '2px 8px',
                    borderRadius: '999px',
                    border: `1px solid ${accentColor}`,
                    fontSize: '0.8rem'
                  }}>
                    {formatPercentLabel(message.progressPercent)}
                  </span>
                )}
              </div>
              {(message.taskId || message.taskTitle || message.taskStatus) && (
                <div style={{
                  fontSize: '0.75rem',
                  color: accentColor,
                  opacity: 0.9,
                  display: 'flex',
                  flexWrap: 'wrap',
                  gap: '10px'
                }}>
                  {message.taskId && <span>Task #{message.taskId}</span>}
                  {message.taskTitle && <span>{message.taskTitle}</span>}
                  {message.taskStatus && <span>Status: {message.taskStatus}</span>}
                </div>
              )}
              {(message.taskId || message.taskTitle || message.taskStatus) && (
                <div className="chat-message__tags">
                  {message.taskId && <span>Task #{message.taskId}</span>}
                  {message.taskTitle && <span>{message.taskTitle}</span>}
                  {message.taskStatus && <span>Status: {message.taskStatus}</span>}
                </div>
              )}
              {(message.taskId || message.taskTitle || message.taskStatus) && (
                <div className="chat-message__tags">
                  {message.taskId && <span>Task #{message.taskId}</span>}
                  {message.taskTitle && <span>{message.taskTitle}</span>}
                  {message.taskStatus && <span>Status: {message.taskStatus}</span>}
                </div>
              )}
            </div>
          );
        })}
        <div ref={messagesEndRef} />
      </div>

      <form onSubmit={handleSubmit} style={{
        padding: '15px',
        backgroundColor: 'rgba(17, 20, 33, 0.98)',
        borderTop: '1px solid rgba(90, 101, 149, 0.9)',
        display: 'flex',
        gap: '10px'
      }}>
        <input
          type="text"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          placeholder="Enter a joyful mission for the agents…"
          disabled={isLoading}
          style={{
            flex: 1,
            padding: '12px 15px',
            backgroundColor: '#121623',
            border: '1px solid rgba(90, 101, 149, 0.9)',
            borderRadius: '999px',
            color: '#f6f1e6',
            fontSize: '0.95rem',
            outline: 'none'
          }}
        />
        <button
          type="submit"
          disabled={!inputValue.trim() || isLoading}
          className="chat-terminal__send"
        >
          <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M22 2L11 13" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M22 2L15 22L11 13L2 9L22 2Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Send
        </button>
      </form>
    </div>
  );
};

export default ChatTerminal;
