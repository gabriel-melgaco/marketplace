import Swal from "sweetalert2";

export async function confirmDelete(options?: {
  title?: string;
  text?: string;
  confirmButtonText?: string;
}): Promise<boolean> {
  const result = await Swal.fire({
    title: options?.title ?? "Excluir anúncio?",
    text: options?.text ?? "Esta ação não pode ser desfeita.",
    icon: "warning",
    showCancelButton: true,
    confirmButtonColor: "#ef4444",
    cancelButtonColor: "#6b7280",
    confirmButtonText: options?.confirmButtonText ?? "Sim, excluir",
    cancelButtonText: "Cancelar",
    reverseButtons: true,
    focusCancel: true,
    customClass: {
      popup: "!rounded-2xl !shadow-2xl",
      title: "!text-lg !font-bold !text-gray-900",
      htmlContainer: "!text-sm !text-gray-500",
      confirmButton: "!rounded-xl !font-semibold !px-6 !py-2.5 !text-sm",
      cancelButton: "!rounded-xl !font-semibold !px-6 !py-2.5 !text-sm",
      actions: "!gap-3",
    },
    buttonsStyling: true,
  });
  return result.isConfirmed;
}

export async function confirmAction(options: {
  title: string;
  text?: string;
  confirmButtonText?: string;
  confirmButtonColor?: string;
}): Promise<boolean> {
  const result = await Swal.fire({
    title: options.title,
    text: options.text,
    icon: "question",
    showCancelButton: true,
    confirmButtonColor: options.confirmButtonColor ?? "#1e3a8a",
    cancelButtonColor: "#6b7280",
    confirmButtonText: options.confirmButtonText ?? "Confirmar",
    cancelButtonText: "Cancelar",
    reverseButtons: true,
    focusCancel: true,
    customClass: {
      popup: "!rounded-2xl !shadow-2xl",
      title: "!text-lg !font-bold !text-gray-900",
      htmlContainer: "!text-sm !text-gray-500",
      confirmButton: "!rounded-xl !font-semibold !px-6 !py-2.5 !text-sm",
      cancelButton: "!rounded-xl !font-semibold !px-6 !py-2.5 !text-sm",
      actions: "!gap-3",
    },
    buttonsStyling: true,
  });
  return result.isConfirmed;
}
