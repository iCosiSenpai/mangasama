import { nextTick, onBeforeUnmount, watch, type Ref } from 'vue'

const FOCUSABLE =
  'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])'

/**
 * Accessibility helpers for an open/close modal: Escape-to-close, a focus
 * trap that keeps Tab/Shift+Tab inside the dialog, and initial focus on the
 * first focusable element when it opens.
 *
 * @param isOpen   reactive open flag
 * @param container ref to the dialog root element
 * @param onClose  called when Escape is pressed
 */
export function useModalA11y(
  isOpen: Ref<boolean>,
  container: Ref<HTMLElement | null>,
  onClose: () => void,
): void {
  function focusable(): HTMLElement[] {
    if (!container.value) return []
    return Array.from(container.value.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
      (el) => el.offsetParent !== null || el === document.activeElement,
    )
  }

  function onKeydown(e: KeyboardEvent): void {
    if (e.key === 'Escape') {
      e.preventDefault()
      onClose()
      return
    }
    if (e.key !== 'Tab') return
    const items = focusable()
    if (items.length === 0) return
    const first = items[0]
    const last = items[items.length - 1]
    const active = document.activeElement as HTMLElement | null
    if (e.shiftKey && active === first) {
      e.preventDefault()
      last.focus()
    } else if (!e.shiftKey && active === last) {
      e.preventDefault()
      first.focus()
    }
  }

  watch(
    isOpen,
    (open) => {
      if (open) {
        document.addEventListener('keydown', onKeydown)
        void nextTick(() => focusable()[0]?.focus())
      } else {
        document.removeEventListener('keydown', onKeydown)
      }
    },
    { immediate: true },
  )

  onBeforeUnmount(() => document.removeEventListener('keydown', onKeydown))
}
