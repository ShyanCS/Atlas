import { useEffect, useRef, type ReactNode, type KeyboardEvent } from 'react'
import { Icon } from './Icon'

export function Dialog({
  open,
  title,
  onClose,
  children,
}: {
  open: boolean
  title: string
  onClose: () => void
  children: ReactNode
}) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])
  const containFocus = (event: KeyboardEvent<HTMLDialogElement>) => {
    if (event.key !== 'Tab') return
    const focusable = Array.from(
      event.currentTarget.querySelectorAll<HTMLElement>(
        'a[href], button, input, select, textarea, summary, [tabindex]',
      ),
    ).filter(
      (element) =>
        !element.matches(':disabled') &&
        element.tabIndex >= 0 &&
        element.getClientRects().length > 0,
    )
    const first = focusable[0],
      last = focusable[focusable.length - 1]
    if (!first || !last) {
      event.preventDefault()
      return
    }
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }
  return (
    <dialog
      ref={ref}
      className="atlas-dialog"
      aria-labelledby="dialog-title"
      onCancel={onClose}
      onClose={onClose}
      onKeyDown={containFocus}
    >
      <header>
        <h2 id="dialog-title">{title}</h2>
        <button className="btn icon-only" onClick={onClose} aria-label="Close dialog">
          <Icon name="close" />
        </button>
      </header>
      {children}
    </dialog>
  )
}
