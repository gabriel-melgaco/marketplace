import api from "@/api/axios";
import type { PresignedUrlRequest, PresignedUrlResponse } from "@/types/product";

export const storageService = {
  async getPresignedUrl(fileName: string, contentType: string) {
    const response = await api.post<PresignedUrlResponse>(
      "/storage/upload/presigned-url/",
      { file_name: fileName, content_type: contentType } as PresignedUrlRequest,
    );
    return response.data;
  },

  async uploadToS3(uploadUrl: string, file: File) {
    await fetch(uploadUrl, {
      method: "PUT",
      body: file,
      headers: {
        "Content-Type": file.type,
      },
    });
  },
};
