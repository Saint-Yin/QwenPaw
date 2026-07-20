import type { CreatorCommand, CreatorCommandAccepted } from '@/contracts/creator';
import { creatorRequest, jsonBody } from './client';

export function submitCreatorCommand(
  projectId: string,
  command: CreatorCommand,
): Promise<CreatorCommandAccepted> {
  return creatorRequest(`/projects/${encodeURIComponent(projectId)}/commands`, {
    method: 'POST',
    headers: { 'Idempotency-Key': command.clientCommandId },
    body: jsonBody(command),
  });
}
