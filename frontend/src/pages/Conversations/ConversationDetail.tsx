import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Send, Loader2, WifiOff, MessageSquare } from 'lucide-react';
import Swal from 'sweetalert2';
import { useAuth } from '@/contexts/AuthContext';
import { useChatContext } from '@/contexts/ChatContext';
import { useChat } from '@/hooks/useChat';
import { chatService } from '@/services/chatService';
import { formatNotificationDate } from '@/utils/notificationUtils';
import type { ChatMessage } from '@/types/chat';

// ── Helpers ───────────────────────────────────────────────────────────────────

function getErrorMessage(err: unknown): string {
  const data = (err as { response?: { data?: unknown } })?.response?.data;
  if (data && typeof data === 'object') {
    const msgs = (Object.values(data).flat() as unknown[]).filter(
      (v): v is string => typeof v === 'string',
    );
    if (msgs.length) return msgs.join(' ');
  }
  if (err instanceof Error) return err.message;
  return 'Ocorreu um erro inesperado.';
}

function useDebounce<T extends (...args: never[]) => void>(fn: T, delay: number): T {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  return useCallback(
    ((...args: Parameters<T>) => {
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => fn(...args), delay);
    }) as T,
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [fn, delay],
  );
}

// ── Header skeleton ────────────────────────────────────────────────────────────

function HeaderNameSkeleton() {
  return (
    <div className="space-y-1.5" aria-hidden="true">
      <div className="h-3.5 w-32 bg-gray-200 animate-pulse rounded-md" />
      <div className="h-2.5 w-16 bg-gray-100 animate-pulse rounded-md" />
    </div>
  );
}

// ── Message bubble ────────────────────────────────────────────────────────────

interface BubbleProps {
  message: ChatMessage;
  isOwn: boolean;
}

function MessageBubble({ message, isOwn }: BubbleProps) {
  return (
    <div
      className={[
        'flex mb-2 px-3 sm:px-4',
        isOwn ? 'justify-end' : 'justify-start',
      ].join(' ')}
    >
      <div
        className={[
          'max-w-[82%] sm:max-w-[70%] relative',
          isOwn
            ? 'bg-blue-800 text-white rounded-2xl rounded-br-md shadow-sm'
            : 'bg-white text-gray-900 rounded-2xl rounded-bl-md shadow-sm border border-gray-100',
        ].join(' ')}
        aria-label={`Mensagem de ${message.sender_name}: ${message.content}`}
      >
        {/* Sender name for received messages */}
        {!isOwn && (
          <p className="text-[11px] font-bold px-3.5 pt-2.5 pb-0 text-blue-700 leading-tight">
            {message.sender_name}
          </p>
        )}

        {/* Message content */}
        <p
          className={[
            'text-sm leading-relaxed whitespace-pre-wrap break-words',
            !isOwn ? 'px-3.5 pt-1.5 pb-2' : 'px-3.5 py-2.5',
          ].join(' ')}
        >
          {message.content}
        </p>

        {/* Timestamp */}
        <p
          className={[
            'text-[10px] px-3.5 pb-2 -mt-1 text-right',
            isOwn ? 'text-blue-300' : 'text-gray-400',
          ].join(' ')}
          aria-hidden="true"
        >
          {formatNotificationDate(message.created_at)}
        </p>
      </div>
    </div>
  );
}

// ── Typing indicator ──────────────────────────────────────────────────────────

function TypingIndicator({ users }: { users: string[] }) {
  if (users.length === 0) return null;
  const label =
    users.length === 1
      ? `${users[0]} está digitando`
      : `${users.join(', ')} estão digitando`;
  return (
    <div
      className="px-4 py-2 flex items-center gap-2"
      aria-live="polite"
      aria-label={label}
    >
      {/* Bubble-style typing indicator */}
      <div className="bg-white border border-gray-100 rounded-2xl rounded-bl-md px-3.5 py-2.5 shadow-sm flex items-center gap-2">
        <span className="text-xs text-gray-500 leading-none">{label}</span>
        <span className="flex items-center gap-0.5" aria-hidden="true">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce"
              style={{ animationDelay: `${i * 160}ms`, animationDuration: '1s' }}
            />
          ))}
        </span>
      </div>
    </div>
  );
}

// ── Disconnected banner ───────────────────────────────────────────────────────

function DisconnectedBanner() {
  return (
    <div
      className="bg-amber-50 border-b border-amber-200 px-4 py-2 flex items-center justify-center gap-2"
      role="status"
      aria-live="polite"
    >
      <WifiOff size={13} className="text-amber-600 flex-shrink-0" aria-hidden="true" />
      <p className="text-xs text-amber-700 font-medium">
        Sem conexão — aguardando reconexão...
      </p>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function ConversationDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const { refreshUnread } = useChatContext();

  const {
    messages,
    connected,
    typingUsers,
    isLoadingHistory,
    hasMoreHistory,
    sendMessage,
    notifyTyping,
    loadMoreHistory,
  } = useChat(id ?? null);

  const [input, setInput] = useState('');
  const [closingConversation, setClosingConversation] = useState(false);
  const [conversationType, setConversationType] = useState<string>('');
  const [participantName, setParticipantName] = useState('');

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesAreaRef = useRef<HTMLDivElement>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const shouldAutoScrollRef = useRef(true);
  const observerRef = useRef<IntersectionObserver | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Fetch conversation metadata (type + other participant name) once.
  useEffect(() => {
    if (!id) return;
    async function fetchMeta() {
      try {
        const conversations = await chatService.listConversations();
        const conv = conversations.find((c) => c.id === id);
        if (conv) {
          setConversationType(conv.conversation_type);
          const other = conv.participants.find((p) => String(p.id) !== String(user?.id));
          setParticipantName(other?.name ?? conv.participants[0]?.name ?? 'Participante');
        }
      } catch {
        // Non-critical
      }
    }
    fetchMeta();
  }, [id, user?.id]);

  // Atualiza o badge de mensagens não lidas ao sair da conversa.
  useEffect(() => {
    return () => {
      refreshUnread();
    };
  }, [refreshUnread]);

  // Auto-scroll to bottom when new messages arrive (only if user is near bottom).
  useLayoutEffect(() => {
    if (shouldAutoScrollRef.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  // Track whether user is near the bottom for auto-scroll decisions.
  const handleScroll = useCallback(() => {
    const el = messagesAreaRef.current;
    if (!el) return;
    const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    shouldAutoScrollRef.current = distFromBottom < 80;
  }, []);

  // IntersectionObserver sentinel at the top for infinite scroll up.
  useEffect(() => {
    if (!hasMoreHistory || isLoadingHistory) return;
    const sentinel = sentinelRef.current;
    if (!sentinel) return;

    observerRef.current?.disconnect();
    observerRef.current = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) loadMoreHistory();
      },
      { root: messagesAreaRef.current, threshold: 0.1 },
    );
    observerRef.current.observe(sentinel);

    return () => observerRef.current?.disconnect();
  }, [hasMoreHistory, isLoadingHistory, loadMoreHistory]);

  // Auto-resize textarea as user types.
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = `${Math.min(ta.scrollHeight, 120)}px`;
  }, [input]);

  const debouncedNotifyTyping = useDebounce(notifyTyping, 300);

  const handleSend = useCallback(() => {
    const trimmed = input.trim();
    if (!trimmed || !connected) return;
    sendMessage(trimmed);
    setInput('');
    shouldAutoScrollRef.current = true;
    setTimeout(() => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 50);
  }, [input, connected, sendMessage]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend],
  );

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      setInput(e.target.value);
      debouncedNotifyTyping();
    },
    [debouncedNotifyTyping],
  );

  const handleCloseConversation = useCallback(async () => {
    if (!id) return;
    const result = await Swal.fire({
      title: 'Fechar conversa?',
      text: 'Esta conversa será encerrada e movida para o histórico.',
      icon: 'question',
      showCancelButton: true,
      confirmButtonText: 'Fechar conversa',
      cancelButtonText: 'Cancelar',
      confirmButtonColor: '#1e3a5f',
      cancelButtonColor: '#6b7280',
      reverseButtons: true,
    });
    if (!result.isConfirmed) return;
    setClosingConversation(true);
    try {
      await chatService.closeConversation(id);
      navigate('/conversations', { replace: true });
    } catch (err: unknown) {
      await Swal.fire({
        title: 'Erro',
        text: getErrorMessage(err),
        icon: 'error',
        confirmButtonColor: '#1e3a5f',
      });
    } finally {
      setClosingConversation(false);
    }
  }, [id, navigate]);

  const isSupport =
    conversationType === 'buyer_support' || conversationType === 'seller_support';
  const currentUserId = user?.id ?? -1;
  const canSend = connected && !!input.trim();

  return (
    <div className="flex flex-col h-full overflow-hidden bg-gray-50">
      {/* ── Header ── */}
      <header className="bg-white border-b border-gray-200 px-3 sm:px-4 py-3 flex items-center gap-2 sm:gap-3 flex-shrink-0 shadow-sm z-10">
        {/* Back button — 44x44 touch target */}
        <button
          type="button"
          onClick={() => navigate('/conversations')}
          aria-label="Voltar à lista de conversas"
          className="w-9 h-9 -ml-1 rounded-xl text-gray-500 hover:text-blue-800 hover:bg-blue-50 flex items-center justify-center transition-colors flex-shrink-0 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
        >
          <ArrowLeft size={20} aria-hidden="true" />
        </button>

        {/* Participant info */}
        <div className="flex-1 min-w-0">
          {participantName ? (
            <>
              <p className="text-sm font-bold text-gray-900 truncate leading-tight">
                {participantName}
              </p>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span
                  aria-hidden="true"
                  className={[
                    'w-2 h-2 rounded-full flex-shrink-0 transition-colors duration-500',
                    connected ? 'bg-green-500' : 'bg-amber-400',
                  ].join(' ')}
                />
                <span className={[
                  'text-xs leading-tight',
                  connected ? 'text-green-600' : 'text-amber-600',
                ].join(' ')}>
                  {connected ? 'Online' : 'Reconectando...'}
                </span>
              </div>
            </>
          ) : (
            <HeaderNameSkeleton />
          )}
        </div>

        {/* Close conversation button (support chats only) */}
        {isSupport && (
          <button
            type="button"
            onClick={handleCloseConversation}
            disabled={closingConversation}
            className="flex-shrink-0 inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-red-200 text-xs font-semibold text-red-600 hover:bg-red-50 hover:border-red-300 hover:text-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-red-400 focus-visible:ring-offset-1"
          >
            {closingConversation && (
              <Loader2 size={11} className="animate-spin" aria-hidden="true" />
            )}
            {closingConversation ? 'Encerrando...' : 'Encerrar'}
          </button>
        )}
      </header>

      {/* ── Disconnected banner (replaces inline hint) ── */}
      {!connected && <DisconnectedBanner />}

      {/* ── Messages area ── */}
      <div
        ref={messagesAreaRef}
        onScroll={handleScroll}
        role="log"
        aria-live="polite"
        aria-label="Mensagens"
        className="flex-1 overflow-y-auto py-3 no-scrollbar"
      >
        {/* Sentinel for loading older messages */}
        {hasMoreHistory && <div ref={sentinelRef} className="h-1" aria-hidden="true" />}

        {/* Loading older messages spinner */}
        {isLoadingHistory && (
          <div
            className="flex justify-center py-4"
            role="status"
            aria-label="Carregando mensagens anteriores"
          >
            <div className="flex items-center gap-2 bg-white border border-gray-100 rounded-full px-4 py-2 shadow-sm">
              <Loader2 size={14} className="animate-spin text-blue-700" aria-hidden="true" />
              <span className="text-xs text-gray-500">Carregando...</span>
            </div>
          </div>
        )}

        {/* Empty history state */}
        {!isLoadingHistory && messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full min-h-[200px] py-16 px-6 text-center gap-4">
            <div className="w-16 h-16 rounded-2xl bg-blue-50 flex items-center justify-center">
              <MessageSquare
                size={28}
                className="text-blue-300"
                strokeWidth={1.5}
                aria-hidden="true"
              />
            </div>
            <div className="space-y-1 max-w-[240px]">
              <p className="text-sm font-semibold text-gray-600">Nenhuma mensagem</p>
              <p className="text-xs text-gray-400 leading-relaxed">
                Seja o primeiro a enviar uma mensagem!
              </p>
            </div>
          </div>
        )}

        {/* Message bubbles */}
        {messages.map((msg) => (
          <MessageBubble
            key={msg.id}
            message={msg}
            isOwn={msg.sender_id === currentUserId}
          />
        ))}

        {/* Typing indicator */}
        <TypingIndicator users={typingUsers} />

        {/* Auto-scroll anchor */}
        <div ref={messagesEndRef} className="h-1" aria-hidden="true" />
      </div>

      {/* ── Input area ── */}
      <div className="bg-white border-t border-gray-200 px-3 sm:px-4 py-2 flex-shrink-0">
        <div className="flex items-end gap-2">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            disabled={!connected}
            rows={1}
            placeholder={connected ? 'Digite sua mensagem...' : 'Aguardando conexão...'}
            aria-label="Digite sua mensagem"
            className={[
              'flex-1 resize-none rounded-2xl border px-3.5 py-2 text-sm text-gray-900',
              'placeholder-gray-400 leading-relaxed overflow-hidden',
              'transition-all duration-150',
              'focus:outline-none focus:ring-2',
              connected
                ? 'bg-gray-50 border-gray-200 focus:border-blue-700 focus:bg-white focus:ring-blue-700/20'
                : 'bg-gray-100 border-gray-200 opacity-60 cursor-not-allowed',
            ].join(' ')}
            style={{ minHeight: '38px', maxHeight: '100px' }}
          />
          <button
            type="button"
            onClick={handleSend}
            disabled={!canSend}
            aria-label="Enviar mensagem"
            className={[
              'flex-shrink-0 w-9 h-9 rounded-2xl flex items-center justify-center transition-all duration-150',
              'focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2',
              canSend
                ? 'bg-blue-800 text-white hover:bg-blue-700 active:bg-blue-900 active:scale-95 shadow-sm'
                : 'bg-gray-100 text-gray-400 cursor-not-allowed',
            ].join(' ')}
          >
            <Send size={15} aria-hidden="true" className={canSend ? '' : 'opacity-60'} />
          </button>
        </div>
      </div>
    </div>
  );
}
