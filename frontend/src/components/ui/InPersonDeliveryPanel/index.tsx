import { useState, useEffect, useCallback } from "react";
import {
  CalendarDays,
  Clock,
  MapPin,
  CheckCircle2,
  Circle,
  Loader2,
  AlertCircle,
  Phone,
  FileText,
  RefreshCw,
} from "lucide-react";
import Swal from "sweetalert2";
import { inPersonService } from "@/services/inPersonService";
import type { InPersonDelivery, InPersonDeliveryUpdateRequest } from "@/services/inPersonService";

// ─── Constants ────────────────────────────────────────────────────────────────

export const MEETING_STATUS_LABELS: Record<string, string> = {
  pending_schedule: "Aguardando Agendamento",
  scheduled: "Agendado",
  confirmed: "Confirmado por Ambas as Partes",
  in_progress: "Em Andamento",
  completed: "Concluído",
  cancelled: "Cancelado",
  no_show: "Não Compareceu",
};

const MEETING_STATUS_COLORS: Record<string, string> = {
  pending_schedule: "bg-gray-100 text-gray-700",
  scheduled: "bg-yellow-100 text-yellow-800",
  confirmed: "bg-blue-100 text-blue-800",
  in_progress: "bg-purple-100 text-purple-800",
  completed: "bg-green-100 text-green-800",
  cancelled: "bg-red-100 text-red-800",
  no_show: "bg-red-100 text-red-800",
};

const SWAL_TOAST = {
  toast: true as const,
  position: "top-end" as const,
  showConfirmButton: false,
  timer: 3500,
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

function getAxiosErrorMessage(err: unknown, fallback: string): string {
  const data = (err as { response?: { data?: unknown } })?.response?.data;
  if (data && typeof data === "object") {
    const errField = (data as Record<string, unknown>).error;
    if (typeof errField === "string") return errField;
    const msgs = (Object.values(data as Record<string, unknown>).flat() as unknown[])
      .filter((v): v is string => typeof v === "string");
    if (msgs.length) return msgs.join(" ");
  }
  if (err instanceof Error) return err.message;
  return fallback;
}

function formatDate(d?: string | null) {
  if (!d) return "—";
  const [y, m, day] = d.split("-");
  return `${day}/${m}/${y}`;
}

function formatTime(t?: string | null) {
  if (!t) return "—";
  return t.slice(0, 5); // HH:MM
}

// ─── Confirmation status row ──────────────────────────────────────────────────

function ConfirmRow({
  label,
  confirmed,
  confirmedAt,
}: {
  label: string;
  confirmed: boolean;
  confirmedAt?: string | null;
}) {
  return (
    <div className="flex items-center justify-between text-sm">
      <div className="flex items-center gap-2">
        {confirmed ? (
          <CheckCircle2 size={15} className="text-green-500 shrink-0" />
        ) : (
          <Circle size={15} className="text-gray-300 shrink-0" />
        )}
        <span className={confirmed ? "text-gray-700 font-medium" : "text-gray-400"}>
          {label}
        </span>
      </div>
      {confirmed && confirmedAt && (
        <span className="text-xs text-gray-400">
          {new Date(confirmedAt).toLocaleDateString("pt-BR")}
        </span>
      )}
    </div>
  );
}

// ─── Props ────────────────────────────────────────────────────────────────────

interface InPersonDeliveryPanelProps {
  deliveryId: number;
  role: "seller" | "buyer";
  onUpdated?: () => void;
}

// ─── Main component ───────────────────────────────────────────────────────────

export function InPersonDeliveryPanel({
  deliveryId,
  role,
  onUpdated,
}: InPersonDeliveryPanelProps) {
  const [delivery, setDelivery] = useState<InPersonDelivery | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Edit form (seller only)
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<InPersonDeliveryUpdateRequest>({});
  const [saving, setSaving] = useState(false);

  // Actions
  const [confirming, setConfirming] = useState(false);
  const [completing, setCompleting] = useState(false);
  const [cancelling, setCancelling] = useState(false);

  const fetchDelivery = useCallback(async () => {
    try {
      const data = await inPersonService.get(deliveryId);
      setDelivery(data);
      setError("");
    } catch (err) {
      setError(getAxiosErrorMessage(err, "Erro ao carregar entrega presencial."));
    } finally {
      setLoading(false);
    }
  }, [deliveryId]);

  useEffect(() => {
    fetchDelivery();
  }, [fetchDelivery]);

  // Initialise edit form from delivery
  useEffect(() => {
    if (!delivery) return;
    setForm({
      meeting_location_name: delivery.meeting_location_name ?? "",
      meeting_address: delivery.meeting_address ?? "",
      meeting_notes: delivery.meeting_notes ?? "",
      scheduled_date: delivery.scheduled_date ?? "",
      scheduled_time: delivery.scheduled_time ?? "",
    });
  }, [delivery]);

  // ── Actions ────────────────────────────────────────────────────────────────

  async function handleSaveUpdate() {
    if (saving) return;
    setSaving(true);
    try {
      const res = await inPersonService.update(deliveryId, form);
      setDelivery(res.delivery);
      setEditing(false);
      Swal.fire({
        ...SWAL_TOAST,
        icon: "success",
        title: "Dados atualizados. O ciclo de confirmações foi reiniciado.",
      });
      onUpdated?.();
    } catch (err) {
      Swal.fire({
        ...SWAL_TOAST,
        icon: "error",
        title: getAxiosErrorMessage(err, "Erro ao atualizar dados."),
      });
    } finally {
      setSaving(false);
    }
  }

  async function handleConfirm() {
    if (confirming) return;
    setConfirming(true);
    try {
      const res = await inPersonService.confirm(deliveryId);
      setDelivery(res.delivery);
      Swal.fire({
        ...SWAL_TOAST,
        icon: "success",
        title: res.message || "Confirmado com sucesso!",
      });
      onUpdated?.();
    } catch (err) {
      Swal.fire({
        ...SWAL_TOAST,
        icon: "error",
        title: getAxiosErrorMessage(err, "Erro ao confirmar."),
      });
    } finally {
      setConfirming(false);
    }
  }

  async function handleComplete() {
    const { value: notes, isConfirmed } = await Swal.fire({
      title: "Confirmar conclusão",
      input: "textarea",
      inputLabel: "Observações (opcional)",
      inputPlaceholder: "Ex: Produto entregue em perfeito estado.",
      showCancelButton: true,
      confirmButtonText: "Confirmar conclusão",
      cancelButtonText: "Cancelar",
    });
    if (!isConfirmed) return;

    setCompleting(true);
    try {
      const res = await inPersonService.complete(deliveryId, notes || undefined);
      setDelivery(res.delivery);
      Swal.fire({
        ...SWAL_TOAST,
        icon: "success",
        title: res.message || "Conclusão registrada!",
      });
      onUpdated?.();
    } catch (err) {
      Swal.fire({
        ...SWAL_TOAST,
        icon: "error",
        title: getAxiosErrorMessage(err, "Erro ao registrar conclusão."),
      });
    } finally {
      setCompleting(false);
    }
  }

  async function handleCancel() {
    const { value: reason, isConfirmed } = await Swal.fire({
      title: "Cancelar entrega presencial?",
      input: "textarea",
      inputLabel: "Motivo do cancelamento (opcional)",
      showCancelButton: true,
      confirmButtonText: "Sim, cancelar",
      cancelButtonText: "Voltar",
      confirmButtonColor: "#dc2626",
    });
    if (!isConfirmed) return;

    setCancelling(true);
    try {
      const res = await inPersonService.cancel(deliveryId, reason || undefined);
      setDelivery(res.delivery);
      Swal.fire({ ...SWAL_TOAST, icon: "success", title: "Entrega cancelada." });
      onUpdated?.();
    } catch (err) {
      Swal.fire({
        ...SWAL_TOAST,
        icon: "error",
        title: getAxiosErrorMessage(err, "Erro ao cancelar."),
      });
    } finally {
      setCancelling(false);
    }
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-4 text-sm text-gray-400">
        <Loader2 size={15} className="animate-spin" />
        Carregando entrega presencial…
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-100 rounded-xl text-sm text-red-700">
        <AlertCircle size={15} className="shrink-0 mt-0.5" />
        {error}
      </div>
    );
  }

  if (!delivery) return null;

  const { meeting_status } = delivery;
  const isTerminal = ["completed", "cancelled", "no_show"].includes(meeting_status);

  // Determine which confirmation the current user has made
  const iConfirmed = role === "seller" ? delivery.seller_confirmed : delivery.buyer_confirmed;
  const iCompleted = role === "seller" ? delivery.seller_completed : delivery.buyer_completed;

  const canConfirm =
    !isTerminal &&
    !iConfirmed &&
    (meeting_status === "scheduled" || meeting_status === "confirmed");

  const canComplete =
    !isTerminal &&
    !iCompleted &&
    (meeting_status === "confirmed" || meeting_status === "in_progress");

  const canCancel = !isTerminal;

  return (
    <div className="border border-indigo-100 rounded-xl overflow-hidden border-l-4 border-l-indigo-400">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 bg-indigo-50 border-b border-indigo-100">
        <div className="flex items-center gap-2">
          <MapPin size={14} className="text-indigo-500 shrink-0" />
          <span className="text-sm font-semibold text-indigo-900">
            Entrega Presencial
          </span>
        </div>
        <span
          className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${
            MEETING_STATUS_COLORS[meeting_status] ?? "bg-gray-100 text-gray-700"
          }`}
        >
          {MEETING_STATUS_LABELS[meeting_status] ?? meeting_status}
        </span>
      </div>

      <div className="p-4 space-y-4">

        {/* ── Cycle reset warning ── */}
        {(meeting_status === "scheduled") && (
          <div className="flex items-start gap-2 p-3 bg-yellow-50 border border-yellow-200 rounded-lg text-xs text-yellow-800">
            <RefreshCw size={13} className="shrink-0 mt-0.5" />
            Qualquer alteração nos dados reinicia o ciclo de confirmações — ambas as partes precisarão confirmar novamente.
          </div>
        )}

        {/* ── Meeting details ── */}
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-sm">
            <CalendarDays size={14} className="text-gray-400 shrink-0" />
            <span className="text-gray-500">Data:</span>
            <span className="font-medium text-gray-800">
              {formatDate(delivery.scheduled_date)}
            </span>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <Clock size={14} className="text-gray-400 shrink-0" />
            <span className="text-gray-500">Horário:</span>
            <span className="font-medium text-gray-800">
              {formatTime(delivery.scheduled_time)}
            </span>
          </div>
          {delivery.meeting_location_name && (
            <div className="flex items-start gap-2 text-sm">
              <MapPin size={14} className="text-gray-400 shrink-0 mt-0.5" />
              <div>
                <span className="font-medium text-gray-800">
                  {delivery.meeting_location_name}
                </span>
                {delivery.meeting_address && (
                  <p className="text-xs text-gray-500 mt-0.5">
                    {delivery.meeting_address}
                  </p>
                )}
              </div>
            </div>
          )}
          {delivery.meeting_notes && (
            <div className="flex items-start gap-2 text-sm">
              <FileText size={14} className="text-gray-400 shrink-0 mt-0.5" />
              <span className="text-gray-600 italic">{delivery.meeting_notes}</span>
            </div>
          )}
          {(delivery.seller_contact_phone || delivery.buyer_contact_phone) && (
            <div className="flex items-center gap-2 text-sm">
              <Phone size={14} className="text-gray-400 shrink-0" />
              <span className="text-gray-500">Contato:</span>
              <span className="font-medium text-gray-800">
                {role === "buyer"
                  ? delivery.seller_contact_phone || "—"
                  : delivery.buyer_contact_phone || "—"}
              </span>
            </div>
          )}
        </div>

        {/* ── Confirmation status ── */}
        <div className="border border-gray-100 rounded-lg p-3 space-y-2 bg-gray-50">
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">
            Confirmações
          </p>
          <ConfirmRow
            label="Vendedor confirmou"
            confirmed={delivery.seller_confirmed}
            confirmedAt={delivery.seller_confirmed_at}
          />
          <ConfirmRow
            label="Comprador confirmou"
            confirmed={delivery.buyer_confirmed}
            confirmedAt={delivery.buyer_confirmed_at}
          />
          {(delivery.seller_completed || delivery.buyer_completed) && (
            <>
              <div className="border-t border-gray-200 pt-2 mt-1" />
              <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">
                Conclusão
              </p>
              <ConfirmRow
                label="Vendedor concluiu"
                confirmed={delivery.seller_completed}
                confirmedAt={delivery.seller_completed_at}
              />
              <ConfirmRow
                label="Comprador concluiu"
                confirmed={delivery.buyer_completed}
                confirmedAt={delivery.buyer_completed_at}
              />
            </>
          )}
        </div>

        {/* ── Seller edit form ── */}
        {role === "seller" && !isTerminal && (
          <>
            {editing ? (
              <div className="space-y-3 border border-gray-200 rounded-xl p-4 bg-gray-50">
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
                  Editar dados do encontro
                </p>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">Data</label>
                    <input
                      type="date"
                      value={form.scheduled_date ?? ""}
                      onChange={(e) =>
                        setForm((f) => ({ ...f, scheduled_date: e.target.value || null }))
                      }
                      className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400/30 focus:border-indigo-400"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">Horário</label>
                    <input
                      type="time"
                      value={form.scheduled_time ?? ""}
                      onChange={(e) =>
                        setForm((f) => ({ ...f, scheduled_time: e.target.value || null }))
                      }
                      className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400/30 focus:border-indigo-400"
                    />
                  </div>
                </div>
                <div>
                  <label className="block text-xs text-gray-500 mb-1">
                    Nome do local
                  </label>
                  <input
                    type="text"
                    placeholder="Ex: Shopping Ibirapuera, Portaria A"
                    value={form.meeting_location_name ?? ""}
                    onChange={(e) =>
                      setForm((f) => ({ ...f, meeting_location_name: e.target.value }))
                    }
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400/30 focus:border-indigo-400"
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-500 mb-1">
                    Endereço completo
                  </label>
                  <input
                    type="text"
                    placeholder="Rua, número, bairro, cidade"
                    value={form.meeting_address ?? ""}
                    onChange={(e) =>
                      setForm((f) => ({ ...f, meeting_address: e.target.value }))
                    }
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400/30 focus:border-indigo-400"
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-500 mb-1">
                    Observações
                  </label>
                  <textarea
                    rows={2}
                    placeholder="Ex: próximo à entrada principal, venha de carro"
                    value={form.meeting_notes ?? ""}
                    onChange={(e) =>
                      setForm((f) => ({ ...f, meeting_notes: e.target.value }))
                    }
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400/30 focus:border-indigo-400 resize-none"
                  />
                </div>

                <div className="flex gap-2 pt-1">
                  <button
                    onClick={handleSaveUpdate}
                    disabled={saving}
                    className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-indigo-700 text-white rounded-lg text-sm font-semibold hover:bg-indigo-800 transition-colors disabled:opacity-60"
                  >
                    {saving ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : null}
                    {saving ? "Salvando…" : "Salvar alterações"}
                  </button>
                  <button
                    onClick={() => setEditing(false)}
                    className="px-4 py-2.5 border border-gray-200 text-gray-600 rounded-lg text-sm font-semibold hover:bg-gray-50 transition-colors"
                  >
                    Cancelar
                  </button>
                </div>
              </div>
            ) : (
              <button
                onClick={() => setEditing(true)}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 border border-indigo-200 text-indigo-700 rounded-lg text-sm font-semibold hover:bg-indigo-50 transition-colors"
              >
                <CalendarDays size={14} />
                {meeting_status === "pending_schedule"
                  ? "Propor data e local"
                  : "Alterar data ou local"}
              </button>
            )}
          </>
        )}

        {/* ── Confirm button ── */}
        {canConfirm && (
          <button
            onClick={handleConfirm}
            disabled={confirming}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-blue-700 text-white rounded-lg text-sm font-semibold hover:bg-blue-800 transition-colors disabled:opacity-60"
          >
            {confirming ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <CheckCircle2 size={14} />
            )}
            {confirming ? "Confirmando…" : "Confirmar encontro"}
          </button>
        )}

        {/* ── Already confirmed ── */}
        {iConfirmed && !delivery.is_fully_confirmed && !isTerminal && (
          <div className="flex items-center gap-2 p-3 bg-green-50 border border-green-200 rounded-lg text-sm text-green-700">
            <CheckCircle2 size={14} className="shrink-0" />
            Você confirmou. Aguardando confirmação da outra parte.
          </div>
        )}

        {/* ── Complete button ── */}
        {canComplete && (
          <button
            onClick={handleComplete}
            disabled={completing}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-emerald-600 text-white rounded-lg text-sm font-semibold hover:bg-emerald-700 transition-colors disabled:opacity-60"
          >
            {completing ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <CheckCircle2 size={14} />
            )}
            {completing ? "Registrando…" : "Marcar como concluído"}
          </button>
        )}

        {/* ── Already completed by me ── */}
        {iCompleted && !delivery.is_fully_completed && !isTerminal && (
          <div className="flex items-center gap-2 p-3 bg-green-50 border border-green-200 rounded-lg text-sm text-green-700">
            <CheckCircle2 size={14} className="shrink-0" />
            Você registrou a conclusão. Aguardando confirmação da outra parte.
          </div>
        )}

        {/* ── Cancel ── */}
        {canCancel && (
          <button
            onClick={handleCancel}
            disabled={cancelling}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 border border-red-200 text-red-600 rounded-lg text-sm font-semibold hover:bg-red-50 transition-colors disabled:opacity-60"
          >
            {cancelling ? <Loader2 size={14} className="animate-spin" /> : null}
            {cancelling ? "Cancelando…" : "Cancelar entrega"}
          </button>
        )}

        {/* ── Terminal states ── */}
        {meeting_status === "completed" && (
          <div className="flex items-center gap-2 p-3 bg-green-50 border border-green-200 rounded-lg text-sm text-green-700 font-medium">
            <CheckCircle2 size={14} className="shrink-0" />
            Entrega concluída com sucesso.
            {delivery.completed_at && (
              <span className="text-xs font-normal text-green-600 ml-1">
                ({new Date(delivery.completed_at).toLocaleDateString("pt-BR")})
              </span>
            )}
          </div>
        )}
        {meeting_status === "cancelled" && (
          <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
            <AlertCircle size={14} className="shrink-0" />
            Esta entrega foi cancelada.
          </div>
        )}
        {meeting_status === "no_show" && (
          <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
            <AlertCircle size={14} className="shrink-0" />
            Uma das partes não compareceu ao encontro.
          </div>
        )}
      </div>
    </div>
  );
}
