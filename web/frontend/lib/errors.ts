/**
 * Mapa de error codes da API → mensagens amigáveis em pt-BR.
 * Usado em todos os fetch calls para exibir feedback claro ao usuário.
 */
export const API_ERRORS: Record<string, string> = {
  CREDENTIALS_MISSING:   "Configure suas credenciais AVA antes de continuar.",
  JOB_ALREADY_RUNNING:   "Já há uma execução em andamento para este quiz.",
  TOKEN_REVOKED:         "Seu token foi revogado. Gere um novo na aba Token.",
  TOKEN_NOT_FOUND:       "Nenhum token configurado. Gere um primeiro.",
  INVALID_CRON:          "Expressão de agendamento inválida.",
  UNAUTHORIZED:          "Sessão expirada. Faça login novamente.",
  RATE_LIMITED:          "Muitas tentativas. Aguarde 1 minuto.",
  VALIDATION_ERROR:      "Dados inválidos. Verifique os campos.",
  NOT_FOUND:             "Recurso não encontrado.",
  SERVER_ERROR:          "Erro interno do servidor. Tente novamente.",
};

/** Returns a human-readable message from an API error response. */
export async function parseApiError(res: Response): Promise<string> {
  try {
    const data = await res.json();
    if (data?.detail?.error && API_ERRORS[data.detail.error]) {
      return API_ERRORS[data.detail.error];
    }
    if (typeof data?.detail === "string") return data.detail;
    if (data?.message) return data.message;
  } catch {
    // not JSON
  }
  if (res.status === 401) return API_ERRORS.UNAUTHORIZED;
  if (res.status === 429) return API_ERRORS.RATE_LIMITED;
  if (res.status === 422) return API_ERRORS.VALIDATION_ERROR;
  if (res.status === 404) return API_ERRORS.NOT_FOUND;
  if (res.status >= 500)  return API_ERRORS.SERVER_ERROR;
  return "Erro inesperado. Tente novamente.";
}

/** Fetch wrapper that rejects with a friendly string on API errors. */
export async function apiFetch(
  input: RequestInfo,
  init?: RequestInit,
): Promise<Response> {
  const res = await fetch(input, { credentials: "include", ...init });
  if (!res.ok) {
    const msg = await parseApiError(res.clone());
    throw new ApiError(msg, res.status);
  }
  return res;
}

export class ApiError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}
