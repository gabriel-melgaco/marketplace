const output = document.getElementById("output");

// Base URL configuravel - altere para testar local ou producao
const API_BASE = window.location.hostname === "localhost"
  ? "http://localhost:8001"
  : "https://api.megdev.com.br";

function log(message) {
  output.textContent += message + "\n";
}

// 1 - Gerar presigned URL
async function getPresignedUrl(token, file) {
  const contentType =
    file.type && file.type !== "" ? file.type : "image/jpeg";

  log("Endpoint: " + API_BASE + "/api/storage/upload/presigned-url/");

  const res = await fetch(
    `${API_BASE}/api/storage/upload/presigned-url/`,
    {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        file_name: file.name,
        content_type: contentType,
      }),
    }
  );

  if (!res.ok) {
    const errorText = await res.text();
    console.error("Erro backend:", errorText);
    throw new Error(`Erro ao gerar presigned URL (HTTP ${res.status}): ${errorText}`);
  }

  return res.json();
}

// 2 - Upload direto para o MinIO
async function uploadToStorage(uploadUrl, file) {
  const contentType =
    file.type && file.type !== "" ? file.type : "image/jpeg";

  const res = await fetch(uploadUrl, {
    method: "PUT",
    headers: {
      "Content-Type": contentType,
    },
    body: file,
  });

  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`Erro no upload para o storage (HTTP ${res.status}): ${errorText}`);
  }
}

// 3 - Associar imagem ao listing
async function attachImage(token, listingId, fileUrl, objectName) {
  const res = await fetch(
    `${API_BASE}/api/products/listings/${listingId}/images/`,
    {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        image_url: fileUrl,
        object_name: objectName,
        is_primary: false,
        order: 0,
      }),
    }
  );

  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`Erro ao salvar imagem no listing (HTTP ${res.status}): ${errorText}`);
  }
  return res.json();
}

// Fluxo completo
document.getElementById("uploadBtn").addEventListener("click", async () => {
  output.textContent = "";

  try {
    const token = document.getElementById("token").value.trim();
    const listingId = document.getElementById("listingId").value;
    const file = document.getElementById("fileInput").files[0];

    if (!token || !listingId || !file) {
      log("Preencha todos os campos (token, listing ID e arquivo).");
      return;
    }

    log(`API Base: ${API_BASE}`);
    log(`Arquivo: ${file.name} (${file.type}, ${(file.size / 1024).toFixed(1)} KB)`);
    log("");

    log("[1/3] Gerando presigned URL...");
    const presigned = await getPresignedUrl(token, file);
    log("OK - object_name: " + presigned.object_name);
    log("OK - file_url: " + presigned.file_url);
    log("");

    log("[2/3] Enviando imagem para storage...");
    await uploadToStorage(presigned.upload_url, file);
    log("OK - Upload concluido");
    log("");

    log("[3/3] Associando imagem ao listing " + listingId + "...");
    const result = await attachImage(
      token,
      listingId,
      presigned.file_url,
      presigned.object_name
    );
    log("OK - Imagem associada!");
    log("");

    log("=== Upload concluido com sucesso! ===");
    log(JSON.stringify(result, null, 2));
  } catch (err) {
    log("ERRO: " + err.message);
    console.error(err);
  }
});
