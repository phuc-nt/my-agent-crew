import { failure } from "./http";

/** A file saved to an agent's inbox, and the line that tells the agent where it is. */
export interface InboxFile {
  path: string;
  line: string;
}

/**
 * Puts one file into the agent's inbox the way the Telegram channel does, so a message can
 * carry it: the server answers with the attachment line to send ahead of the words. The body
 * is the file itself, not a form, so nothing has to parse multipart on the way in.
 */
export async function uploadToInbox(agentId: string, file: File): Promise<InboxFile> {
  const name = encodeURIComponent(file.name || "file");
  const response = await fetch(`/api/agents/${encodeURIComponent(agentId)}/inbox?name=${name}`, {
    method: "POST",
    headers: { "content-type": file.type || "application/octet-stream" },
    body: file,
  });
  if (!response.ok) throw await failure(response);
  return (await response.json()) as InboxFile;
}
