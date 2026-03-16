import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Loader2, AlertCircle } from 'lucide-react';
import { productService } from '@/services/productService';
import { chatService } from '@/services/chatService';

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

export function Chat() {
  const { listingId } = useParams<{ listingId?: string }>();
  const navigate = useNavigate();
  const [error, setError] = useState('');
  const ranRef = useRef(false);

  useEffect(() => {
    // StrictMode fires effects twice in dev — guard with a ref.
    if (ranRef.current) return;
    ranRef.current = true;

    if (!listingId) {
      navigate('/conversations', { replace: true });
      return;
    }

    const id = Number(listingId);
    if (Number.isNaN(id)) {
      navigate('/conversations', { replace: true });
      return;
    }

    async function openChat() {
      try {
        const listing = await productService.getListingById(id);
        const conversation = await chatService.createConversation(
          listing.seller,
          'buyer_seller',
          { listingId: id },
        );
        navigate(`/conversations/${conversation.id}`, { replace: true });
      } catch (err: unknown) {
        setError(getErrorMessage(err));
      }
    }

    openChat();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
        <div className="bg-white rounded-xl shadow-md border border-gray-100 p-8 max-w-sm w-full text-center space-y-4">
          <div className="flex justify-center">
            <AlertCircle size={40} className="text-red-500" aria-hidden="true" />
          </div>
          <p className="text-sm text-gray-700">{error}</p>
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="inline-flex items-center gap-1.5 text-sm font-medium text-blue-800 hover:underline"
          >
            <ArrowLeft size={15} aria-hidden="true" />
            Voltar
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <div className="flex flex-col items-center gap-3 text-gray-500">
        <Loader2 size={32} className="animate-spin text-blue-800" aria-hidden="true" />
        <p className="text-sm">Abrindo conversa...</p>
      </div>
    </div>
  );
}
