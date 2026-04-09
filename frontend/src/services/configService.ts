import api from "@/api/axios";

export async function getMarketplaceFee(): Promise<number> {
  const response = await api.get<{ platform_fee_percentage: unknown }>(
    "/config/marketplace/fee/",
  );
  // Coerce to number in case the API returns a string, then validate range
  const fee = Number(response.data.platform_fee_percentage);
  if (!isFinite(fee) || fee < 0 || fee >= 100) {
    throw new Error(`Taxa inválida recebida da API: ${response.data.platform_fee_percentage}`);
  }
  return fee;
}
