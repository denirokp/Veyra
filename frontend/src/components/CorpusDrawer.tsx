import { Drawer } from './Drawer'
import { CorpusPage } from '../pages/CorpusPage'

interface Props {
  open: boolean
  onClose: () => void
}

export function CorpusDrawer({ open, onClose }: Props) {
  return (
    <Drawer open={open} onClose={onClose} title="📂 Корпус документов" width="w-[760px]">
      <CorpusPage />
    </Drawer>
  )
}
