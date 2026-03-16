import { useNavigate, useLocation } from 'react-router-dom';
import { MessageCircle, Loader2, AlertCircle, RefreshCw } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { useConversations } from '@/hooks/useConversations';
import { toPublicUrl } from '@/services/storageService';
import { formatNotificationDate } from '@/utils/notificationUtils';
import type { Conversation } from '@/types/chat';

// ── Helpers ───────────────────────────────────────────────────────────────────

function getOtherParticipantName(conversation: Conversation, currentUserId: number): string {
  const other = conversation.participants.find((p) => p.user.id !== currentUserId);
  return other?.user.full_name ?? conversation.participants[0]?.user.full_name ?? 'Participante';
}

function getOtherParticipantPicture(
  conversation: Conversation,
  currentUserId: number,
): string | null {
  const other = conversation.participants.find((p) => p.user.id !== currentUserId);
  return other?.user.picture ?? null;
}

function getInitial(name: string): string {
  return name.trim().charAt(0).toUpperCase();
}

// ── Skeleton for loading state ─────────────────────────────────────────────────

function ConversationSkeleton() {
  return (
    <div className="flex items-center gap-3 px-4 py-3.5 border-b border-gray-100" aria-hidden="true">
      {/* Avatar skeleton */}
      <div className="flex-shrink-0 w-11 h-11 rounded-full bg-gray-200 animate-pulse" />
      {/* Text skeletons */}
      <div className="flex-1 min-w-0 space-y-2">
        <div className="flex items-center justify-between gap-4">
          <div className="h-3.5 bg-gray-200 animate-pulse rounded-md w-2/5" />
          <div className="h-3 bg-gray-200 animate-pulse rounded-md w-10" />
        </div>
        <div className="h-3 bg-gray-200 animate-pulse rounded-md w-3/4" />
      </div>
    </div>
  );
}

// ── ConversationItem ──────────────────────────────────────────────────────────

interface ConversationItemProps {
  conversation: Conversation;
  currentUserId: number;
  isActive: boolean;
  onClick: () => void;
}

function ConversationItem({
  conversation,
  currentUserId,
  isActive,
  onClick,
}: ConversationItemProps) {
  const name = getOtherParticipantName(conversation, currentUserId);
  const picture = getOtherParticipantPicture(conversation, currentUserId);
  const hasUnread = conversation.unread_count > 0;
  const lastMsg = conversation.last_message
    ? conversation.last_message.content
    : conversation.unread_count > 0
      ? 'Nova mensagem'
      : '';
  const time = formatNotificationDate(conversation.updated_at);

  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={`Conversa com ${name}${hasUnread ? `, ${conversation.unread_count} mensagens não lidas` : ''}`}
      aria-current={isActive ? 'true' : undefined}
      className={[
        'w-full text-left flex items-center gap-3 px-4 py-4 border-b border-gray-100',
        'transition-colors duration-150',
        'focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue-600',
        isActive
          ? 'bg-blue-50 border-l-[3px] border-l-blue-800 hover:bg-blue-50/80'
          : 'hover:bg-gray-50 border-l-[3px] border-l-transparent',
      ].join(' ')}
    >
      {/* Avatar */}
      <div className="flex-shrink-0 relative">
        {picture ? (
          <img
            src={toPublicUrl(picture)}
            alt={name}
            className={[
              'w-12 h-12 rounded-full object-cover',
              isActive ? 'ring-2 ring-blue-400 ring-offset-1' : '',
            ].join(' ')}
          />
        ) : (
          <div
            className={[
              'w-12 h-12 rounded-full flex items-center justify-center font-bold text-sm select-none',
              isActive
                ? 'bg-blue-800 text-white'
                : 'bg-blue-100 text-blue-800',
            ].join(' ')}
          >
            <span aria-hidden="true">{getInitial(name)}</span>
          </div>
        )}
        {hasUnread && (
          <span
            aria-hidden="true"
            className="absolute -top-0.5 -right-0.5 h-3.5 w-3.5 rounded-full bg-red-500 border-2 border-white shadow-sm"
          />
        )}
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline justify-between gap-2 mb-1">
          <p
            className={[
              'text-sm leading-tight truncate',
              hasUnread ? 'font-bold text-gray-900' : 'font-medium text-gray-700',
            ].join(' ')}
          >
            {name}
          </p>
          <span
            className={[
              'flex-shrink-0 text-[11px] whitespace-nowrap tabular-nums',
              hasUnread ? 'text-blue-700 font-semibold' : 'text-gray-400',
            ].join(' ')}
          >
            {time}
          </span>
        </div>
        <div className="flex items-center justify-between gap-2">
          <p
            className={[
              'text-xs truncate leading-snug',
              hasUnread ? 'text-gray-700 font-medium' : 'text-gray-500',
            ].join(' ')}
          >
            {lastMsg || <span className="italic text-gray-400">Sem mensagens ainda</span>}
          </p>
          {hasUnread && (
            <span
              aria-hidden="true"
              className="flex-shrink-0 min-w-[20px] h-5 px-1.5 rounded-full bg-blue-800 text-white text-[10px] font-bold flex items-center justify-center leading-none shadow-sm"
            >
              {conversation.unread_count > 99 ? '99+' : conversation.unread_count}
            </span>
          )}
        </div>
      </div>
    </button>
  );
}

// ── ConversationsPage ─────────────────────────────────────────────────────────

export function ConversationsPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useAuth();
  const { conversations, isLoading, error, refresh } = useConversations('active');

  const currentUserId = user?.id ?? -1;

  // Determine the active conversation from the URL, if any.
  const activeMatch = location.pathname.match(/^\/conversations\/([^/]+)/);
  const activeId = activeMatch?.[1] ?? null;

  return (
    <div className="h-full overflow-y-auto bg-gray-50">
      <div className="max-w-2xl mx-auto">

        {/* Header */}
        <div className="bg-white border-b border-gray-200 px-4 py-3.5 flex items-center justify-between sticky top-0 z-10 shadow-sm">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-blue-800 flex items-center justify-center flex-shrink-0">
              <MessageCircle size={16} className="text-white" aria-hidden="true" />
            </div>
            <div>
              <h1 className="text-sm font-bold text-gray-900 leading-tight">Mensagens</h1>
              {!isLoading && !error && (
                <p className="text-[11px] text-gray-400 leading-tight">
                  {conversations.length === 0
                    ? 'Nenhuma conversa'
                    : `${conversations.length} conversa${conversations.length > 1 ? 's' : ''}`}
                </p>
              )}
            </div>
          </div>
          <button
            type="button"
            onClick={refresh}
            aria-label="Atualizar conversas"
            disabled={isLoading}
            className="w-9 h-9 rounded-xl text-gray-400 hover:text-blue-800 hover:bg-blue-50 transition-colors flex items-center justify-center focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <RefreshCw
              size={15}
              aria-hidden="true"
              className={isLoading ? 'animate-spin' : ''}
            />
          </button>
        </div>

        {/* Loading skeletons */}
        {isLoading && (
          <div
            className="bg-white shadow-sm md:rounded-xl md:mt-4 md:mx-4 md:mb-4 overflow-hidden border border-gray-100"
            role="status"
            aria-label="Carregando conversas"
          >
            {[...Array(5)].map((_, i) => (
              <ConversationSkeleton key={i} />
            ))}
          </div>
        )}

        {/* Error state */}
        {error && !isLoading && (
          <div className="m-4 bg-white rounded-xl border border-gray-100 shadow-md p-8 flex flex-col items-center gap-4 text-center">
            <div className="w-14 h-14 rounded-full bg-red-50 flex items-center justify-center">
              <AlertCircle size={26} className="text-red-500" aria-hidden="true" />
            </div>
            <div className="space-y-1">
              <p className="text-sm font-semibold text-gray-800">Não foi possível carregar</p>
              <p className="text-xs text-gray-500 leading-relaxed">{error}</p>
            </div>
            <button
              type="button"
              onClick={refresh}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-blue-800 text-white text-sm font-medium hover:bg-blue-700 active:bg-blue-900 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2"
            >
              <RefreshCw size={13} aria-hidden="true" />
              Tentar novamente
            </button>
          </div>
        )}

        {/* Empty state */}
        {!isLoading && !error && conversations.length === 0 && (
          <div className="flex flex-col items-center justify-center py-20 px-6 text-center gap-5">
            <div className="w-20 h-20 rounded-2xl bg-blue-50 flex items-center justify-center">
              <MessageCircle size={36} className="text-blue-300" strokeWidth={1.5} aria-hidden="true" />
            </div>
            <div className="space-y-1.5 max-w-xs">
              <p className="text-sm font-semibold text-gray-700">Nenhuma conversa ainda</p>
              <p className="text-xs text-gray-400 leading-relaxed">
                Acesse um produto e clique em &ldquo;Chat com vendedor&rdquo; para iniciar uma conversa.
              </p>
            </div>
          </div>
        )}

        {/* Conversation list */}
        {!isLoading && !error && conversations.length > 0 && (
          <div
            className="bg-white shadow-md rounded-none md:rounded-xl md:mt-4 md:mx-4 md:mb-4 overflow-hidden border border-gray-100"
            role="list"
            aria-label="Lista de conversas"
          >
            {conversations.map((conv) => (
              <div key={conv.id} role="listitem">
                <ConversationItem
                  conversation={conv}
                  currentUserId={currentUserId}
                  isActive={conv.id === activeId}
                  onClick={() => navigate(`/conversations/${conv.id}`)}
                />
              </div>
            ))}
          </div>
        )}

      </div>
    </div>
  );
}
