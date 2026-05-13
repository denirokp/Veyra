import { Drawer } from './Drawer'
import { DocumentsPage } from '../pages/DocumentsPage'

interface Props {
  open: boolean
  onClose: () => void
}

export function DocumentsDrawer({ open, onClose }: Props) {
  return (
    <Drawer open={open} onClose={onClose} title="📂 Документы" width="w-[760px]">
      <DocumentsPage />
    </Drawer>
  )
}
