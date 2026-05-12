import { create } from 'zustand'
import { v4 as uuidv4 } from 'uuid'
import { sendChat } from '../api/client'
import type { Message, ChatMode, ChatResponse } from '../types'

interface ChatState {
  messages: Message[]
  loading: boolean
  mode: ChatMode | null
  sessionId: string
  send: (text: string, file?: File) => Promise<void>
  setMode: (mode: ChatMode | null) => void
  clear: () => void
}

async function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve((reader.result as string).split(',')[1])
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  loading: false,
  mode: null,
  sessionId: uuidv4(),

  setMode: (mode) => set({ mode }),
  clear: () => set({ messages: [] }),

  send: async (text, file) => {
    const userMsg: Message = {
      id: uuidv4(),
      role: 'user',
      content: text,
      timestamp: new Date(),
    }
    set((s) => ({ messages: [...s.messages, userMsg], loading: true }))

    try {
      const fileB64 = file ? await fileToBase64(file) : undefined
      const response: ChatResponse = await sendChat({
        message: text,
        mode: get().mode,
        file: fileB64,
        session_id: get().sessionId,
      })

      const assistantMsg: Message = {
        id: uuidv4(),
        role: 'assistant',
        content: response.answer,
        response,
        timestamp: new Date(),
      }
      set((s) => ({ messages: [...s.messages, assistantMsg] }))
    } catch (err: any) {
      const errorMsg: Message = {
        id: uuidv4(),
        role: 'assistant',
        content: `Ошибка: ${err?.response?.data?.detail ?? err.message ?? 'Неизвестная ошибка'}`,
        timestamp: new Date(),
      }
      set((s) => ({ messages: [...s.messages, errorMsg] }))
    } finally {
      set({ loading: false })
    }
  },
}))
