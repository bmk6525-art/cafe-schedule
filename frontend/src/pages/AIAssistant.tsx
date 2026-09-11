import { useState, useRef, useEffect } from 'react';
import './AIAssistant.css';

interface Message { role: 'user' | 'assistant'; content: string; }

const STUB_RESPONSES = [
  "스케줄 관련 질문을 분석하고 있습니다... (현재 AI 기능은 API 키 연동 후 활성화됩니다)",
  "급여 계산 결과를 요약해 드릴 수 있습니다. API 키를 설정하면 실제 데이터를 기반으로 답변드립니다.",
  "근무 패턴 최적화에 대한 제안은 Claude API 연동 후 제공됩니다.",
  "안녕하세요! 카페 스케줄 AI 어시스턴트입니다. 현재 데모 모드로 동작 중입니다.",
];

let stubIdx = 0;

export default function AIAssistant() {
  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', content: '안녕하세요! 카페 스케줄 AI 어시스턴트입니다.\n현재 데모 모드로 동작 중입니다. API 키를 설정하면 실제 AI 답변을 받을 수 있습니다.\n\n스케줄, 급여, 직원 관리에 대해 무엇이든 물어보세요!' }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  async function send() {
    const text = input.trim();
    if (!text || loading) return;
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: text }]);
    setLoading(true);
    await new Promise(r => setTimeout(r, 800 + Math.random() * 600));
    const reply = STUB_RESPONSES[stubIdx % STUB_RESPONSES.length];
    stubIdx++;
    setMessages(prev => [...prev, { role: 'assistant', content: reply }]);
    setLoading(false);
  }

  function onKey(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  }

  return (
    <div className="ai-wrap">
      <div className="page-header">
        <div>
          <h2 className="page-title">AI 어시스턴트</h2>
          <p className="page-subtitle">스케줄 · 급여 · 직원 관리 도우미 (데모 모드)</p>
        </div>
        <span className="ai-status-badge">데모 모드</span>
      </div>

      <div className="ai-notice">
        <strong>API 키 미설정</strong> — 현재 데모 모드로 동작합니다. Claude API 키를 환경변수 <code>ANTHROPIC_API_KEY</code>에 설정하면 실제 AI 기능이 활성화됩니다.
      </div>

      <div className="card ai-chat-card">
        <div className="ai-messages">
          {messages.map((m, i) => (
            <div key={i} className={`ai-msg ai-msg--${m.role}`}>
              <div className="ai-msg-avatar">
                {m.role === 'assistant' ? '🤖' : '👤'}
              </div>
              <div className="ai-msg-bubble">
                {m.content.split('\n').map((line, j) => (
                  <span key={j}>{line}<br /></span>
                ))}
              </div>
            </div>
          ))}
          {loading && (
            <div className="ai-msg ai-msg--assistant">
              <div className="ai-msg-avatar">🤖</div>
              <div className="ai-msg-bubble ai-msg-bubble--loading">
                <span /><span /><span />
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div className="ai-input-row">
          <textarea
            className="ai-input"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={onKey}
            placeholder="질문을 입력하세요 (Enter: 전송, Shift+Enter: 줄바꿈)"
            rows={2}
            disabled={loading}
          />
          <button className="btn btn--primary ai-send-btn" onClick={send} disabled={loading || !input.trim()}>
            전송
          </button>
        </div>
      </div>

      <div className="ai-suggestions">
        <p className="ai-suggestions-label">빠른 질문</p>
        <div className="ai-chips">
          {['이번 달 급여 요약해줘', '주휴수당 위험 직원은?', '스케줄 공백 알려줘', '파트타이머 배치 최적화'].map(q => (
            <button key={q} className="ai-chip" onClick={() => setInput(q)}>
              {q}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
