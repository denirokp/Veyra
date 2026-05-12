import { create } from 'zustand'
import { v4 as uuidv4 } from 'uuid'
import { sendChat, uploadDocument, reviewInitiative } from '../api/client'
import { queryClient } from '../queryClient'
import type { Message, ChatMode, ChatResponse, Document } from '../types'

interface ChatState {
  messages: Message[]
  loading: boolean
  uploading: boolean
  mode: ChatMode | null
  sessionId: string
  inputPrefill: string
  send: (text: string, file?: File) => Promise<void>
  uploadFile: (file: File) => Promise<void>
  setMode: (mode: ChatMode | null) => void
  setPrefill: (text: string) => void
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

async function readFileText(file: File): Promise<string> {
  return new Promise((resolve) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as string)
    reader.onerror = () => resolve('')
    reader.readAsText(file)
  })
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  loading: false,
  uploading: false,
  mode: null,
  sessionId: uuidv4(),
  inputPrefill: '',

  setMode: (mode) => set({ mode }),
  setPrefill: (text) => set({ inputPrefill: text }),
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

  uploadFile: async (file: File) => {
    const pendingId = uuidv4()
    const pendingMsg: Message = {
      id: pendingId,
      role: 'system',
      content: `Загружаю «${file.name}»…`,
      timestamp: new Date(),
    }
    set((s) => ({ messages: [...s.messages, pendingMsg], uploading: true }))

    try {
      // 1. Загружаем документ
      const doc: Document = await uploadDocument(file, {
        title: file.name.replace(/\.[^.]+$/, ''),
        status: 'actual',
      })

      // 2. Читаем первые 2000 символов для initiative review
      //    (бэкенд индексирует async, поэтому делаем review по сырому тексту файла)
      let fileText = ''
      if (file.type === 'text/plain' || file.name.endsWith('.md') || file.name.endsWith('.txt')) {
        fileText = (await readFileText(file)).slice(0, 2000)
      }

      // 3. Initiative Review с небольшой задержкой (даём бэкенду записать чанки)
      await new Promise((r) => setTimeout(r, 2500))

      let review = null
      try {
        review = await reviewInitiative(doc.title, fileText || `Документ: ${doc.title}`)
      } catch {
        // review необязателен — продолжаем без него
      }

      // 4. Заменяем pending сообщение на результат
      const successMsg: Message = {
        id: pendingId,
        role: 'system',
        content: '',
        uploadedDoc: doc,
        uploadReview: review ?? undefined,
        timestamp: new Date(),
      }
      set((s) => ({
        messages: s.messages.map((m) => (m.id === pendingId ? successMsg : m)),
        uploading: false,
      }))

      // 5. Инвалидируем кэш документов и статистики
      queryClient.invalidateQueries({ queryKey: ['documents'] })
      queryClient.invalidateQueries({ queryKey: ['stats'] })
    } catch (err: any) {
      const errMsg: Message = {
        id: pendingId,
        role: 'system',
        content: `Ошибка загрузки: ${err?.response?.data?.detail ?? err.message ?? 'Неизвестная ошибка'}`,
        timestamp: new Date(),
      }
      set((s) => ({
        messages: s.messages.map((m) => (m.id === pendingId ? errMsg : m)),
        uploading: false,
      }))
    }
  },
}))
