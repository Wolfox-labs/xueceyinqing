import { request } from './client'

export interface FileTicketResponse {
  ticket: string
  url: string
  filename: string
  expires_at: string
}

export function createFileTicket(filename: string) {
  return request<FileTicketResponse>('/files/ticket', {
    method: 'POST',
    body: { filename },
  })
}